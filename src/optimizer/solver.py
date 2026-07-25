"""
Deterministic Setpoint Optimizer engine.
Implements propose_setpoints solver per 06_Control_System.md §2-3 and ADR-005.
Evaluates bounded-horizon candidate setpoints to minimize objective function:
  minimize: w_energy * predicted_kWh + w_comfort * pmv_penalty
  subject to hard bounds: PMV in [-1.5, +1.5], setpoint in allow_list bounds.
"""

from typing import Dict, Any, List, Optional, Tuple
from src.shared.types import SensorSnapshot, CandidateAction, ForecastWindow
from src.shared.logging import get_logger
from src.config.schema import ActuatorConfig
from src.comfort.pmv import compute_pmv, PMVInputValidationError

logger = get_logger("optimizer.solver")


def propose_setpoints_solver(
    objective_weights: Dict[str, float],
    horizon_steps: int,
    current_snapshot: SensorSnapshot,
    allow_list: List[ActuatorConfig],
    forecast: Optional[ForecastWindow] = None,
    carbon_aware: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates candidate setpoint actions over allow-listed bounds using a deterministic grid search.

    Returns:
      {
         "status": "success" | "infeasible",
         "candidate": CandidateAction dict or None,
         "predicted_kwh_horizon": float,
         "predicted_pmv_range": [float, float],
         "rationale_tags": List[str]
      }
    """
    w_energy = float(objective_weights.get("w_energy", 0.5))
    w_comfort = float(objective_weights.get("w_comfort_penalty", 0.5))

    # Identify heating and cooling actuators from allow-list
    htg_act: Optional[ActuatorConfig] = None
    clg_act: Optional[ActuatorConfig] = None

    for a in allow_list:
        if "heat" in a.logical_name.lower() or "htg" in a.logical_name.lower():
            htg_act = a
        elif "cool" in a.logical_name.lower() or "clg" in a.logical_name.lower():
            clg_act = a

    # Default fallback setpoints if allow-list is generic
    if not htg_act or not clg_act:
        htg_act = allow_list[0] if allow_list else ActuatorConfig("htg_sp", "Type", "Ctrl", "Key", 15.0, 23.0)
        clg_act = allow_list[1] if len(allow_list) > 1 else ActuatorConfig("clg_sp", "Type", "Ctrl", "Key", 22.0, 30.0)

    # Extract current indoor conditions
    current_zone = current_snapshot.zones[0] if current_snapshot.zones else None
    t_in = current_zone.air_temp_c if current_zone else 23.0
    rh_in = current_zone.rh_pct if current_zone else 50.0

    best_score = float("inf")
    best_candidate: Optional[Dict[str, float]] = None
    best_pmv_range: Tuple[float, float] = (0.0, 0.0)
    best_kwh: float = 0.0
    rationale_tags: List[str] = []

    # Discretize setpoint space (1.0°C steps)
    htg_steps = [round(htg_act.min + i * 1.0, 1) for i in range(int(htg_act.max - htg_act.min) + 1)]
    clg_steps = [round(clg_act.min + i * 1.0, 1) for i in range(int(clg_act.max - clg_act.min) + 1)]

    for htg in htg_steps:
        for clg in clg_steps:
            # Deadband check: cooling setpoint must be >= heating setpoint + 1.0°C
            if clg < htg + 1.0:
                continue

            # Predict steady-state zone temperature resulting from candidate setpoints
            # Simple physical proxy: if heating setpoint > t_in, zone warms to htg; if cooling setpoint < t_in, zone cools to clg
            predicted_t_in = t_in
            if t_in < htg:
                predicted_t_in = htg
            elif t_in > clg:
                predicted_t_in = clg

            # Compute predicted PMV
            try:
                pmv_res = compute_pmv(
                    air_temp_c=max(10.0, min(32.0, predicted_t_in)),
                    mean_radiant_temp_c=max(10.0, min(40.0, predicted_t_in)),
                    air_speed_ms=0.1,
                    rh_pct=max(0.0, min(100.0, rh_in)),
                )
                pmv_val = pmv_res.pmv
            except PMVInputValidationError:
                pmv_val = 2.0  # Heavy penalty if out of bounds

            # Check HARD comfort constraint (CC-2: PMV in [-1.5, +1.5])
            if not (-1.5 <= pmv_val <= 1.5):
                continue

            # Estimate energy consumption (kWh) over horizon
            # Higher thermal lift from outdoor ambient increases energy
            outdoor_t = forecast.series[0].outdoor_temp_c if forecast and forecast.series else 25.0
            delta_t = abs(predicted_t_in - outdoor_t)
            kwh_step = (0.5 + 0.15 * delta_t) * (horizon_steps * 0.25)

            # Soft comfort penalty for deviation outside target band [-0.5, +0.5]
            comfort_penalty = 0.0
            if abs(pmv_val) > 0.5:
                comfort_penalty = (abs(pmv_val) - 0.5) ** 2

            score = w_energy * kwh_step + w_comfort * 10.0 * comfort_penalty

            if score < best_score:
                best_score = score
                best_candidate = {
                    htg_act.logical_name: htg,
                    clg_act.logical_name: clg,
                }
                best_pmv_range = (round(pmv_val - 0.1, 2), round(pmv_val + 0.1, 2))
                best_kwh = round(kwh_step, 2)

    if best_candidate is None:
        logger.warning("propose_setpoints_solver found no candidate satisfying hard bounds -> infeasible")
        return {
            "status": "infeasible",
            "candidate": None,
            "predicted_kwh_horizon": 0.0,
            "predicted_pmv_range": [-2.0, 2.0],
            "rationale_tags": ["infeasible_hard_bounds"],
        }

    # Generate rationale tags
    if w_comfort > w_energy:
        rationale_tags.append("comfort_priority")
    else:
        rationale_tags.append("energy_savings_priority")

    if forecast and forecast.series and forecast.series[0].outdoor_temp_c > 30.0:
        rationale_tags.append("peak_heat_forecast")

    logger.info(f"propose_setpoints_solver proposed candidate: {best_candidate} (score={best_score:.2f})")
    return {
        "status": "success",
        "candidate": best_candidate,
        "predicted_kwh_horizon": best_kwh,
        "predicted_pmv_range": [best_pmv_range[0], best_pmv_range[1]],
        "rationale_tags": rationale_tags,
    }
