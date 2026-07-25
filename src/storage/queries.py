"""
Query functions for Storage inspection, Analytics, and get_history MCP tool.
Implements 09_MCP_Architecture.md §2.8 and 12_API_Design.md §2.
"""

import json
from typing import Any, Dict, List, Optional
from src.shared.logging import get_logger

logger = get_logger("storage.queries")


def get_recent_snapshots(conn: Any, run_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves the most recent sensor snapshots for a run."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sim_time, zone_id, air_temp_c, rh_pct, pmv, ppd_pct, meters_json, phase, timestamp "
            "FROM sensor_snapshots WHERE run_id=? ORDER BY timestamp DESC LIMIT ?",
            (run_id, limit),
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append(
                {
                    "sim_time": r[0],
                    "zone_id": r[1],
                    "air_temp_c": r[2],
                    "rh_pct": r[3],
                    "pmv": r[4],
                    "ppd_pct": r[5],
                    "meters": json.loads(r[6]),
                    "phase": r[7],
                    "timestamp": r[8],
                }
            )
        return result
    except Exception as e:
        logger.error(f"Error querying recent snapshots for run '{run_id}': {e}")
        return []


def get_similar_days(conn: Any, run_id: str, target_air_temp_c: float, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieves past days with similar average zone temperatures (for get_history MCP tool).
    Bounded output format.
    """
    try:
        cursor = conn.cursor()
        # Find snapshots closest in air_temp_c to target_air_temp_c
        cursor.execute(
            "SELECT sim_time, air_temp_c, pmv, ABS(air_temp_c - ?) as diff "
            "FROM sensor_snapshots WHERE run_id=? AND phase='run' ORDER BY diff ASC LIMIT ?",
            (target_air_temp_c, run_id, limit),
        )
        rows = cursor.fetchall()
        return [{"sim_time": r[0], "air_temp_c": r[1], "pmv": r[2]} for r in rows]
    except Exception as e:
        logger.error(f"Error querying similar days for run '{run_id}': {e}")
        return []


def get_recent_incidents(conn: Any, run_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves recent incidents for a run."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cycle_id, severity, reason, raised_at FROM incidents WHERE run_id=? ORDER BY raised_at DESC LIMIT ?",
            (run_id, limit),
        )
        rows = cursor.fetchall()
        return [{"cycle_id": r[0], "severity": r[1], "reason": r[2], "raised_at": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Error querying incidents for run '{run_id}': {e}")
        return []


def get_decision_trace(conn: Any, cycle_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves the complete DecisionLog trace for a cycle_id (FR-13)."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT run_id, cycle_id, sim_time, rationale, action_json, outcome, trace_json, timestamp "
            "FROM decision_logs WHERE cycle_id=?",
            (cycle_id,),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "run_id": r[0],
            "cycle_id": r[1],
            "sim_time": r[2],
            "rationale": r[3],
            "action_or_incident": json.loads(r[4]),
            "outcome": r[5],
            "trace": json.loads(r[6]),
            "timestamp": r[7],
        }
    except Exception as e:
        logger.error(f"Error querying decision trace for cycle '{cycle_id}': {e}")
        return None


def get_run_summary(conn: Any, run_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves RunSummary record for a run."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT run_id, run_mode, total_kwh, pmv_band_compliance_pct, pct_cycles_fallback, status, started_at, ended_at "
            "FROM run_summaries WHERE run_id=?",
            (run_id,),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "run_id": r[0],
            "run_mode": r[1],
            "total_kwh": r[2],
            "pmv_band_compliance_pct": r[3],
            "pct_cycles_fallback": r[4],
            "status": r[5],
            "started_at": r[6],
            "ended_at": r[7],
        }
    except Exception as e:
        logger.error(f"Error querying run summary for run '{run_id}': {e}")
        return None
