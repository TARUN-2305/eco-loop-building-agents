"""
MCP tool: validate_action.
Implements 09_MCP_Architecture.md §2.6.
"""

from typing import Dict, Any, List, Union, Optional
from src.validator.bounds import validate_action
from src.config.schema import ActuatorConfig
from src.shared.types import CandidateAction


def execute_validate_action(
    candidate: Optional[Union[CandidateAction, Dict[str, float]]] = None,
    cycle_id: str = "cycle_default",
    allow_list: Optional[List[ActuatorConfig]] = None,
    predicted_pmv: float = 0.0,
    predicted_demand_kw: float = 0.0,
    peak_demand_threshold_kw: float = None,
    action: Optional[Dict[str, float]] = None,
    candidate_setpoints: Optional[Dict[str, float]] = None,
    setpoints: Optional[Dict[str, float]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Executes deterministic validation of a candidate setpoint action.
    Accepts candidate, action, candidate_setpoints, or setpoints aliases.
    """
    target_candidate = candidate or action or candidate_setpoints or setpoints or kwargs
    if target_candidate is None:
        return {"valid": False, "reasons": ["No candidate or action provided"], "cycle_id": cycle_id}

    if allow_list is None:
        return {"valid": False, "reasons": ["Allow list context missing"], "cycle_id": cycle_id}

    if isinstance(target_candidate, dict):
        unwrapped: Dict[str, float] = {}
        for k, v in target_candidate.items():
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    try:
                        unwrapped[sub_k] = float(sub_v)
                    except (ValueError, TypeError):
                        pass
            else:
                try:
                    unwrapped[k] = float(v)
                except (ValueError, TypeError):
                    pass
        target_candidate = unwrapped

        valid_names = {a.logical_name for a in allow_list}
        norm_candidate: Dict[str, float] = {}
        for k, v in target_candidate.items():
            if k in valid_names:
                norm_candidate[k] = float(v)
            else:
                matched = False
                for act in allow_list:
                    if ("heat" in k.lower() and "heat" in act.logical_name.lower()) or \
                       ("cool" in k.lower() and "cool" in act.logical_name.lower()):
                        norm_candidate[act.logical_name] = float(v)
                        matched = True
                        break
                if not matched:
                    norm_candidate[k] = float(v)
        target_candidate = norm_candidate

    res = validate_action(
        candidate=target_candidate,
        allow_list=allow_list,
        predicted_pmv=predicted_pmv,
        predicted_demand_kw=predicted_demand_kw,
        peak_demand_threshold_kw=peak_demand_threshold_kw,
    )

    return {
        "valid": res.valid,
        "reasons": res.reasons,
        "cycle_id": cycle_id,
    }
