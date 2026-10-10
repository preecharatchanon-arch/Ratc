from __future__ import annotations

import hashlib
import fcntl
import json
import math
import os
import pickle
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx
import networkx as nx
from shapely.geometry import Point, shape
try:
    from shapely import covers as shapely_covers, points as shapely_points
except ImportError:  # pragma: no cover - OSMnx 2.x installs Shapely 2.x
    shapely_covers = shapely_points = None

from .config import RUNTIME_DIR, settings
from .db import get_setting, log_event, set_setting, utc_now
from .graph_store import GRAPH_STORE


# Keep this intentionally conservative. It represents ordinary motor-vehicle roads,
# not every OSM highway object. Service roads are optional through the profile.
DRIVE_HIGHWAYS = [
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "road",
]
SERVICE_HIGHWAYS = DRIVE_HIGHWAYS + ["service"]
BLOCKED_ACCESS_VALUES = {"no", "private"}

# Country-agnostic free-flow defaults used only when OSM does not provide a
# usable maxspeed for an edge/highway class. OSMnx keeps explicit maxspeed tags
# when they exist, then uses these class defaults for missing values. The final
# fallback covers uncommon/compound highway tags without crashing sparse-tag
# extracts (some countries have virtually no maxspeed tagging at all).
DEFAULT_HIGHWAY_SPEEDS_KPH: dict[str, float] = {
    "motorway": 100.0, "motorway_link": 60.0,
    "trunk": 80.0, "trunk_link": 50.0,
    "primary": 60.0, "primary_link": 45.0,
    "secondary": 50.0, "secondary_link": 40.0,
    "tertiary": 40.0, "tertiary_link": 35.0,
    "unclassified": 30.0, "residential": 30.0,
    "living_street": 15.0, "service": 20.0, "road": 25.0,
}
DEFAULT_SPEED_FALLBACK_KPH = 30.0

def add_edge_speeds_and_times(graph, ox=None):
    """Attach robust speed/travel-time attributes to an OSMnx graph.

    OSMnx's default imputation needs at least one usable ``maxspeed`` value
    somewhere in the graph. That assumption is false for many regional extracts.
    This helper keeps locally observed class speeds when available, supplies class
    defaults only for highway classes with no speed tags, and uses a conservative
    fallback for uncommon/invalid classes. Thus sparse-tag extracts do not crash
    while richer extracts still learn from their own local OSM speed evidence.
    """
    ox = ox or _import_osmnx()
    routing_api = getattr(ox, "routing", None)
    add_speeds = getattr(routing_api, "add_edge_speeds", None) or getattr(ox, "add_edge_speeds", None)
    add_times = getattr(routing_api, "add_edge_travel_times", None) or getattr(ox, "add_edge_travel_times", None)
    if not callable(add_speeds) or not callable(add_times):
        raise RuntimeError("Installed OSMnx does not expose edge speed/travel-time helpers")
    # Preserve local evidence whenever it exists. For a highway class with at
    # least one maxspeed tag, omit that class from ``hwy_speeds`` so OSMnx
    # imputes missing edges from the graph's own observed local values. Only
    # wholly untagged classes receive our conservative class default.
    observed_classes: set[str] = set()
    graph_classes: set[str] = set()
    for _, _, _, data in graph.edges(keys=True, data=True):
        highway = data.get("highway")
        highway = highway[0] if isinstance(highway, list) and highway else highway
        if isinstance(highway, str) and highway:
            graph_classes.add(highway)
            if data.get("maxspeed") not in (None, "", [], ()):
                observed_classes.add(highway)
    sparse_defaults = {
        highway: speed
        for highway, speed in DEFAULT_HIGHWAY_SPEEDS_KPH.items()
        if highway in graph_classes and highway not in observed_classes
    }
    graph = add_speeds(
        graph,
        hwy_speeds=sparse_defaults or None,
        fallback=float(DEFAULT_SPEED_FALLBACK_KPH),
    )
    graph = add_times(graph)
    return graph

_CATALOG_RESULT_CACHE_LOCK = threading.Lock()
_CATALOG_RESULT_CACHE: dict[tuple[bool, int, int], dict[str, Any]] = {}

_REGION_GEOMETRY_CACHE_LOCK = threading.Lock()
_REGION_GEOMETRY_CACHE: dict[tuple[str, int, int], Any] = {}


def _import_osmnx():
    try:
        import osmnx as ox
    except ImportError as exc:
        raise RuntimeError("OSMnx is not installed. Run the installer cell again.") from exc
    return ox


def _data_dir() -> Path:
    raw = os.getenv("VRP_OSM_DATA_DIR", "").strip()
    root = Path(raw).expanduser() if raw else RUNTIME_DIR / "osm-data"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()






def region_cache_dir() -> Path:
    # Regional transformations are scratch/compute data and stay on the
    # runtime-local filesystem; verified source/cache storage is configured separately.
    root = Path(os.getenv("VRP_REGION_CACHE_DIR", RUNTIME_DIR / "regional-cache"))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()






def _replace_with_link_or_copy(source: Path, destination: Path) -> None:
    """Atomically expose a same-filesystem cache without duplicating bytes.

    Regional caches and the active network pickle both live under the Colab
    runtime directory. A hard link avoids copying tens/hundreds of MB on each
    cache reopen. Cross-device/unsupported filesystems fall back to copy2.
    """
    source = Path(source); destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".link.tmp")
    temp.unlink(missing_ok=True)
    try:
        os.link(source, temp)
    except OSError:
        shutil.copy2(source, temp)
    temp.replace(destination)

def _cleanup_operating_scratch(*paths: Path) -> dict[str, Any]:
    """Remove disposable extraction intermediates after a graph is durable.

    The checksum-verified regional PBF and final GraphStore pickle are the two
    authoritative artifacts. region-raw/roads PBF and XML are build scratch and
    can be very large; retaining them after success wastes Colab SSD capacity and
    can slow later workflows through disk pressure. Cleanup is deliberately
    best-effort and happens only after the final graph/cache has been published.
    """
    removed = 0
    released = 0
    warnings: list[str] = []
    for raw in paths:
        path = Path(raw)
        try:
            if path.is_file():
                released += int(path.stat().st_size)
                path.unlink()
                removed += 1
        except OSError as exc:
            warnings.append(f"{path.name}: {exc}")
    return {"removed_files": removed, "released_bytes": released, "warnings": warnings}


def persistent_region_cache_dir() -> Path:
    """Processed graph cache colocated with the configured OSM data directory.

    The default Colab path is runtime-local and disappears with the runtime. It
    survives restarts only when ``VRP_OSM_DATA_DIR`` points at mounted persistent
    storage (for example Google Drive). Raw extraction/XML scratch files remain
    in the separate runtime cache.
    """
    root = _data_dir() / "prepared-regions"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()



def _human_bytes(value: int | float | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if number < 1024 or unit == "TB":
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} TB"


def _file_md5(path: Path, progress: Callable[[dict[str, Any]], None] | None = None) -> str:
    """Hash an already-written file.

    Fresh regional downloads normally do not call this after transfer: their
    checksum is accumulated in the same pass that writes network bytes. This
    helper remains for recovery/resume cases where bytes pre-date this process.
    """
    digest = hashlib.md5()
    total = path.stat().st_size
    read = 0
    started = time.monotonic()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(16 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            read += len(chunk)
            if progress:
                elapsed = max(0.001, time.monotonic() - started)
                rate = read / elapsed
                remaining = max(0, total - read)
                progress({
                    "phase": "verify", "done": read, "total": total,
                    "elapsed_s": elapsed, "rate_bps": rate,
                    "eta_s": remaining / rate if rate > 0 else None,
                })
    return digest.hexdigest()


def _md5_digest_for_prefix(
    path: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
    message: str = "Checking retained partial bytes before resume",
):
    """Return an MD5 state containing an existing staged-file prefix.

    hashlib state is not serialized between runtimes. Interrupted downloads
    therefore re-read only the retained prefix before append-resume; ordinary
    fresh downloads start with an empty digest and avoid a second full-file pass.
    """
    digest = hashlib.md5()
    if not path.exists() or path.stat().st_size <= 0:
        return digest
    total = int(path.stat().st_size)
    read = 0
    started = time.monotonic()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
            read += len(chunk)
            if progress:
                elapsed = max(0.001, time.monotonic() - started)
                rate = max(1.0, read / elapsed)
                progress({
                    "phase": "download", "message": message,
                    "done": read, "total": total, "elapsed_s": elapsed,
                    "rate_bps": rate, "eta_s": max(0, total - read) / rate,
                })
    return digest

def _parse_md5_text(text: str) -> str:
    token = text.strip().split()[0] if text.strip() else ""
    if len(token) != 32 or any(c not in "0123456789abcdefABCDEF" for c in token):
        raise RuntimeError("The regional-source checksum response was not a valid MD5 value")
    return token.lower()








def bbox_from_places(places: list[dict[str, Any]], margin_m: float) -> tuple[float, float, float, float]:
    if not places:
        raise ValueError("No places are available to define the operating area")
    lats = [float(p["lat"]) for p in places]
    lons = [float(p["lon"]) for p in places]
    if any(not math.isfinite(v) or v < -90.0 or v > 90.0 for v in lats):
        raise ValueError("Operating-area latitude is outside the valid WGS84 range")
    if any(not math.isfinite(v) or v < -180.0 or v > 180.0 for v in lons):
        raise ValueError("Operating-area longitude is outside the valid WGS84 range")
    if max(lons) - min(lons) > 180.0:
        raise ValueError(
            "The operating area crosses the antimeridian. FleetRoute will not create an almost-worldwide "
            "bounding box silently; choose a regional extract and stops on one side of ±180°."
        )
    mean_lat = sum(lats) / len(lats)
    lat_pad = margin_m / 111_320.0
    lon_pad = margin_m / (111_320.0 * max(0.01, abs(math.cos(math.radians(mean_lat)))))
    left = min(lons) - lon_pad
    right = max(lons) + lon_pad
    bottom = min(lats) - lat_pad
    top = max(lats) + lat_pad
    if left < -180.0 or right > 180.0:
        raise ValueError(
            "The requested operating margin crosses the antimeridian. Reduce the margin or use stops on one side of ±180°."
        )
    return max(-180.0, left), max(-90.0, bottom), min(180.0, right), min(90.0, top)


def stable_bbox(bbox: tuple[float, float, float, float], grid_degrees: float = 0.025) -> tuple[float, float, float, float]:
    """Snap extents to stable tiles so tiny plan edits reuse the same cache."""
    left, bottom, right, top = bbox
    left = math.floor(left / grid_degrees) * grid_degrees
    bottom = math.floor(bottom / grid_degrees) * grid_degrees
    right = math.ceil(right / grid_degrees) * grid_degrees
    top = math.ceil(top / grid_degrees) * grid_degrees
    return left, bottom, right, top


def _profile_highways(network_type: str) -> list[str]:
    return SERVICE_HIGHWAYS if network_type == "drive_service" else DRIVE_HIGHWAYS


def _cache_key(bbox: tuple[float, float, float, float], network_type: str, pbf: Path) -> str:
    """Stable regional cache key across Colab restarts and Drive remounts.

    The previous key included the staged local file mtime. Copying the same
    Legacy persistent-source staging gave the PBF a new mtime every session, so an identical
    operating area missed the persistent cache and rebuilt from scratch. Use the
    verified source identity instead.
    """
    rounded = [round(value, 5) for value in bbox]
    region = selected_osm_region() or {}
    receipt = _source_receipt(region.get("id")) if region.get("id") else {}
    signature = {
        "bbox": rounded,
        "network_type": network_type,
        "region_id": region.get("id") or "",
        "source_md5": receipt.get("verified_md5") or "",
        "source_timestamp": receipt.get("source_timestamp") or receipt.get("remote_last_modified") or "",
        "pbf_size": int(pbf.stat().st_size),
        "schema": 8,
    }
    return hashlib.sha256(json.dumps(signature, sort_keys=True).encode("utf-8")).hexdigest()[:18]


def _terminate_process_tree(process: subprocess.Popen, *, grace_s: float = 5.0) -> None:
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=grace_s)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
    else:
        process.kill()
    try:
        process.wait(timeout=max(1.0, grace_s))
    except subprocess.TimeoutExpired:
        pass


