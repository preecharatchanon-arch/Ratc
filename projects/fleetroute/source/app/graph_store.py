from __future__ import annotations

import heapq
import math
import pickle
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.ops import transform as shapely_transform
from shapely.strtree import STRtree

from .config import settings


# Lightweight WGS84 grid used for ordinary nearest-edge queries. A fixed
# 0.001-degree cell is roughly 110 m north/south and remains conservative
# because exact metric distance is still computed on every candidate edge.
# This avoids scanning every edge bound for each imported/customer point.
_EDGE_GRID_DEG = 0.001
_EDGE_GRID_MAX_CELLS_PER_EDGE = 256
_EDGE_GRID_MAX_QUERY_CELLS = 40_000


def osm_bool(value: Any) -> bool:
    """Interpret OSM/GraphML boolean-like values without Python string truthiness."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, (list, tuple, set)):
        return any(osm_bool(item) for item in value)
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "t", "-1", "reversible", "alternating"}:
        return True
    if text in {"", "0", "false", "no", "n", "f", "none", "null"}:
        return False
    return False


@dataclass(slots=True)
class EdgeRecord:
    u: Any
    v: Any
    key: Any
    geometry_wgs84: list[list[float]]
    geometry_projected: LineString
    data: dict[str, Any]


class GraphStore:
    """Thread-safe in-memory road graph and spatial indexes.

    GraphML is retained only as an optional evidence/export format. Interactive
    requests load the trusted local pickle once and then reuse the same graph,
    nearest-node index, nearest-edge index, and edge lookup maps.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._graph: nx.MultiDiGraph | None = None
        self._signature: tuple[str, int, int] | None = None
        self._edge_records: list[EdgeRecord] = []
        self._edge_light_records: list[tuple[Any, Any, Any, dict[str, Any]]] = []
        self._edge_bounds_wgs84: np.ndarray | None = None
        self._edge_grid: dict[tuple[int, int], list[int]] = {}
        self._edge_grid_global: list[int] = []
        self._edge_projection_cache: OrderedDict[int, EdgeRecord] = OrderedDict()
        self._edge_tree: STRtree | None = None
        self._node_tree: cKDTree | None = None
        self._node_ids: list[Any] = []
        self._node_xy: np.ndarray | None = None
        self._to_projected: Transformer | None = None
        self._to_wgs84: Transformer | None = None
        self._edge_exact: dict[tuple[str, str, str], tuple[Any, Any, Any]] = {}
        self._edge_pairs: dict[tuple[str, str], list[tuple[Any, Any, Any]]] = {}
        self._node_by_text: dict[str, Any] = {}
        self._node_access_record: dict[Any, tuple[Any, Any, Any, dict[str, Any]]] = {}
        self._edge_spatial_ready = False
        self._geojson_cache: dict[tuple[int, str], dict[str, Any]] = {}
        self._viewport_cache: OrderedDict[tuple[float, float, float, float, int], dict[str, Any]] = OrderedDict()
        self._metadata: dict[str, Any] = {}

    @staticmethod
    def _source_signature(path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))

    @staticmethod
    def _edge_geometry(graph: nx.MultiDiGraph, u: Any, v: Any, data: dict[str, Any]) -> list[list[float]]:
        geom = data.get("geometry")
        if geom is not None and hasattr(geom, "coords"):
            return [[float(y), float(x)] for x, y in geom.coords]
        return [
            [float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])],
            [float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])],
        ]

    def invalidate(self) -> None:
        with self._lock:
            self._graph = None
            self._signature = None
            self._edge_records = []
            self._edge_light_records = []
            self._edge_bounds_wgs84 = None
            self._edge_grid = {}
            self._edge_grid_global = []
            self._edge_projection_cache = OrderedDict()
            self._edge_tree = None
            self._node_tree = None
            self._node_ids = []
            self._node_xy = None
            self._to_projected = None
            self._to_wgs84 = None
            self._edge_exact = {}
            self._edge_pairs = {}
            self._node_by_text = {}
            self._node_access_record = {}
            self._edge_spatial_ready = False
            self._geojson_cache = {}
            self._viewport_cache = OrderedDict()
            self._metadata = {}

    def available(self) -> bool:
        return self._graph is not None or settings.network_pickle.exists() or settings.network_graphml.exists()

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._metadata)

    def update_metadata(self, metadata: dict[str, Any] | None) -> None:
        """Replace descriptive metadata without rebuilding graph indexes.

        This is used when a prepared graph cache is reopened. The graph and its
        indexes are already current; only session-level evidence such as
        ``cache_hit`` or the active cache path changed.
        """
        with self._lock:
            self._metadata = dict(metadata or {})

    def set_graph(self, graph: nx.MultiDiGraph, metadata: dict[str, Any] | None = None, persist: bool = True) -> None:
        with self._lock:
            self._graph = graph
            self._metadata = dict(metadata or {})
            self._build_indexes_locked()
            if persist:
                settings.network_pickle.parent.mkdir(parents=True, exist_ok=True)
                tmp = settings.network_pickle.with_suffix(settings.network_pickle.suffix + ".tmp")
                with tmp.open("wb") as handle:
                    pickle.dump({"graph": graph, "metadata": self._metadata}, handle, protocol=pickle.HIGHEST_PROTOCOL)
                tmp.replace(settings.network_pickle)
                self._signature = self._source_signature(settings.network_pickle)

    def _load_locked(self) -> nx.MultiDiGraph:
        # Prefer the fast trusted local pickle. Fall back to GraphML for backwards compatibility.
        if settings.network_pickle.exists():
            signature = self._source_signature(settings.network_pickle)
            if self._graph is not None and self._signature == signature:
                return self._graph
            with settings.network_pickle.open("rb") as handle:
                payload = pickle.load(handle)
            if isinstance(payload, dict) and "graph" in payload:
                graph = payload["graph"]
                self._metadata = dict(payload.get("metadata") or {})
            else:
                graph = payload
                self._metadata = {}
            self._graph = graph
            self._signature = signature
            self._build_indexes_locked()
            return graph

        if settings.network_graphml.exists():
            try:
                import osmnx as ox
            except ImportError as exc:
                raise RuntimeError("OSMnx is required to import the legacy GraphML cache") from exc
            graph = ox.io.load_graphml(filepath=settings.network_graphml)
            self._graph = graph
            self._metadata = {}
            self._build_indexes_locked()
            # Convert the legacy cache once so every subsequent request is fast.
            settings.network_pickle.parent.mkdir(parents=True, exist_ok=True)
            with settings.network_pickle.open("wb") as handle:
                pickle.dump({"graph": graph, "metadata": self._metadata}, handle, protocol=pickle.HIGHEST_PROTOCOL)
            self._signature = self._source_signature(settings.network_pickle)
            return graph

        raise ValueError("Prepare the operating road graph first")

    def get_graph(self) -> nx.MultiDiGraph:
        with self._lock:
            if self._graph is not None:
                return self._graph
            return self._load_locked()

    def _build_indexes_locked(self) -> None:
        graph = self._graph
        if graph is None:
            return

        crs = CRS.from_user_input(graph.graph.get("crs") or "EPSG:4326")
        if crs.is_geographic:
            # Derive a metric CRS from the actual operating graph. UTM is fast
            # and accurate for ordinary latitudes; a local azimuthal projection
            # keeps extreme-latitude regions valid as well. No country-specific
            # fallback coordinates are used.
            xs = [float(data.get("x", 0.0)) for _, data in graph.nodes(data=True)]
            ys = [float(data.get("y", 0.0)) for _, data in graph.nodes(data=True)]
            mean_lon = float(np.mean(xs)) if xs else 0.0
            mean_lat = float(np.mean(ys)) if ys else 0.0
            mean_lon = ((mean_lon + 180.0) % 360.0) - 180.0
            mean_lat = max(-90.0, min(90.0, mean_lat))
            if -80.0 <= mean_lat <= 84.0:
                zone = max(1, min(60, int((mean_lon + 180.0) // 6.0) + 1))
                epsg = 32600 + zone if mean_lat >= 0 else 32700 + zone
                projected_crs = CRS.from_epsg(epsg)
            else:
                projected_crs = CRS.from_proj4(
                    f"+proj=aeqd +lat_0={mean_lat:.8f} +lon_0={mean_lon:.8f} "
                    "+datum=WGS84 +units=m +no_defs"
                )
        else:
            projected_crs = crs

        self._to_projected = Transformer.from_crs("EPSG:4326", projected_crs, always_xy=True)
        self._to_wgs84 = Transformer.from_crs(projected_crs, "EPSG:4326", always_xy=True)

        node_ids: list[Any] = []
        node_lon: list[float] = []
        node_lat: list[float] = []
        for node_id, data in graph.nodes(data=True):
            node_ids.append(node_id)
            node_lon.append(float(data["x"]))
            node_lat.append(float(data["y"]))
        self._node_ids = node_ids
        self._node_by_text = {str(node_id): node_id for node_id in node_ids}
        if node_ids:
            # PyProj accepts vector inputs. One vectorized transform avoids tens
            # of thousands of Python->PROJ calls when a regional graph opens.
            projected_x, projected_y = self._to_projected.transform(
                np.asarray(node_lon, dtype=np.float64), np.asarray(node_lat, dtype=np.float64)
            )
            self._node_xy = np.column_stack((projected_x, projected_y))
            self._node_tree = cKDTree(self._node_xy)
        else:
            self._node_xy = None
            self._node_tree = None

        # Build only cheap identity/access maps eagerly. Creating projected
        # Shapely geometry for every road edge is expensive and is unnecessary
        # for solver runs and generated scenarios, which operate on exact graph
        # nodes. The spatial edge tree is constructed lazily the first time a
        # user actually asks for arbitrary map-edge snapping. Road-layer
        # viewports use the cheap WGS84 bounds index below.
        exact: dict[tuple[str, str, str], tuple[Any, Any, Any]] = {}
        pairs: dict[tuple[str, str], list[tuple[Any, Any, Any]]] = {}
        access: dict[Any, tuple[Any, Any, Any, dict[str, Any]]] = {}
        light_records: list[tuple[Any, Any, Any, dict[str, Any]]] = []
        wgs84_bounds: list[tuple[float, float, float, float]] = []
        edge_grid: dict[tuple[int, int], list[int]] = {}
        edge_grid_global: list[int] = []
        for edge_index, (u, v, key, data) in enumerate(graph.edges(keys=True, data=True)):
            identity = (str(u), str(v), str(key))
            exact[identity] = (u, v, key)
            pairs.setdefault((str(u), str(v)), []).append((u, v, key))
            access.setdefault(u, (u, v, key, data))
            access.setdefault(v, (u, v, key, data))
            light_records.append((u, v, key, data))
            geometry = data.get("geometry")
            if geometry is not None and hasattr(geometry, "bounds"):
                minx, miny, maxx, maxy = geometry.bounds
            else:
                ux, uy = float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])
                vx, vy = float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])
                minx, maxx = min(ux, vx), max(ux, vx)
                miny, maxy = min(uy, vy), max(uy, vy)
            minx, miny, maxx, maxy = float(minx), float(miny), float(maxx), float(maxy)
            wgs84_bounds.append((minx, miny, maxx, maxy))
            # Populate a cheap spatial grid while the edge bounds are already hot.
            # Ordinary OSM road segments occupy only one or a few cells. Extremely
            # long/dateline-spanning geometries are kept in a tiny global fallback
            # list rather than exploding the grid.
            gx0 = math.floor((minx + 180.0) / _EDGE_GRID_DEG)
            gx1 = math.floor((maxx + 180.0) / _EDGE_GRID_DEG)
            gy0 = math.floor((miny + 90.0) / _EDGE_GRID_DEG)
            gy1 = math.floor((maxy + 90.0) / _EDGE_GRID_DEG)
            cell_count = max(0, gx1 - gx0 + 1) * max(0, gy1 - gy0 + 1)
            if cell_count <= 0 or cell_count > _EDGE_GRID_MAX_CELLS_PER_EDGE:
                edge_grid_global.append(edge_index)
            else:
                for gx in range(gx0, gx1 + 1):
                    for gy in range(gy0, gy1 + 1):
                        edge_grid.setdefault((gx, gy), []).append(edge_index)
        self._edge_records = []
        self._edge_light_records = light_records
        self._edge_bounds_wgs84 = np.asarray(wgs84_bounds, dtype=np.float64) if wgs84_bounds else np.empty((0, 4), dtype=np.float64)
        self._edge_grid = edge_grid
        self._edge_grid_global = edge_grid_global
        self._edge_projection_cache = OrderedDict()
        self._edge_tree = None
        self._edge_spatial_ready = False
        self._node_access_record = access
        self._edge_exact = exact
        self._edge_pairs = pairs
        self._geojson_cache = {}
        self._viewport_cache = OrderedDict()

    def _ensure_edge_spatial_index_locked(self) -> None:
        if self._edge_spatial_ready:
            return
        graph = self._graph
        if graph is None:
            graph = self._load_locked()
        if self._to_projected is None:
            raise ValueError("The operating graph projection is unavailable")
        records: list[EdgeRecord] = []
        geometries: list[LineString] = []
        for u, v, key, data in graph.edges(keys=True, data=True):
            latlon = self._edge_geometry(graph, u, v, data)
            line_wgs84 = LineString([(float(point[1]), float(point[0])) for point in latlon])
            line_projected = shapely_transform(self._to_projected.transform, line_wgs84)
            record = EdgeRecord(u, v, key, latlon, line_projected, dict(data))
            records.append(record)
            geometries.append(line_projected)
        self._edge_records = records
        self._edge_tree = STRtree(geometries) if geometries else None
        self._edge_spatial_ready = True

    def resolve_node(self, value: Any) -> Any | None:
        """Resolve a persisted OSM-node token in O(1)."""
        with self._lock:
            self.get_graph()
            return self._node_by_text.get(str(value))

    def access_for_node(self, node_id: Any) -> dict[str, Any]:
        """Return exact road-access evidence for a node already in the graph."""
        with self._lock:
            graph = self.get_graph()
            node = node_id if node_id in graph else self._node_by_text.get(str(node_id))
            if node is None or node not in graph:
                raise ValueError("The requested road node is not present in the active graph")
            record = self._node_access_record.get(node)
            if record is None:
                raise ValueError("The requested road node has no incident road segment")
            u, v, key, data = record
            highway = data.get("highway", "unclassified")
            if isinstance(highway, list):
                highway = highway[0] if highway else "unclassified"
            name = data.get("name")
            if isinstance(name, list):
                name = " / ".join(str(x) for x in name if x)
            return {
                "road_name": str(name or "Unnamed road"),
                "highway": str(highway or "unclassified"),
                "oneway": osm_bool(data.get("oneway")),
                "direction_text": "one-way" if osm_bool(data.get("oneway")) else "two-way road record",
                "osm_u": str(u),
                "osm_v": str(v),
                "osm_key": str(key),
                "access_osm_node": str(node),
                "snap_lat": float(graph.nodes[node]["y"]),
                "snap_lon": float(graph.nodes[node]["x"]),
                "snap_distance_m": 0.0,
                "geometry": self._edge_geometry(graph, u, v, data),
                "maxspeed": data.get("maxspeed", ""),
                "lanes": data.get("lanes", ""),
            }

    def nearest_node(self, lat: float, lon: float) -> Any:
        with self._lock:
            self.get_graph()
            if self._node_tree is None or self._to_projected is None:
                raise ValueError("The operating graph contains no indexed nodes")
            x, y = self._to_projected.transform(float(lon), float(lat))
            _, index = self._node_tree.query([x, y], k=1)
            return self._node_ids[int(index)]

    def nodes_within_radius(self, lat: float, lon: float, radius_m: float, *, limit: int | None = None) -> list[tuple[Any, float]]:
        """Return indexed graph nodes inside a metric radius without graph traversal.

        The operating graph is already the depot's round-trip SCC, so these nodes
        are route-reachable by construction. This makes random scenario generation
        an O(log n + k) spatial query instead of a full Dijkstra scan.
        """
        with self._lock:
            self.get_graph()
            if self._node_tree is None or self._node_xy is None or self._to_projected is None:
                raise ValueError("The operating graph contains no indexed nodes")
            radius = max(0.0, float(radius_m))
            x, y = self._to_projected.transform(float(lon), float(lat))
            indexes = self._node_tree.query_ball_point([x, y], r=radius)
            if not indexes:
                return []
            # Vectorize the distance calculation. The previous Python loop called
            # np.linalg.norm once per candidate and then fully sorted the result;
            # dense 200–450 stop scenarios can expose tens of thousands of nearby
            # nodes. Keep identical nearest-first semantics but use one NumPy pass
            # and an O(n) partial selection when a limit is requested.
            raw_indexes = np.asarray(indexes, dtype=np.int64)
            origin = np.asarray([x, y], dtype=np.float64)
            deltas = self._node_xy[raw_indexes] - origin
            distances = np.sqrt(np.einsum("ij,ij->i", deltas, deltas))
            if limit is not None:
                cap = max(0, int(limit))
                if cap == 0:
                    return []
                if len(raw_indexes) > cap:
                    selected = np.argpartition(distances, cap - 1)[:cap]
                    selected = selected[np.argsort(distances[selected], kind="stable")]
                else:
                    selected = np.argsort(distances, kind="stable")
            else:
                selected = np.argsort(distances, kind="stable")
            return [
                (self._node_ids[int(raw_indexes[pos])], float(distances[pos]))
                for pos in selected
            ]

    def _projected_edge_record_locked(self, index: int) -> EdgeRecord:
        """Return one exact projected edge geometry with a small bounded LRU."""
        index = int(index)
        cached = self._edge_projection_cache.get(index)
        if cached is not None:
            self._edge_projection_cache.move_to_end(index)
            return cached
        graph = self._graph
        if graph is None:
            graph = self._load_locked()
        if self._to_projected is None:
            raise ValueError("The operating graph projection is unavailable")
        u, v, key, data = self._edge_light_records[index]
        latlon = self._edge_geometry(graph, u, v, data)
        line_wgs84 = LineString([(float(item[1]), float(item[0])) for item in latlon])
        line_projected = shapely_transform(self._to_projected.transform, line_wgs84)
        record = EdgeRecord(u, v, key, latlon, line_projected, dict(data))
        self._edge_projection_cache[index] = record
        self._edge_projection_cache.move_to_end(index)
        while len(self._edge_projection_cache) > 4096:
            self._edge_projection_cache.popitem(last=False)
        return record

    def _edge_grid_candidates_locked(
        self, lat: float, lon: float, radius_m: float
    ) -> list[int]:
        """Return a conservative local edge candidate set without an O(E) scan.

        Edge membership is indexed by WGS84 bounding-box cells. The query window
        is deliberately a little larger than the requested metric radius; exact
        projected geometry distance decides the winner, so the grid is only a
        candidate accelerator and never a feasibility approximation.
        """
        if not self._edge_grid and not self._edge_grid_global:
            return []
        latitude = float(lat)
        longitude = float(lon)
        cos_lat = max(0.05, abs(math.cos(math.radians(latitude))))
        # Slightly conservative earth-degree conversion avoids boundary misses.
        lat_pad = float(radius_m) / 109_500.0
        lon_pad = float(radius_m) / (109_500.0 * cos_lat)
        gx0 = math.floor((longitude - lon_pad + 180.0) / _EDGE_GRID_DEG)
        gx1 = math.floor((longitude + lon_pad + 180.0) / _EDGE_GRID_DEG)
        gy0 = math.floor((latitude - lat_pad + 90.0) / _EDGE_GRID_DEG)
        gy1 = math.floor((latitude + lat_pad + 90.0) / _EDGE_GRID_DEG)
        cell_count = max(0, gx1 - gx0 + 1) * max(0, gy1 - gy0 + 1)
        # A click far outside the prepared operating area can have a nearest-node
        # upper bound of many kilometres. Enumerating millions of empty grid cells
        # would turn an error-path click into a CPU stall; return no local candidate
        # and let nearest_edge() build/use the exact global STRtree instead.
        if cell_count <= 0 or cell_count > _EDGE_GRID_MAX_QUERY_CELLS:
            return []
        candidates: set[int] = set(self._edge_grid_global)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                candidates.update(self._edge_grid.get((gx, gy), ()))
        return list(candidates)

    def _nearby_edge_record_locked(self, lat: float, lon: float, point: Point) -> EdgeRecord | None:
        """Return the exact nearest edge using a provable nearest-node bound.

        The nearest graph node lies on at least one road edge, therefore the
        point-to-nearest-node distance is an upper bound on point-to-nearest-edge
        distance. We only need to evaluate edges whose WGS84 bounding boxes can
        intersect that metric-radius window. This removes the old O(E) bounds scan
        per point and is especially important for 100--450-row CSV imports.
        """
        graph = self._graph
        if graph is None or self._to_projected is None or self._node_tree is None:
            return None
        # ``point`` is already in the same projected CRS as the node KD-tree.
        node_distance, _ = self._node_tree.query([float(point.x), float(point.y)], k=1)
        upper_bound_m = max(1.0, float(node_distance) + 0.5)
        indexes = self._edge_grid_candidates_locked(float(lat), float(lon), upper_bound_m)
        if not indexes:
            return None
        # The grid cell itself is deliberately coarse. Before constructing any
        # Shapely geometry, reject candidates whose WGS84 bbox has a conservative
        # metric lower bound already worse than the nearest-node upper bound.
        # 100 km/degree is intentionally below the real local scale almost
        # everywhere, so this filter can admit false positives but must not drop
        # a genuinely closer road.
        if self._edge_bounds_wgs84 is not None and len(indexes) > 8:
            idx = np.asarray(indexes, dtype=np.int64)
            bounds = self._edge_bounds_wgs84[idx]
            longitude = float(lon); latitude = float(lat)
            dx_deg = np.maximum(np.maximum(bounds[:, 0] - longitude, longitude - bounds[:, 2]), 0.0)
            dy_deg = np.maximum(np.maximum(bounds[:, 1] - latitude, latitude - bounds[:, 3]), 0.0)
            cos_lat = max(0.02, abs(math.cos(math.radians(latitude))))
            lower_m = np.hypot(dx_deg * 100_000.0 * cos_lat, dy_deg * 100_000.0)
            keep = lower_m <= (upper_bound_m + 2.0)
            idx = idx[keep]
            if len(idx):
                indexes = idx.astype(int).tolist()
        best_record: EdgeRecord | None = None
        best_distance = float("inf")
        for index in indexes:
            record = self._projected_edge_record_locked(int(index))
            distance = float(point.distance(record.geometry_projected))
            if distance < best_distance:
                best_distance = distance
                best_record = record
        # Grid candidate construction is conservative. The nearest-node bound
        # guarantees at least one incident edge no farther than upper_bound_m.
        # If that invariant is ever violated (corrupt/odd geometry), fail over to
        # the exact global STRtree instead of returning an approximation.
        if best_record is not None and best_distance <= upper_bound_m + 1e-6:
            return best_record
        return None

    def nearest_edge(self, lat: float, lon: float) -> dict[str, Any]:
        with self._lock:
            self.get_graph()
            if self._to_projected is None or self._to_wgs84 is None:
                raise ValueError("The operating graph contains no indexed road segments")
            x, y = self._to_projected.transform(float(lon), float(lat))
            point = Point(x, y)
            record = self._nearby_edge_record_locked(float(lat), float(lon), point)
            if record is None:
                # Unusual far-off clicks retain the exact global fallback.
                self._ensure_edge_spatial_index_locked()
                if self._edge_tree is None:
                    raise ValueError("The operating graph contains no indexed road segments")
                index = self._edge_tree.nearest(point)
                if isinstance(index, (int, np.integer)):
                    record = self._edge_records[int(index)]
                else:
                    match_index = next((i for i, rec in enumerate(self._edge_records) if rec.geometry_projected.equals(index)), None)
                    if match_index is None:
                        raise ValueError("Could not resolve the selected road segment")
                    record = self._edge_records[match_index]
            projected_nearest = record.geometry_projected.interpolate(record.geometry_projected.project(point))
            snap_lon, snap_lat = self._to_wgs84.transform(projected_nearest.x, projected_nearest.y)
            distance_m = float(point.distance(projected_nearest))
            access_node = self.nearest_node(snap_lat, snap_lon)
            data = record.data
            highway = data.get("highway", "unclassified")
            if isinstance(highway, list):
                highway = highway[0] if highway else "unclassified"
            name = data.get("name")
            if isinstance(name, list):
                name = " / ".join(str(x) for x in name if x)
            return {
                "road_name": str(name or "Unnamed road"),
                "highway": str(highway or "unclassified"),
                "oneway": osm_bool(data.get("oneway")),
                "direction_text": "one-way" if osm_bool(data.get("oneway")) else "two-way road record",
                "osm_u": str(record.u),
                "osm_v": str(record.v),
                "osm_key": str(record.key),
                "access_osm_node": str(access_node),
                "snap_lat": float(snap_lat),
                "snap_lon": float(snap_lon),
                "snap_distance_m": distance_m,
                "geometry": record.geometry_wgs84,
                "maxspeed": data.get("maxspeed", ""),
                "lanes": data.get("lanes", ""),
            }

    def resolve_edge(self, osm_u: Any, osm_v: Any, osm_key: Any | None = None) -> list[tuple[Any, Any, Any]]:
        with self._lock:
            self.get_graph()
            if osm_key is not None:
                match = self._edge_exact.get((str(osm_u), str(osm_v), str(osm_key)))
                if match is not None:
                    return [match]
            return list(self._edge_pairs.get((str(osm_u), str(osm_v)), []))

    def geojson(self, max_edges: int = 8_000, detail: str = "balanced") -> dict[str, Any]:
        with self._lock:
            graph = self.get_graph()
            key = (int(max_edges), str(detail))
            cached = self._geojson_cache.get(key)
            if cached is not None:
                return cached

            rank = {
                "motorway": 0, "motorway_link": 1, "trunk": 2, "trunk_link": 3,
                "primary": 4, "primary_link": 5, "secondary": 6, "secondary_link": 7,
                "tertiary": 8, "tertiary_link": 9, "unclassified": 10,
                "residential": 11, "living_street": 12, "road": 13, "service": 14,
            }
            candidates: list[tuple[int, float, int]] = []
            for index, (_, _, _, data) in enumerate(self._edge_light_records):
                highway = data.get("highway", "unclassified")
                if isinstance(highway, list):
                    highway = highway[0] if highway else "unclassified"
                priority = rank.get(str(highway), 15)
                try:
                    length = float(data.get("length", 0.0) or 0.0)
                except (TypeError, ValueError):
                    length = 0.0
                candidates.append((priority, -length, index))
            candidates.sort(key=lambda item: (item[0], item[1]))
            chosen = candidates[: max(100, int(max_edges))]

            features = []
            for _, _, index in chosen:
                u, v, edge_key, data = self._edge_light_records[index]
                geometry = self._edge_geometry(graph, u, v, data)
                if len(geometry) > 14:
                    step = max(1, len(geometry) // 12)
                    sampled = geometry[::step]
                    if sampled[-1] != geometry[-1]:
                        sampled.append(geometry[-1])
                    geometry = sampled
                highway = data.get("highway", "unclassified")
                if isinstance(highway, list):
                    highway = highway[0] if highway else "unclassified"
                name = data.get("name")
                if isinstance(name, list):
                    name = " / ".join(str(x) for x in name if x)
                speed = data.get("speed_kph", 35.0)
                if isinstance(speed, list):
                    speed = speed[0] if speed else 35.0
                try:
                    speed = float(speed)
                except (TypeError, ValueError):
                    speed = 35.0
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[point[1], point[0]] for point in geometry]},
                    "properties": {
                        "name": str(name or ""),
                        "highway": str(highway),
                        "oneway": osm_bool(data.get("oneway")),
                        "speed_kph": speed,
                        "osm_u": str(u), "osm_v": str(v), "osm_key": str(edge_key),
                    },
                })
            result = {
                "type": "FeatureCollection",
                "features": features,
                "truncated": graph.number_of_edges() > len(features),
                "total_edges": int(graph.number_of_edges()),
                "rendered_edges": len(features),
            }
            self._geojson_cache[key] = result
            return result


    def geojson_bbox(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        max_edges: int = 4_000,
    ) -> dict[str, Any]:
        """Return visible road segments using lightweight WGS84 edge bounds.

        Viewport rendering no longer forces projected Shapely geometry/STRtree
        construction for every edge. The precise projected tree remains lazy and
        is reserved for arbitrary nearest-edge snapping.
        """
        with self._lock:
            graph = self.get_graph()
            south, north = sorted((float(south), float(north)))
            west, east = sorted((float(west), float(east)))
            cache_key = (round(south, 4), round(west, 4), round(north, 4), round(east, 4), int(max_edges))
            cached = self._viewport_cache.get(cache_key)
            if cached is not None:
                self._viewport_cache.move_to_end(cache_key)
                return {**cached, "cache_hit": True}

            bounds = self._edge_bounds_wgs84
            if bounds is None or len(bounds) == 0:
                indexes: list[int] = []
            else:
                mask = (
                    (bounds[:, 0] <= east) & (bounds[:, 2] >= west)
                    & (bounds[:, 1] <= north) & (bounds[:, 3] >= south)
                )
                indexes = np.flatnonzero(mask).astype(int).tolist()
            candidate_count = len(indexes)

            # Major and named roads first when a dense viewport exceeds the cap.
            # Keep the rank table outside the key callback: this callback may run
            # tens of thousands of times during one pan/zoom request.
            highway_rank = {
                "motorway": 0, "trunk": 1, "primary": 2, "secondary": 3,
                "tertiary": 4, "unclassified": 5, "residential": 6,
                "service": 7, "living_street": 8,
            }
            def priority(index: int) -> tuple[int, int, float]:
                data = self._edge_light_records[index][3]
                highway = data.get("highway")
                if isinstance(highway, list):
                    highway = highway[0] if highway else ""
                rank = highway_rank.get(str(highway), 9)
                named = 0 if data.get("name") else 1
                try:
                    length = -float(data.get("length", 0.0))
                except (TypeError, ValueError):
                    length = 0.0
                return rank, named, length

            limit = max(1, int(max_edges))
            indexes = heapq.nsmallest(limit, indexes, key=priority) if len(indexes) > limit else sorted(indexes, key=priority)
            features = []
            for index in indexes:
                u, v, edge_key, data = self._edge_light_records[index]
                geometry = self._edge_geometry(graph, u, v, data)
                highway = data.get("highway", "unclassified")
                if isinstance(highway, list):
                    highway = highway[0] if highway else "unclassified"
                name = data.get("name")
                if isinstance(name, list):
                    name = " / ".join(str(x) for x in name if x)
                speed = data.get("speed_kph", 35.0)
                if isinstance(speed, list):
                    speed = speed[0] if speed else 35.0
                try:
                    speed = float(speed)
                except (TypeError, ValueError):
                    speed = 35.0
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[point[1], point[0]] for point in geometry]},
                    "properties": {
                        "name": str(name or ""), "highway": str(highway),
                        "oneway": osm_bool(data.get("oneway")), "speed_kph": speed,
                        "osm_u": str(u), "osm_v": str(v), "osm_key": str(edge_key),
                    },
                })
            result = {
                "type": "FeatureCollection",
                "features": features,
                "total_edges": int(graph.number_of_edges()),
                "total_matches": int(candidate_count),
                "candidate_edges": int(candidate_count),
                "rendered_edges": len(features),
                "truncated": candidate_count > len(features),
                "bounds": {"south": south, "west": west, "north": north, "east": east},
                "cache_hit": False,
            }
            self._viewport_cache[cache_key] = result
            self._viewport_cache.move_to_end(cache_key)
            while len(self._viewport_cache) > 32:
                self._viewport_cache.popitem(last=False)
            return result


GRAPH_STORE = GraphStore()
