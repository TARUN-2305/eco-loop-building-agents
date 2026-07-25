"""
Database schema definitions for DuckDB and SQLite embedded stores.
Implements 11_Database_Design.md §6.
"""

from typing import Any
from src.shared.logging import get_logger

logger = get_logger("storage.schema")

DDL_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY,
    run_mode VARCHAR NOT NULL,
    idf_name VARCHAR NOT NULL,
    epw_name VARCHAR NOT NULL,
    started_at VARCHAR NOT NULL,
    status VARCHAR NOT NULL
);
"""

DDL_SENSOR_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS sensor_snapshots (
    run_id VARCHAR NOT NULL,
    sim_time VARCHAR NOT NULL,
    zone_id VARCHAR NOT NULL,
    air_temp_c DOUBLE NOT NULL,
    rh_pct DOUBLE NOT NULL,
    pmv DOUBLE NOT NULL,
    ppd_pct DOUBLE NOT NULL,
    meters_json VARCHAR NOT NULL,
    phase VARCHAR NOT NULL,
    timestamp VARCHAR NOT NULL
);
"""

DDL_DECISION_LOGS = """
CREATE TABLE IF NOT EXISTS decision_logs (
    run_id VARCHAR NOT NULL,
    cycle_id VARCHAR PRIMARY KEY,
    sim_time VARCHAR NOT NULL,
    rationale VARCHAR NOT NULL,
    action_json VARCHAR NOT NULL,
    outcome VARCHAR NOT NULL,
    trace_json VARCHAR NOT NULL,
    timestamp VARCHAR NOT NULL
);
"""

DDL_INCIDENTS = """
CREATE TABLE IF NOT EXISTS incidents (
    run_id VARCHAR NOT NULL,
    cycle_id VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    raised_at VARCHAR NOT NULL
);
"""

DDL_RUN_SUMMARIES = """
CREATE TABLE IF NOT EXISTS run_summaries (
    run_id VARCHAR PRIMARY KEY,
    run_mode VARCHAR NOT NULL,
    total_kwh DOUBLE NOT NULL,
    pmv_band_compliance_pct DOUBLE NOT NULL,
    pct_cycles_fallback DOUBLE NOT NULL,
    status VARCHAR NOT NULL,
    started_at VARCHAR NOT NULL,
    ended_at VARCHAR
);
"""


def initialize_schema(conn: Any) -> None:
    """Initializes schema tables idempotently on a DuckDB or SQLite connection."""
    try:
        # SQLite uses REAL instead of DOUBLE, but DOUBLE is standard SQL recognized by both
        cursor = conn.cursor()
        cursor.execute(DDL_RUNS)
        cursor.execute(DDL_SENSOR_SNAPSHOTS)
        cursor.execute(DDL_DECISION_LOGS)
        cursor.execute(DDL_INCIDENTS)
        cursor.execute(DDL_RUN_SUMMARIES)
        conn.commit()
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database schema: {e}")
        raise
