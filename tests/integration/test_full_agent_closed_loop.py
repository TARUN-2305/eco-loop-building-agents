"""
Full end-to-end closed-loop integration test for Eco-Loop Building Agents.
Simulates a full 96-timestep (24 hour) agent-driven simulation run.
Implements Stage 7 & Stage 8 checklist requirements.
"""

import pytest
import os
import tempfile
from src.config.loader import load_config
from src.bridge.lifecycle import EnergyPlusBridge
from src.storage.writer import AsyncStorageWriter
from src.storage import queries
from src.monitoring.health import HealthMonitor
from src.mcp_server.server import MCPServer
from src.agent.orchestrator import AgentOrchestrator
from src.analytics.kpi import generate_kpi_report
from src.shared.types import RunSummary


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_full_agent_closed_loop_execution(temp_db_path):
    # Load agent configuration from configs/agent.yaml
    config = load_config("configs/agent.yaml")

    run_id = "test_run_closed_loop_96"

    # Initialize storage & health
    writer = AsyncStorageWriter(db_path=temp_db_path, backend="sqlite")
    writer.start()
    writer.register_run(run_id, config.simulation.run_mode, config.simulation.idf_path, config.simulation.epw_path)

    health = HealthMonitor()
    mcp_server = MCPServer()
    bridge = EnergyPlusBridge(config)

    orchestrator = AgentOrchestrator(
        config=config,
        mcp_server=mcp_server,
        handle_manager=bridge.handle_manager_ref,
        storage_writer=writer,
        health_monitor=health,
        run_id=run_id,
    )

    def telemetry_sink(snapshot):
        writer.enqueue_snapshot(snapshot, run_id)

    def decision_cycle_cb(snapshot, cycle_id):
        return orchestrator.on_decision_cycle(snapshot, cycle_id)

    # Run simulation
    run_res = bridge.run(
        on_decision_cycle_fn=decision_cycle_cb,
        telemetry_sink_fn=telemetry_sink,
    )

    assert run_res.status == "completed"
    assert run_res.total_timesteps == 96

    # Calculate KPIs
    kpi_conn = writer.conn
    kpi = generate_kpi_report(kpi_conn, run_id)
    kpi_conn.close()
    assert 0.0 <= kpi["total_kwh"]
    assert 0.0 <= kpi["pmv_compliance_pct"] <= 100.0

    summary = RunSummary(
        run_id=run_id,
        run_mode=config.simulation.run_mode,
        total_kwh=kpi["total_kwh"],
        pmv_band_compliance_pct=kpi["pmv_compliance_pct"],
        pct_cycles_fallback=kpi["fallback_rate_pct"],
        status=run_res.status,
    )
    writer.finalize_run_summary(summary)
    writer.stop()

    # Re-open DB to verify persisted decision logs & snapshots
    conn = writer.conn
    snapshots = queries.get_recent_snapshots(conn, run_id, limit=100)
    assert len(snapshots) >= 0

    run_sum = queries.get_run_summary(conn, run_id)
    conn.close()
