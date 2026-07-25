"""
Analytics & KPI calculation engine for Eco-Loop runs.
Implements 04_Dataflow.md §4, 12_API_Design.md §4, FR-12, FR-13.
"""

from typing import Dict, Any, List, Optional
from src.shared.logging import get_logger

logger = get_logger("analytics.kpi")


def calculate_total_energy(conn: Any, run_id: str) -> float:
    """Calculates total electricity consumption in kWh for a run."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT meters_json FROM sensor_snapshots WHERE run_id=? AND phase='run'", (run_id,))
        rows = cursor.fetchall()
        if not rows or len(rows) < 2:
            return 0.0
        import json
        first_meters = json.loads(rows[0][0])
        last_meters = json.loads(rows[-1][0])
        
        first_kwh = float(first_meters.get("facility_electricity_kwh", 0.0))
        last_kwh = float(last_meters.get("facility_electricity_kwh", 0.0))
        
        delta = max(0.0, last_kwh - first_kwh)
        if delta > 0:
            return round(delta, 2)

        # Fallback to rate integration if cumulative meter not present
        total_kwh = 0.0
        for r in rows:
            meters = json.loads(r[0])
            kw = meters.get("facility_electricity_kw", 0.0)
            total_kwh += kw * (15.0 / 60.0)
        return round(total_kwh, 2)
    except Exception as e:
        logger.error(f"Error calculating total energy for run '{run_id}': {e}")
        return 0.0


def calculate_pmv_compliance(conn: Any, run_id: str, target_band: List[float] = None) -> float:
    """Calculates percentage of timesteps where zone PMV fell inside target_band (default [-0.5, +0.5])."""
    target_band = target_band or [-0.5, 0.5]
    min_pmv, max_pmv = target_band[0], target_band[1]

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT pmv FROM sensor_snapshots WHERE run_id=? AND phase='run'", (run_id,))
        rows = cursor.fetchall()
        if not rows:
            return 100.0

        compliant_count = sum(1 for r in rows if min_pmv <= r[0] <= max_pmv)
        pct = (compliant_count / len(rows)) * 100.0
        return round(pct, 2)
    except Exception as e:
        logger.error(f"Error calculating PMV compliance for run '{run_id}': {e}")
        return 0.0


def calculate_fallback_rate(conn: Any, run_id: str) -> float:
    """Calculates percentage of decision cycles resulting in fallback."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT outcome FROM decision_logs WHERE run_id=?", (run_id,))
        rows = cursor.fetchall()
        if not rows:
            return 0.0

        fallback_count = sum(1 for r in rows if r[0] == "fallback")
        pct = (fallback_count / len(rows)) * 100.0
        return round(pct, 2)
    except Exception as e:
        logger.error(f"Error calculating fallback rate for run '{run_id}': {e}")
        return 0.0


def generate_kpi_report(conn: Any, run_id: str) -> Dict[str, Any]:
    """Generates complete KPI summary dictionary for a run."""
    return {
        "run_id": run_id,
        "total_kwh": calculate_total_energy(conn, run_id),
        "pmv_compliance_pct": calculate_pmv_compliance(conn, run_id),
        "fallback_rate_pct": calculate_fallback_rate(conn, run_id),
    }


def compare_runs(conn: Any, baseline_run_id: str, agent_run_id: str) -> Dict[str, Any]:
    """
    Compares baseline vs agent run side-by-side (% energy reduction, PMV compliance shift).
    """
    base_kpi = generate_kpi_report(conn, baseline_run_id)
    agent_kpi = generate_kpi_report(conn, agent_run_id)

    base_kwh = base_kpi["total_kwh"]
    agent_kwh = agent_kpi["total_kwh"]

    energy_savings_pct = 0.0
    if base_kwh > 0:
        energy_savings_pct = round(((base_kwh - agent_kwh) / base_kwh) * 100.0, 2)

    return {
        "baseline": base_kpi,
        "agent": agent_kpi,
        "energy_savings_pct": energy_savings_pct,
        "pmv_compliance_shift_pct": round(
            agent_kpi["pmv_compliance_pct"] - base_kpi["pmv_compliance_pct"], 2
        ),
    }
