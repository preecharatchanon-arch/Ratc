from __future__ import annotations

import asyncio
import codecs
import json
import math
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from .analytics import convergence_summary, create_run_evidence_zip
from .config import RUNTIME_DIR, settings
from .db import (
    expire_stale_jobs_if_due,
    get_job,
    get_job_with_events,
    init_db,
    list_active_jobs,
    recover_interrupted_jobs,
    request_job_cancel,
)
from .engine import (
    activate_region_source,
    add_place,
    app_state,
    clear_active_places,
    deactivate_closure,
    decide_closure,
    delete_region_source,
    developer_runtime_overview,
    generate_demo_plan,
    geocode_search,
    import_plan_rows,
    list_closures,
    network_geojson,
    network_viewport_geojson,
    preflight_status,
    preview_road_access,
    preview_road_edge,
    queue_clustering_benchmark,
    queue_convergence_analysis,
    queue_complete_demo,
    queue_network_build,
    queue_rush_workflow,
    queue_scenario_generation,
    queue_single_clustering,
    queue_solve,
    queue_region_download,
    read_job_log,
    read_runtime_file,
    remove_place,
    report_closure,
    save_operating_settings,
    solver_command_preview,
    solver_profiles,
    update_place,
    validate_extra_solver_args,
)
from .exports import create_driver_package

app = FastAPI(title=settings.app_name, version="3.1.4")
app.add_middleware(GZipMiddleware, minimum_size=1200)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()
    recover_interrupted_jobs()


@app.on_event("shutdown")
async def shutdown() -> None:
    """Ask every background job to stop before the server process exits.

    Colab users commonly interrupt/re-run the launcher cell. Native jobs own
    separate process groups so cancellation can terminate their full child tree,
    but that only happens while the worker is alive to observe the request. Give
    workers a short graceful window here instead of orphaning a solver/osmium
    process when uvicorn is stopped.
    """
    active = list_active_jobs(include_evidence=True)
    for job in active:
        request_job_cancel(int(job["id"]))
    if not active:
        return
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 7.0
    while loop.time() < deadline:
        if not list_active_jobs(include_evidence=True):
            return
        await asyncio.sleep(0.2)


@app.middleware("http")
async def token_gate(request: Request, call_next):
    query_token = request.query_params.get("token")
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    secure_cookie = request.url.scheme == "https" or forwarded_proto == "https"
    if settings.app_token and request.url.path not in {"/health", "/login"}:
        supplied = (
            query_token
            or request.headers.get("x-app-token")
            or request.cookies.get("vrp_app_token")
        )
        if not supplied or not secrets.compare_digest(str(supplied), settings.app_token):
            response = HTMLResponse(
                """<!doctype html><html lang='en'><head><meta name='viewport' content='width=device-width,initial-scale=1'>
                <style>
                body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#07192d;color:#fff;display:grid;place-items:center;min-height:100vh;margin:0}.card{max-width:430px;padding:30px;background:#102b47;border:1px solid #294766;border-radius:22px;box-shadow:0 25px 70px #0005}input,button{width:100%;padding:14px;margin-top:12px;border-radius:11px;border:0;font:inherit}button{background:#0f8c7f;color:white;font-weight:800}.tag{font-size:11px;letter-spacing:.15em;color:#92dfd2}</style></head>
                <body><form class='card' method='get'><div class='tag'>FLEETROUTE DECISION SUPPORT</div><h1>Access FleetRoute</h1><p>Enter the access token printed by the launcher.</p><input name='token' type='password' required autocomplete='current-password' placeholder='Access token'><button>Open Control Center</button></form></body></html>""",
                status_code=401,
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'"
            )
            return response

        # The Colab launcher opens ``/?token=...`` once. After successful
        # verification, move the credential into an HttpOnly cookie and clean
        # it out of browser history, copied URLs, screenshots, and referrers.
        # Preserve every unrelated query item and its ordering.
        if query_token and request.method == "GET":
            remaining = [
                (key, value)
                for key, value in request.query_params.multi_items()
                if key != "token"
            ]
            clean_url = request.url.path
            if remaining:
                clean_url += "?" + urlencode(remaining, doseq=True)
            response = RedirectResponse(clean_url, status_code=303)
            response.set_cookie(
                "vrp_app_token", settings.app_token, httponly=True,
                secure=secure_cookie, samesite="lax",
                max_age=60 * 60 * 24 * 7, path="/",
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'"
            )
            return response
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        # The notebook may be replaced without changing the public release
        # number. Revalidate static files so an older app.js is never kept for
        # a year under the same URL after an upgrade.
        response.headers["Cache-Control"] = "no-cache"
    elif request.url.path.startswith("/api/") or request.url.path in {"/", "/simulation"} or request.url.path.startswith("/driver/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    if settings.app_token and request.query_params.get("token"):
        response.set_cookie(
            "vrp_app_token", settings.app_token, httponly=True,
            secure=secure_cookie, samesite="lax",
            max_age=60 * 60 * 24 * 7, path="/",
        )
    # Send only the origin to map providers, never paths, query strings or tokens.
    # OSM requires a Referer for browser tile requests. Login/token redirects
    # above deliberately retain no-referrer until credentials leave the URL.
    response.headers.setdefault("Referrer-Policy", "strict-origin")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "img-src 'self' data: blob: https://tile.openstreetmap.org https://services.arcgisonline.com; "
        "connect-src 'self'; worker-src 'self' blob:"
    )
    if secure_cookie:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


