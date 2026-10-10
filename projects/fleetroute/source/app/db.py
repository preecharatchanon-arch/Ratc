from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from .config import settings

_DB_SCHEMA_LOCK = threading.RLock()
_STALE_CHECK_LOCK = threading.Lock()
_LAST_STALE_CHECK_MONOTONIC = 0.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite connection without a process-wide mutex.

    WAL is enabled once during init_db(). A global Python lock previously
    serialized UI reads, SSE heartbeats, cancellation checks, and worker writes.
    SQLite WAL plus busy_timeout safely arbitrates the rare writer collision
    while allowing independent readers to proceed concurrently.
    """
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        if conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS places (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL CHECK(role IN ('depot','customer')),
        name TEXT NOT NULL,
        address TEXT NOT NULL DEFAULT '',
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        demand REAL NOT NULL DEFAULT 0,
        service_s REAL NOT NULL DEFAULT 0,
        earliest_s REAL NOT NULL DEFAULT 0,
        latest_s REAL NOT NULL DEFAULT 86400,
        external_id TEXT NOT NULL DEFAULT '',
        access_lat REAL,
        access_lon REAL,
        access_road TEXT NOT NULL DEFAULT '',
        access_distance_m REAL,
        access_osm_node TEXT NOT NULL DEFAULT '',
        access_osm_u TEXT NOT NULL DEFAULT '',
        access_osm_v TEXT NOT NULL DEFAULT '',
        access_osm_key TEXT NOT NULL DEFAULT '',
        access_highway TEXT NOT NULL DEFAULT '',
        access_direction TEXT NOT NULL DEFAULT '',
        access_reachable INTEGER NOT NULL DEFAULT 0,
        access_verified INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_active_depot
      ON places(role) WHERE role='depot' AND active=1;

    CREATE TABLE IF NOT EXISTS closures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reported_at TEXT NOT NULL,
        reporter TEXT NOT NULL DEFAULT '',
        source_truck_id INTEGER,
        note TEXT NOT NULL DEFAULT '',
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        road_name TEXT NOT NULL DEFAULT '',
        highway TEXT NOT NULL DEFAULT '',
        osm_u TEXT NOT NULL,
        osm_v TEXT NOT NULL,
        osm_key TEXT NOT NULL,
        geometry_json TEXT NOT NULL DEFAULT '[]',
        snap_distance_m REAL,
        direction_text TEXT NOT NULL DEFAULT '',
        block_reverse INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
        approved_at TEXT,
        approved_by TEXT,
        expires_at TEXT,
        reroute_job_id INTEGER
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        updated_at TEXT,
        heartbeat_at TEXT,
        message TEXT NOT NULL DEFAULT '',
        stage_key TEXT NOT NULL DEFAULT '',
        stage_label TEXT NOT NULL DEFAULT '',
        stage_index INTEGER NOT NULL DEFAULT 0,
        stage_count INTEGER NOT NULL DEFAULT 1,
        progress REAL NOT NULL DEFAULT 0,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        log_path TEXT NOT NULL DEFAULT '',
        result_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS job_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        ts TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'info',
        stage_key TEXT NOT NULL DEFAULT '',
        message TEXT NOT NULL,
        data_json TEXT NOT NULL DEFAULT '{}',
        log_offset INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS job_events_job_id_idx ON job_events(job_id,id);

    CREATE TABLE IF NOT EXISTS route_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        source_job_id INTEGER,
        route_count INTEGER NOT NULL,
        customer_count INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        FOREIGN KEY(source_job_id) REFERENCES jobs(id)
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL DEFAULT 'system',
        action TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS geocode_cache (
        query TEXT PRIMARY KEY,
        response_json TEXT NOT NULL,
        cached_at TEXT NOT NULL
    );
    """
    with _DB_SCHEMA_LOCK:
        with connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(schema)
            # Safe migration from previous FleetRoute prototypes.
            for definition in [
                "access_lat REAL",
                "access_lon REAL",
                "access_road TEXT NOT NULL DEFAULT ''",
                "access_distance_m REAL",
                "access_osm_node TEXT NOT NULL DEFAULT ''",
                "access_osm_u TEXT NOT NULL DEFAULT ''",
                "access_osm_v TEXT NOT NULL DEFAULT ''",
                "access_osm_key TEXT NOT NULL DEFAULT ''",
                "access_highway TEXT NOT NULL DEFAULT ''",
                "access_direction TEXT NOT NULL DEFAULT ''",
                "access_reachable INTEGER NOT NULL DEFAULT 0",
                "access_verified INTEGER NOT NULL DEFAULT 0",
            ]:
                _add_column(conn, "places", definition)
            for definition in [
                "highway TEXT NOT NULL DEFAULT ''",
                "geometry_json TEXT NOT NULL DEFAULT '[]'",
                "snap_distance_m REAL",
                "direction_text TEXT NOT NULL DEFAULT ''",
                "application_status TEXT NOT NULL DEFAULT 'pending'",
                "applied_at TEXT",
                "applied_revision INTEGER NOT NULL DEFAULT 0",
                "route_version_after INTEGER",
                "reroute_deferred INTEGER NOT NULL DEFAULT 0",
                "reroute_message TEXT NOT NULL DEFAULT ''",
                "source_truck_id INTEGER",
            ]:
                _add_column(conn, "closures", definition)
            for definition in [
                "updated_at TEXT",
                "heartbeat_at TEXT",
                "stage_key TEXT NOT NULL DEFAULT ''",
                "stage_label TEXT NOT NULL DEFAULT ''",
                "stage_index INTEGER NOT NULL DEFAULT 0",
                "stage_count INTEGER NOT NULL DEFAULT 1",
                "progress REAL NOT NULL DEFAULT 0",
                "cancel_requested INTEGER NOT NULL DEFAULT 0",
            ]:
                _add_column(conn, "jobs", definition)
            conn.execute("UPDATE jobs SET updated_at=COALESCE(updated_at,created_at), heartbeat_at=COALESCE(heartbeat_at,started_at,created_at)")
            conn.execute("UPDATE closures SET application_status=CASE WHEN status='approved' THEN 'applied' WHEN status='rejected' THEN 'rejected' WHEN status='expired' THEN 'removed' ELSE 'pending' END WHERE application_status IS NULL OR application_status='' OR (status='approved' AND application_status='pending')")
    defaults = {
        "fleet": {
            "trucks": 4,
            "capacity": 100.0,
            "network_type": "drive",
            "network_margin_m": 1200,
            "snap_max_m": 350,
            "network_scope": "regional_offline",
            "operating_radius_m": 8000,
        },
        "solver": {
            "seed": 777,
            "instances": 6,
            "hard_time_limit_s": 30,
            "objective_mode": "distance",
            "use_time_window": True,
            "route_start_time_s": 8 * 3600,
            "allow_multi_trip": False,
            "max_trips_per_truck": 3,
            "clustering": "none",
            "clustering_strict": False,
            "run_convergence_analysis": False,
            "profile": "auto_dynamic",
            "advanced": {},
            "extra_args": "",
        },
        "ui": {"language": "en", "theme": "elite"},
        "osm_setup": {"mode": "regional_offline", "auto_expand": True, "source_ready": False},
        "route_state": {
            "stale": True,
            "reason": "No route has been prepared",
            "route_version": None,
            "route_phase": "empty",
            "optimization_completed": False,
            "optimization_outcome": "not_started",
        },
        "closure_revision": {"revision": 0},
        "pending_reroute": {"pending": False},
        "settings_revision": {"fleet": 0, "solver": 0},
    }
    for key, value in defaults.items():
        if get_setting(key) is None:
            set_setting(key, value)
    # Forward-fill newly introduced fields without replacing a user's existing
    # solver choices when an older runtime database is opened by this release.
    current_solver = get_setting("solver") or {}
    merged_solver = {**defaults["solver"], **current_solver}
    research_overrides = os.getenv("VRP_ENABLE_RESEARCH_SOLVER_OVERRIDES", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not research_overrides:
        # Production deployments never inherit stale research-only argv controls.
        merged_solver["advanced"] = {}
        merged_solver["extra_args"] = ""
        merged_solver["extra_overrides"] = []
    if merged_solver != current_solver:
        set_setting("solver", merged_solver)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_setting(key: str) -> Any:
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM app_settings WHERE key=?", (key,)
        ).fetchone()
    return json.loads(row["value_json"]) if row else None