def _ensure_osmium(progress: Callable[[dict[str, Any]], None] | None = None) -> str:
    """Return the osmium executable, installing it lazily on Colab/Linux when possible.

    Cached prepared regions never call this function. Installation is serialized
    so a background graph build and an operator action cannot race apt/dpkg.
    """
    existing = shutil.which("osmium")
    if existing:
        return existing
    lock_path = RUNTIME_DIR / "osmium-install.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_handle:
        wait_started = time.monotonic()
        next_notice = 0.0
        while True:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                # Notebook startup may already be prewarming osmium. Keep the
                # graph-build job visibly alive rather than blocking silently on
                # the package-manager lock.
                existing = shutil.which("osmium")
                if existing:
                    return existing
                elapsed = time.monotonic() - wait_started
                if progress and elapsed >= next_notice:
                    progress({
                        "phase": "install",
                        "message": f"Road extraction tool is warming in the background · {elapsed:.1f}s",
                        "elapsed_s": elapsed,
                        "expected_s": 45.0,
                    })
                    next_notice = elapsed + 1.0
                time.sleep(0.20)
        existing = shutil.which("osmium")
        if existing:
            return existing
        apt = shutil.which("apt-get")
        if not apt or (hasattr(os, "geteuid") and os.geteuid() != 0):
            raise RuntimeError(
                "osmium-tool is required only for the first build of an uncached regional road graph. "
                "Install osmium-tool on this host, then retry; verified prepared-region caches remain usable without it."
            )
        if progress:
            progress({"phase": "install", "message": "Installing osmium-tool for the first uncached regional extraction"})
        env = dict(os.environ)
        env.setdefault("DEBIAN_FRONTEND", "noninteractive")
        commands = (
            ([apt, "update", "-qq"], "Refreshing package metadata", 70.0),
            ([apt, "install", "-y", "-qq", "osmium-tool"], "Installing osmium-tool", 120.0),
        )
        for command, label, expected_s in commands:
            _run(
                list(command), label, timeout=600, progress=progress, phase="install",
                expected_s=expected_s, env=env,
            )
        existing = shutil.which("osmium")
        if not existing:
            raise RuntimeError("osmium-tool installation completed without exposing an osmium executable")
        return existing


def _run(
    command: list[str],
    label: str,
    timeout: int = 900,
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    phase: str = "working",
    expected_s: float = 60.0,
    env: dict[str, str] | None = None,
) -> None:
    """Run osmium with honest elapsed heartbeats and no pipe deadlock.

    Osmium is usually quiet, but piping diagnostics without draining them can
    still block a long command. Diagnostics now go to a temporary file while
    the UI receives independent persisted heartbeats.
    """
    started = time.monotonic()
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as diagnostics:
        process = subprocess.Popen(
            command,
            stdout=diagnostics,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            env=env,
            start_new_session=(os.name != "nt"),
        )
        last_emit = 0.0
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > timeout:
                    _terminate_process_tree(process, grace_s=5.0)
                    raise TimeoutError(f"{label} exceeded the {timeout} second safety timeout")
                if progress and elapsed - last_emit >= 0.65:
                    progress({
                        "phase": phase,
                        "message": f"{label} · {elapsed:.1f}s",
                        "elapsed_s": elapsed,
                        "expected_s": float(expected_s),
                    })
                    last_emit = elapsed
                time.sleep(0.08)
            process.wait()
        except BaseException:
            _terminate_process_tree(process, grace_s=4.0)
            raise
        diagnostics.flush()
        diagnostics.seek(0)
        output = diagnostics.read()

    elapsed = time.monotonic() - started
    if progress:
        progress({
            "phase": phase,
            "message": f"{label} complete · {elapsed:.1f}s",
            "elapsed_s": elapsed,
            "expected_s": float(expected_s),
            "phase_complete": True,
        })
    if process.returncode != 0:
        raise RuntimeError(
            f"{label} failed (exit {process.returncode}).\n"
            f"Command: {' '.join(command)}\n{output}"
        )


def _call_with_progress(
    function: Callable[[], Any],
    *,
    progress: Callable[[dict[str, Any]], None] | None,
    phase: str,
    label: str,
    expected_s: float,
) -> Any:
    """Emit honest elapsed-time heartbeats while a Python GIS call is active."""
    if progress is None:
        return function()
    stop = False
    started = time.monotonic()
    callback_error: list[BaseException] = []

    def heartbeat() -> None:
        nonlocal stop
        while not stop:
            elapsed = time.monotonic() - started
            try:
                progress({
                    "phase": phase,
                    "message": f"{label} · {elapsed:.1f}s",
                    "elapsed_s": elapsed,
                    "expected_s": float(expected_s),
                })
            except BaseException as exc:
                callback_error.append(exc)
                stop = True
                return
            time.sleep(0.55)

    import threading
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        result = function()
    finally:
        stop = True
        thread.join(timeout=1.5)
    if callback_error:
        raise callback_error[0]
    elapsed = time.monotonic() - started
    progress({
        "phase": phase,
        "message": f"{label} complete · {elapsed:.1f}s",
        "elapsed_s": elapsed,
        "expected_s": float(expected_s),
        "phase_complete": True,
    })
    return result


def _set_useful_tags(ox) -> None:
    wanted = {
        "access", "area", "bridge", "highway", "hgv", "junction", "lanes", "maxheight",
        "maxspeed", "maxweight", "motor_vehicle", "name", "oneway", "ref", "service",
        "surface", "tunnel", "vehicle", "width",
    }
    ox.settings.useful_tags_way = list(dict.fromkeys([*ox.settings.useful_tags_way, *sorted(wanted)]))


def _tag_values(value: Any) -> set[str]:
    """Normalize OSMnx scalar/list tags without silently trusting list order."""
    if value is None:
        return set()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return {str(item).strip().lower() for item in values if str(item or "").strip()}


def _post_filter_graph(graph, network_type: str):
    allowed = set(_profile_highways(network_type))
    remove = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        highways = _tag_values(data.get("highway"))
        access_values = (
            _tag_values(data.get("access"))
            | _tag_values(data.get("motor_vehicle"))
            | _tag_values(data.get("vehicle"))
        )
        # Simplification can combine differing highway values into a list. Keeping
        # an edge must not depend on whichever value OSMnx happened to place first.
        if not (highways & allowed):
            remove.append((u, v, key))
            continue
        # A simplified edge that contains an explicitly blocked motor-vehicle
        # segment is conservatively rejected as a whole.
        if access_values & BLOCKED_ACCESS_VALUES:
            remove.append((u, v, key))
    graph.remove_edges_from(remove)
    isolates = list(nx.isolates(graph))
    graph.remove_nodes_from(isolates)
    return graph


def _select_round_trip_component(graph, depot_lat: float, depot_lon: float):
    """Choose the closest viable strongly-connected road component to the depot.

    The geometrically nearest OSM node can sit on a tiny one-way/service fragment.
    Rejecting an otherwise valid city because of that single node is a false
    negative. We keep the nearest viable SCC instead; the normal snap-distance
    contract still decides whether the depot is close enough to that road network.
    """
    components = list(nx.strongly_connected_components(graph))
    if not components:
        raise ValueError("The selected operating area has no strongly connected driving component")
    node_to_component: dict[Any, int] = {}
    for index, nodes in enumerate(components):
        for node in nodes:
            node_to_component[node] = index

    # Rank every component by the closest node using an equirectangular local
    # approximation. This is only a selector; final snap evidence uses exact
    # projected geometry in GraphStore.
    cos_lat = max(0.01, abs(math.cos(math.radians(float(depot_lat)))))
    best_distance: dict[int, float] = {}
    best_node: dict[int, Any] = {}
    for node, data in graph.nodes(data=True):
        try:
            lat = float(data["y"]); lon = float(data["x"])
        except Exception:
            continue
        dy = (lat - float(depot_lat)) * 111_320.0
        dx = (lon - float(depot_lon)) * 111_320.0 * cos_lat
        d2 = dx * dx + dy * dy
        ci = node_to_component.get(node)
        if ci is not None and d2 < best_distance.get(ci, float("inf")):
            best_distance[ci] = d2
            best_node[ci] = node

    for ci in sorted(best_distance, key=best_distance.get):
        nodes = components[ci]
        if len(nodes) < 8:
            continue
        candidate = graph.subgraph(nodes)
        if candidate.number_of_edges() < 12:
            continue
        return best_node[ci], nodes, math.sqrt(best_distance[ci])
    raise ValueError("No usable round-trip drivable component exists near the depot")


