"""
Unit tests for AsyncStorageWriter, priority backpressure handling, and query functions.
Implements Stage 3 checklist requirements.
"""

import pytest
import os
import tempfile
import time
from src.storage.writer import AsyncStorageWriter
from src.storage import queries
from src.shared.types import SensorSnapshot, ZoneState, DecisionLog, Incident, RunSummary, ToolTrace


@pytest.fixture
def temp_sqlite_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            pass


def test_sqlite_writer_async_persistence(temp_sqlite_db):
    writer = AsyncStorageWriter(db_path=temp_sqlite_db, backend="sqlite", queue_capacity=100)
    writer.start()

    run_id = "run_test_01"
    writer.register_run(run_id, run_mode="agent", idf_name="base.idf", epw_name="test.epw")

    # Enqueue a SensorSnapshot
    snap = SensorSnapshot(
        sim_time="Day_1_Hour_12.00",
        zones=[ZoneState("Zone1", 22.5, 45.0, None, 0.1, 5.5, {"htg_sp": 20.0})],
        meters={"facility_electricity_kw": 12.5},
    )
    writer.enqueue_snapshot(snap, run_id)

    # Enqueue a DecisionLog
    dlog = DecisionLog(
        run_id=run_id,
        cycle_id="cycle_100",
        sim_time="Day_1_Hour_12.00",
        rationale="Comfort priority",
        action_or_incident={"htg_sp": 20.5},
        outcome="committed",
        trace=[ToolTrace("propose_setpoints", {"w_energy": 0.5}, "candidate generated")],
    )
    writer.enqueue_decision_log(dlog)

    # Enqueue an Incident
    inc = Incident("cycle_101", "LLM timeout", "warning")
    writer.enqueue_incident(inc, run_id)

    # Finalize RunSummary
    summary = RunSummary(
        run_id=run_id,
        run_mode="agent",
        total_kwh=120.5,
        pmv_band_compliance_pct=95.0,
        pct_cycles_fallback=0.0,
        status="completed",
    )
    writer.finalize_run_summary(summary)

    # Flush writer
    writer.stop()
    time.sleep(0.2)

    # Re-open connection to verify persistence via queries
    conn = writer._connect_db()
    try:
        snapshots = queries.get_recent_snapshots(conn, run_id, limit=10)
        assert len(snapshots) == 1
        assert snapshots[0]["sim_time"] == "Day_1_Hour_12.00"
        assert snapshots[0]["air_temp_c"] == 22.5

        trace = queries.get_decision_trace(conn, "cycle_100")
        assert trace is not None
        assert trace["rationale"] == "Comfort priority"
        assert trace["outcome"] == "committed"

        incidents = queries.get_recent_incidents(conn, run_id)
        assert len(incidents) == 1
        assert incidents[0]["reason"] == "LLM timeout"

        sum_res = queries.get_run_summary(conn, run_id)
        assert sum_res is not None
        assert sum_res["total_kwh"] == 120.5
        assert sum_res["pmv_band_compliance_pct"] == 95.0
    finally:
        conn.close()


def test_priority_backpressure_drops_snapshots_first(temp_sqlite_db):
    # Small capacity queue (capacity = 2)
    writer = AsyncStorageWriter(db_path=temp_sqlite_db, backend="sqlite", queue_capacity=2)
    # Do NOT start the background thread so queue stays full

    run_id = "run_test_backpressure"

    snap1 = SensorSnapshot("Timestep_1", [], {})
    snap2 = SensorSnapshot("Timestep_2", [], {})
    snap3 = SensorSnapshot("Timestep_3", [], {})

    writer.enqueue_snapshot(snap1, run_id)
    writer.enqueue_snapshot(snap2, run_id)
    # Third snapshot triggers drop of snap1
    writer.enqueue_snapshot(snap3, run_id)

    assert writer._dropped_snapshots_count == 1

    # Start thread and stop to flush
    writer.start()
    writer.stop()
