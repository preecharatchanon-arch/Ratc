from __future__ import annotations

import os
import queue
import re
import shlex
import signal
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .db import (
    create_job_event,
    get_job,
    job_cancel_requested,
    update_job,
    utc_now,
)


class JobCancelled(RuntimeError):
    pass


def _terminate_process_tree(process: subprocess.Popen, *, grace_s: float = 4.0) -> None:
    """Terminate the complete Unix process group owned by one job process.

    Compiler/GIS wrappers can spawn descendants. Killing only the immediate
    parent leaves CPU-heavy children running after a timeout/cancel in Colab.
    On non-POSIX hosts we fall back to the direct subprocess API.
    """
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


class JobReporter:
    """Structured job status with flushed audit and decoded process-stream logs."""

    def __init__(self, job_id: int, log_path: Path, *, stage_count: int) -> None:
        self.job_id = int(job_id)
        self.log_path = Path(log_path)
        self.stage_count = max(1, int(stage_count))
        self.stage_key = "queued"
        self.stage_label = "Queued"
        self.stage_index = 0
        self.progress = 0.0
        self._message = "Queued"
        self._started_monotonic = time.monotonic()
        self._stage_started_monotonic = self._started_monotonic
        # The database heartbeat remains high-frequency for liveness, while
        # the human-readable audit file is rate limited so it stays useful.
        self._last_audit_heartbeat_monotonic = self._started_monotonic
        self._audit_heartbeat_interval_s = 2.0
        # Child cancellation polls are capped at ~4 Hz. The previous 80 ms
        # query opened ~12 SQLite connections/second per process for no
        # user-visible benefit and competed with SSE/UI reads.
        self._last_cancel_check_monotonic = 0.0
        self._cancel_poll_interval_s = 0.25
        self._cancel_cached = False
        self._result_cache: dict[str, Any] = dict((get_job(self.job_id) or {}).get("result") or {})
        self._stage_timings: list[dict[str, Any]] = []
        self._last_recorded_stage_index = 0
        self._lock = threading.RLock()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("", encoding="utf-8")
        # Keep one line-buffered handle per job. The previous implementation
        # opened and fsynced the file for every solver line, which made verbose
        # runs dramatically slower and delayed the UI itself.
        self._log_handle = self.log_path.open("a", encoding="utf-8", buffering=1)
        self.raw_log_path = self.log_path.with_suffix(".raw.log")
        self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.raw_log_path.exists():
            self.raw_log_path.write_text("", encoding="utf-8")
        self._raw_log_handle = self.raw_log_path.open("a", encoding="utf-8", buffering=1)
        self.stdout_log_path = self.log_path.with_suffix(".stdout.log")
        self.stderr_log_path = self.log_path.with_suffix(".stderr.log")
        for stream_path in [self.stdout_log_path, self.stderr_log_path]:
            if not stream_path.exists():
                stream_path.write_text("", encoding="utf-8")
        self._stdout_log_handle = self.stdout_log_path.open("a", encoding="utf-8", buffering=1)
        self._stderr_log_handle = self.stderr_log_path.open("a", encoding="utf-8", buffering=1)
        self._closed = False
        # Structured, low-rate optimizer telemetry. The native solver already
        # emits a validated process-wide incumbent event *after* hard-feasibility
        # validation. We consume those existing stderr lines here rather than
        # asking the C++ hot loop to write another live file or duplicate global
        # best state. The payload is persisted by the normal 0.5 s heartbeat.
        self._optimizer_live_state: dict[str, Any] | None = None
        self._optimizer_curve_limit = 192
        # Timing receipt for the most recent child process. Generic callers still
        # receive the historical (returncode, wall_seconds) tuple, while solver
        # orchestration can separately consume native-preparation and governed
        # search time without confusing the user's search budget with process wall.
        self._last_process_timing: dict[str, Any] = {}
        update_job(
            self.job_id,
            log_path=str(self.log_path),
            stage_count=self.stage_count,
            progress=0.0,
            stage_index=0,
            stage_key="queued",
            stage_label="Queued",
            heartbeat_at=utc_now(),
        )

    def log_offset(self) -> int:
        try:
            return int(self.log_path.stat().st_size)
        except OSError:
            return 0

    def raw_log_offset(self) -> int:
        try:
            return int(self.raw_log_path.stat().st_size)
        except OSError:
            return 0

    def last_process_timing(self) -> dict[str, Any]:
        """Return a copy of the latest child timing receipt."""
        with self._lock:
            return dict(self._last_process_timing)

    def append_raw(self, text: str) -> None:
        """Write the merged process stream plus explicit command/exit boundaries."""
        if text is None:
            return
        text = str(text)
        with self._lock:
            if self._closed:
                return
            self._raw_log_handle.write(text)
            self._raw_log_handle.flush()

    def append_stdout(self, text: str) -> None:
        if text is None:
            return
        with self._lock:
            if not self._closed:
                self._stdout_log_handle.write(str(text))
                self._stdout_log_handle.flush()

    def append_stderr(self, text: str) -> None:
        if text is None:
            return
        with self._lock:
            if not self._closed:
                self._stderr_log_handle.write(str(text))
                self._stderr_log_handle.flush()

    def append(self, text: str, *, prefix_time: bool = False) -> None:
        if text is None:
            return
        text = str(text)
        if prefix_time:
            text = f"[{utc_now()}] {text}"
        if not text.endswith("\n"):
            text += "\n"
        with self._lock:
            if self._closed:
                return
            self._log_handle.write(text)
            # flush() makes bytes visible to /log-chunk immediately without the
            # extreme storage penalty of fsync() for every output line.
            self._log_handle.flush()

    @staticmethod
    def _native_key_values(line: str) -> dict[str, str]:
        return {match.group(1): match.group(2) for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)", line)}

    def _ingest_optimizer_telemetry(self, items: list[tuple[str, str]]) -> None:
        """Recover authoritative live incumbent changes from native stderr.

        EvidenceWarmStart exposes independently validated construction incumbents
        without mutating the solver governor; EvidenceGlobal/EvidenceCheckpoint
        cover the process-wide search incumbent after the native hard-feasibility
        gate. Together they give the live UI a truthful start-to-finish curve
        without polling convergence.csv while it is still being produced.
        """
        state = self._optimizer_live_state
        for source, line in items:
            if source != "stderr" or not line:
                continue

            phase: str | None = None
            if "[BackendPrep]" in line:
                phase = "road-cost-preparation"
            elif "[EvidenceWarmStart]" in line or "[SavingsWarmStart]" in line:
                phase = "initial-route-construction"
            elif "[ClusterWarmStartReceipt]" in line:
                phase = "validated-warm-start"
            elif "[SolverConfig]" in line:
                phase = "optimizer-initialization"
            elif "[EliteEvolution]" in line:
                phase = "solution-refinement"
            elif "[AnytimeTransition-E1]" in line:
                phase = "final-refinement"
            elif "[PhaseEngine-E32]" in line:
                lower = line.lower()
                if "transition_to_final_mode" in lower:
                    phase = "final-refinement"
                elif " end" in lower or "event=end" in lower:
                    phase = "search-complete"
                else:
                    phase = "adaptive-search"

            if phase is not None:
                if state is None:
                    state = {
                        "schema": 1,
                        "source": "validated_incumbent_evidence",
                        "curve": [],
                        "global_best": None,
                        "improvement_events": 0,
                        "curve_decimated": False,
                    }
                state["phase"] = phase

            if "[BackendPrep]" in line and state is not None:
                prep_values = self._native_key_values(line)
                prep: dict[str, Any] = {"event": str(prep_values.get("event") or "progress")}
                for key in ("sources_done", "sources_total", "graph_nodes", "graph_edges"):
                    try:
                        prep[key] = int(float(prep_values[key]))
                    except (KeyError, TypeError, ValueError):
                        pass
                try:
                    prep["elapsed_s"] = round(float(prep_values["elapsed_s"]), 6)
                except (KeyError, TypeError, ValueError):
                    pass
                state["backend_prep"] = prep

            if ("[EvidenceWarmStart]" not in line and
                    "[EvidenceGlobal]" not in line and
                    "[EvidenceCheckpoint]" not in line):
                continue

            values = self._native_key_values(line)
            try:
                time_s = float(values.get("time_s", "nan"))
                objective = float(values.get("objective", "nan"))
            except (TypeError, ValueError):
                continue
            if not (time_s >= 0.0 and objective > 0.0):
                continue

            if state is None:
                state = {
                    "schema": 1,
                    "source": "validated_incumbent_evidence",
                    "curve": [],
                    "global_best": None,
                    "improvement_events": 0,
                    "curve_decimated": False,
                }

            previous = state.get("global_best")
            # A process-wide incumbent is monotone by construction. Reject any
            # malformed/out-of-order diagnostic that would claim regression.
            if previous is not None and objective >= float(previous) - 1e-9:
                continue

            event_name = str(values.get("event") or (
                "validated_warm_start" if "[EvidenceWarmStart]" in line
                else "global_feasible_improvement" if "[EvidenceGlobal]" in line
                else "validated_checkpoint"
            ))
            point = {
                "time_s": round(time_s, 6),
                "best": objective,
                "event": event_name,
            }
            curve = list(state.get("curve") or [])
            curve.append(point)
            state["global_best"] = objective
            state["last_improvement_time_s"] = round(time_s, 6)
            state["last_event"] = event_name
            state["improvement_events"] = int(state.get("improvement_events") or 0) + 1

            # Keep heartbeat JSON bounded. We only drop old *real* incumbent
            # events; no interpolation or synthetic point is ever introduced.
            if len(curve) > self._optimizer_curve_limit:
                middle = curve[1:-1:2]
                curve = [curve[0], *middle, curve[-1]]
                state["curve_decimated"] = True
            state["curve"] = curve

        if state is not None:
            self._optimizer_live_state = state
            self._result_cache["optimizer_live"] = dict(state)

    def sync_log(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._log_handle.flush()
            self._raw_log_handle.flush()
            self._stdout_log_handle.flush()
            self._stderr_log_handle.flush()
            try:
                os.fsync(self._log_handle.fileno())
            except OSError:
                pass

    def close_log(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._log_handle.flush()
            self._raw_log_handle.flush()
            self._stdout_log_handle.flush()
            self._stderr_log_handle.flush()
            self._log_handle.close()
            self._raw_log_handle.close()
            self._stdout_log_handle.close()
            self._stderr_log_handle.close()
            self._closed = True

    def merge_result(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._result_cache.update(patch)
            update_job(self.job_id, result_json=self._result_cache)
            return dict(self._result_cache)

    def _record_stage_timing_locked(self, now_mono: float | None = None) -> None:
        """Persist one timing record per completed stage without another timer thread."""
        if self.stage_index <= 0 or self.stage_index == self._last_recorded_stage_index:
            return
        now_mono = time.monotonic() if now_mono is None else float(now_mono)
        self._stage_timings.append({
            "key": self.stage_key,
            "label": self.stage_label,
            "index": self.stage_index,
            "elapsed_s": round(max(0.0, now_mono - self._stage_started_monotonic), 3),
        })
        self._last_recorded_stage_index = self.stage_index

    def _performance_payload_locked(self, now_mono: float | None = None) -> dict[str, Any]:
        now_mono = time.monotonic() if now_mono is None else float(now_mono)
        return {
            "job_elapsed_s": round(max(0.0, now_mono - self._started_monotonic), 3),
            "stage_timings": list(self._stage_timings),
        }

    def stage(
        self,
        key: str,
        label: str,
        index: int,
        progress: float,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        progress = round(max(0.0, min(100.0, float(progress))), 1)
        index = max(0, min(self.stage_count, int(index)))
        with self._lock:
            now_mono = time.monotonic()
            self._record_stage_timing_locked(now_mono)
            self.stage_key = str(key)
            self.stage_label = str(label)
            self.stage_index = index
            self.progress = progress
            self._message = str(message)
            self._stage_started_monotonic = now_mono
            extra = dict(data or {})
            extra.setdefault("indeterminate", False)
            extra.setdefault("progress_kind", "milestone")
            # Publish an offset only after the matching audit record is
            # flushed. Otherwise an SSE snapshot can point at bytes that do
            # not exist yet and the UI may miss the stage until a later poll.
            self.append(f"\n=== {index}/{self.stage_count} · {label} · {progress:.1f}% ===\n{message}")
            audit_offset = self.log_offset()
            live = {
                "stage_key": self.stage_key,
                "stage_label": self.stage_label,
                "stage_index": self.stage_index,
                "stage_count": self.stage_count,
                "progress": self.progress,
                "message": self._message,
                "job_elapsed_s": round(time.monotonic() - self._started_monotonic, 2),
                "stage_elapsed_s": 0.0,
                "log_offset": audit_offset,
                "raw_log_offset": self.raw_log_offset(),
                "raw_log_path": str(self.raw_log_path),
                **extra,
            }
            self._result_cache["live"] = live
            self._result_cache["performance"] = self._performance_payload_locked(now_mono)
            update_job(
                self.job_id,
                message=self._message,
                stage_key=self.stage_key,
                stage_label=self.stage_label,
                stage_index=self.stage_index,
                stage_count=self.stage_count,
                progress=self.progress,
                heartbeat_at=utc_now(),
                result_json=self._result_cache,
            )
            event_id = create_job_event(
                self.job_id,
                str(message),
                level=level,
                stage_key=self.stage_key,
                data={"label": self.stage_label, "index": index, "count": self.stage_count, "progress": progress, **extra},
                log_offset=audit_offset,
            )
            live["event_id"] = event_id
            self._result_cache["live"] = live
            # Persist the event id without another read/merge transaction.
            update_job(self.job_id, result_json=self._result_cache)
            self.sync_log()

    def heartbeat(
        self,
        progress: float | None = None,
        message: str | None = None,
        *,
        data: dict[str, Any] | None = None,
        force: bool = False,
    ) -> None:
        now_mono = time.monotonic()
        with self._lock:
            if progress is not None:
                self.progress = round(max(0.0, min(99.9, float(progress))), 1)
            if message is not None:
                self._message = str(message)
            extra = dict(data or {})
            if extra.get("indeterminate"):
                extra.setdefault("progress_kind", "indeterminate")
            elif "phase_progress" in extra or (extra.get("total") and extra.get("done") is not None):
                extra.setdefault("progress_kind", "measured")
            else:
                extra.setdefault("progress_kind", "milestone")
            should_audit = force or now_mono - self._last_audit_heartbeat_monotonic >= self._audit_heartbeat_interval_s
            if should_audit:
                elapsed = max(0.0, now_mono - self._started_monotonic)
                message_one_line = " ".join(self._message.splitlines()).strip()
                self.append(
                    f"[HEARTBEAT +{elapsed:.1f}s] {self.stage_index}/{self.stage_count} · "
                    f"{self.stage_label} · {self.progress:.1f}% · {message_one_line}"
                )
                self._last_audit_heartbeat_monotonic = now_mono
            audit_offset = self.log_offset()
            live = {
                "stage_key": self.stage_key,
                "stage_label": self.stage_label,
                "stage_index": self.stage_index,
                "stage_count": self.stage_count,
                "progress": self.progress,
                "message": self._message,
                "job_elapsed_s": round(now_mono - self._started_monotonic, 2),
                "stage_elapsed_s": round(now_mono - self._stage_started_monotonic, 2),
                "log_offset": audit_offset,
                "raw_log_offset": self.raw_log_offset(),
                "raw_log_path": str(self.raw_log_path),
                **extra,
            }
            self._result_cache["live"] = live
            update_job(
                self.job_id,
                heartbeat_at=utc_now(),
                progress=self.progress,
                stage_key=self.stage_key,
                stage_label=self.stage_label,
                stage_index=self.stage_index,
                stage_count=self.stage_count,
                message=self._message,
                result_json=self._result_cache,
            )

    def check_cancelled(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_cancel_check_monotonic >= self._cancel_poll_interval_s:
            self._last_cancel_check_monotonic = now
            self._cancel_cached = bool(job_cancel_requested(self.job_id))
        if self._cancel_cached:
            raise JobCancelled("Cancelled by user")

    def finish(self, message: str, result: dict[str, Any] | None = None) -> None:
        now_mono = time.monotonic()
        with self._lock:
            self._record_stage_timing_locked(now_mono)
            performance = self._performance_payload_locked(now_mono)
            self.append(f"\n=== COMPLETE · 100.0% ===\n{message}")
            audit_offset = self.log_offset()
        payload = dict(self._result_cache)
        payload.update(result or {})
        payload["performance"] = performance
        if self._last_process_timing:
            # Preserve the final native-process clock breakdown after the live
            # heartbeat is replaced by the terminal payload. This is especially
            # useful for distinguishing road-cost preparation, governed search,
            # and a true watchdog overrun in Evidence & Logs.
            payload["process_timing"] = dict(self._last_process_timing)
        payload["live"] = {
            "stage_key": "complete",
            "stage_label": "Complete",
            "stage_index": self.stage_count,
            "stage_count": self.stage_count,
            "progress": 100.0,
            "message": str(message),
            "job_elapsed_s": round(now_mono - self._started_monotonic, 2),
            "stage_elapsed_s": round(now_mono - self._stage_started_monotonic, 2),
            "progress_kind": "complete",
            "indeterminate": False,
            "log_offset": audit_offset,
            "raw_log_offset": self.raw_log_offset(),
            "raw_log_path": str(self.raw_log_path),
        }
        event_id = create_job_event(
            self.job_id,
            str(message),
            level="success",
            stage_key="complete",
            data={"progress": 100.0},
            log_offset=audit_offset,
        )
        payload["live"]["event_id"] = event_id
        update_job(
            self.job_id,
            status="succeeded",
            finished_at=utc_now(),
            heartbeat_at=utc_now(),
            message=str(message),
            stage_key="complete",
            stage_label="Complete",
            stage_index=self.stage_count,
            stage_count=self.stage_count,
            progress=100.0,
            result_json=payload,
        )
        self.sync_log()
        self.close_log()

    def fail(self, error: BaseException, *, cancelled: bool = False) -> None:
        message = "Cancelled by user" if cancelled else str(error)
        now_mono = time.monotonic()
        with self._lock:
            self._record_stage_timing_locked(now_mono)
            performance = self._performance_payload_locked(now_mono)
            self.append(f"\n=== {'CANCELLED' if cancelled else 'FAILED'} ===\n{message}")
            audit_offset = self.log_offset()
        payload = dict(self._result_cache)
        payload.update({"error": message, "cancelled": bool(cancelled), "performance": performance})
        if self._last_process_timing:
            payload["process_timing"] = dict(self._last_process_timing)
        payload["live"] = {
            "stage_key": self.stage_key,
            "stage_label": self.stage_label,
            "stage_index": self.stage_index,
            "stage_count": self.stage_count,
            "progress": round(self.progress, 1),
            "message": message,
            "job_elapsed_s": round(now_mono - self._started_monotonic, 2),
            "stage_elapsed_s": round(now_mono - self._stage_started_monotonic, 2),
            "progress_kind": "terminal",
            "indeterminate": False,
            "log_offset": audit_offset,
            "raw_log_offset": self.raw_log_offset(),
            "raw_log_path": str(self.raw_log_path),
        }
        event_id = create_job_event(
            self.job_id,
            message,
            level="warning" if cancelled else "error",
            stage_key=self.stage_key,
            data={"progress": self.progress, "cancelled": bool(cancelled)},
            log_offset=audit_offset,
        )
        payload["live"]["event_id"] = event_id
        # Keep the legacy status set compatible with existing SQLite databases.
        update_job(
            self.job_id,
            status="cancelled" if cancelled else "failed",
            finished_at=utc_now(),
            heartbeat_at=utc_now(),
            message=message,
            progress=round(self.progress, 1),
            result_json=payload,
        )
        self.sync_log()
        self.close_log()

    def run_process(
        self,
        command: Iterable[str],
        *,
        cwd: Path,
        stdin_path: Path | None = None,
        mirror_path: Path | None = None,
        stdout_mirror_path: Path | None = None,
        stderr_mirror_path: Path | None = None,
        timeout_s: float,
        expected_s: float | None = None,
        budget_start_marker: str | None = None,
        pre_budget_timeout_s: float | None = None,
        progress_start: float,
        progress_end: float,
        progress_label: str,
        env: dict[str, str] | None = None,
    ) -> tuple[int, float]:
        """Run a subprocess while preserving decoded merged, stdout, and stderr text streams."""
        raw_command = [str(item) for item in command]
        command_text = shlex.join(raw_command)
        self.append("PROCESS COMMAND\n" + command_text)
        self.append_raw("$ " + command_text + "\n")
        if stdin_path is not None:
            try:
                stdin_size = stdin_path.stat().st_size
            except OSError:
                stdin_size = -1
            self.append_raw(f"[stdin: {stdin_path} · {stdin_size} bytes]\n")

        if shutil.which("stdbuf"):
            command = ["stdbuf", "-oL", "-eL", *raw_command]
        else:
            command = raw_command

        input_handle = stdin_path.open("r", encoding="utf-8") if stdin_path else None

        def open_mirror(path: Path | None):
            if path is None:
                return None
            path.parent.mkdir(parents=True, exist_ok=True)
            return path.open("w", encoding="utf-8", buffering=1)

        mirror_handle = open_mirror(mirror_path)
        stdout_mirror_handle = open_mirror(stdout_mirror_path)
        stderr_mirror_handle = open_mirror(stderr_mirror_path)

        # FleetRoute owns a small, structured stderr envelope around every
        # native process.  A quiet child (or one that exits before its first
        # cerr flush) must never make a real solver launch look as if it never
        # happened.  These lines are deliberately written to the same stderr
        # destinations as child cerr, so the UI, downloadable evidence, and
        # per-job diagnostics all see one truthful lifecycle.
        terminal_evidence_written = False

        def emit_stderr_evidence(line: str) -> None:
            text = line.rstrip("\n") + "\n"
            self.append_raw(text)
            self.append_stderr(text)
            if stderr_mirror_handle is not None:
                stderr_mirror_handle.write(text)
                stderr_mirror_handle.flush()
            if mirror_handle is not None:
                mirror_handle.write(text)
                mirror_handle.flush()

        started = time.monotonic()
        with self._lock:
            self._last_process_timing = {
                "status": "launching",
                "budget_marker_required": bool(budget_start_marker),
                "budget_s": float(expected_s) if expected_s is not None else None,
            }
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=input_handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                errors="replace",
                start_new_session=(os.name != "nt"),
            )
        except Exception as exc:
            # The child was not created, but the attempted native invocation is
            # still operational evidence. Keep the stderr contract intact so a
            # missing binary/bad cwd cannot look like an optimizer that was
            # never started.
            launch_elapsed = time.monotonic() - started
            with self._lock:
                self._last_process_timing = {
                    "status": "launch_failed", "process_elapsed_s": launch_elapsed,
                    "governed_elapsed_s": None, "preparation_elapsed_s": launch_elapsed,
                    "budget_started": False,
                    "budget_s": float(expected_s) if expected_s is not None else None,
                }
            emit_stderr_evidence(
                "[FleetRouteProcess] event=ERROR "
                f"pid=unavailable elapsed_s={launch_elapsed:.2f} "
                f"overall_pct={float(progress_start):.2f} "
                f"error={type(exc).__name__} state=launch_failed"
            )
            if input_handle is not None:
                input_handle.close()
            for handle in [mirror_handle, stdout_mirror_handle, stderr_mirror_handle]:
                if handle is not None:
                    handle.flush()
                    handle.close()
            raise
        # Make process ownership visible immediately. Previously the first audit
        # evidence after PROCESS COMMAND could be delayed until a child line or
        # the 0.5 s heartbeat, which made a quiet C++ startup look like no solver
        # had been launched at all.
        self.append(f"PROCESS START · {progress_label} · pid {process.pid}")
        budget_value = float(expected_s) if expected_s and float(expected_s) > 0 else 0.0
        emit_stderr_evidence(
            "[FleetRouteProcess] event=START "
            f"pid={process.pid} stage={self.stage_index}/{self.stage_count} "
            f"elapsed_s=0.0 budget_s={budget_value:.2f} phase_pct=0.00 "
            f"overall_pct={float(progress_start):.2f} state=running"
        )
        self.heartbeat(
            progress_start,
            f"{progress_label} · process started",
            data={
                "elapsed_s": 0.0,
                "process_pid": process.pid,
                "process_alive": True,
                "stdout_log_path": str(self.stdout_log_path),
                "stderr_log_path": str(self.stderr_log_path),
            },
        )

        line_queue: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=20_000)

        def reader(stream, source: str) -> None:
            assert stream is not None
            try:
                for line in iter(stream.readline, ""):
                    line_queue.put((source, line))
            finally:
                line_queue.put((source, None))

        threads = [
            threading.Thread(target=reader, args=(process.stdout, "stdout"), daemon=True, name=f"job-{self.job_id}-stdout"),
            threading.Thread(target=reader, args=(process.stderr, "stderr"), daemon=True, name=f"job-{self.job_id}-stderr"),
        ]
        for thread in threads:
            thread.start()

        eof_sources: set[str] = set()
        process_exit_seen_at: float | None = None
        last_heartbeat = 0.0
        last_progress_evidence = -1.0
        # A route-search budget may intentionally start *after* native road-cost
        # preparation.  Keep those clocks separate so a large directed graph is
        # not killed merely because dense-pair preprocessing consumed the small
        # fixed grace that follows the user-selected search budget.
        budget_started_at: float | None = None
        budget_started_process_elapsed_s: float | None = None

        def write_chunks(items: list[tuple[str, str]]) -> None:
            nonlocal budget_started_at, budget_started_process_elapsed_s
            if not items:
                return
            if budget_start_marker and budget_started_at is None:
                for source, text in items:
                    if source == "stderr" and budget_start_marker in text:
                        budget_started_at = time.monotonic()
                        budget_started_process_elapsed_s = budget_started_at - started
                        break
            self._ingest_optimizer_telemetry(items)
            merged = "".join(text for _, text in items)
            stdout_text = "".join(text for source, text in items if source == "stdout")
            stderr_text = "".join(text for source, text in items if source == "stderr")
            self.append_raw(merged)
            if stdout_text:
                self.append_stdout(stdout_text)
                if stdout_mirror_handle is not None:
                    stdout_mirror_handle.write(stdout_text)
                    stdout_mirror_handle.flush()
            if stderr_text:
                self.append_stderr(stderr_text)
                if stderr_mirror_handle is not None:
                    stderr_mirror_handle.write(stderr_text)
                    stderr_mirror_handle.flush()
            if mirror_handle is not None:
                mirror_handle.write(merged)
                mirror_handle.flush()

        try:
            while True:
                self.check_cancelled()

                # Drain native lines before evaluating the watchdog.  In
                # marker-aware mode this prevents a just-emitted BudgetScope
                # receipt from sitting in the queue while the outer process
                # clock incorrectly fires.
                drained: list[tuple[str, str]] = []
                while len(drained) < 500:
                    try:
                        source, item = line_queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        eof_sources.add(source)
                    else:
                        drained.append((source, item))
                write_chunks(drained)

                now = time.monotonic()
                elapsed = now - started
                governed_elapsed = (
                    max(0.0, now - budget_started_at)
                    if budget_started_at is not None else None
                )
                timeout_phase = "process"
                timeout_elapsed = elapsed
                timeout_limit = float(timeout_s)
                if budget_start_marker:
                    if budget_started_at is None:
                        timeout_phase = "native_preparation"
                        timeout_limit = float(pre_budget_timeout_s or timeout_s)
                    else:
                        timeout_phase = "governed_search"
                        timeout_elapsed = float(governed_elapsed or 0.0)

                if timeout_elapsed > timeout_limit:
                    with self._lock:
                        self._last_process_timing = {
                            "status": "timeout",
                            "phase": timeout_phase,
                            "process_elapsed_s": elapsed,
                            "governed_elapsed_s": governed_elapsed,
                            "preparation_elapsed_s": (
                                budget_started_process_elapsed_s
                                if budget_started_process_elapsed_s is not None else elapsed
                            ),
                            "budget_started": budget_started_at is not None,
                            "budget_s": float(expected_s) if expected_s is not None else None,
                            "timeout_s": timeout_limit,
                        }
                    _terminate_process_tree(process, grace_s=5.0)
                    for thread in threads:
                        thread.join(timeout=0.5)
                    timed_out_items: list[tuple[str, str]] = []
                    while True:
                        try:
                            source, item = line_queue.get_nowait()
                        except queue.Empty:
                            break
                        if item is not None:
                            timed_out_items.append((source, item))
                    write_chunks(timed_out_items)
                    emit_stderr_evidence(
                        "[FleetRouteProcess] event=TIMEOUT "
                        f"pid={process.pid} phase={timeout_phase} process_elapsed_s={elapsed:.2f} "
                        f"governed_elapsed_s={(governed_elapsed if governed_elapsed is not None else -1.0):.2f} "
                        f"timeout_s={timeout_limit:.2f} overall_pct={float(self.progress):.2f} state=failed"
                    )
                    terminal_evidence_written = True
                    if timeout_phase == "native_preparation":
                        raise TimeoutError(
                            f"{progress_label} road-cost preparation exceeded the {timeout_limit:.0f}-second preparation limit"
                        )
                    budget_text = (
                        f"{float(expected_s):.0f}s search budget and {max(0.0, timeout_limit - float(expected_s)):.0f}s shutdown grace"
                        if expected_s is not None else f"{timeout_limit:.0f}s execution limit"
                    )
                    raise TimeoutError(
                        f"{progress_label} did not exit within the configured limit ({budget_text})"
                    )

                if now - last_heartbeat >= 0.50:
                    # When a process has a configured time/search budget, report
                    # *budget consumption* as a measured quantity. This is not an
                    # estimate of solution quality or completion; it simply keeps
                    # the UI honest and live instead of sitting at one percentage
                    # and then jumping at process exit.
                    budget_s = float(expected_s) if expected_s and float(expected_s) > 0 else None
                    if budget_s is not None:
                        if budget_start_marker and budget_started_at is None:
                            phase_progress = 0.0
                            overall_progress = progress_start
                            heartbeat_data = {
                                "elapsed_s": 0.0,
                                "process_elapsed_s": round(elapsed, 2),
                                "governed_elapsed_s": 0.0,
                                "budget_started": False,
                                "process_pid": process.pid,
                                "indeterminate": True,
                                "progress_kind": "indeterminate",
                                "phase_progress": None,
                                "phase_metric": "native_route_cost_preparation",
                                "budget_s": round(budget_s, 2),
                                "process_alive": True,
                                "stdout_log_path": str(self.stdout_log_path),
                                "stderr_log_path": str(self.stderr_log_path),
                            }
                            message = f"Preparing native route-cost backend · {elapsed:.1f}s"
                        else:
                            measured_elapsed = float(governed_elapsed if governed_elapsed is not None else elapsed)
                            phase_progress = min(99.5, max(0.0, measured_elapsed / budget_s * 100.0))
                            overall_progress = progress_start + (progress_end - progress_start) * phase_progress / 100.0
                            heartbeat_data = {
                                "elapsed_s": round(measured_elapsed, 2),
                                "process_elapsed_s": round(elapsed, 2),
                                "governed_elapsed_s": round(measured_elapsed, 2),
                                "budget_started": True,
                                "budget_started_process_elapsed_s": (
                                    round(float(budget_started_process_elapsed_s), 2)
                                    if budget_started_process_elapsed_s is not None else None
                                ),
                                "process_pid": process.pid,
                                "indeterminate": False,
                                "progress_kind": "measured",
                                "phase_progress": round(phase_progress, 2),
                                "phase_metric": "time_budget_used",
                                "budget_s": round(budget_s, 2),
                                "process_alive": True,
                                "stdout_log_path": str(self.stdout_log_path),
                                "stderr_log_path": str(self.stderr_log_path),
                            }
                            message = f"{progress_label} · {measured_elapsed:.1f}s / {budget_s:.0f}s search budget"
                    else:
                        overall_progress = progress_start
                        heartbeat_data = {
                            "elapsed_s": round(elapsed, 2),
                            "process_pid": process.pid,
                            "indeterminate": True,
                            "process_alive": True,
                            "stdout_log_path": str(self.stdout_log_path),
                            "stderr_log_path": str(self.stderr_log_path),
                        }
                        message = f"{progress_label} · {elapsed:.1f}s · live process"
                    self.heartbeat(overall_progress, message, data=heartbeat_data)
                    last_heartbeat = now

                # Persist a human-readable progress sample once per second.
                # The database heartbeat remains twice as frequent for smooth
                # UI animation; the evidence file stays compact and useful.
                if now - last_progress_evidence >= 1.0:
                    budget_s = float(expected_s) if expected_s and float(expected_s) > 0 else 0.0
                    measured_elapsed = (
                        float(governed_elapsed)
                        if governed_elapsed is not None else (0.0 if budget_start_marker else elapsed)
                    )
                    phase_pct = min(99.5, max(0.0, measured_elapsed / budget_s * 100.0)) if budget_s else 0.0
                    overall_pct = (
                        progress_start + (progress_end - progress_start) * phase_pct / 100.0
                        if budget_s else progress_start
                    )
                    emit_stderr_evidence(
                        "[FleetRouteProgress] event=PROGRESS "
                        f"pid={process.pid} stage={self.stage_index}/{self.stage_count} "
                        f"process_elapsed_s={elapsed:.2f} governed_elapsed_s={measured_elapsed:.2f} "
                        f"budget_started={1 if (not budget_start_marker or budget_started_at is not None) else 0} "
                        f"budget_s={budget_s:.2f} phase_pct={phase_pct:.2f} "
                        f"overall_pct={overall_pct:.2f} state=running"
                    )
                    last_progress_evidence = now

                returncode = process.poll()
                if returncode is not None:
                    if process_exit_seen_at is None:
                        process_exit_seen_at = time.monotonic()
                    if (len(eof_sources) == 2 and line_queue.empty()) or time.monotonic() - process_exit_seen_at > 2.0:
                        break
                time.sleep(0.08)

            for thread in threads:
                thread.join(timeout=0.5)
            final_items: list[tuple[str, str]] = []
            while True:
                try:
                    source, item = line_queue.get_nowait()
                except queue.Empty:
                    break
                if item is not None:
                    final_items.append((source, item))
            write_chunks(final_items)

            elapsed = time.monotonic() - started
            governed_final = (
                max(0.0, time.monotonic() - budget_started_at)
                if budget_started_at is not None else None
            )
            preparation_final = (
                budget_started_process_elapsed_s
                if budget_started_process_elapsed_s is not None
                else (elapsed if budget_start_marker else 0.0)
            )
            returncode = int(process.returncode or 0)
            with self._lock:
                self._last_process_timing = {
                    "status": "complete" if returncode == 0 else "failed",
                    "process_elapsed_s": elapsed,
                    "governed_elapsed_s": governed_final,
                    "preparation_elapsed_s": preparation_final,
                    "budget_started": budget_started_at is not None,
                    "budget_s": float(expected_s) if expected_s is not None else None,
                    "returncode": returncode,
                }
            timing_suffix = (
                f" · {elapsed:.1f}s total · {governed_final:.1f}s search"
                if governed_final is not None else f" · {elapsed:.1f}s"
            )
            self.append(f"PROCESS EXIT · {progress_label} · code {returncode}{timing_suffix}")
            emit_stderr_evidence(
                "[FleetRouteProcess] event=EXIT "
                f"pid={process.pid} code={returncode} process_elapsed_s={elapsed:.2f} "
                f"governed_elapsed_s={(governed_final if governed_final is not None else -1.0):.2f} "
                f"preparation_elapsed_s={preparation_final:.2f} "
                f"budget_started={1 if budget_started_at is not None else 0} "
                f"budget_s={(float(expected_s) if expected_s is not None else 0.0):.2f} "
                f"phase_pct=100.00 overall_pct={float(progress_end):.2f} "
                f"state={'complete' if returncode == 0 else 'failed'}"
            )
            terminal_evidence_written = True
            heartbeat_elapsed = (
                governed_final if budget_start_marker and governed_final is not None else elapsed
            )
            self.heartbeat(
                progress_end,
                f"{progress_label} complete{timing_suffix}",
                data={
                    "elapsed_s": round(float(heartbeat_elapsed), 2),
                    "process_elapsed_s": round(elapsed, 2),
                    "governed_elapsed_s": (
                        round(float(governed_final), 2) if governed_final is not None else None
                    ),
                    "preparation_elapsed_s": round(float(preparation_final), 2),
                    "budget_started": budget_started_at is not None,
                    "budget_s": float(expected_s) if expected_s is not None else None,
                    "returncode": returncode,
                    "indeterminate": False,
                    "process_alive": False,
                    "stdout_log_path": str(self.stdout_log_path),
                    "stderr_log_path": str(self.stderr_log_path),
                },
                force=True,
            )
            return returncode, elapsed
        except JobCancelled:
            cancelled_elapsed = time.monotonic() - started
            cancelled_governed = (
                max(0.0, time.monotonic() - budget_started_at)
                if budget_started_at is not None else None
            )
            with self._lock:
                self._last_process_timing = {
                    "status": "cancelled", "process_elapsed_s": cancelled_elapsed,
                    "governed_elapsed_s": cancelled_governed,
                    "preparation_elapsed_s": (
                        budget_started_process_elapsed_s
                        if budget_started_process_elapsed_s is not None else cancelled_elapsed
                    ),
                    "budget_started": budget_started_at is not None,
                    "budget_s": float(expected_s) if expected_s is not None else None,
                }
            _terminate_process_tree(process, grace_s=4.0)
            for thread in threads:
                thread.join(timeout=0.5)
            cancelled_items: list[tuple[str, str]] = []
            while True:
                try:
                    source, item = line_queue.get_nowait()
                except queue.Empty:
                    break
                if item is not None:
                    cancelled_items.append((source, item))
            write_chunks(cancelled_items)
            emit_stderr_evidence(
                "[FleetRouteProcess] event=CANCELLED "
                f"pid={process.pid} elapsed_s={time.monotonic() - started:.2f} "
                f"overall_pct={float(self.progress):.2f} state=cancelled"
            )
            terminal_evidence_written = True
            raise
        except Exception as exc:
            error_elapsed = time.monotonic() - started
            error_governed = (
                max(0.0, time.monotonic() - budget_started_at)
                if budget_started_at is not None else None
            )
            with self._lock:
                if self._last_process_timing.get("status") != "timeout":
                    self._last_process_timing = {
                        "status": "error", "process_elapsed_s": error_elapsed,
                        "governed_elapsed_s": error_governed,
                        "preparation_elapsed_s": (
                            budget_started_process_elapsed_s
                            if budget_started_process_elapsed_s is not None else error_elapsed
                        ),
                        "budget_started": budget_started_at is not None,
                        "budget_s": float(expected_s) if expected_s is not None else None,
                        "error": type(exc).__name__,
                    }
            if process.poll() is None:
                _terminate_process_tree(process, grace_s=4.0)
            if not terminal_evidence_written:
                emit_stderr_evidence(
                    "[FleetRouteProcess] event=ERROR "
                    f"pid={process.pid} code={process.returncode if process.returncode is not None else 'unknown'} "
                    f"elapsed_s={time.monotonic() - started:.2f} "
                    f"overall_pct={float(self.progress):.2f} error={type(exc).__name__} state=failed"
                )
                terminal_evidence_written = True
            raise
        finally:
            if input_handle is not None:
                input_handle.close()
            for stream in [process.stdout, process.stderr]:
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            for handle in [mirror_handle, stdout_mirror_handle, stderr_mirror_handle]:
                if handle is not None:
                    handle.flush()
                    handle.close()