def prepare_operating_graph(
    places: list[dict[str, Any]],
    network_type: str,
    margin_m: float,
    depot_lat: float,
    depot_lon: float,
    output_graphml: Path,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    build_started = time.monotonic()
    source_pbf = region_pbf_path()
    source_status = region_source_status(False)
    if not source_status.get("ready"):
        raise ValueError("Download and verify the active regional road source before preparing an operating area")
    active_region = source_status.get("region") or {}
    if active_region.get("id"):
        # Guard the complete plan before installing/calling osmium. The depot can
        # be inside an extract while one distant work point is outside it; waiting
        # for extraction/OSMnx and discovering that later wastes tens of seconds
        # and produces a misleading access failure. Unknown boundary data remains
        # allowed only because explicit source activation is the operator's trust
        # decision in that case.
        plan_points = list(places or [])
        if not plan_points:
            plan_points = [{"role": "depot", "name": "Depot", "lat": float(depot_lat), "lon": float(depot_lon)}]
        plan_coverage = region_points_coverage(str(active_region["id"]), plan_points)
        if plan_coverage.get("known") and plan_coverage.get("covers_all") is False:
            outside_count = int(plan_coverage.get("outside_count") or 0)
            outside = plan_coverage.get("outside") or []
            labels = [str(item.get("name") or item.get("role") or "plan point") for item in outside[:4]]
            detail = f" ({', '.join(labels)})" if labels else ""
            raise ValueError(
                f"{outside_count} current plan point{' is' if outside_count == 1 else 's are'} outside the active regional road source "
                f"'{active_region.get('name') or active_region.get('id')}'{detail}. "
                "Choose/download a region that contains the depot and all work points before extracting roads."
            )
    # Resolve the prepared cache before staging the regional PBF. A prepared
    # region should reopen from its compact graph cache in seconds, not pay a
    # source-file extraction/conversion cost on every runtime session.
    bbox = stable_bbox(bbox_from_places(places, margin_m))
    key = _cache_key(bbox, network_type, source_pbf)
    cache = region_cache_dir() / key
    cache.mkdir(parents=True, exist_ok=True)
    cached_pickle = cache / "operating.fast.pkl"
    metadata_path = cache / "metadata.json"
    persistent_cache = persistent_region_cache_dir() / key
    persistent_pickle = persistent_cache / "operating.fast.pkl"
    persistent_metadata = persistent_cache / "metadata.json"

    restored_from_persistent = False
    if (not cached_pickle.exists() or not metadata_path.exists()) and persistent_pickle.exists() and persistent_metadata.exists():
        if progress:
            progress({"phase": "cache", "message": "Restoring prepared operating area from configured cache storage"})
        _replace_with_link_or_copy(persistent_pickle, cached_pickle)
        shutil.copy2(persistent_metadata, metadata_path)
        restored_from_persistent = True

    if cached_pickle.exists() and metadata_path.exists():
        try:
            if progress:
                progress({"phase": "cache", "message": "Loading the cached operating graph"})
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["cache_hit"] = True
            metadata["path"] = str(settings.network_pickle)

            # Current regional caches use the exact same GraphStore pickle wrapper
            # as the active runtime. Legacy bare-graph caches are migrated once.
            if metadata.get("cache_format") == "graphstore-wrapper-v1":
                _replace_with_link_or_copy(cached_pickle, settings.network_pickle)
                GRAPH_STORE.invalidate()
                GRAPH_STORE.get_graph()
                GRAPH_STORE.update_metadata(metadata)
            else:
                with cached_pickle.open("rb") as handle:
                    payload = pickle.load(handle)
                graph = payload.get("graph") if isinstance(payload, dict) and "graph" in payload else payload
                if graph is None:
                    raise ValueError("Prepared operating graph cache is invalid")
                metadata["cache_format"] = "graphstore-wrapper-v1"
                GRAPH_STORE.set_graph(graph, metadata, persist=True)
                _replace_with_link_or_copy(settings.network_pickle, cached_pickle)
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                try:
                    persistent_cache.mkdir(parents=True, exist_ok=True)
                    _replace_with_link_or_copy(cached_pickle, persistent_pickle)
                    shutil.copy2(metadata_path, persistent_metadata)
                except Exception:
                    pass
            if progress:
                progress({"phase": "complete", "message": "Cached operating graph ready"})
            return metadata
        except Exception as exc:
            # A derived cache is disposable. Reject corruption/incompatible
            # payloads and rebuild from the checksum-verified regional PBF rather
            # than trapping the workspace in a permanent cache-load failure.
            if exc.__class__.__name__ == "JobCancelled":
                raise
            GRAPH_STORE.invalidate()
            settings.network_pickle.unlink(missing_ok=True)
            cached_pickle.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            if restored_from_persistent:
                persistent_pickle.unlink(missing_ok=True)
                persistent_metadata.unlink(missing_ok=True)
            log_event("osm.operating_graph.cache_rejected", {
                "cache_key": key, "error": f"{type(exc).__name__}: {exc}",
                "restored_from_configured_cache": restored_from_persistent,
            }, "system")
            if progress:
                progress({"phase": "cache", "message": "Cached graph was invalid; rebuilding safely from the verified regional source"})

    # No processed cache exists: osmium and the regional PBF are needed only
    # for the actual extraction/build path. Cached regions remain usable even if
    # the current runtime has not installed osmium yet.
    osmium = _ensure_osmium(progress)
    pbf = local_selected_region_pbf(progress)
    left, bottom, right, top = bbox
    raw_pbf = cache / "region-raw.osm.pbf"
    roads_pbf = cache / "region-roads.osm.pbf"  # legacy fallback only
    roads_xml = cache / "region-roads.osm"
    if progress:
        progress({"phase": "extract", "message": "Extracting the operating area from the selected regional PBF"})
    _run([
        osmium, "extract", "--bbox", f"{left},{bottom},{right},{top}",
        "--strategy", "complete_ways", "--set-bounds", "--overwrite",
        "--output", str(raw_pbf), str(pbf),
    ], "Regional operating-area extract", timeout=1200, progress=progress, phase="extract", expected_s=45)

    highways = ",".join(_profile_highways(network_type))
    # Fast path: osmium tags-filter can write OSM XML directly. This removes a
    # complete roads-PBF write followed by a complete roads-PBF read/cat pass.
    # If a host/osmium build rejects direct XML output, fall back to the older
    # two-step PBF->XML path rather than weakening graph correctness.
    filter_pipeline = "direct_xml"
    if progress:
        progress({"phase": "filter", "message": "Filtering drivable roads directly into the OSMnx input"})
    try:
        roads_xml.unlink(missing_ok=True)
        _run([
            osmium, "tags-filter", "--overwrite", "--output", str(roads_xml), str(raw_pbf),
            f"w/highway={highways}", "r/type=restriction",
        ], "Drivable-road filter", timeout=1200, progress=progress, phase="filter", expected_s=22)
        if not roads_xml.is_file() or roads_xml.stat().st_size < 128:
            raise RuntimeError("Direct road-filter output was empty")
        with roads_xml.open("rb") as probe:
            prefix = probe.read(4096).lstrip()
        if b"<osm" not in prefix and not prefix.startswith(b"<?xml"):
            raise RuntimeError("Direct road-filter output was not OSM XML")
    except Exception as direct_exc:
        if direct_exc.__class__.__name__ == "JobCancelled":
            raise
        filter_pipeline = "pbf_then_xml_fallback"
        roads_xml.unlink(missing_ok=True)
        if progress:
            progress({
                "phase": "filter",
                "message": "Direct road filtering was unavailable; using the compatible conversion fallback",
            })
        _run([
            osmium, "tags-filter", "--overwrite", "--output", str(roads_pbf), str(raw_pbf),
            f"w/highway={highways}", "r/type=restriction",
        ], "Drivable-road filter", timeout=1200, progress=progress, phase="filter", expected_s=18)
        _run([
            osmium, "cat", "--overwrite", "--output", str(roads_xml), str(roads_pbf),
        ], "Regional PBF-to-XML conversion", timeout=1200, progress=progress, phase="convert", expected_s=22)

    ox = _import_osmnx()
    _set_useful_tags(ox)
    if progress:
        progress({"phase": "graph", "message": "Building directed road graph"})
    graph = _call_with_progress(
        lambda: ox.graph.graph_from_xml(
            roads_xml, bidirectional=False, simplify=True, retain_all=True,
        ),
        progress=progress, phase="graph", label="Building and simplifying directed graph", expected_s=75,
    )
    graph = _post_filter_graph(graph, network_type)
    if graph.number_of_edges() == 0:
        raise ValueError("The selected operating area contains no usable driving edges")

    # Some regional extracts have no usable maxspeed tags at all. OSMnx's
    # default inference raises in that case, so use the shared global fallback
    # profile while preserving every explicit OSM maxspeed that is available.
    graph = add_edge_speeds_and_times(graph, ox)

    depot_node, component, depot_component_snap_m = _select_round_trip_component(
        graph, float(depot_lat), float(depot_lon)
    )
    graph = graph.subgraph(component).copy()
    tagged_maxspeed_edges = sum(
        1 for _, _, _, data in graph.edges(keys=True, data=True)
        if data.get("maxspeed") not in (None, "", [], ())
    )

    metadata = {
        "source": f"{(selected_osm_region() or {}).get('name', 'Regional')} offline PBF",
        "source_path": str(pbf),
        "source_md5": (_source_receipt((selected_osm_region() or {}).get("id")) if (selected_osm_region() or {}).get("id") else {}).get("verified_md5"),
        "source_region_id": (selected_osm_region() or {}).get("id"),
        "source_region_name": (selected_osm_region() or {}).get("name"),
        "cache_key": key,
        "cache_hit": False,
        "cache_format": "graphstore-wrapper-v1",
        "bbox": [left, bottom, right, top],
        "network_type": network_type,
        "margin_m": float(margin_m),
        "road_filter_pipeline": filter_pipeline,
        "nodes": int(graph.number_of_nodes()),
        "edges": int(graph.number_of_edges()),
        "depot_osm_node": str(depot_node),
        "depot_component_node_distance_m": round(float(depot_component_snap_m), 3),
        "round_trip_component": True,
        "speed_model": {
            "explicit_maxspeed_edges": int(tagged_maxspeed_edges),
            "imputed_edge_count": max(0, int(graph.number_of_edges()) - int(tagged_maxspeed_edges)),
            "fallback_kph": float(DEFAULT_SPEED_FALLBACK_KPH),
            "policy": "OSM maxspeed/local class mean when present; otherwise highway-class defaults with conservative fallback",
        },
        "built_at": utc_now(),
        "path": str(settings.network_pickle),
        "storage": "local-memory-plus-pickle",
    }

    # Serialize the final graph exactly once. The regional cache and persistent
    # cache are byte-for-byte copies of the active GraphStore payload. This
    # removes a second full NetworkX pickle pass from graph preparation.
    GRAPH_STORE.set_graph(graph, metadata, persist=True)
    _replace_with_link_or_copy(settings.network_pickle, cached_pickle)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    # Persist only the compact final graph, never the huge XML/PBF scratch files.
    try:
        persistent_cache.mkdir(parents=True, exist_ok=True)
        _replace_with_link_or_copy(cached_pickle, persistent_pickle)
        shutil.copy2(metadata_path, persistent_metadata)
        metadata["persistent_cache"] = str(persistent_pickle)
        GRAPH_STORE.update_metadata(metadata)
    except Exception as exc:
        metadata["persistent_cache_warning"] = str(exc)
        GRAPH_STORE.update_metadata(metadata)
    # Only now that the active and prepared graph caches are durable may the
    # extraction intermediates be discarded. A failed graph build intentionally
    # leaves them available for diagnostics until the next rebuild/cleanup.
    scratch_cleanup = _cleanup_operating_scratch(raw_pbf, roads_pbf, roads_xml)
    metadata["scratch_cleanup"] = scratch_cleanup
    metadata["build_elapsed_s"] = round(time.monotonic() - build_started, 3)
    GRAPH_STORE.update_metadata(metadata)
    # Refresh metadata after the final timing/cleanup fields so reopened cache
    # diagnostics describe the same completed build generation.
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        if persistent_cache.exists():
            shutil.copy2(metadata_path, persistent_metadata)
    except Exception:
        pass
    log_event("osm.operating_graph.prepared", metadata, "dispatcher")
    if progress:
        progress({"phase": "complete", "message": "Operating graph ready"})
    return metadata

# =============================================================================
# INTERNATIONAL REGION SOURCES
# =============================================================================
from urllib.parse import urlparse

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"
GEOFABRIK_INDEX_NOGEOM_URL = "https://download.geofabrik.de/index-v1-nogeom.json"
GEOFABRIK_INDEX_NOGEOM_MIRRORS = (
    "https://josm.openstreetmap.de/remote/geofabrik-index-v1-nogeom.json",
)
GEOFABRIK_HOST = "download.geofabrik.de"
# Since 2025-09-01 Geofabrik intentionally redirects *-latest files to a
# date-stamped object. Public download mirrors may use download-extN hosts.
# Catalog URLs must still originate from the canonical download.geofabrik.de.
GEOFABRIK_DOWNLOAD_HOST_RE = re.compile(r"^download(?:-ext\d+)?\.geofabrik\.de$")
GEOFABRIK_DATED_TOKEN_RE = re.compile(r"^\d{6}(?:\d{2})?$")
CATALOG_TTL_S = 6 * 60 * 60
MIN_PBF_BYTES = 64 * 1024


def _safe_region_id(region_id: str) -> str:
    value = str(region_id or "").strip().lower()
    if not value or len(value) > 120:
        raise ValueError("Choose an operating region first")
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-/" for ch in value):
        raise ValueError("Invalid region identifier")
    if value.startswith("/") or value.endswith("/") or "//" in value or ".." in value:
        raise ValueError("Invalid region identifier")
    return value


def _trusted_geofabrik_pbf_url(url: str) -> str:
    """Validate a canonical PBF URL obtained from Geofabrik's catalog."""
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or parsed.hostname != GEOFABRIK_HOST:
        raise ValueError("FleetRoute only accepts HTTPS PBF sources from download.geofabrik.de")
    if parsed.query or parsed.fragment or not parsed.path.endswith("-latest.osm.pbf"):
        raise ValueError("The selected Geofabrik source is not a supported latest .osm.pbf extract")
    return raw


def _geofabrik_download_host(hostname: str | None) -> bool:
    return bool(hostname and GEOFABRIK_DOWNLOAD_HOST_RE.fullmatch(str(hostname).lower()))


def _geofabrik_family_parts(requested_url: str, *, expected: str) -> tuple[str, str, str]:
    """Return (directory, extract basename, suffix) for a canonical latest URL."""
    requested = urlparse(str(requested_url or ""))
    if requested.scheme != "https" or requested.hostname != GEOFABRIK_HOST or requested.query or requested.fragment:
        raise RuntimeError("The requested regional source is not a canonical Geofabrik URL")
    suffix = "-latest.osm.pbf.md5" if expected == "md5" else "-latest.osm.pbf"
    name = Path(requested.path).name
    if not name.endswith(suffix):
        raise RuntimeError("The requested regional source does not match the expected Geofabrik file type")
    extract = name[:-len(suffix)]
    if not extract:
        raise RuntimeError("The requested Geofabrik extract name is empty")
    return str(Path(requested.path).parent).replace("\\", "/"), extract, suffix


def _trusted_geofabrik_aux_url(
    url: str, *, expected: str, requested_url: str | None = None
) -> str:
    """Validate catalog responses and Geofabrik's post-2025 redirect targets.

    Geofabrik changed ``*-latest`` downloads on 2025-09-01: the canonical
    latest URL now redirects to the date-stamped immutable object (for example
    ``germany-latest.osm.pbf`` -> ``germany-250901.osm.pbf``).  The old
    verifier rejected that official redirect and therefore broke every PBF
    download.  We accept only the same extract family, directory, file type and
    an official public Geofabrik download host.
    """
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        raise RuntimeError("The regional road-data request was redirected to an invalid URL")

    if expected == "catalog":
        if parsed.hostname != GEOFABRIK_HOST or parsed.path not in {"/index-v1.json", "/index-v1-nogeom.json"}:
            raise RuntimeError("The regional catalog was redirected to an unexpected resource")
        return raw

    if expected not in {"pbf", "md5"}:
        raise ValueError("Unknown Geofabrik resource type")
    if not _geofabrik_download_host(parsed.hostname):
        raise RuntimeError("The regional road-data request left the official Geofabrik download hosts")

    suffix = ".osm.pbf.md5" if expected == "md5" else ".osm.pbf"
    if not parsed.path.endswith(suffix):
        raise RuntimeError(f"The regional {expected.upper()} redirect changed file type")

    if requested_url:
        req_dir, extract, _ = _geofabrik_family_parts(requested_url, expected=expected)
        final_dir = str(Path(parsed.path).parent).replace("\\", "/")
        if final_dir != req_dir:
            raise RuntimeError("The regional road-data redirect changed extract directory")
        name = Path(parsed.path).name
        exact_latest = f"{extract}-latest{suffix}"
        if name != exact_latest:
            prefix = f"{extract}-"
            if not (name.startswith(prefix) and name.endswith(suffix)):
                raise RuntimeError("The regional road-data redirect changed extract identity")
            token = name[len(prefix):-len(suffix)]
            if not GEOFABRIK_DATED_TOKEN_RE.fullmatch(token):
                raise RuntimeError("The regional road-data redirect did not resolve to a dated Geofabrik object")
    return raw


def _verify_geofabrik_response(
    response: httpx.Response, *, expected: str, requested_url: str | None = None
) -> str:
    return _trusted_geofabrik_aux_url(str(response.url), expected=expected, requested_url=requested_url)


def _source_version_from_url(url: str) -> str | None:
    name = Path(urlparse(str(url)).path).name
    match = re.search(r"-(\d{6}(?:\d{2})?)\.osm\.pbf(?:\.md5)?$", name)
    return match.group(1) if match else None


def _part_identity_path(part: Path) -> Path:
    return part.with_suffix(part.suffix + ".source.json")


def _read_part_identity(part: Path) -> dict[str, Any]:
    meta = _part_identity_path(part)
    if not meta.is_file():
        return {}
    try:
        value = json.loads(meta.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_part_identity(part: Path, value: dict[str, Any]) -> None:
    meta = _part_identity_path(part)
    temp = meta.with_suffix(meta.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temp, meta)


def _resolve_remote_pbf(
    url: str, canonical_url: str, headers: dict[str, str]
) -> tuple[str, int | None, str | None]:
    """Best-effort resolve of ``*-latest`` to Geofabrik's immutable dated PBF."""
    try:
        # Metadata resolution is an interactive-path operation.  A HEAD request
        # should never be allowed to hold the UI for minutes merely to learn a
        # redirect/size.  Failure here is non-fatal: the streamed GET below still
        # verifies the exact checksum and response identity.
        with httpx.Client(
            timeout=httpx.Timeout(10.0, connect=6.0, read=8.0, write=8.0, pool=6.0),
            follow_redirects=True, headers=headers
        ) as client:
            response = client.head(url, headers={"Accept-Encoding": "identity"})
            response.raise_for_status()
            final_url = _trusted_geofabrik_aux_url(
                str(response.url), expected="pbf", requested_url=canonical_url
            )
            length = int(response.headers.get("content-length") or 0) or None
            return final_url, length, response.headers.get("last-modified")
    except Exception:
        return url, None, None


def _check_download_disk_space(destination: Path, remote_size: int | None, resume_bytes: int = 0) -> None:
    if not remote_size or remote_size <= 0:
        return
    remaining = max(0, int(remote_size) - max(0, int(resume_bytes)))
    # Keep a practical reserve for SQLite, logs and local graph extraction.
    reserve = max(512 * 1024 * 1024, min(4 * 1024**3, int(remote_size * 0.12)))
    free = shutil.disk_usage(destination.parent).free
    if free < remaining + reserve:
        raise RuntimeError(
            "Not enough local disk space for this regional road extract: "
            f"{_human_bytes(free)} free, about {_human_bytes(remaining + reserve)} required. "
            "Choose a smaller state/province extract or point VRP_OSM_DATA_DIR at larger storage."
        )


def _catalog_cache_path(include_geometry: bool = True) -> Path:
    return RUNTIME_DIR / ("geofabrik-index-v1.json" if include_geometry else "geofabrik-index-v1-nogeom.json")


def _load_geofabrik_index(include_geometry: bool = True, force: bool = False) -> dict[str, Any]:
    cache = _catalog_cache_path(include_geometry)
    url = GEOFABRIK_INDEX_URL if include_geometry else GEOFABRIK_INDEX_NOGEOM_URL
    fresh = cache.exists() and (time.time() - cache.stat().st_mtime) < CATALOG_TTL_S
    if not force and fresh:
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            if payload.get("type") == "FeatureCollection":
                return payload
        except Exception:
            pass
    headers = {"User-Agent": "FleetRoute-Routing-Workspace/1.0 region-selector"}
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, read=18.0), follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            _verify_geofabrik_response(response, expected="catalog")
            max_catalog_bytes = 100 * 1024 * 1024 if include_geometry else 20 * 1024 * 1024
            declared = int(response.headers.get("content-length") or 0)
            if declared and declared > max_catalog_bytes:
                raise RuntimeError("The regional catalog response was unexpectedly large")
            if len(response.content) > max_catalog_bytes:
                raise RuntimeError("The regional catalog response was unexpectedly large")
            payload = response.json()
        if payload.get("type") != "FeatureCollection":
            raise RuntimeError("Unexpected Geofabrik catalog format")
        temp = cache.with_suffix(cache.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temp.replace(cache)
        return payload
    except Exception:
        if cache.exists():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                if payload.get("type") == "FeatureCollection":
                    return payload
            except Exception:
                pass
        raise RuntimeError("The regional data catalog is temporarily unavailable. Use a verified local source or try again.")


def _catalog_feature(region_id: str, include_geometry: bool = False) -> dict[str, Any]:
    rid = _safe_region_id(region_id)
    payload = _load_geofabrik_index(include_geometry=include_geometry)
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        if str(props.get("id") or "").lower() == rid:
            return feature
    raise ValueError(f"Region '{rid}' is not present in the Geofabrik catalog")


def _catalog_feature_from_local_cache(region_id: str) -> dict[str, Any] | None:
    """Resolve a region from either cached catalog without network I/O."""
    rid = _safe_region_id(region_id)
    for include_geometry in (True, False):
        cache = _catalog_cache_path(include_geometry)
        if not cache.is_file():
            continue
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            if str(props.get("id") or "").lower() == rid:
                return feature
    return None


def geofabrik_catalog(include_geometry: bool = True, force: bool = False) -> dict[str, Any]:
    """Return the live Geofabrik hierarchy with an explicit source-contract audit.

    Every PBF URL in the catalog is validated before it can become selectable.
    Parent countries/regions that have no direct PBF remain in the hierarchy and
    are counted as covered when a downloadable descendant exists.  This keeps a
    future Geofabrik catalog/path change visible instead of silently presenting a
    country as unsupported.
    """
    cache_file = _catalog_cache_path(include_geometry)
    result_cache_key: tuple[bool, int, int] | None = None
    if not force and cache_file.is_file():
        try:
            cache_stat = cache_file.stat()
            if (time.time() - cache_stat.st_mtime) < CATALOG_TTL_S:
                result_cache_key = (bool(include_geometry), int(cache_stat.st_mtime_ns), int(cache_stat.st_size))
                with _CATALOG_RESULT_CACHE_LOCK:
                    cached_result = _CATALOG_RESULT_CACHE.get(result_cache_key)
                if cached_result is not None:
                    return cached_result
        except OSError:
            pass

    raw = _load_geofabrik_index(include_geometry=include_geometry, force=force)
    try:
        cache_stat = cache_file.stat()
        result_cache_key = (bool(include_geometry), int(cache_stat.st_mtime_ns), int(cache_stat.st_size))
    except OSError:
        result_cache_key = (bool(include_geometry), 0, len(raw.get("features") or []))

    features: list[dict[str, Any]] = []
    raw_pbf_count = 0
    trusted_pbf_count = 0
    rejected_pbf: list[dict[str, str]] = []
    country_iso_codes: set[str] = set()

    for feature in raw.get("features") or []:
        props = feature.get("properties") or {}
        urls = props.get("urls") or {}
        pbf_url = urls.get("pbf")
        try:
            rid = _safe_region_id(props.get("id"))
        except Exception:
            continue
        trusted = None
        if pbf_url:
            raw_pbf_count += 1
            try:
                trusted = _trusted_geofabrik_pbf_url(pbf_url)
                trusted_pbf_count += 1
            except Exception as exc:
                # Preserve navigation but make the rejection observable to QA/UI.
                rejected_pbf.append({
                    "id": rid,
                    "url": str(pbf_url),
                    "reason": str(exc),
                })
        raw_iso2 = props.get("iso3166-1:alpha2") or []
        if isinstance(raw_iso2, str):
            iso2 = [raw_iso2]
        else:
            iso2 = [str(value) for value in raw_iso2 if str(value or "").strip()]
        iso2 = [value.strip().upper() for value in iso2 if value.strip()]
        country_iso_codes.update(iso2)
        item = {
            "type": "Feature",
            "properties": {
                "id": rid,
                "name": str(props.get("name") or rid),
                "parent": props.get("parent"),
                "iso2": iso2,
                "pbf_url": trusted,
                "downloadable": bool(trusted),
                "source_rejected": bool(pbf_url and not trusted),
            },
            "geometry": feature.get("geometry") if include_geometry else None,
        }
        features.append(item)

    by_id = {item["properties"]["id"]: item for item in features}
    children: dict[str, list[str]] = {}
    for item in features:
        props = item["properties"]
        parent = str(props.get("parent") or "").strip().lower()
        if parent:
            children.setdefault(parent, []).append(props["id"])

    descendant_memo: dict[str, bool] = {}

    def has_downloadable_descendant(region_id: str, visiting: set[str] | None = None) -> bool:
        cached = descendant_memo.get(region_id)
        if cached is not None:
            return cached
        active = set() if visiting is None else visiting
        if region_id in active:
            descendant_memo[region_id] = False
            return False
        active.add(region_id)
        found = False
        for child_id in children.get(region_id, ()):
            child = by_id.get(child_id)
            if not child:
                continue
            if child["properties"].get("downloadable") or has_downloadable_descendant(child_id, active):
                found = True
                break
        active.discard(region_id)
        descendant_memo[region_id] = found
        return found

    covered_iso: set[str] = set()
    uncovered_iso: set[str] = set()
    for item in features:
        props = item["properties"]
        codes = props.get("iso2") or []
        if not codes:
            continue
        covered = bool(props.get("downloadable")) or has_downloadable_descendant(props["id"])
        (covered_iso if covered else uncovered_iso).update(codes)

    # A code can appear on more than one feature; any covered occurrence wins.
    uncovered_iso.difference_update(covered_iso)
    result = {
        "type": "FeatureCollection",
        "features": features,
        "updated_at": utc_now(),
        "source": GEOFABRIK_INDEX_URL if include_geometry else GEOFABRIK_INDEX_NOGEOM_URL,
        "audit": {
            "catalog_features": len(features),
            "pbf_urls_seen": raw_pbf_count,
            "trusted_pbf_urls": trusted_pbf_count,
            "rejected_pbf_urls": len(rejected_pbf),
            "rejected_examples": rejected_pbf[:20],
            "country_iso_codes": len(country_iso_codes),
            "country_iso_codes_with_downloadable_extract": len(covered_iso),
            "country_iso_codes_without_downloadable_extract": sorted(uncovered_iso),
        },
    }
    with _CATALOG_RESULT_CACHE_LOCK:
        # Keep the newest projection for each catalog mode. The UI commonly loads
        # the geometry catalog and then asks for a no-geometry status projection;
        # clearing the whole cache here forced a second parse of the large geometry
        # JSON at PBF-download completion. Keys include file mtime+size, so stale
        # entries cannot be selected after the on-disk cache changes.
        _CATALOG_RESULT_CACHE[result_cache_key] = result
        for cached_key in list(_CATALOG_RESULT_CACHE):
            if cached_key != result_cache_key and cached_key[0] == include_geometry:
                _CATALOG_RESULT_CACHE.pop(cached_key, None)
        while len(_CATALOG_RESULT_CACHE) > 4:
            _CATALOG_RESULT_CACHE.pop(next(iter(_CATALOG_RESULT_CACHE)), None)
    return result


def _iso2_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item or "").strip()]
    return []


