from __future__ import annotations

import json
import hashlib
import platform
import os
import queue
import re
import signal
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse, urlencode
from pathlib import Path

APP_VERSION = "3.1.4"
ROOT = Path(__file__).resolve().parent
RUNTIME = Path(os.getenv("VRP_RUNTIME_DIR", ROOT / "runtime")).expanduser().resolve()
TOKEN = os.getenv("VRP_APP_TOKEN") or secrets.token_urlsafe(18)
CLOUDFLARED_VERSION = "2026.5.2"
_CLOUDFLARED_ASSETS = {
    "x86_64": ("cloudflared-linux-amd64", "5286698547f03df745adb2355f04c12dde52ef425491e81f433642d695521886"),
    "amd64": ("cloudflared-linux-amd64", "5286698547f03df745adb2355f04c12dde52ef425491e81f433642d695521886"),
    "aarch64": ("cloudflared-linux-arm64", "5a4e8ce2701105271412059f44b6a0bf1ae4542b4d98ff3180c0c019443a5815"),
    "arm64": ("cloudflared-linux-arm64", "5a4e8ce2701105271412059f44b6a0bf1ae4542b4d98ff3180c0c019443a5815"),
}

NATIVE_READY_RECEIPT = "native_engines_ready.json"


def _native_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _native_component_paths(environment: dict[str, str]) -> dict[str, tuple[Path, Path]]:
    runtime = Path(environment.get("VRP_RUNTIME_DIR", str(RUNTIME))).expanduser().resolve()
    return {
        "clustering": (ROOT / "cluster.cpp", Path(environment.get("VRP_CLUSTER_BIN", str(runtime / "cluster"))).expanduser().resolve()),
        "optimizer": (ROOT / "solver.cpp", Path(environment.get("VRP_SOLVER_BIN", str(runtime / "solver"))).expanduser().resolve()),
    }


def _native_receipt_path(environment: dict[str, str]) -> Path:
    runtime = Path(environment.get("VRP_RUNTIME_DIR", str(RUNTIME))).expanduser().resolve()
    return runtime / NATIVE_READY_RECEIPT


def native_engine_receipt_status(environment: dict[str, str] | None = None) -> tuple[bool, str]:
    """Lightweight integrity check for engines already prepared in this runtime.

    Cell 1 performs the expensive compile/fingerprint path. Cell 2 should not
    import the full routing backend and probe g++ again merely to rediscover the
    same result. The receipt binds each source, executable, and build marker by
    SHA-256; any source/binary/marker change falls back to the normal compiler
    path rather than being trusted blindly.
    """
    env = dict(os.environ if environment is None else environment)
    path = _native_receipt_path(env)
    if not path.is_file():
        return False, "readiness receipt missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"readiness receipt unreadable: {type(exc).__name__}"
    if payload.get("app_version") != APP_VERSION:
        return False, "readiness receipt belongs to another app version"
    receipts = payload.get("components")
    if not isinstance(receipts, dict):
        return False, "readiness receipt component table missing"
    for name, (source, binary) in _native_component_paths(env).items():
        item = receipts.get(name)
        if not isinstance(item, dict):
            return False, f"{name} readiness entry missing"
        marker = binary.with_suffix(binary.suffix + ".build.sha256")
        if not source.is_file() or not binary.is_file() or binary.stat().st_size <= 0 or not marker.is_file():
            return False, f"{name} source, executable, or build marker missing"
        try:
            if str(source.resolve()) != str(item.get("source_path")) or str(binary.resolve()) != str(item.get("binary_path")):
                return False, f"{name} readiness path changed"
            if marker.read_text(encoding="utf-8").strip() != str(item.get("build_marker") or ""):
                return False, f"{name} build marker changed"
            if _native_sha256(source) != str(item.get("source_sha256") or ""):
                return False, f"{name} source changed"
            if _native_sha256(binary) != str(item.get("binary_sha256") or ""):
                return False, f"{name} executable changed"
        except OSError as exc:
            return False, f"{name} readiness check failed: {type(exc).__name__}"
    return True, "verified"


