from __future__ import annotations

import csv
import html
import json
import shutil
import zipfile
import threading
from pathlib import Path
from urllib.parse import urlencode

from .config import RUNTIME_DIR, settings
from .db import get_setting, latest_route_version


def _coord(stop: dict) -> str:
    return f"{float(stop['lat']):.7f},{float(stop['lon']):.7f}"


def _maps_url(stops: list[dict]) -> str:
    if len(stops) < 2:
        return ""
    params = [
        ("api", "1"),
        ("origin", _coord(stops[0])),
        ("destination", _coord(stops[-1])),
        ("travelmode", "driving"),
        ("dir_action", "navigate"),
    ]
    if len(stops) > 2:
        params.append(("waypoints", "|".join(_coord(s) for s in stops[1:-1])))
    return "https://www.google.com/maps/dir/?" + urlencode(params)


def _split_stops(stops: list[dict], max_waypoints: int = 9) -> list[list[dict]]:
    max_locations = max_waypoints + 2
    chunks = []
    start = 0
    while start < len(stops) - 1:
        end = min(len(stops), start + max_locations)
        chunk = stops[start:end]
        if len(chunk) < 2:
            break
        chunks.append(chunk)
        start = end - 1
    return chunks


def _trip_groups(stops: list[dict]) -> list[list[dict]]:
    if not stops:
        return []
    groups: list[list[dict]] = []
    current = [stops[0]]
    for index, stop in enumerate(stops[1:], 1):
        current.append(stop)
        if stop.get("kind") == "depot" and len(current) > 1:
            groups.append(current)
            if index < len(stops) - 1:
                current = [stop]
    if len(current) > 1 and (not groups or groups[-1][-1] is not current[-1]):
        groups.append(current)
    return groups


_DRIVER_PACKAGE_LOCK = threading.Lock()


def _clock(value: object) -> str:
    try:
        seconds = max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return "—"
    return f"{(seconds // 3600) % 24:02d}:{(seconds % 3600) // 60:02d}"


def _plan_status(payload: dict, route_state: dict, version_id: int | None = None) -> dict:
    source = str(route_state.get("solution_source") or payload.get("solution_source") or "")
    completed = bool(
        route_state.get("optimization_completed")
        or route_state.get("optimization_checked_at")
        or source == "cpp_optimizer"
    )
    displayed_version = int(version_id or payload.get("version_id") or 0)
    state_version = int(route_state.get("route_version") or 0)
    # Treat missing/mismatched publication identity as stale even if a legacy or
    # recovered database incorrectly says stale=false. External navigation is a
    # field action and therefore requires an exact route-state generation match.
    stale = bool(route_state.get("stale")) or displayed_version <= 0 or state_version != displayed_version
    if stale:
        return {"phase": "stale", "badge": "STALE", "title": "Plan does not match current inputs", "detail": "Re-optimize before operational use", "completed": False}
    if not completed:
        return {"phase": "prepared", "badge": "INITIAL PLAN", "title": "Constraint-valid initial plan", "detail": "No completed optimizer result is published yet", "completed": False}
    if source == "cpp_optimizer":
        return {"phase": "optimized", "badge": "OPTIMIZED", "title": "Routing complete", "detail": "Optimization completed and passed independent validation", "completed": True}
    return {"phase": "reviewed", "badge": "COMPLETED", "title": "Routing complete · initial plan retained", "detail": "Optimization completed and was validated, but no better route was found", "completed": True}