def _region_from_feature(feature: dict[str, Any], *, selected_at: str | None = None) -> dict[str, Any]:
    props = feature.get("properties") or {}
    # Accept both the raw Geofabrik index shape (urls/iso3166...) and FleetRoute's
    # browser catalog projection (pbf_url/iso2).
    pbf_url = props.get("pbf_url") or (props.get("urls") or {}).get("pbf")
    region = {
        "id": _safe_region_id(props.get("id")),
        "name": str(props.get("name") or props.get("id")),
        "parent": props.get("parent"),
        "iso2": _iso2_list(props.get("iso2") or props.get("iso3166-1:alpha2")),
        "pbf_url": _trusted_geofabrik_pbf_url(pbf_url),
    }
    if selected_at:
        region["selected_at"] = selected_at
    return region


def _region_record(region_id: str) -> dict[str, Any]:
    """Resolve one trusted region without changing active or browsed state."""
    rid = _safe_region_id(region_id)
    receipt = _source_receipt(rid)
    if receipt.get("pbf_url"):
        try:
            return {
                "id": rid,
                "name": str(receipt.get("region_name") or rid),
                "parent": receipt.get("parent"),
                "iso2": _iso2_list(receipt.get("iso2")),
                "pbf_url": _trusted_geofabrik_pbf_url(receipt.get("pbf_url")),
            }
        except Exception:
            pass
    feature = _catalog_feature_from_local_cache(rid) or _catalog_feature(rid, include_geometry=False)
    return _region_from_feature(feature)


