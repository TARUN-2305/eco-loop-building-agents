"""
Primary CLI Entry Point for Eco-Loop Building Agents.
Implements 05_Runtime_Execution.md §1-2 and MODULE_BREAKDOWN.md.
"""

import argparse
import sys
import uuid
import time
from src.shared.logging import get_logger
from src.config.loader import load_config, ConfigValidationError
from src.bridge.lifecycle import EnergyPlusBridge
from src.storage.writer import AsyncStorageWriter
from src.storage import queries
from src.monitoring.health import HealthMonitor
from src.mcp_server.server import MCPServer
from src.agent.orchestrator import AgentOrchestrator
from src.agent.llm_client import LLMClient
from src.dashboard.server import DashboardServer
from src.analytics.kpi import generate_kpi_report
from src.shared.types import RunSummary

logger = get_logger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="Eco-Loop Closed-Loop Building Management System")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/agent.yaml",
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["baseline", "agent"],
        default=None,
        help="Override simulation run mode (baseline or agent)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch read-only HTTP dashboard server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP dashboard server",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. Load configuration
    try:
        config = load_config(args.config)
        logger.info(f"Loaded configuration from '{args.config}' for building '{config.building_id}'")
    except ConfigValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        sys.exit(1)

    # 2. Mint run_id
    run_id = f"run_{config.simulation.run_mode}_{uuid.uuid4().hex[:8]}"

    # 3. Initialize Storage
    storage_writer = AsyncStorageWriter(
        db_path=config.storage.path, backend=config.storage.backend
    )
    storage_writer.start()
    storage_writer.register_run(
        run_id=run_id,
        run_mode=config.simulation.run_mode,
        idf_name=config.simulation.idf_path,
        epw_name=config.simulation.epw_path,
    )

    # 4. Initialize Health Monitor
    health_monitor = HealthMonitor()

    # 5. Initialize MCP Server and Orchestrator
    mcp_server = MCPServer()
    llm_client = LLMClient(config.llm)

    bridge = EnergyPlusBridge(config)

    orchestrator = AgentOrchestrator(
        config=config,
        mcp_server=mcp_server,
        handle_manager=bridge.handle_manager_ref,
        storage_writer=storage_writer,
        health_monitor=health_monitor,
        llm_client=llm_client,
        run_id=run_id,
    )

    # 6. Initialize Dashboard if requested
    dashboard_server = None
    if args.dashboard:
        dashboard_server = DashboardServer(
            port=args.port,
            db_conn=storage_writer._conn,
            active_run_id=run_id,
            health_monitor=health_monitor,
        )
        dashboard_server.start()

    # 7. Define Bridge callbacks
    def telemetry_sink(snapshot):
        storage_writer.enqueue_snapshot(snapshot, run_id)

    def decision_cycle_cb(snapshot, cycle_id):
        return orchestrator.on_decision_cycle(snapshot, cycle_id)

    # 8. Execute EnergyPlus simulation Bridge run
    logger.info(f"Executing run '{run_id}'...")
    run_result = bridge.run(
        on_decision_cycle_fn=decision_cycle_cb if config.simulation.run_mode == "agent" else None,
        telemetry_sink_fn=telemetry_sink,
    )

    logger.info(f"Run completed with status '{run_result.status}', total timesteps={run_result.total_timesteps}")

    # 9. Calculate KPIs & Finalize Run Summary
    kpi = generate_kpi_report(storage_writer._conn, run_id)
    summary = RunSummary(
        run_id=run_id,
        run_mode=config.simulation.run_mode,
        total_kwh=kpi["total_kwh"],
        pmv_band_compliance_pct=kpi["pmv_compliance_pct"],
        pct_cycles_fallback=kpi["fallback_rate_pct"],
        status=run_result.status,
    )
    storage_writer.finalize_run_summary(summary)

    # 10. Clean shutdown
    if dashboard_server:
        dashboard_server.stop()
    storage_writer.stop()

    logger.info("Eco-Loop execution finished cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