def _driver_html(route: dict, version_id: int, plan_status: dict) -> str:
    stops = route["stops"]
    customer_stop_count = sum(stop.get("kind") == "customer" for stop in stops)
    route_json = json.dumps(route, ensure_ascii=False).replace("</", "<\\/")
    route_buttons = []
    navigation_allowed = plan_status.get("phase") != "stale"
    trip_groups = _trip_groups(stops)
    if navigation_allowed:
        for trip_number, trip in enumerate(trip_groups, 1):
            chunks = _split_stops(trip)
            for part_number, chunk in enumerate(chunks, 1):
                suffix = f" · part {part_number}/{len(chunks)}" if len(chunks) > 1 else ""
                route_buttons.append(
                    f'<a class="maps" href="{html.escape(_maps_url(chunk), quote=True)}" target="_blank" rel="noopener">'
                    f'Open Google Maps · trip {trip_number}{suffix}</a>'
                )
    else:
        route_buttons.append('<span class="maps disabled" aria-disabled="true">Navigation disabled · plan update required</span>')
    def _tw_label(stop: dict) -> str:
        raw = str(stop.get("time_window_status") or "").strip().casefold()
        labels = {
            "not_enforced": "Not enforced",
            "on_time": "On time",
            "waiting": "Waiting",
            "late": "Late",
            "depot": "Depot",
        }
        return labels.get(raw, raw.replace("_", " ").title() if raw else "—")

    rows = []
    for stop in stops:
        orders = stop.get("orders") or []
        label = "Depot" if stop.get("kind") == "depot" else " · ".join(str(o.get("name", "Work point")) for o in orders) or "Work point"
        rows.append(
            f"<tr><td>{int(stop.get('sequence', 0))}</td><td>{html.escape(label)}</td>"
            f"<td>{int(stop.get('trip_number') or 1)}</td><td>{float(stop.get('demand', 0)):.1f}</td>"
            f"<td>{_clock(stop.get('arrival_s'))}</td><td>{_clock(stop.get('service_start_s'))}</td>"
            f"<td>{_clock(stop.get('earliest_s', stop.get('earliest')))}–{_clock(stop.get('latest_s', stop.get('latest')))}</td>"
            f"<td>{float(stop.get('waiting_s') or 0)/60:.0f} min</td><td>{html.escape(_tw_label(stop))}</td>"
            f"<td>{float(stop.get('lat')):.6f}, {float(stop.get('lon')):.6f}</td></tr>"
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Truck {route['truck_id']} · FleetRoute</title>
<link rel="stylesheet" href="assets/leaflet/leaflet.css">
<style>
:root{{--navy:#0b1f3a;--teal:#0f766e;--mint:#e2f5f1;--paper:#f4f7fa;--ink:#172033;--line:#d7e0e9}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:var(--ink)}}
.hero{{background:linear-gradient(135deg,#081b32,#143f62);color:white;padding:28px 20px}}.hero>div{{max-width:1180px;margin:auto}}
.tag{{font-size:11px;letter-spacing:.16em;color:#9fe3d6;font-weight:800}}h1{{margin:6px 0 4px;font-size:clamp(28px,5vw,48px)}}p{{margin:0;color:#d2deea}}
main{{max-width:1180px;margin:-16px auto 40px;padding:0 14px}}.card{{background:white;border:1px solid var(--line);border-radius:20px;box-shadow:0 18px 50px rgba(11,31,58,.12);overflow:hidden;margin-bottom:18px}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:18px}}.metric{{background:#f7fafc;border-radius:13px;padding:12px}}.metric span{{display:block;font-size:11px;color:#667085}}.metric b{{font-size:20px;color:var(--navy)}}
#map{{height:430px}}.actions{{display:flex;flex-wrap:wrap;gap:10px;padding:16px}}.maps{{background:var(--teal);color:white;text-decoration:none;border-radius:12px;padding:12px 15px;font-weight:800}}.maps.disabled{{background:#e9eef2;color:#71818d;cursor:not-allowed}}
table{{width:100%;border-collapse:collapse;min-width:760px}}th,td{{padding:11px 12px;border-bottom:1px solid #e9eef3;text-align:left}}th{{background:#edf3f7;color:var(--navy);font-size:11px;text-transform:uppercase}}.scroll{{overflow:auto}}
.plan-state{{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:16px;padding:13px 15px;border:1px solid #d7e0e9;border-radius:13px;background:#f8fafb}}.plan-state b,.plan-state small{{display:block}}.plan-state small{{margin-top:2px;color:#667085}}.plan-state span{{padding:7px 10px;border-radius:999px;background:#e6edf1;font-size:10px;font-weight:900;letter-spacing:.08em}}.plan-state.prepared{{border-color:#e8d0a4;background:#fff9ef}}.plan-state.prepared span{{background:#ffebc5;color:#8b5a0d}}.plan-state.optimized,.plan-state.reviewed{{border-color:#b7dfd7;background:#effaf7}}.plan-state.optimized span,.plan-state.reviewed span{{background:#d8f2ec;color:#087166}}.plan-state.stale{{border-color:#e8c3bc;background:#fff3f0}}.plan-state.stale span{{background:#f3dcd7;color:#96382e}}
.notice{{margin:0 16px 16px;background:var(--mint);border-left:4px solid var(--teal);padding:12px;border-radius:10px;font-size:13px}}
@media(max-width:700px){{.summary{{grid-template-columns:1fr 1fr}}#map{{height:340px}}}}
</style></head><body>
<header class="hero"><div><div class="tag">OFFLINE DRIVER MANIFEST</div><h1>Truck {route['truck_id']} · Route v{version_id}</h1><p>Published stop order, schedule, and road geometry</p></div></header>
<main><section class="card"><div class="plan-state {plan_status['phase']}"><div><b>{html.escape(plan_status['title'])}</b><small>{html.escape(plan_status['detail'])}</small></div><span>{html.escape(plan_status['badge'])}</span></div><div class="summary"><div class="metric"><span>Work stops</span><b>{customer_stop_count}</b></div><div class="metric"><span>Distance</span><b>{float(route.get('distance_m',0))/1000:.1f} km</b></div><div class="metric"><span>Operating window</span><b>{_clock(route.get('route_start_time_s'))}–{_clock(route.get('finish_time_s'))}</b></div><div class="metric"><span>Trips</span><b>{int(route.get('trip_count') or 1)}</b></div></div><div id="map"></div><div class="actions">{''.join(route_buttons)}</div><div class="notice">{('This plan is stale. Do not use external navigation until dispatch publishes an updated route. ' if plan_status['phase']=='stale' else '')}The published manifest, schedule, and route geometry remain available offline. Basemap tiles require internet access. Google Maps is only a navigation handoff and may not model vehicle height, weight, access, or hazardous-cargo restrictions.</div></section>
<section class="card scroll"><table><thead><tr><th>#</th><th>Work stop</th><th>Trip</th><th>Demand</th><th>ETA</th><th>Service start</th><th>Time window</th><th>Wait</th><th>Status</th><th>Coordinates</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section></main>
<script src="assets/leaflet/leaflet.js"></script><script>
const route={route_json};const map=L.map('map');const fallback='data:image/svg+xml;charset=UTF-8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="%23eaf0f4"/></svg>');L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19,attribution:'© OpenStreetMap',errorTileUrl:fallback}}).addTo(map);
const line=L.polyline(route.geometry||[],{{color:'{('#0f766e' if plan_status['completed'] else '#c18322')}',weight:6,opacity:.88,dashArray:{('null' if plan_status['completed'] else "'12 9'")}}}).addTo(map);(route.stops||[]).forEach(s=>L.circleMarker([s.lat,s.lon],{{radius:s.kind==='depot'?8:6,color:'#fff',weight:2,fillColor:s.kind==='depot'?'#0b1f3a':'#0f766e',fillOpacity:1}}).bindPopup(`<b>${{s.sequence}} · ${{s.kind}}</b>`).addTo(map));if(line.getBounds().isValid())map.fitBounds(line.getBounds(),{{padding:[25,25]}});else if(route.stops?.length)map.setView([route.stops[0].lat,route.stops[0].lon],14);
</script></body></html>"""


def create_driver_package() -> Path:
    # Generation uses one shared staging directory as well as one final ZIP.
    # Keep the *entire* export under one lock: locking only the ZIP writer lets
    # concurrent requests delete each other's staging files before packaging.
    with _DRIVER_PACKAGE_LOCK:
        latest = latest_route_version()
        if not latest:
            raise ValueError("No fleet-plan route version exists")
        payload = latest["payload"]
        version_id = int(latest["id"])
        plan_status = _plan_status(payload, get_setting("route_state") or {}, version_id)
        output_dir = RUNTIME_DIR / "DriverOperations"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)
        leaflet_source = Path(__file__).resolve().parent / "static" / "vendor" / "leaflet"
        shutil.copytree(leaflet_source, output_dir / "assets" / "leaflet")
        route_links = []
        for route in payload.get("routes", []):
            name = f"truck_{int(route['truck_id']):03d}.html"
            (output_dir / name).write_text(_driver_html(route, version_id, plan_status), encoding="utf-8")
            route_links.append((route, name))
        cards = []
        for route, name in route_links:
            customer_stop_count = sum(
                stop.get("kind") == "customer" for stop in route.get("stops", [])
            )
            cards.append(
                f'<a class="truck" href="{name}"><span>TRUCK {route["truck_id"]}</span><b>{customer_stop_count} work stops</b><small>{float(route.get("distance_m",0))/1000:.1f} km · open driver manifest →</small></a>'
            )
        dashboard = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FleetRoute Driver Operations</title><style>*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f2f6f9;color:#172033}}header{{background:#0b1f3a;color:#fff;padding:34px}}header div,main{{max-width:1100px;margin:auto}}h1{{margin:4px 0}}p{{color:#c9d7e5}}main{{padding:24px 16px}}.status{{margin-bottom:16px;padding:12px 14px;border:1px solid #d6e0e9;border-radius:13px;background:#fff}}.status b,.status small{{display:block}}.status small{{margin-top:3px;color:#667085}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:15px}}.truck{{background:#fff;border:1px solid #d6e0e9;border-radius:18px;padding:18px;text-decoration:none;color:#172033;box-shadow:0 10px 30px rgba(11,31,58,.08)}}.truck span{{display:block;color:#0f766e;font-size:11px;font-weight:800;letter-spacing:.13em}}.truck b{{display:block;font-size:26px;color:#0b1f3a;margin:5px 0}}.truck small{{color:#667085}}</style></head><body><header><div><small>FLEETROUTE · DRIVER OPERATIONS</small><h1>All driver manifests</h1><p>Fleet plan version {version_id} · manifests and schedules work offline</p></div></header><main><div class="status"><b>{html.escape(plan_status['title'])} · {html.escape(plan_status['badge'])}</b><small>{html.escape(plan_status['detail'])}</small></div><div class="grid">{''.join(cards)}</div></main></body></html>"""
        (output_dir / "OPEN_ALL_TRUCKS.html").write_text(dashboard, encoding="utf-8")
        (output_dir / "routes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with (output_dir / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["truck_id", "sequence", "trip_number", "kind", "name", "lat", "lon", "demand", "arrival_s", "service_start_s", "departure_s", "earliest_s", "latest_s", "waiting_s", "time_window_status"])
            for route in payload.get("routes", []):
                for stop in route.get("stops", []):
                    names = " / ".join(str(o.get("name", "")) for o in stop.get("orders", []))
                    # This CSV is part of the driver package, not the raw solver
                    # evidence bundle, so use the same human-readable status the
                    # HTML manifest shows instead of leaking internal enum text.
                    tw_status = str(stop.get("time_window_status") or "").strip().casefold()
                    tw_status = {
                        "not_enforced": "Not enforced",
                        "on_time": "On time",
                        "waiting": "Waiting",
                        "late": "Late",
                        "depot": "Depot",
                    }.get(tw_status, tw_status.replace("_", " ").title() if tw_status else "")
                    writer.writerow([route["truck_id"], stop["sequence"], stop.get("trip_number", 1), stop["kind"], names, stop["lat"], stop["lon"], stop.get("demand", 0), stop.get("arrival_s"), stop.get("service_start_s"), stop.get("departure_s"), stop.get("earliest_s", stop.get("earliest")), stop.get("latest_s", stop.get("latest")), stop.get("waiting_s", 0), tw_status])
        zip_path = settings.driver_package_zip
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        temp_zip = zip_path.with_suffix(zip_path.suffix + ".tmp")
        temp_zip.unlink(missing_ok=True)
        try:
            with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in output_dir.rglob("*"):
                    if file.is_symlink() or not file.is_file():
                        continue
                    resolved = file.resolve(strict=True)
                    resolved.relative_to(output_dir.resolve())
                    archive.write(resolved, arcname=str(resolved.relative_to(output_dir.parent.resolve())))
            temp_zip.replace(zip_path)
        finally:
            temp_zip.unlink(missing_ok=True)
        return zip_path