def _read_region_setting(key: str) -> dict[str, Any] | None:
    value = get_setting(key) or None
    if not value:
        return None
    try:
        rid = _safe_region_id(value.get("id"))
        pbf_url = _trusted_geofabrik_pbf_url(value.get("pbf_url"))
    except Exception:
        return None
    return {
        "id": rid,
        "name": str(value.get("name") or rid),
        "parent": value.get("parent"),
        "iso2": _iso2_list(value.get("iso2")),
        "pbf_url": pbf_url,
    }


def selected_osm_region() -> dict[str, Any] | None:
    """Return the *active* verified road source identity.

    This setting is deliberately not changed when the operator merely browses a
    different country/region in the catalog.
    """
    return _read_region_setting("osm_selected_region")


def browsed_osm_region() -> dict[str, Any] | None:
    """Return the catalog/download target without mutating the active source."""
    return _read_region_setting("osm_browsed_region") or selected_osm_region()


def select_osm_region(region_id: str) -> dict[str, Any]:
    """Browse/select a catalog target only; never switch the active road source.

    If the geometry catalog is already in local cache (the normal map-first UI
    path), snapshot this region's exact boundary now. That moves the tiny boundary
    serialization off the post-download critical path without making a network
    request and without changing active-source state.
    """
    region = _region_record(region_id)
    region["selected_at"] = utc_now()
    set_setting("osm_browsed_region", region)
    boundary_cached = False
    try:
        boundary_cached = bool(snapshot_region_geometry(region["id"]))
    except Exception:
        # Browsing must remain available even if a local geometry cache is absent
        # or damaged. Coverage stays fail-closed until a valid boundary is present.
        boundary_cached = False
    log_event(
        "osm.region.browsed",
        {
            "region_id": region["id"],
            "region_name": region["name"],
            "boundary_snapshot_cached": boundary_cached,
        },
        "dispatcher",
    )
    return region_target_status(region)


def set_active_osm_region(region_id: str) -> dict[str, Any]:
    """Persist an already-verified region as active. Derived-state invalidation
    belongs to the engine, which owns route/input publication semantics.
    """
    region = _region_record(region_id)
    receipt = _source_receipt(region["id"])
    ready, reason = _verified_local_source(region, receipt)
    if not ready:
        raise ValueError(reason or "Download and verify this regional road source before activating it")
    region["selected_at"] = utc_now()
    set_setting("osm_selected_region", region)
    set_setting("osm_browsed_region", region)
    return region_source_status(False)


def _boundary_snapshot_path(region_id: str) -> Path:
    # Do not create the source directory just to inspect a boundary.
    return _data_dir() / "sources" / _region_storage_key(region_id) / "boundary.geojson"


def _boundary_snapshot_meta_path(region_id: str) -> Path:
    return _boundary_snapshot_path(region_id).with_suffix(".source.json")


def _geometry_catalog_identity() -> dict[str, int] | None:
    cache = _catalog_cache_path(True)
    if not cache.is_file():
        return None
    try:
        st = cache.stat()
        return {"mtime_ns": int(st.st_mtime_ns), "size_bytes": int(st.st_size)}
    except OSError:
        return None


def _geometry_payload_from_local_catalog(region_id: str) -> dict[str, Any] | None:
    rid = _safe_region_id(region_id)
    cache = _catalog_cache_path(True)
    if not cache.is_file():
        return None
    # The selector API normally parsed this exact catalog moments earlier. Reuse
    # that in-memory projection first so download completion does not reparse the
    # large geometry JSON. After a restart, fall back to the cached file.
    try:
        st = cache.stat()
        key = (True, int(st.st_mtime_ns), int(st.st_size))
        with _CATALOG_RESULT_CACHE_LOCK:
            projected = _CATALOG_RESULT_CACHE.get(key)
        if projected is not None:
            for feature in projected.get("features") or []:
                props = feature.get("properties") or {}
                if str(props.get("id") or "").lower() == rid and feature.get("geometry"):
                    return feature.get("geometry")
    except OSError:
        pass
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            if str(props.get("id") or "").lower() == rid and feature.get("geometry"):
                return feature.get("geometry")
    except Exception:
        return None
    return None