def _write_native_engine_receipt(environment: dict[str, str]) -> Path:
    path = _native_receipt_path(environment)
    path.parent.mkdir(parents=True, exist_ok=True)
    components: dict[str, dict[str, object]] = {}
    for name, (source, binary) in _native_component_paths(environment).items():
        marker = binary.with_suffix(binary.suffix + ".build.sha256")
        if not source.is_file() or not binary.is_file() or binary.stat().st_size <= 0 or not marker.is_file():
            raise RuntimeError(f"Cannot publish native readiness receipt: {name} build is incomplete")
        components[name] = {
            "source_path": str(source.resolve()),
            "source_sha256": _native_sha256(source),
            "binary_path": str(binary.resolve()),
            "binary_sha256": _native_sha256(binary),
            "binary_bytes": int(binary.stat().st_size),
            "build_marker": marker.read_text(encoding="utf-8").strip(),
        }
    payload = {
        "schema": 1,
        "app_version": APP_VERSION,
        "prepared_unix_s": round(time.time(), 3),
        "components": components,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def _process_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _spawn_detached_prewarm(name: str, code: str, environment: dict[str, str]) -> tuple[str, Path]:
    """Start one idempotent best-effort preparation task without blocking UI startup."""
    runtime = Path(environment.get("VRP_RUNTIME_DIR", str(RUNTIME))).expanduser().resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    pid_path = runtime / f"{name}.pid"
    log_path = runtime / f"{name}.log"
    try:
        if pid_path.is_file():
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            if _process_alive(pid):
                return "warming", log_path
    except Exception:
        pass
    output = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", code],
        cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    output.close()
    pid_path.write_text(str(process.pid) + "\n", encoding="utf-8")
    return "started", log_path


def start_native_prewarm(environment: dict[str, str] | None = None) -> tuple[str, Path]:
    env = dict(os.environ if environment is None else environment)
    env.setdefault("VRP_RUNTIME_DIR", str(RUNTIME))
    ready, _ = native_engine_receipt_status(env)
    if ready:
        return "ready", Path(env["VRP_RUNTIME_DIR"]) / "native_prepare.log"
    return _spawn_detached_prewarm(
        "native_prepare_background",
        "from launch_colab import prepare_native_engines; prepare_native_engines()",
        env,
    )


def start_osmium_prewarm(environment: dict[str, str] | None = None) -> tuple[str, Path]:
    """Best-effort overlap of first-use osmium installation with operator setup.

    Failure never blocks workspace launch; an uncached graph build retries through
    offline_osm._ensure_osmium with visible progress.
    """
    env = dict(os.environ if environment is None else environment)
    env.setdefault("VRP_RUNTIME_DIR", str(RUNTIME))
    if shutil.which("osmium"):
        return "ready", Path(env["VRP_RUNTIME_DIR"]) / "osmium_prewarm.log"
    if not shutil.which("apt-get") or (hasattr(os, "geteuid") and os.geteuid() != 0):
        return "unavailable", Path(env["VRP_RUNTIME_DIR"]) / "osmium_prewarm.log"
    return _spawn_detached_prewarm(
        "osmium_prewarm",
        "from app.offline_osm import _ensure_osmium; print(_ensure_osmium(None), flush=True)",
        env,
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def stop_process(process: subprocess.Popen[object] | None, timeout: float = 5.0) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def stop_process_group(process: subprocess.Popen[object] | None, timeout: float = 3.0) -> None:
    """Stop a detached preparation process and any compiler child it owns."""
    if process is None:
        return
    try:
        # start_new_session makes pid the owned process-group ID. The parent
        # may already have exited while a compiler descendant is still alive.
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=timeout)
    except (ProcessLookupError, PermissionError):
        return
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    finally:
        # wait() tracks the parent only, not every descendant in its group.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def prepare_native_engines(environment: dict[str, str] | None = None, timeout: float = 1860) -> None:
    """Prepare both exact production builds, usually as a background warm-up.

    The same function is safe for foreground/local preparation: fingerprinted
    cross-process locks prevent duplicate compilers and atomically publish only
    complete binaries.
    """
    environment = dict(os.environ if environment is None else environment)
    environment.setdefault("VRP_RUNTIME_DIR", str(RUNTIME))
    ready, readiness_reason = native_engine_receipt_status(environment)
    if ready:
        print("Native engines: verified readiness receipt; clustering and routing optimizer are already built.", flush=True)
        return
    runtime = Path(environment["VRP_RUNTIME_DIR"])
    runtime.mkdir(parents=True, exist_ok=True)
    log_path = runtime / "native_prepare.log"
    script = """import concurrent.futures, os, time
from app.config import settings
from app.engine import _compile_cpp
components = [
    (1, settings.cluster_cpp, settings.cluster_bin, 'clustering engine'),
    (2, settings.solver_cpp, settings.solver_bin, 'routing optimizer'),
]
def build(item):
    index, source, binary, label = item
    started = time.monotonic()
    before = binary.stat().st_mtime_ns if binary.exists() else None
    print(f'[{index}/2] Preparing {label}: checking cache; compiling if needed...', flush=True)
    _compile_cpp(source, binary, label)
    reused = before is not None and before == binary.stat().st_mtime_ns
    print(f'[{index}/2] {label.capitalize()} ready ({"cached" if reused else "compiled"}; {time.monotonic()-started:.1f}s).', flush=True)

workers = 2 if (os.cpu_count() or 1) >= 2 else 1
if workers > 1:
    print('Building independent native engines concurrently on available CPU capacity.', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(build, item) for item in components]
        for future in futures:
            future.result()
else:
    for item in components:
        build(item)
"""
    print("Preparing native engines. The first uncached build can take several minutes; the workspace may remain usable while this warms in the background.", flush=True)
    print("Build log:", log_path, flush=True)
    started = time.monotonic()
    heartbeat = started + 10
    with log_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", script], cwd=ROOT, env=environment,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            with log_path.open(encoding="utf-8", errors="replace") as progress:
                while True:
                    # Check exit before reading so the last lines cannot be lost.
                    code = process.poll()
                    for line in progress:
                        print(line, end="", flush=True)
                    if code is not None:
                        if code != 0:
                            raise RuntimeError(f"Native engine preparation failed (exit {code}). Launch was stopped. See {log_path}; resolve the build error and rerun cell 1.")
                        break
                    now = time.monotonic()
                    if now - started >= timeout:
                        raise RuntimeError(f"Native engine preparation timed out. Launch was stopped. See {log_path} and rerun cell 1.")
                    if now >= heartbeat:
                        print(f"Still preparing native engines ({now-started:.0f}s elapsed)...", flush=True)
                        heartbeat = now + 10
                    time.sleep(0.25)
        finally:
            stop_process_group(process)
    receipt_path = _write_native_engine_receipt(environment)
    print("Both native engines are ready; no background compilation is pending.", flush=True)
    print("Native readiness receipt:", receipt_path, flush=True)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a launch credential to a redirected host.
        return None


def probe_workspace(base: str, startup_id: str, token: str, timeout: float = 5,
                    include_ui: bool = True) -> None:
    """Verify this launch's health and authenticated entry page, not just DNS."""
    opener = urllib.request.build_opener(_NoRedirect())
    headers = {"Cache-Control": "no-cache", "User-Agent": f"FleetRoute/{APP_VERSION}"}
    request = urllib.request.Request(base + "/health?startup=" + startup_id, headers=headers)
    with opener.open(request, timeout=timeout) as response:
        health = json.loads(response.read(65536).decode("utf-8"))
        if response.status != 200 or health.get("ok") is not True or health.get("version") != APP_VERSION or health.get("startup_id") != startup_id:
            raise RuntimeError("Health response does not belong to this FleetRoute launch")
    if include_ui:
        authenticated = {**headers, "x-app-token": token}
        for path, expected in [("/", b"/static/app.js"), ("/static/app.js", b"function subscribeToActiveJob(")]:
            request = urllib.request.Request(base + path, headers=authenticated)
            with opener.open(request, timeout=timeout) as response:
                if response.status != 200 or expected not in response.read(2_000_000):
                    raise RuntimeError("FleetRoute UI did not pass the startup check")


def wait_for_workspace(base: str, startup_id: str, token: str, server, tunnel=None,
                       timeout: float = 60, include_ui: bool = True) -> None:
    deadline = time.monotonic() + timeout
    heartbeat = time.monotonic() + 10
    last_error = "No response"
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("FleetRoute server exited during startup; see uvicorn.log")
        if tunnel is not None and tunnel.poll() is not None:
            raise RuntimeError("Cloudflare tunnel exited before public verification")
        try:
            probe_workspace(base, startup_id, token, timeout=min(5, max(.1, deadline-time.monotonic())), include_ui=include_ui)
            if server.poll() is not None or (tunnel is not None and tunnel.poll() is not None):
                raise RuntimeError("A startup process exited during verification")
            return
        except Exception as exc:
            # Do not print request URLs, headers, or credentials in diagnostics.
            if isinstance(exc, urllib.error.HTTPError):
                last_error = f"HTTP {exc.code}"
            elif isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, socket.gaierror):
                last_error = "DNS lookup failed"
            else:
                last_error = type(exc).__name__
        if time.monotonic() >= heartbeat:
            print(f"Waiting for {'public HTTPS' if tunnel is not None else 'local app'} verification ({last_error})...", flush=True)
            heartbeat = time.monotonic() + 10
        time.sleep(min(1, max(0, deadline-time.monotonic())))
    raise RuntimeError(f"Workspace verification timed out ({last_error}). No working launch link has been confirmed.")