def _validation_json_safe(value: Any) -> Any:
    """Make FastAPI/Pydantic validation details safe for strict JSON output.

    Python's JSON parser accepts non-standard NaN/Infinity tokens. Pydantic then
    correctly rejects them, but the rejected input can be echoed inside
    ``exc.errors()`` and fail Starlette's strict JSON serializer. Never turn a
    malformed numeric request into a secondary 500 while reporting the 422.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(key): _validation_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_validation_json_safe(item) for item in value]
    return str(value)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": _validation_json_safe(exc.errors())})


def _public_error_message(exc: Exception) -> str:
    """Return an actionable browser error without leaking runtime internals.

    Full subprocess/compiler diagnostics remain in persisted job and evidence logs.
    API responses are deliberately bounded because notebook paths, access tokens,
    and multi-megabyte native stderr do not belong in browser alerts.
    """
    text = str(exc).strip() or type(exc).__name__
    if settings.app_token:
        text = text.replace(settings.app_token, "<redacted>")
    replacements = {
        str(RUNTIME_DIR): "<runtime>",
        str(settings.solver_cpp.parent.resolve()): "<app>",
        str(settings.database_path.parent.resolve()): "<runtime>",
    }
    for raw, label in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if raw:
            text = text.replace(raw, label)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 6:
        lines = lines[:6] + ["Full details are available in Evidence & Logs."]
    text = " ".join(lines)
    if len(text) > 900:
        text = text[:820].rstrip() + "… Full details are available in Evidence & Logs."
    return text


def api_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=_public_error_message(exc))


class OSMDownloadPayload(BaseModel):
    force: bool = False

class OSMRegionPayload(BaseModel):
    region_id: str = Field(min_length=1, max_length=120)


class AccessPreviewPayload(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    max_snap_m: float | None = Field(default=None, gt=0, le=10_000, allow_inf_nan=False)


class AccessPreparePayload(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    max_snap_m: float | None = Field(default=None, gt=0, le=10_000, allow_inf_nan=False)


class PlacePayload(BaseModel):
    role: str = "customer"
    name: str
    address: str = ""
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    demand: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    service_s: float = Field(default=300.0, ge=0, allow_inf_nan=False)
    earliest_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    latest_s: float = Field(default=86400.0, ge=0, allow_inf_nan=False)
    external_id: str = ""
    access: dict[str, Any] | None = None
    allow_pending: bool = False


class PlaceUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    lon: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    demand: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    service_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    earliest_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    latest_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class SettingsPayload(BaseModel):
    # Both dictionaries are optional at the transport layer. The engine merges a
    # supplied partial update with the saved operating contract before validating
    # it, so changing one concern cannot reset the other.
    fleet: dict[str, Any] = Field(default_factory=dict)
    solver: dict[str, Any] = Field(default_factory=dict)


class SolvePayload(BaseModel):
    rebuild_network: bool = False
    reason: str = "manual solve"


class DemoPayload(BaseModel):
    count: int = Field(default=12, ge=3, le=500)
    radius_m: float = Field(default=4200.0, ge=400, le=150_000, allow_inf_nan=False)
    seed: int = Field(default=777, ge=0, le=4_294_967_295)
    center_lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    center_lon: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    replace_customers: bool = True
    demand_mode: str = "auto"
    demand_profile: str = "standard"
    demand_min: int = 4
    demand_max: int = 18
    service_mode: str = "auto"
    service_min: int = 5
    service_max: int = 15
    time_window_mode: str = "open"
    trucks: int | None = None
    capacity: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    auto_optimize: bool = False
    run_optimizer: bool = False
    optimizer_clustering: str = "none"


class CompleteDemoPayload(BaseModel):
    count: int = Field(default=12, ge=3, le=100)
    clustering: str = "road_savings"


class SingleClusteringPayload(BaseModel):
    method: str


class PlanImportPayload(BaseModel):
    rows: list[dict[str, Any]]
    replace: bool = False
    use_current_depot: bool = True


class RushPayload(BaseModel):
    rows: list[dict[str, Any]]
    clustering: str = "road_savings"
    replace: bool = True
    use_current_depot: bool = True
    fleet: dict[str, Any] | None = None
    solver: dict[str, Any] | None = None


class SolverPreviewPayload(BaseModel):
    fleet: dict[str, Any] | None = None
    solver: dict[str, Any] | None = None


class BenchmarkPayload(BaseModel):
    root_mode: str = "road_savings"


class ClosurePayload(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    reporter: str = Field(default="driver", min_length=1, max_length=120)
    source_truck_id: int | None = Field(default=None, ge=0)
    note: str = Field(default="", max_length=2000)
    block_reverse: bool = True
    expires_at: str | None = Field(default=None, max_length=64)
    edge: dict[str, Any] | None = None


class ClosureDecision(BaseModel):
    approve: bool
    actor: str = "dispatcher"
    rerun: bool = True


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": settings.app_name, "version": "3.1.4", "startup_id": settings.startup_id}


@app.get("/", response_class=FileResponse)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/driver/{truck_id}", response_class=FileResponse)
def driver_page(truck_id: int = ApiPath(ge=0)):
    return FileResponse(STATIC_DIR / "driver.html")


@app.get("/simulation", response_class=FileResponse)
def simulation_page():
    return FileResponse(STATIC_DIR / "simulation.html")


@app.get("/api/state")
def state(include_routes: bool = Query(default=True)):
    try:
        return app_state(include_routes=include_routes)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/osm/status")
def osm_status():
    try:
        from .offline_osm import region_source_status
        return region_source_status(check_remote=False)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/osm/catalog")
def osm_catalog(geometry: bool = Query(default=True), refresh: bool = Query(default=False)):
    try:
        from .offline_osm import geofabrik_catalog
        return geofabrik_catalog(include_geometry=geometry, force=refresh)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/osm/library")
def osm_library():
    try:
        from .offline_osm import osm_source_library
        return {"items": osm_source_library()}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/osm/region")
def osm_select_region(payload: OSMRegionPayload):
    """Browse a catalog/download target. This does not switch active roads."""
    try:
        from .offline_osm import select_osm_region
        return select_osm_region(payload.region_id)
    except Exception as exc:
        raise api_error(exc)



@app.get("/api/osm/recommend")
def osm_recommend_region(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    """Return a non-mutating region suggestion for one real coordinate."""
    try:
        from .offline_osm import recommend_region_for_points
        return recommend_region_for_points([
            {"role": "depot", "name": "Selected depot", "lat": float(lat), "lon": float(lon)}
        ])
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/osm/activate")
def osm_activate_region(payload: OSMRegionPayload):
    try:
        return activate_region_source(payload.region_id)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/osm/download")
def osm_download(payload: OSMDownloadPayload):
    try:
        return {"job_id": queue_region_download(payload.force)}
    except Exception as exc:
        raise api_error(exc)


@app.delete("/api/osm/source")
def osm_delete():
    try:
        return delete_region_source()
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/preflight")
def preflight():
    try:
        return preflight_status()
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/geocode")
def geocode(q: str = Query(min_length=3, max_length=240), limit: int = Query(default=7, ge=1, le=20)):
    try:
        return {"results": geocode_search(q, limit)}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/access/preview")
def access_preview(payload: AccessPreviewPayload):
    try:
        return preview_road_access(payload.lat, payload.lon, payload.max_snap_m)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/access/prepare", status_code=202)
def access_prepare(payload: AccessPreparePayload):
    try:
        job_id = queue_network_build({"lat": payload.lat, "lon": payload.lon, "max_snap_m": payload.max_snap_m})
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/road-edge/preview")
def edge_preview(payload: AccessPreviewPayload):
    try:
        return preview_road_edge(payload.lat, payload.lon)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/places")
def create_place(payload: PlacePayload):
    try:
        return add_place(payload.model_dump())
    except Exception as exc:
        raise api_error(exc)


@app.patch("/api/places/{place_id}")
def patch_place(place_id: int, payload: PlaceUpdate):
    try:
        return update_place(place_id, payload.model_dump(exclude_none=True))
    except Exception as exc:
        raise api_error(exc)


@app.delete("/api/places/{place_id}")
def delete_place(place_id: int):
    try:
        remove_place(place_id)
        return {"ok": True}
    except Exception as exc:
        raise api_error(exc)


@app.delete("/api/places")
def clear_places():
    try:
        return clear_active_places()
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/demo")
def create_demo(payload: DemoPayload):
    try:
        return generate_demo_plan(**payload.model_dump())
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/scenario/preview")
def preview_scenario(payload: DemoPayload):
    try:
        from .engine import scenario_contract_preview
        return scenario_contract_preview(payload.model_dump())
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/scenario", status_code=202)
def create_scenario(payload: DemoPayload):
    try:
        return {"job_id": queue_scenario_generation(payload.model_dump()), "status": "queued"}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/workflows/demo", status_code=202)
def complete_demo(payload: CompleteDemoPayload):
    try:
        return {"job_id": queue_complete_demo(payload.count, payload.clustering), "status": "queued"}
    except Exception as exc:
        raise api_error(exc)




@app.post("/api/plan/import")
def plan_import(payload: PlanImportPayload):
    try:
        return import_plan_rows(
            payload.rows, replace=payload.replace, use_current_depot=payload.use_current_depot,
            event_action="plan.csv.imported",
        )
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/workflows/rush", status_code=202)
def rush_workflow(payload: RushPayload):
    try:
        job_id = queue_rush_workflow(payload.model_dump())
        return {"job_id": job_id, "status": "queued", "clustering": payload.clustering}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/clustering/test", status_code=202)
def clustering_test(payload: SingleClusteringPayload):
    try:
        return {"job_id": queue_single_clustering(payload.method), "status": "queued", "method": payload.method}
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/solver/profiles")
def get_solver_profiles():
    return solver_profiles()


@app.post("/api/solver/command-preview")
def command_preview(payload: SolverPreviewPayload):
    try:
        fleet = dict(app_state(include_routes=False).get("fleet") or {})
        solver = dict(app_state(include_routes=False).get("solver") or {})
        if payload.fleet:
            fleet.update(payload.fleet)
        if payload.solver:
            solver.update(payload.solver)
        validate_extra_solver_args(solver.get("extra_args", ""))
        preview = solver_command_preview({"fleet": fleet, "solver": solver}, clustering_used=solver.get("clustering") not in {"none", "off", ""})
        return {**preview, "profiles": solver_profiles()}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/settings")
def save_settings(payload: SettingsPayload):
    try:
        return save_operating_settings(payload.fleet, payload.solver)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/network/build", status_code=202)
def build_network():
    try:
        job_id = queue_network_build()
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/network/geojson")
def network_map(
    max_edges: int = Query(default=8000, ge=100, le=25000),
    detail: str = Query(default="balanced"),
):
    try:
        return network_geojson(max_edges, detail)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/network/viewport")
def network_viewport(
    south: float = Query(ge=-90, le=90, allow_inf_nan=False),
    west: float = Query(ge=-180, le=180, allow_inf_nan=False),
    north: float = Query(ge=-90, le=90, allow_inf_nan=False),
    east: float = Query(ge=-180, le=180, allow_inf_nan=False),
    max_edges: int = Query(default=4000, ge=100, le=10000),
):
    try:
        return network_viewport_geojson(south, west, north, east, max_edges=max_edges)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/routes/latest")
def latest_routes_payload():
    from .db import latest_route_version
    return latest_route_version() or {}


@app.post("/api/solve", status_code=202)
def solve(payload: SolvePayload):
    try:
        job_id = queue_solve(payload.rebuild_network, payload.reason)
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/clustering/benchmark", status_code=202)
def clustering_benchmark(payload: BenchmarkPayload):
    try:
        job_id = queue_clustering_benchmark(payload.root_mode)
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/analytics/convergence")
def convergence():
    try:
        return convergence_summary(include_points=True)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/analytics/convergence/build", status_code=202)
def build_convergence_report():
    try:
        job_id = queue_convergence_analysis()
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/developer/runtime")
def developer_runtime():
    try:
        return developer_runtime_overview()
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/developer/files/{file_key}")
def developer_file(
    file_key: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=512 * 1024, ge=16 * 1024, le=2 * 1024 * 1024),
):
    try:
        return read_runtime_file(file_key, offset=offset, limit=limit)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int):
    expire_stale_jobs_if_due()
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/events")
def job_events(
    job_id: int,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=250, ge=1, le=1000),
):
    expire_stale_jobs_if_due()
    job, rows = get_job_with_events(job_id, after, limit)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"events": rows, "job": job}


@app.get("/api/jobs/{job_id}/log-chunk")
def job_log_chunk(
    job_id: int,
    offset: int = Query(default=0, ge=0),
    source: str = Query(default="raw", pattern="^(raw|stdout|stderr|audit)$"),
    limit: int = Query(default=512 * 1024, ge=16 * 1024, le=2 * 1024 * 1024),
    tail_bytes: int = Query(default=0, ge=0, le=2 * 1024 * 1024),
):
    expire_stale_jobs_if_due()
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    audit_path = Path(job.get("log_path") or "")
    suffixes = {"raw": ".raw.log", "stdout": ".stdout.log", "stderr": ".stderr.log"}
    path = audit_path.with_suffix(suffixes[source]) if source in suffixes and audit_path.name else audit_path
    terminal = job.get("status") in {"succeeded", "failed", "cancelled"}
    if not path.is_file():
        return {
            "offset": 0,
            "next_offset": 0,
            "size": 0,
            "text": "",
            "terminal": terminal,
            "at_eof": True,
            "complete": terminal,
            "source": source,
            "truncated_start": False,
        }
    size = path.stat().st_size
    read_limit = max(16 * 1024, min(int(limit), 2 * 1024 * 1024))
    tail_window = max(0, min(int(tail_bytes), 2 * 1024 * 1024))
    if tail_window and int(offset) <= 0:
        safe_offset = max(0, size - tail_window)
    else:
        safe_offset = max(0, min(int(offset), size))
    with path.open("rb") as handle:
        # A tail window can begin in the middle of a UTF-8 character. Advance
        # past continuation bytes so the first visible character is intact.
        while 0 < safe_offset < size:
            handle.seek(safe_offset)
            first = handle.read(1)
            if not first or first[0] & 0xC0 != 0x80:
                break
            safe_offset += 1
        handle.seek(safe_offset)
        raw = handle.read(read_limit)
    at_physical_eof = safe_offset + len(raw) >= size
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    text = decoder.decode(raw, final=at_physical_eof)
    pending, _ = decoder.getstate()
    consumed = len(raw) - len(pending)
    next_offset = safe_offset + consumed
    at_eof = next_offset >= size
    return {
        "offset": safe_offset,
        "next_offset": next_offset,
        "size": size,
        "text": text,
        "terminal": terminal,
        "at_eof": at_eof,
        "complete": terminal and at_eof,
        "source": source,
        "truncated_start": bool(tail_window and safe_offset > 0),
    }


@app.get("/api/jobs/{job_id}/stream")
async def job_stream(job_id: int):
    expire_stale_jobs_if_due()
    initial, _ = get_job_with_events(job_id, 0, 1)
    if not initial:
        raise HTTPException(status_code=404, detail="Job not found")

    async def events():
        last_event = 0
        last_signature = None
        terminal_seen = 0
        last_keepalive = 0.0
        while True:
            expire_stale_jobs_if_due()
            job, rows = get_job_with_events(job_id, last_event, 250)
            if not job:
                break
            for row in rows:
                last_event = max(last_event, int(row["id"]))
                yield "event: job-event\ndata: " + json.dumps(row, ensure_ascii=False) + "\n\n"
            signature = (job.get("updated_at"), job.get("progress"), job.get("message"), job.get("status"))
            if signature != last_signature:
                last_signature = signature
                yield "event: snapshot\ndata: " + json.dumps(job, ensure_ascii=False) + "\n\n"
            if job.get("status") in {"succeeded", "failed", "cancelled"}:
                terminal_seen += 1
                if terminal_seen >= 2:
                    break
            else:
                terminal_seen = 0
            now = asyncio.get_running_loop().time()
            if now - last_keepalive >= 10.0:
                yield ": keepalive\n\n"
                last_keepalive = now
            await asyncio.sleep(0.65)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    if not request_job_cancel(job_id):
        raise HTTPException(status_code=409, detail="Job is not running or cannot be cancelled")
    return {"ok": True, "job_id": job_id}


@app.get("/api/jobs/{job_id}/log", response_class=PlainTextResponse)
def job_log(job_id: int, source: str = Query(default="raw", pattern="^(raw|stdout|stderr|audit)$")):
    try:
        return read_job_log(job_id, source=source)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/closures")
def closures_list():
    try:
        return {"closures": list_closures()}
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/closures")
def create_closure(payload: ClosurePayload):
    try:
        return report_closure(payload.model_dump())
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/closures/{closure_id}/decision")
def closure_decision(closure_id: int, payload: ClosureDecision):
    try:
        return decide_closure(closure_id, payload.approve, payload.actor, payload.rerun)
    except Exception as exc:
        raise api_error(exc)


@app.post("/api/closures/{closure_id}/reopen")
def reopen_closure(
    closure_id: int,
    actor: str = Query(default="dispatcher", min_length=1, max_length=120),
    rerun: bool = Query(default=True),
):
    try:
        return deactivate_closure(closure_id, actor, rerun)
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/export/driver-package")
def driver_package():
    try:
        return FileResponse(create_driver_package(), filename="Driver_Operations_Package.zip")
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/export/run-evidence")
def run_evidence():
    try:
        return FileResponse(create_run_evidence_zip(), filename="FleetRoute_Run_Evidence.zip")
    except Exception as exc:
        raise api_error(exc)


@app.get("/api/artifacts/{artifact_path:path}")
def artifact(artifact_path: str):
    try:
        candidate = (RUNTIME_DIR / artifact_path).resolve()
        candidate.relative_to(RUNTIME_DIR.resolve())
        if not candidate.is_file():
            raise FileNotFoundError("Artifact not found")
        return FileResponse(candidate)
    except Exception as exc:
        raise api_error(exc)