def snapshot_region_geometry(region_id: str) -> bool:
    """Persist the exact Geofabrik catalog boundary when it is already cached.

    No network request is made here. A missing boundary therefore produces an
    explicit 'coverage unknown' state instead of guessing from a country name or
    rectangular bounding box. A snapshot is reused only when it is valid JSON and
    its sidecar matches the current geometry-catalog file identity; a refreshed
    catalog therefore forces an exact rebuild rather than silently keeping stale
    coverage geometry.
    """
    rid = _safe_region_id(region_id)
    path = _boundary_snapshot_path(rid)
    meta_path = _boundary_snapshot_meta_path(rid)
    catalog_identity = _geometry_catalog_identity()

    if path.is_file():
        try:
            geometry_existing = json.loads(path.read_text(encoding="utf-8"))
            valid_existing = isinstance(geometry_existing, dict) and bool(geometry_existing.get("type"))
            if valid_existing:
                if catalog_identity is None:
                    # The persisted exact snapshot remains useful after a restart
                    # even before the catalog is loaded again.
                    return True
                meta_existing = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
                if meta_existing.get("catalog_identity") == catalog_identity:
                    return True
        except Exception:
            pass

    geometry = _geometry_payload_from_local_catalog(rid)
    if not geometry:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(geometry, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)
    meta_temp = meta_path.with_suffix(meta_path.suffix + ".tmp")
    meta_temp.write_text(json.dumps({
        "region_id": rid,
        "catalog_identity": catalog_identity,
        "snapshotted_at": utc_now(),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(meta_temp, meta_path)
    with _REGION_GEOMETRY_CACHE_LOCK:
        _REGION_GEOMETRY_CACHE.clear()
    return True


def _region_geometry(region_id: str):
    rid = _safe_region_id(region_id)
    snapshot = _boundary_snapshot_path(rid)
    geometry = None
    stamp = (0, 0)
    if snapshot.is_file():
        try:
            st = snapshot.stat(); stamp = (int(st.st_mtime_ns), int(st.st_size))
            geometry = json.loads(snapshot.read_text(encoding="utf-8"))
        except Exception:
            geometry = None
    if geometry is None:
        cache = _catalog_cache_path(True)
        try:
            st = cache.stat(); stamp = (int(st.st_mtime_ns), int(st.st_size))
        except OSError:
            stamp = (0, 0)
        geometry = _geometry_payload_from_local_catalog(rid)
    if not geometry:
        return None
    key = (rid, stamp[0], stamp[1])
    with _REGION_GEOMETRY_CACHE_LOCK:
        cached = _REGION_GEOMETRY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        geom = shape(geometry)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty:
            return None
    except Exception:
        return None
    with _REGION_GEOMETRY_CACHE_LOCK:
        _REGION_GEOMETRY_CACHE.clear()
        _REGION_GEOMETRY_CACHE[key] = geom
    return geom


def region_points_coverage(region_id: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    """Return geometric coverage for real depot/customer points.

    ``known=False`` is intentionally distinct from ``covers_all=False``. The
    caller decides whether unknown geometry is acceptable; plan-critical routing
    gates fail closed until positive boundary evidence is available.
    """
    rid = _safe_region_id(region_id)
    valid_points: list[dict[str, Any]] = []
    for item in points or []:
        try:
            lat = float(item.get("lat")); lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            valid_points.append({**item, "lat": lat, "lon": lon})
    if not valid_points:
        return {"known": True, "covers_all": True, "outside_count": 0, "outside": [], "point_count": 0, "region_id": rid}
    geometry = _region_geometry(rid)
    if geometry is None:
        return {"known": False, "covers_all": None, "outside_count": None, "outside": [], "point_count": len(valid_points), "region_id": rid}
    outside: list[dict[str, Any]] = []
    try:
        if callable(shapely_points) and callable(shapely_covers):
            # Shapely 2 vectorizes the exact same boundary-inclusive ``covers``
            # predicate. One native geometry call replaces hundreds of Python
            # Point allocations on every 300–450 stop state refresh.
            point_array = shapely_points(
                [float(item["lon"]) for item in valid_points],
                [float(item["lat"]) for item in valid_points],
            )
            covered_flags = shapely_covers(geometry, point_array)
        else:
            covered_flags = [geometry.covers(Point(float(item["lon"]), float(item["lat"]))) for item in valid_points]
    except Exception:
        # Coverage is a safety gate: if vectorization is unavailable/broken,
        # fall back to the scalar geometry predicate rather than guessing.
        covered_flags = []
        for item in valid_points:
            try:
                covered_flags.append(geometry.covers(Point(float(item["lon"]), float(item["lat"]))))
            except Exception:
                covered_flags.append(False)
    for item, covered in zip(valid_points, covered_flags):
        if not bool(covered):
            outside.append({
                "id": item.get("id"), "role": item.get("role"), "name": item.get("name") or item.get("external_id"),
                "lat": item["lat"], "lon": item["lon"],
            })
    return {
        "known": True, "covers_all": not outside, "outside_count": len(outside),
        "outside": outside[:20], "point_count": len(valid_points), "region_id": rid,
    }



def recommend_region_for_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Recommend a catalog/download region that geometrically covers ``points``.

    This is a *browser-assistance* helper, not an activation decision. It never
    changes the browsed region, active source, graph, or route state. The caller
    may use the returned region as a preselected download target after showing it
    to the operator.

    Preference order is intentionally conservative:
      1. identify the smallest country-level catalog feature covering all points;
      2. use that country itself when it has a trusted PBF download;
      3. otherwise use the smallest downloadable descendant that also covers all
         points (for catalogs where a country is split into subregions).

    If the local/live geometry catalog cannot prove containment, return
    ``found=False`` rather than guessing from names or bounding boxes.
    """
    valid: list[dict[str, Any]] = []
    for item in points or []:
        try:
            lat = float(item.get("lat")); lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            valid.append({**item, "lat": lat, "lon": lon})
    if not valid:
        return {"found": False, "reason": "No valid coordinates supplied", "point_count": 0}

    try:
        catalog = geofabrik_catalog(include_geometry=True, force=False)
    except Exception as exc:
        return {
            "found": False,
            "reason": f"Region boundary catalog is unavailable: {type(exc).__name__}: {exc}",
            "point_count": len(valid),
        }

    features = list(catalog.get("features") or [])
    by_id = {
        str((feature.get("properties") or {}).get("id") or "").lower(): feature
        for feature in features
        if (feature.get("properties") or {}).get("id")
    }
    try:
        point_geoms = [Point(float(item["lon"]), float(item["lat"])) for item in valid]
    except Exception:
        return {"found": False, "reason": "Invalid coordinate geometry", "point_count": len(valid)}

    containing: list[tuple[float, dict[str, Any]]] = []
    for feature in features:
        geometry_payload = feature.get("geometry")
        props = feature.get("properties") or {}
        if not geometry_payload or not props.get("id"):
            continue
        try:
            geom = shape(geometry_payload)
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty or not all(geom.covers(point) for point in point_geoms):
                continue
            area = float(geom.area)
        except Exception:
            continue
        containing.append((area, feature))

    if not containing:
        return {
            "found": False,
            "reason": "No catalog boundary was found that contains the supplied coordinates",
            "point_count": len(valid),
        }
    containing.sort(key=lambda item: item[0])

    country_features = [
        (area, feature) for area, feature in containing
        if _iso2_list((feature.get("properties") or {}).get("iso2") or (feature.get("properties") or {}).get("iso3166-1:alpha2"))
    ]
    country_feature = country_features[0][1] if country_features else None
    country_id = str(((country_feature or {}).get("properties") or {}).get("id") or "").lower()

    def is_downloadable(feature: dict[str, Any]) -> bool:
        props = feature.get("properties") or {}
        raw = props.get("pbf_url") or (props.get("urls") or {}).get("pbf")
        if not raw:
            return False
        try:
            return bool(_trusted_geofabrik_pbf_url(raw))
        except Exception:
            return False

    def descends_from(feature: dict[str, Any], ancestor_id: str) -> bool:
        if not ancestor_id:
            return True
        props = feature.get("properties") or {}
        current = str(props.get("id") or "").lower()
        seen: set[str] = set()
        while current and current not in seen:
            if current == ancestor_id:
                return True
            seen.add(current)
            parent = str(((by_id.get(current) or {}).get("properties") or {}).get("parent") or "").lower()
            current = parent
        return False

    suggested_feature = None
    if country_feature is not None and is_downloadable(country_feature):
        suggested_feature = country_feature
    else:
        downloadables = [
            (area, feature) for area, feature in containing
            if is_downloadable(feature) and descends_from(feature, country_id)
        ]
        if not downloadables:
            downloadables = [(area, feature) for area, feature in containing if is_downloadable(feature)]
        if downloadables:
            suggested_feature = min(downloadables, key=lambda item: item[0])[1]

    def public_region(feature: dict[str, Any] | None) -> dict[str, Any] | None:
        if feature is None:
            return None
        props = feature.get("properties") or {}
        raw = props.get("pbf_url") or (props.get("urls") or {}).get("pbf")
        trusted = None
        if raw:
            try:
                trusted = _trusted_geofabrik_pbf_url(raw)
            except Exception:
                trusted = None
        return {
            "id": str(props.get("id") or ""),
            "name": str(props.get("name") or props.get("id") or "Region"),
            "parent": props.get("parent"),
            "iso2": _iso2_list(props.get("iso2") or props.get("iso3166-1:alpha2")),
            "downloadable": bool(trusted),
            "pbf_url": trusted,
        }

    country = public_region(country_feature)
    suggested = public_region(suggested_feature)
    return {
        "found": bool(suggested or country),
        "point_count": len(valid),
        "country": country,
        "recommended_region": suggested,
        "requires_subregion": bool(country and suggested and country.get("id") != suggested.get("id")),
        "reason": None if (suggested or country) else "The containing catalog region has no trusted downloadable road extract",
    }

def _region_storage_key(region_id: str) -> str:
    return _safe_region_id(region_id).replace("/", "__")


def _region_source_dir(region_id: str) -> Path:
    path = _data_dir() / "sources" / _region_storage_key(region_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def region_pbf_path(region: dict[str, Any] | None = None) -> Path:
    selected = region or selected_osm_region()
    if not selected:
        return _data_dir() / "sources" / "unselected.osm.pbf"
    basename = Path(urlparse(selected["pbf_url"]).path).name
    return _region_source_dir(selected["id"]) / basename


def region_md5_path(region: dict[str, Any] | None = None) -> Path:
    return region_pbf_path(region).with_suffix(region_pbf_path(region).suffix + ".md5")


def _all_source_receipts() -> dict[str, Any]:
    receipts = get_setting("osm_source_receipts") or {}
    if isinstance(receipts, dict):
        return receipts
    return {}


def _source_receipt(region_id: str) -> dict[str, Any]:
    return dict(_all_source_receipts().get(_safe_region_id(region_id)) or {})


def _save_source_receipt(region_id: str, receipt: dict[str, Any]) -> None:
    receipts = _all_source_receipts()
    receipts[_safe_region_id(region_id)] = dict(receipt)
    set_setting("osm_source_receipts", receipts)


def _verified_local_source(region: dict[str, Any], receipt: dict[str, Any]) -> tuple[bool, str | None]:
    pbf = region_pbf_path(region)
    if not pbf.exists() or pbf.stat().st_size < MIN_PBF_BYTES:
        return False, "source file missing"
    expected_size = int(receipt.get("size_bytes") or 0)
    verified_md5 = str(receipt.get("verified_md5") or "").strip().lower()
    if not verified_md5:
        return False, "checksum not verified"
    stat = pbf.stat()
    if expected_size and stat.st_size != expected_size:
        return False, "source file changed after verification"
    expected_mtime_ns = int(receipt.get("mtime_ns") or 0)
    if expected_mtime_ns and stat.st_mtime_ns != expected_mtime_ns:
        return False, "source file changed after verification"
    return True, None


def _region_status(region: dict[str, Any] | None, check_remote: bool = False) -> dict[str, Any]:
    if not region:
        return {
            "ready": False, "selected": False, "region": None,
            "size_bytes": 0, "size_human": "—", "path": None,
            "data_dir": str(_data_dir()), "osmium_available": shutil.which("osmium") is not None,
        }
    pbf = region_pbf_path(region)
    receipt = _source_receipt(region["id"])
    ready, reason = _verified_local_source(region, receipt)
    status = {
        "ready": ready,
        "selected": True,
        "region": region,
        "region_id": region["id"],
        "region_name": region["name"],
        "path": str(pbf),
        "size_bytes": pbf.stat().st_size if pbf.exists() else 0,
        "size_human": _human_bytes(pbf.stat().st_size if pbf.exists() else 0),
        "download_url": region["pbf_url"],
        "downloaded_at": receipt.get("downloaded_at"),
        "verified_md5": receipt.get("verified_md5"),
        "source_timestamp": receipt.get("source_timestamp"),
        "remote_size_bytes": receipt.get("remote_size_bytes"),
        "remote_last_modified": receipt.get("remote_last_modified"),
        "data_dir": str(_data_dir()),
        "osmium_available": shutil.which("osmium") is not None,
        "verification_warning": reason if not ready and pbf.exists() else None,
    }
    if check_remote:
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0, read=8.0, write=5.0, pool=5.0), follow_redirects=True) as client:
                response = client.head(region["pbf_url"])
                response.raise_for_status()
                _verify_geofabrik_response(response, expected="pbf", requested_url=region["pbf_url"])
            status["remote_size_bytes"] = int(response.headers.get("content-length") or 0)
            status["remote_last_modified"] = response.headers.get("last-modified")
            receipt.update({
                "remote_size_bytes": status["remote_size_bytes"],
                "remote_last_modified": status["remote_last_modified"],
            })
            _save_source_receipt(region["id"], receipt)
        except Exception as exc:
            status["remote_check_warning"] = str(exc)
    return status


def region_source_status(check_remote: bool = False) -> dict[str, Any]:
    """Status of the active road source used by graph/solver operations."""
    return _region_status(selected_osm_region(), check_remote)


def region_target_status(region: dict[str, Any] | None = None, check_remote: bool = False) -> dict[str, Any]:
    """Status of the browsed/download target. This never changes active routing state."""
    target = region or browsed_osm_region()
    status = _region_status(target, check_remote)
    active = selected_osm_region()
    status["active"] = bool(active and target and active.get("id") == target.get("id"))
    status["active_region_id"] = active.get("id") if active else None
    return status


def osm_source_library() -> list[dict[str, Any]]:
    receipts = _all_source_receipts()
    active = selected_osm_region()
    browsed = browsed_osm_region()
    entries = []
    for rid, receipt in receipts.items():
        try:
            safe_id = _safe_region_id(rid)
            region = {
                "id": safe_id,
                "name": str(receipt.get("region_name") or safe_id),
                "parent": receipt.get("parent"),
                "iso2": _iso2_list(receipt.get("iso2")),
                "pbf_url": _trusted_geofabrik_pbf_url(receipt.get("pbf_url")),
            }
            pbf = region_pbf_path(region)
            ready, reason = _verified_local_source(region, receipt)
            entries.append({
                "id": safe_id, "name": region["name"], "parent": region.get("parent"),
                "iso2": region.get("iso2"), "ready": ready, "warning": reason,
                "selected": bool(active and active.get("id") == safe_id),
                "active": bool(active and active.get("id") == safe_id),
                "browsed": bool(browsed and browsed.get("id") == safe_id),
                "path": str(pbf), "size_bytes": pbf.stat().st_size if pbf.exists() else 0,
                "size_human": _human_bytes(pbf.stat().st_size if pbf.exists() else 0),
                "verified_md5": receipt.get("verified_md5"), "downloaded_at": receipt.get("downloaded_at"),
                "source_timestamp": receipt.get("source_timestamp"),
            })
        except Exception:
            continue
    entries.sort(key=lambda x: (not x["ready"], not x["active"], x["name"].lower()))
    return entries

def download_selected_region_pbf(
    progress: Callable[[dict[str, Any]], None] | None = None,
    force: bool = False,
    *,
    region_id: str | None = None,
    _checksum_retries: int = 1,
) -> dict[str, Any]:
    # Freeze the download target. Browsing another country while this job is
    # running must never redirect an in-flight large transfer.
    region = _region_record(region_id) if region_id else browsed_osm_region()
    if not region:
        raise ValueError("Choose a region on the map before downloading road data")

    canonical_pbf_url = _trusted_geofabrik_pbf_url(region["pbf_url"])
    pbf = region_pbf_path(region)
    md5_file = region_md5_path(region)
    current = _region_status(region, False)
    if current.get("ready") and not force:
        return region_target_status(region)

    pbf.parent.mkdir(parents=True, exist_ok=True)
    part = pbf.with_suffix(pbf.suffix + ".part")
    part_identity_path = _part_identity_path(part)
    if force:
        part.unlink(missing_ok=True)
        part_identity_path.unlink(missing_ok=True)

    if progress:
        progress({"phase": "metadata", "message": f"Resolving {region['name']} immutable road-data version"})

    headers = {
        "User-Agent": "FleetRoute-Routing-Workspace/1.0 region-source",
        "Accept-Encoding": "identity",
    }

    # Geofabrik changed *-latest downloads on 2025-09-01 to HTTP redirects.
    # Resolve that redirect first and then pin all transfer/resume work to the
    # immutable dated object. This both fixes the post-2025 redirect contract and
    # prevents a midnight/latest rollover from corrupting resumed large downloads.
    resolved_pbf_url, remote_size, remote_last_modified = _resolve_remote_pbf(
        canonical_pbf_url, canonical_pbf_url, headers
    )
    resolved_pbf_url = _trusted_geofabrik_aux_url(
        resolved_pbf_url, expected="pbf", requested_url=canonical_pbf_url
    )

    # Resolve a tiny checksum sidecar on the interactive path.  The old v7
    # implementation allowed four sequential 90 s reads here, so a transient
    # metadata/CDN problem could make a 25 s PBF download look frozen for minutes.
    # Keep correctness (trusted host + exact MD5 + snapshot pinning) but fail fast.
    canonical_md5_url = canonical_pbf_url + ".md5"
    dated_md5_url = resolved_pbf_url + ".md5"
    checksum_candidates: list[str] = []
    for candidate in (dated_md5_url, canonical_md5_url, canonical_md5_url):
        if candidate not in checksum_candidates or candidate == canonical_md5_url and checksum_candidates.count(candidate) < 2:
            checksum_candidates.append(candidate)

    expected_md5: str | None = None
    md5_text: str | None = None
    resolved_md5_url: str | None = None
    last_error: Exception | None = None

    for attempt, md5_request_url in enumerate(checksum_candidates, start=1):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(12.0, connect=6.0, read=10.0, write=8.0, pool=6.0),
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = client.get(md5_request_url)
                response.raise_for_status()
                resolved_md5_url = _verify_geofabrik_response(
                    response, expected="md5", requested_url=canonical_md5_url
                )
                # A checksum sidecar should be tiny.  Reject anomalous responses
                # before decoding rather than buffering arbitrary metadata.
                if len(response.content) > 64 * 1024:
                    raise RuntimeError("Geofabrik checksum metadata was unexpectedly large")
                expected_md5 = _parse_md5_text(response.text)
                md5_text = response.text

            # The checksum is snapshot authority.  A dated checksum pins the PBF
            # to the same immutable date, preventing latest-rollover mixing.
            md5_version = _source_version_from_url(resolved_md5_url)
            head_version = _source_version_from_url(resolved_pbf_url)
            if md5_version:
                pinned_pbf_url = _trusted_geofabrik_aux_url(
                    resolved_md5_url[:-4],
                    expected="pbf",
                    requested_url=canonical_pbf_url,
                )
                resolved_pbf_url = pinned_pbf_url
                if remote_size is None or head_version != md5_version:
                    probed_url, probed_size, probed_last_modified = _resolve_remote_pbf(
                        pinned_pbf_url, canonical_pbf_url, headers
                    )
                    if _source_version_from_url(probed_url) not in {None, md5_version}:
                        raise RuntimeError("Geofabrik changed snapshot version while resolving the dated PBF")
                    remote_size = probed_size or remote_size
                    remote_last_modified = probed_last_modified or remote_last_modified
            break
        except Exception as exc:
            if exc.__class__.__name__ == "JobCancelled":
                raise
            last_error = exc
            expected_md5 = None
            md5_text = None
            resolved_md5_url = None
            if progress:
                progress({
                    "phase": "metadata",
                    "message": (
                        f"Checksum metadata retry {attempt}/{len(checksum_candidates)}"
                        if attempt < len(checksum_candidates)
                        else "Checksum metadata lookup failed; preserving the previous verified source"
                    ),
                })
            if attempt < len(checksum_candidates):
                time.sleep(0.75)

    if not expected_md5 or md5_text is None or not resolved_md5_url:
        raise RuntimeError(
            f"Could not read Geofabrik checksum metadata quickly; retry the source download: {last_error}"
        )

    # A canonical latest checksum can still be returned without an HTTP redirect
    # by an intermediary. Resolve its PBF target once more so the actual transfer
    # is immutable whenever Geofabrik exposes the dated target.
    if not _source_version_from_url(resolved_pbf_url):
        resolved_pbf_url, probed_size, probed_last_modified = _resolve_remote_pbf(
            canonical_pbf_url, canonical_pbf_url, headers
        )
        remote_size = probed_size or remote_size
        remote_last_modified = probed_last_modified or remote_last_modified

    pbf_version = _source_version_from_url(resolved_pbf_url)
    md5_version = _source_version_from_url(resolved_md5_url)
    if pbf_version and md5_version and pbf_version != md5_version:
        raise RuntimeError(
            f"Regional source version mismatch: PBF {pbf_version} does not match checksum {md5_version}"
        )
    source_version = pbf_version or md5_version
    transfer_identity = {
        "canonical_pbf_url": canonical_pbf_url,
        "resolved_pbf_url": resolved_pbf_url,
        "resolved_md5_url": resolved_md5_url,
        "source_version": source_version,
        "expected_md5": expected_md5.lower(),
    }

    # Never resume bytes from yesterday's object into today's redirected latest.
    existing_identity = _read_part_identity(part)
    verified_staged_md5: str | None = None
    if part.exists():
        identity_matches = bool(existing_identity) and all(
            str(existing_identity.get(key) or "") == str(transfer_identity.get(key) or "")
            for key in ("resolved_pbf_url", "expected_md5")
        )
        if not identity_matches:
            # A complete legacy .part can still be recovered if it already equals
            # the exact current checksum; otherwise unknown partial bytes are unsafe.
            recovered = False
            staged_size = int(part.stat().st_size)
            could_be_complete = staged_size >= MIN_PBF_BYTES and (remote_size is None or staged_size >= int(remote_size))
            if could_be_complete:
                try:
                    verified_staged_md5 = _file_md5(part).lower()
                    recovered = verified_staged_md5 == expected_md5.lower()
                except Exception:
                    recovered = False
                    verified_staged_md5 = None
            if not recovered:
                part.unlink(missing_ok=True)
                part_identity_path.unlink(missing_ok=True)
                verified_staged_md5 = None

    # A fully-downloaded .part can be left behind if the prior runtime died after
    # transfer but before publication. Verify it once before touching the network.
    staged_size = int(part.stat().st_size) if part.exists() else 0
    could_be_complete = staged_size >= MIN_PBF_BYTES and (remote_size is None or staged_size >= int(remote_size))
    if part.exists() and could_be_complete:
        try:
            staged_md5 = verified_staged_md5 or _file_md5(part).lower()
            if staged_md5 == expected_md5.lower():
                os.replace(part, pbf)
                part_identity_path.unlink(missing_ok=True)
                md5_temp = md5_file.with_suffix(md5_file.suffix + ".tmp")
                md5_temp.write_text(md5_text, encoding="utf-8")
                os.replace(md5_temp, md5_file)
                receipt = {
                    "region_id": region["id"],
                    "region_name": region["name"],
                    "parent": region.get("parent"),
                    "iso2": region.get("iso2"),
                    "pbf_url": canonical_pbf_url,
                    "resolved_pbf_url": resolved_pbf_url,
                    "resolved_md5_url": resolved_md5_url,
                    "source_version": source_version,
                    "verified_md5": staged_md5,
                    "size_bytes": pbf.stat().st_size,
                    "remote_size_bytes": remote_size or pbf.stat().st_size,
                    "mtime_ns": pbf.stat().st_mtime_ns,
                    "downloaded_at": utc_now(),
                    "remote_last_modified": remote_last_modified,
                    "source_timestamp": source_version or remote_last_modified,
                }
                _save_source_receipt(region["id"], receipt)
                snapshot_region_geometry(region["id"])
                if progress:
                    progress({
                        "phase": "complete",
                        "message": f"{region['name']} road source recovered and verified",
                        "done": pbf.stat().st_size,
                        "total": pbf.stat().st_size,
                    })
                return region_target_status(region)
        except Exception:
            pass

    _write_part_identity(part, transfer_identity)
    resume_bytes = part.stat().st_size if part.exists() else 0
    _check_download_disk_space(pbf, remote_size, resume_bytes)

    transfer_error: Exception | None = None
    streamed_md5: str | None = None
    transfer_attempts = 3
    for attempt in range(1, transfer_attempts + 1):
        try:
            resume_from = part.stat().st_size if part.exists() else 0
            digest = (
                _md5_digest_for_prefix(
                    part,
                    progress=progress,
                    message=f"Checking retained {region['name']} bytes before resume",
                )
                if resume_from else hashlib.md5()
            )
            request_headers = {"Accept-Encoding": "identity"}
            if resume_from:
                request_headers["Range"] = f"bytes={resume_from}-"
            with httpx.Client(
                timeout=httpx.Timeout(60.0, connect=10.0, read=45.0, write=15.0, pool=10.0),
                follow_redirects=True,
                headers=headers,
            ) as client:
                with client.stream("GET", resolved_pbf_url, headers=request_headers) as response:
                    if response.status_code == 416 and resume_from:
                        staged_md5 = digest.hexdigest().lower()
                        if staged_md5 == expected_md5.lower():
                            streamed_md5 = staged_md5
                            transfer_error = None
                            break
                        part.unlink(missing_ok=True)
                        _write_part_identity(part, transfer_identity)
                        raise RuntimeError("Server rejected the resume range and the staged file was not complete")

                    response.raise_for_status()
                    final_transfer_url = _verify_geofabrik_response(
                        response,
                        expected="pbf",
                        requested_url=canonical_pbf_url,
                    )
                    final_version = _source_version_from_url(final_transfer_url)
                    if source_version and final_version != source_version:
                        raise RuntimeError(
                            "Geofabrik returned a different dated snapshot than the verified checksum"
                        )
                    resumed = bool(resume_from and response.status_code == 206)
                    if resumed:
                        content_range = str(response.headers.get("content-range") or "")
                        if not content_range.startswith(f"bytes {resume_from}-"):
                            raise RuntimeError("Geofabrik returned an inconsistent Content-Range for the resumed download")
                    else:
                        # A server/proxy that ignores Range restarts both local bytes
                        # and the streaming checksum state instead of appending twice.
                        resume_from = 0
                        digest = hashlib.md5()

                    content_length = int(response.headers.get("content-length") or 0)
                    total = resume_from + content_length if content_length else (remote_size or 0)
                    mode = "ab" if resumed else "wb"
                    downloaded = resume_from
                    started = time.monotonic()
                    with part.open(mode) as handle:
                        for chunk in response.iter_bytes(1 * 1024 * 1024):
                            if not chunk:
                                continue
                            handle.write(chunk)
                            digest.update(chunk)
                            downloaded += len(chunk)
                            if progress:
                                elapsed = max(.001, time.monotonic() - started)
                                rate = max(1.0, (downloaded - resume_from) / elapsed)
                                progress({
                                    "phase": "download",
                                    "message": f"Downloading + verifying {region['name']} road data · attempt {attempt}/{transfer_attempts}",
                                    "done": downloaded,
                                    "total": total,
                                    "elapsed_s": elapsed,
                                    "rate_bps": rate,
                                    "eta_s": ((total - downloaded) / rate) if total and downloaded < total else None,
                                })
                    if part.stat().st_size < MIN_PBF_BYTES:
                        raise RuntimeError("Downloaded PBF is unexpectedly small")
                    streamed_md5 = digest.hexdigest().lower()
                    remote_last_modified = response.headers.get("last-modified") or remote_last_modified
            transfer_error = None
            break
        except Exception as exc:
            if exc.__class__.__name__ == "JobCancelled":
                raise
            transfer_error = exc
            streamed_md5 = None
            if progress:
                progress({
                    "phase": "download",
                    "message": f"Road-data transfer attempt {attempt}/{transfer_attempts} failed; retaining only same-version partial bytes",
                })
            if attempt < transfer_attempts:
                time.sleep(1.25 * attempt)

    if transfer_error is not None:
        raise RuntimeError(f"Regional PBF download failed after {transfer_attempts} attempts: {transfer_error}")
    if not part.exists() or part.stat().st_size < MIN_PBF_BYTES:
        raise RuntimeError("Regional PBF download did not produce a usable staged file")

    # On the normal fresh path the authoritative MD5 was accumulated while the
    # bytes were written. Verification is therefore immediate here instead of a
    # second full read of a country-scale PBF. Recovery paths still fail closed.
    actual_md5 = (streamed_md5 or _file_md5(part, progress)).lower()
    if progress:
        progress({
            "phase": "verify",
            "message": f"{region['name']} checksum verified",
            "done": part.stat().st_size,
            "total": part.stat().st_size,
            "elapsed_s": 0.0,
            "eta_s": 0.0,
        })
    if actual_md5 != expected_md5.lower():
        part.unlink(missing_ok=True)
        part_identity_path.unlink(missing_ok=True)
        if _checksum_retries > 0:
            if progress:
                progress({
                    "phase": "verify",
                    "message": "Checksum mismatch detected; resolving a fresh immutable regional snapshot",
                    "done": 0,
                    "total": 0,
                })
            return download_selected_region_pbf(
                progress,
                force=True,
                region_id=region["id"],
                _checksum_retries=_checksum_retries - 1,
            )
        raise RuntimeError("Downloaded PBF checksum did not match Geofabrik metadata after a clean retry")

    os.replace(part, pbf)
    part_identity_path.unlink(missing_ok=True)
    md5_temp = md5_file.with_suffix(md5_file.suffix + ".tmp")
    md5_temp.write_text(md5_text, encoding="utf-8")
    os.replace(md5_temp, md5_file)
    receipt = {
        "region_id": region["id"],
        "region_name": region["name"],
        "parent": region.get("parent"),
        "iso2": region.get("iso2"),
        "pbf_url": canonical_pbf_url,
        "resolved_pbf_url": resolved_pbf_url,
        "resolved_md5_url": resolved_md5_url,
        "source_version": source_version,
        "verified_md5": actual_md5,
        "size_bytes": pbf.stat().st_size,
        "remote_size_bytes": remote_size or pbf.stat().st_size,
        "mtime_ns": pbf.stat().st_mtime_ns,
        "downloaded_at": utc_now(),
        "remote_last_modified": remote_last_modified,
        "source_timestamp": source_version or remote_last_modified,
    }
    _save_source_receipt(region["id"], receipt)
    snapshot_region_geometry(region["id"])
    if progress:
        progress({
            "phase": "complete",
            "message": f"{region['name']} road source is ready",
            "done": pbf.stat().st_size,
            "total": pbf.stat().st_size,
        })
    return region_target_status(region)


def remove_selected_region_pbf() -> dict[str, Any]:
    region = selected_osm_region()
    if not region:
        return region_source_status(False)
    pbf = region_pbf_path(region)
    md5 = region_md5_path(region)
    part = pbf.with_suffix(pbf.suffix + ".part")
    for path in (pbf, md5, part, _part_identity_path(part)):
        path.unlink(missing_ok=True)

    # The runtime staging file may be a hard link to the verified source. Remove
    # that orphan too so deleting a source really releases its disk allocation.
    local_dir = RUNTIME_DIR / "osm-local" / _region_storage_key(region["id"])
    local = local_dir / pbf.name
    for path in (
        local,
        local.with_suffix(local.suffix + ".source.json"),
        local.with_suffix(local.suffix + ".part"),
    ):
        path.unlink(missing_ok=True)
    try:
        local_dir.rmdir()
    except OSError:
        pass

    receipts = _all_source_receipts()
    receipts.pop(region["id"], None)
    set_setting("osm_source_receipts", receipts)
    set_setting("osm_selected_region", None)
    return region_source_status(False)


def local_selected_region_pbf(progress: Callable[[dict[str, Any]], None] | None = None) -> Path:
    region = selected_osm_region()
    status = region_source_status(False)
    if not region or not status.get("ready"):
        raise ValueError("Download and verify the selected regional road source first")
    source = region_pbf_path(region)
    local_dir = RUNTIME_DIR / "osm-local" / _region_storage_key(region["id"])
    local_dir.mkdir(parents=True, exist_ok=True)
    local = local_dir / source.name
    receipt = _source_receipt(region["id"])
    source_identity = {
        "region_id": region["id"], "size_bytes": int(source.stat().st_size),
        "verified_md5": str(receipt.get("verified_md5") or ""),
        "source_timestamp": str(receipt.get("source_timestamp") or ""),
    }
    identity_path = local.with_suffix(local.suffix + ".source.json")
    if local.exists() and local.stat().st_size == source.stat().st_size and identity_path.exists():
        try:
            if json.loads(identity_path.read_text(encoding="utf-8")) == source_identity:
                return local
        except Exception:
            pass
    total_size = int(source.stat().st_size)
    if progress:
        progress({"phase": "stage_source", "message": f"Staging {region['name']} road source on the local SSD", "done": 0, "total": total_size})
    temp = local.with_suffix(local.suffix + ".part")
    temp.unlink(missing_ok=True)
    # Standard Colab paths are both under /content. Hard-link the immutable,
    # checksum-verified source instead of copying a country-scale PBF again.
    # Cross-device or unsupported filesystems keep the measured copy fallback.
    try:
        os.link(source, temp)
        copied = total_size
        if progress:
            progress({"phase": "stage_source", "message": f"Linked verified {region['name']} road source into the runtime", "done": copied, "total": total_size})
    except OSError:
        copied = 0
        with source.open("rb") as src, temp.open("wb") as dst:
            while True:
                chunk = src.read(16 * 1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk); copied += len(chunk)
                if progress:
                    progress({"phase": "stage_source", "message": f"Staging {region['name']} road source", "done": copied, "total": total_size})
        if copied != total_size:
            temp.unlink(missing_ok=True)
            raise RuntimeError("Regional PBF staging was incomplete")
    temp.replace(local)
    identity_path.write_text(json.dumps(source_identity, sort_keys=True), encoding="utf-8")
    return local