def start_tunnel(binary: Path, port: int, log_path: Path):
    process = subprocess.Popen(
        [str(binary), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    urls: queue.Queue[str] = queue.Queue(maxsize=1)
    def reader() -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            assert process.stdout is not None
            for line in process.stdout:
                handle.write(line)
                handle.flush()
                public = quick_tunnel_url_from_log(line)
                if public:
                    try:
                        urls.put_nowait(public)
                    except queue.Full:
                        pass
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    return process, urls, thread


def wait_for_tunnel_url(process, urls, server, timeout: float = 60) -> str:
    deadline = time.monotonic() + timeout
    heartbeat = time.monotonic() + 10
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("FleetRoute server exited; see uvicorn.log")
        if process.poll() is not None:
            raise RuntimeError("Cloudflare tunnel exited without a verified link")
        try:
            return urls.get(timeout=min(1, max(.01, deadline-time.monotonic())))
        except queue.Empty:
            if time.monotonic() >= heartbeat:
                print("Waiting for Cloudflare to create a temporary address...", flush=True)
                heartbeat = time.monotonic() + 10
    raise RuntimeError("Cloudflare did not provide a tunnel address in time")


def is_usable_cloudflared(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size <= 1_000_000:
            return False
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quick_tunnel_url_from_log(line: str) -> str | None:
    """Return only a generated TryCloudflare hostname, never its API endpoint."""
    for candidate in re.findall(r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.trycloudflare\.com(?![a-z0-9.:-])", line):
        hostname = (urlparse(candidate).hostname or "").lower()
        label = hostname.removesuffix(".trycloudflare.com")
        # Failure output contains https://api.trycloudflare.com/tunnel.  That is
        # Cloudflare's control endpoint, not a public URL for this workspace.
        if label and label != "api":
            return candidate
    return None


def cloudflared_binary() -> Path:
    # A system-managed installation is allowed; its provenance belongs to the
    # host image. The notebook fallback is pinned and checksum-verified.
    existing = shutil.which("cloudflared")
    if existing:
        path = Path(existing).resolve()
        try:
            version_text = subprocess.run(
                [str(path), "--version"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
        except Exception:
            version_text = "system-managed"
        (RUNTIME / "cloudflared_provenance.json").write_text(json.dumps({
            "source": "system", "path": str(path), "version": version_text,
            "sha256": _sha256_file(path),
        }, indent=2), encoding="utf-8")
        return path
    machine = platform.machine().lower()
    if machine not in _CLOUDFLARED_ASSETS:
        raise RuntimeError(f"Unsupported architecture for pinned cloudflared: {machine}")
    asset, expected_sha256 = _CLOUDFLARED_ASSETS[machine]
    url = f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/{asset}"
    target = RUNTIME / f"cloudflared-{CLOUDFLARED_VERSION}-{asset}"
    if target.exists() and (_sha256_file(target) != expected_sha256 or not is_usable_cloudflared(target)):
        target.unlink(missing_ok=True)
    if not target.exists():
        temporary = target.with_suffix(".download")
        temporary.unlink(missing_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": f"FleetRoute/{APP_VERSION}"})
        digest = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
        # Verify in the same pass that writes the pinned binary. This preserves
        # exact SHA-256 integrity while avoiding a second full read immediately
        # after a fresh download. Cached binaries are still re-hashed on reuse.
        got = digest.hexdigest()
        if got != expected_sha256 or not is_usable_cloudflared(temporary):
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded cloudflared failed SHA-256 verification: {got}")
        temporary.chmod(0o755)
        os.replace(temporary, target)
    target.chmod(0o755)
    (RUNTIME / "cloudflared_provenance.json").write_text(json.dumps({
        "version": CLOUDFLARED_VERSION,
        "asset": asset,
        "sha256": expected_sha256,
        "url": url,
    }, indent=2), encoding="utf-8")
    return target


def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("PORT") or free_port())
    environment = os.environ.copy()
    environment["VRP_APP_TOKEN"] = TOKEN
    environment["VRP_RUNTIME_DIR"] = str(RUNTIME)
    startup_id = secrets.token_hex(16)
    environment["VRP_STARTUP_ID"] = startup_id
    environment.setdefault(
        "VRP_GEOCODER_USER_AGENT",
        f"FleetRoute-Routing-Workspace/{APP_VERSION}",
    )

    # Native compilation is exact/fingerprint-bound but no longer blocks the UI.
    # It warms in parallel with region selection/PBF setup; an early Optimize job
    # waits visibly on the same component lock and reuses the atomically published
    # binary as soon as it is ready.
    native_warm_state, native_warm_log = start_native_prewarm(environment)
    osmium_warm_state, osmium_warm_log = start_osmium_prewarm(environment)
    print(f"Native engines: {native_warm_state} · {native_warm_log}", flush=True)
    print(f"Road extraction tool: {osmium_warm_state} · {osmium_warm_log}", flush=True)
    print("Starting the local application...", flush=True)
    server_log_path = RUNTIME / "uvicorn.log"
    server_log = server_log_path.open("w", encoding="utf-8")
    server = None
    tunnel: subprocess.Popen[str] | None = None
    reader_thread = None
    announced = False
    try:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
            cwd=ROOT, env=environment, stdout=server_log, stderr=subprocess.STDOUT,
        )
        wait_for_workspace(f"http://127.0.0.1:{port}", startup_id, TOKEN, server)
        print("Local application verified. Preparing the public connection...", flush=True)
        binary = cloudflared_binary()
        tunnel_log_path = RUNTIME / "cloudflared.log"
        tunnel_log_path.write_text("FleetRoute public startup checks\n", encoding="utf-8")
        public = None
        for attempt in range(1, 4):
            print(f"Public connection attempt {attempt}/3: waiting for tunnel and HTTPS verification...", flush=True)
            with tunnel_log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n--- Startup attempt {attempt}/3 ---\n")
            try:
                tunnel, urls, reader_thread = start_tunnel(binary, port, tunnel_log_path)
                candidate = wait_for_tunnel_url(tunnel, urls, server)
                wait_for_workspace(candidate, startup_id, TOKEN, server, tunnel=tunnel)
                public = candidate
                break
            except Exception as exc:
                stop_process(tunnel)
                if reader_thread:
                    reader_thread.join(timeout=2)
                tunnel = None
                reader_thread = None
                reason = str(exc).replace(TOKEN, "[redacted]")[:500]
                print(f"Public connection attempt {attempt}/3 was not verified: {reason}", flush=True)
                with tunnel_log_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"Startup verification failed: {reason}\n")
                if server.poll() is not None:
                    raise RuntimeError(f"The app server stopped. See {server_log_path}; rerun cell 2 after resolving the error.") from None
        if not public:
            raise RuntimeError(f"No working public link was verified after 3 attempts. The workspace was NOT opened. See {tunnel_log_path} for DNS/tunnel errors. Keep your data; rerun cell 2 when connectivity is available. Old temporary links may no longer work.")
        print("\n" + "=" * 78)
        print("FLEETROUTE WORKSPACE — STARTUP CHECKS PASSED")
        print("=" * 78)
        print("Open:", public + "/?" + urlencode({"token": TOKEN}))
        ready_now, _ = native_engine_receipt_status(environment)
        print("Native engines:", "ready" if ready_now else "warming in background (initial feasible planning remains available)")
        print("Public HTTPS, this app instance, and app entry files: verified from this runtime.")
        print("Server log:", server_log_path)
        print("Tunnel log:", tunnel_log_path)
        print("Keep cell 2 running. Stopping it or losing the runtime closes this temporary link.")
        print("If your browser reports DNS failure, rerun cell 2 and use its newest verified link.")
        print("Road downloads and uncached graph construction show measured progress; repeated graphs/materializations reuse verified caches.")
        print("=" * 78, flush=True)
        announced = True
        while True:
            if server.poll() is not None:
                raise RuntimeError(f"The app server stopped. This link is no longer usable. See {server_log_path} and rerun cell 2.")
            if tunnel.poll() is not None:
                raise RuntimeError(f"The public tunnel stopped. This link is no longer active. See {tunnel_log_path} and rerun cell 2.")
            time.sleep(1)
    finally:
        stop_process(tunnel)
        if reader_thread:
            reader_thread.join(timeout=2)
        # Uvicorn shutdown requests cancellation for active background jobs.
        # Give that hook enough time to terminate native child process groups.
        stop_process(server, timeout=10.0)
        server_log.close()
        if announced:
            print("Workspace stopped. The link printed above is no longer active; rerun cell 2 for a new one.", flush=True)


if __name__ == "__main__":
    main()
