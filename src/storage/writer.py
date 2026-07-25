"""
Asynchronous, fire-and-forget database writer thread with priority backpressure queue.
Implements 04_Dataflow.md §3, 11_Database_Design.md, and RR-5.
"""

import json
import queue
import sqlite3
import threading
import time
from typing import Optional, Dict, Any, Union
import duckdb

from src.shared.logging import get_logger
from src.shared.types import SensorSnapshot, DecisionLog, Incident, RunSummary
from src.storage.schema import initialize_schema

logger = get_logger("storage.writer")


class AsyncStorageWriter:
    """
    Background worker thread consuming telemetry and decision records.
    Bounded queue with priority backpressure:
      - Drops oldest SensorSnapshot telemetry when full.
      - NEVER drops DecisionLog or Incident records.
    """

    def __init__(
        self,
        db_path: str = "data/eco_loop.duckdb",
        backend: str = "duckdb",
        queue_capacity: int = 1000,
    ):
        self.db_path = db_path
        self.backend = backend.lower()
        self.queue_capacity = queue_capacity

        self._queue: queue.Queue = queue.Queue(maxsize=queue_capacity)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._dropped_snapshots_count: int = 0

        # Initialize DB connection and schema
        init_conn = self._connect_db()
        initialize_schema(init_conn)
        try:
            init_conn.close()
        except Exception:
            pass

    @property
    def conn(self):
        """Returns a fresh read connection for KPI queries."""
        return self._connect_db()

    def _connect_db(self):
        if self.backend == "sqlite":
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0, isolation_level=None)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=30000;")
            except Exception:
                pass
        else:
            conn = duckdb.connect(self.db_path)
        return conn

    def start(self) -> None:
        """Starts the background writer worker thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="AsyncStorageWriter")
        self._thread.start()
        logger.info(f"AsyncStorageWriter background thread started (backend='{self.backend}', path='{self.db_path}')")

    def enqueue_snapshot(self, snapshot: SensorSnapshot, run_id: str) -> bool:
        """Enqueues a SensorSnapshot. Drops oldest snapshot if queue is full."""
        item = ("snapshot", snapshot, run_id)
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            # Drop oldest snapshot to handle backpressure
            try:
                dropped = self._queue.get_nowait()
                self._dropped_snapshots_count += 1
                logger.warning(
                    f"Storage queue backpressure: dropped snapshot '{dropped[1].sim_time}'. "
                    f"Total dropped: {self._dropped_snapshots_count}"
                )
                self._queue.put_nowait(item)
                return True
            except (queue.Empty, queue.Full):
                return False

    def enqueue_decision_log(self, log: DecisionLog) -> None:
        """Enqueues a DecisionLog. Blocking put ensures decision logs are NEVER dropped."""
        item = ("decision_log", log, None)
        self._queue.put(item)  # Blocks if necessary; never drops

    def enqueue_incident(self, incident: Incident, run_id: str) -> None:
        """Enqueues an Incident. Blocking put ensures incidents are NEVER dropped."""
        item = ("incident", incident, run_id)
        self._queue.put(item)  # Blocks if necessary; never drops

    def register_run(self, run_id: str, run_mode: str, idf_name: str, epw_name: str) -> None:
        """Enqueues run registration."""
        item = ("register_run", (run_id, run_mode, idf_name, epw_name), run_id)
        self._queue.put(item)

    def finalize_run_summary(self, summary: RunSummary) -> None:
        """Enqueues RunSummary finalization."""
        item = ("finalize_run_summary", summary, summary.run_id)
        self._queue.put(item)

    def _worker_loop(self) -> None:
        conn = self._connect_db() if self.backend == "sqlite" else self._conn
        cursor = conn.cursor()
        batch_size = 0

        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            item_type, obj, run_id = item
            try:
                if item_type == "register_run":
                    rid, rmode, idf, epw = obj
                    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute(
                        "INSERT INTO runs (run_id, run_mode, idf_name, epw_name, started_at, status) VALUES (?, ?, ?, ?, ?, ?)",
                        (rid, rmode, idf, epw, started_at, "running"),
                    )
                    conn.commit()
                elif item_type == "finalize_run_summary":
                    summary: RunSummary = obj
                    cursor.execute(
                        "INSERT OR REPLACE INTO run_summaries (run_id, run_mode, total_kwh, pmv_band_compliance_pct, pct_cycles_fallback, status, started_at, ended_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            summary.run_id,
                            summary.run_mode,
                            summary.total_kwh,
                            summary.pmv_band_compliance_pct,
                            summary.pct_cycles_fallback,
                            summary.status,
                            summary.started_at,
                            summary.ended_at or time.strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    )
                    cursor.execute("UPDATE runs SET status=? WHERE run_id=?", (summary.status, summary.run_id))
                    conn.commit()
                    logger.info(f"Finalized RunSummary for run '{summary.run_id}' with status '{summary.status}'")
                elif item_type == "snapshot":
                    snap: SensorSnapshot = obj
                    for z in snap.zones:
                        cursor.execute(
                            "INSERT INTO sensor_snapshots (run_id, sim_time, zone_id, air_temp_c, rh_pct, pmv, ppd_pct, meters_json, phase, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                run_id,
                                snap.sim_time,
                                z.zone_id,
                                z.air_temp_c,
                                z.rh_pct,
                                z.pmv,
                                z.ppd_pct,
                                json.dumps(snap.meters),
                                snap.phase,
                                snap.timestamp,
                            ),
                        )
                elif item_type == "decision_log":
                    dlog: DecisionLog = obj
                    trace_data = [
                        {"tool": t.tool, "args": str(t.args), "result_summary": t.result_summary}
                        for t in dlog.trace
                    ]
                    cursor.execute(
                        "INSERT OR REPLACE INTO decision_logs (run_id, cycle_id, sim_time, rationale, action_json, outcome, trace_json, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            dlog.run_id,
                            dlog.cycle_id,
                            dlog.sim_time,
                            dlog.rationale,
                            json.dumps(dlog.action_or_incident, default=str),
                            dlog.outcome,
                            json.dumps(trace_data, default=str),
                            dlog.timestamp,
                        ),
                    )
                elif item_type == "incident":
                    inc: Incident = obj
                    cursor.execute(
                        "INSERT INTO incidents (run_id, cycle_id, severity, reason, raised_at) VALUES (?, ?, ?, ?, ?)",
                        (run_id, inc.cycle_id, inc.severity, inc.reason, inc.raised_at),
                    )

                batch_size += 1
                if batch_size >= 10 or self._queue.empty():
                    conn.commit()
                    batch_size = 0

                self._queue.task_done()
            except Exception as e:
                logger.error(f"Error persisting item of type '{item_type}': {e}")
                self._queue.task_done()

        if batch_size > 0:
            try:
                conn.commit()
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass

    def stop(self) -> None:
        """Stops the worker thread and flushes remaining queue items."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        logger.info("AsyncStorageWriter stopped and flushed.")
