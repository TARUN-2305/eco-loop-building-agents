"""
MCP tool: propose_setpoints.
Implements 09_MCP_Architecture.md §2.5.
"""

from typing import Dict, Any, List, Optional
from src.optimizer.solver import propose_setpoints_solver
from src.shared.types import SensorSnapshot, ForecastWindow
from src.config.schema import ActuatorConfig


def execute_propose_setpoints(
    objective_weights: Optional[Dict[str, float]] = None,
    horizon_steps: int = 4,
    current_snapshot: Optional[SensorSnapshot] = None,
    allow_list: Optional[List[ActuatorConfig]] = None,
    forecast: Optional[ForecastWindow] = None,
    carbon_aware: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """
    Invokes deterministic optimizer solver to compute setpoints.
    Returns candidate action or isError: True if infeasible.
    """
    weights = objective_weights or {"w_energy": 0.5, "w_comfort_penalty": 0.5}

    if current_snapshot is None or allow_list is None:
        return {"isError": True, "reason": "missing_context", "detail": "Snapshot and allow_list context required"}

    res = propose_setpoints_solver(
        objective_weights=weights,
        horizon_steps=horizon_steps,
        current_snapshot=current_snapshot,
        allow_list=allow_list,
        forecast=forecast,
        carbon_aware=carbon_aware,
    )

    if res["status"] == "infeasible":
        return {
            "isError": True,
            "reason": "infeasible",
            "detail": "No candidate setpoint satisfied hard comfort and actuator bounds",
            "rationale_tags": res["rationale_tags"],
        }

    return {
        "candidate": res["candidate"],
        "predicted_kwh_horizon": res["predicted_kwh_horizon"],
        "predicted_pmv_range": res["predicted_pmv_range"],
        "rationale_tags": res["rationale_tags"],
    }
