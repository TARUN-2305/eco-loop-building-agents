"""
MCP tool: apply_setpoints.
Implements 09_MCP_Architecture.md §2.7, SR-2, and SR-4.
Independently re-validates server-side before committing.
"""

from typing import Dict, Any, List, Optional
from src.bridge.handles import HandleManager
from src.validator.bounds import validate_action
from src.config.schema import Config, ActuatorConfig


def execute_apply_setpoints(
    action: Optional[Dict[str, float]] = None,
    cycle_id: str = "cycle_default",
    handle_manager: Optional[HandleManager] = None,
    config: Optional[Config] = None,
    api: Any = None,
    state: Any = None,
    candidate: Optional[Dict[str, float]] = None,
    candidate_setpoints: Optional[Dict[str, float]] = None,
    setpoints: Optional[Dict[str, float]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Applies validated setpoints to EnergyPlus via Bridge with server-side re-validation.
    Idempotent by cycle_id. Supports parameter aliases and ignores unexpected kwargs.
    """
    target_action = action or candidate or candidate_setpoints or setpoints or kwargs
    if not target_action:
        return {"isError": True, "reason": "missing_action", "detail": "No setpoint action dictionary provided"}

    if not config or not handle_manager:
        return {"isError": True, "reason": "missing_context", "detail": "Config and handle_manager context required"}

    # Unwrap nested dictionary if passed (e.g. {'setpoint_candidate': {'zone1_heating_setpoint': 15.0}})
    unwrapped_action: Dict[str, float] = {}
    for k, v in target_action.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                try:
                    unwrapped_action[sub_k] = float(sub_v)
                except (ValueError, TypeError):
                    pass
        else:
            try:
                unwrapped_action[k] = float(v)
            except (ValueError, TypeError):
                pass
    target_action = unwrapped_action

    # Normalize key names (e.g., 'heating' -> 'zone1_heating_setpoint')
    valid_names = {a.logical_name for a in config.actuators}
    norm_action: Dict[str, float] = {}
    for k, v in target_action.items():
        if k in valid_names:
            norm_action[k] = float(v)
        else:
            matched = False
            for act in config.actuators:
                if ("heat" in k.lower() and "heat" in act.logical_name.lower()) or \
                   ("cool" in k.lower() and "cool" in act.logical_name.lower()):
                    norm_action[act.logical_name] = float(v)
                    matched = True
                    break
            if not matched:
                norm_action[k] = float(v)
    target_action = norm_action

    # 1. Mandatory server-side re-validation (SR-2)
    val_res = validate_action(target_action, config.actuators)
    if not val_res.valid:
        return {
            "isError": True,
            "reason": "out_of_bounds",
            "detail": f"Server-side re-validation failed: {val_res.reasons}",
        }

    # 2. Delegate writes to HandleManager
    applied_action: Dict[str, float] = {}
    for logical_name, val in target_action.items():
        success = handle_manager.commit_actuator(
            api=api,
            state=state,
            logical_name=logical_name,
            value=val,
            cycle_id=cycle_id,
            config=config,
        )
        if not success:
            return {
                "isError": True,
                "reason": "commit_failed",
                "detail": f"Failed to commit actuator '{logical_name}'={val} for cycle '{cycle_id}'",
            }
        applied_action[logical_name] = val

    return {
        "committed": True,
        "applied_action": applied_action,
        "cycle_id": cycle_id,
    }