def get_settings(keys: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Fetch several settings in one SQLite round trip."""
    names = [str(key) for key in keys]
    if not names:
        return {}
    placeholders = ",".join("?" for _ in names)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT key,value_json FROM app_settings WHERE key IN ({placeholders})", names
        ).fetchall()
    result: dict[str, Any] = {}
    for row in rows:
        try:
            result[str(row["key"])] = json.loads(row["value_json"])
        except Exception:
            result[str(row["key"])] = None
    return result


def set_setting(key: str, value: Any) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings(key,value_json,updated_at)
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET
              value_json=excluded.value_json,
              updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), utc_now()),
        )


def log_event(action: str, details: Any = None, actor: str = "system") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events(ts,actor,action,details_json) VALUES(?,?,?,?)",
            (utc_now(), actor, action, json.dumps(details or {}, ensure_ascii=False)),
        )


def create_job(kind: str, message: str = "") -> int:
    with connect() as conn:
        now = utc_now()
        cur = conn.execute(
            "INSERT INTO jobs(kind,status,created_at,updated_at,heartbeat_at,message,stage_count) VALUES(?,?,?,?,?,?,?)",
            (kind, "queued", now, now, now, message, 1),
        )
        return int(cur.lastrowid)


def update_job(job_id: int, **fields: Any) -> None:
    allowed = {
        "status",
        "started_at",
        "finished_at",
        "updated_at",
        "heartbeat_at",
        "message",
        "stage_key",
        "stage_label",
        "stage_index",
        "stage_count",
        "progress",
        "cancel_requested",
        "log_path",
        "result_json",
    }
    pairs = [(k, v) for k, v in fields.items() if k in allowed]
    if not any(k == "updated_at" for k, _ in pairs):
        pairs.append(("updated_at", utc_now()))
    if not pairs:
        return
    columns = ", ".join(f"{k}=?" for k, _ in pairs)
    values = [
        json.dumps(v, ensure_ascii=False)
        if k == "result_json" and not isinstance(v, str)
        else v
        for k, v in pairs
    ]
    values.append(job_id)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {columns} WHERE id=?", values)


def latest_route_version() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM route_versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["payload"] = json.loads(data.pop("payload_json"))
    return data


def get_job(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["result"] = json.loads(item.pop("result_json"))
    except Exception:
        item["result"] = {}
    return item


def create_job_event(
    job_id: int,
    message: str,
    *,
    level: str = "info",
    stage_key: str = "",
    data: Any = None,
    log_offset: int = 0,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO job_events(job_id,ts,level,stage_key,message,data_json,log_offset) VALUES(?,?,?,?,?,?,?)",
            (job_id, utc_now(), level, stage_key, message, json.dumps(data or {}, ensure_ascii=False), int(log_offset)),
        )
        return int(cur.lastrowid)


def list_job_events(job_id: int, after_id: int = 0, limit: int = 250) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM job_events WHERE job_id=? AND id>? ORDER BY id LIMIT ?",
            (job_id, int(after_id), max(1, min(int(limit), 1000))),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["data"] = json.loads(item.pop("data_json"))
        except Exception:
            item["data"] = {}
        result.append(item)
    return result



def get_job_with_events(job_id: int, after_id: int = 0, limit: int = 250) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Read one job snapshot and its new events from one connection."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (int(job_id),)).fetchone()
        if row is None:
            return None, []
        rows = conn.execute(
            "SELECT * FROM job_events WHERE job_id=? AND id>? ORDER BY id LIMIT ?",
            (int(job_id), int(after_id), max(1, min(int(limit), 1000))),
        ).fetchall()
    job = dict(row)
    try:
        job["result"] = json.loads(job.pop("result_json"))
    except Exception:
        job["result"] = {}
    events: list[dict[str, Any]] = []
    for event_row in rows:
        item = dict(event_row)
        try:
            item["data"] = json.loads(item.pop("data_json"))
        except Exception:
            item["data"] = {}
        events.append(item)
    return job, events



def list_active_jobs(*, include_evidence: bool = True) -> list[dict[str, Any]]:
    query = "SELECT * FROM jobs WHERE status IN ('queued','running')"
    params: tuple[Any, ...] = ()
    if not include_evidence:
        query += " AND kind <> ?"
        params = ("evidence",)
    query += " ORDER BY id"
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["result"] = json.loads(item.pop("result_json"))
        except Exception:
            item["result"] = {}
        result.append(item)
    return result


def recover_interrupted_jobs() -> int:
    """Close jobs left active by a disconnected/restarted runtime.

    Background worker threads cannot survive a Python/Colab restart. Leaving
    their rows as ``running`` creates the exact frozen-progress illusion that
    the UI must never show. Recovery is intentionally performed once during
    FastAPI startup, before new workers are queued.
    """
    now = utc_now()
    message = "Interrupted because the application runtime restarted"
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,result_json FROM jobs WHERE status IN ('queued','running')"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["result_json"] or "{}")
            except Exception:
                payload = {}
            payload.update({
                "error": message,
                "interrupted": True,
                "live": {
                    "stage_key": "interrupted",
                    "stage_label": "Interrupted",
                    "progress": float(payload.get("live", {}).get("progress", 0.0) or 0.0),
                    "message": message,
                },
            })
            conn.execute(
                """UPDATE jobs SET status='failed',finished_at=?,updated_at=?,heartbeat_at=?,
                   message=?,stage_key='interrupted',stage_label='Interrupted',
                   cancel_requested=0,result_json=? WHERE id=?""",
                (now, now, now, message, json.dumps(payload, ensure_ascii=False), int(row["id"])),
            )
            conn.execute(
                "INSERT INTO job_events(job_id,ts,level,stage_key,message,data_json,log_offset) VALUES(?,?,?,?,?,?,?)",
                (int(row["id"]), now, "error", "interrupted", message,
                 json.dumps({"runtime_restart": True}, ensure_ascii=False), 0),
            )
    return len(rows)



def expire_stale_jobs(max_silence_s: float = 180.0) -> int:
    """Fail active jobs whose persisted heartbeat stopped unexpectedly.

    Every legitimate long-running FleetRoute operation emits a heartbeat well
    below this threshold, including OSM extraction, Python GIS processing, C++
    compilation, clustering, and solver execution. This watchdog therefore
    prevents a dead worker/thread from remaining visually active forever.
    """
    threshold = datetime.now(timezone.utc) - timedelta(seconds=max(30.0, float(max_silence_s)))
    now = utc_now()
    message = "Worker heartbeat stopped; the job was closed instead of leaving frozen progress"
    expired: list[sqlite3.Row] = []
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,heartbeat_at,result_json,progress,stage_key,stage_label,stage_index,stage_count "
            "FROM jobs WHERE status IN ('queued','running')"
        ).fetchall()
        for row in rows:
            raw = row["heartbeat_at"]
            try:
                heartbeat = datetime.fromisoformat(str(raw)) if raw else None
                if heartbeat and heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=timezone.utc)
            except Exception:
                heartbeat = None
            if heartbeat is not None and heartbeat >= threshold:
                continue
            try:
                payload = json.loads(row["result_json"] or "{}")
            except Exception:
                payload = {}
            progress = round(max(0.0, min(99.9, float(row["progress"] or 0.0))), 1)
            payload.update({
                "error": message,
                "heartbeat_timeout": True,
                "live": {
                    "stage_key": str(row["stage_key"] or "stalled"),
                    "stage_label": str(row["stage_label"] or "Stalled"),
                    "stage_index": int(row["stage_index"] or 0),
                    "stage_count": max(1, int(row["stage_count"] or 1)),
                    "progress": progress,
                    "message": message,
                },
            })
            conn.execute(
                """UPDATE jobs SET status='failed',finished_at=?,updated_at=?,heartbeat_at=?,
                   message=?,progress=?,result_json=? WHERE id=?""",
                (now, now, now, message, progress, json.dumps(payload, ensure_ascii=False), int(row["id"])),
            )
            conn.execute(
                "INSERT INTO job_events(job_id,ts,level,stage_key,message,data_json,log_offset) VALUES(?,?,?,?,?,?,?)",
                (int(row["id"]), now, "error", str(row["stage_key"] or "stalled"), message,
                 json.dumps({"heartbeat_timeout": True, "max_silence_s": float(max_silence_s)}, ensure_ascii=False), 0),
            )
            expired.append(row)
    return len(expired)

def expire_stale_jobs_if_due(max_silence_s: float = 180.0, min_interval_s: float = 3.0) -> int:
    """Throttle watchdog scans used by high-frequency read endpoints."""
    global _LAST_STALE_CHECK_MONOTONIC
    interval = max(0.25, float(min_interval_s))
    now = time.monotonic()
    if now - _LAST_STALE_CHECK_MONOTONIC < interval:
        return 0
    with _STALE_CHECK_LOCK:
        now = time.monotonic()
        if now - _LAST_STALE_CHECK_MONOTONIC < interval:
            return 0
        count = expire_stale_jobs(max_silence_s)
        _LAST_STALE_CHECK_MONOTONIC = now
        return count


def request_job_cancel(job_id: int) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["status"] not in {"queued", "running"}:
            return False
        conn.execute("UPDATE jobs SET cancel_requested=1,updated_at=? WHERE id=?", (utc_now(), job_id))
    return True


def job_cancel_requested(job_id: int) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
    return bool(row and row["cancel_requested"])
