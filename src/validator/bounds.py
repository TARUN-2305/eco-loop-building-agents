"""
Deterministic Validator module.
Pure, total, deterministic safety gate enforcing SR-1, SR-2, CC-2, and 06_Control_System.md §4.
Never raises an exception; returns ValidationResult(valid=bool, reasons=[...]).
"""

from typing import Dict, Any, List, Union
from src.shared.types import ValidationResult, CandidateAction
from src.config.schema import ActuatorConfig


def validate_action(
    candidate: Union[CandidateAction, Dict[str, float]],
    allow_list: List[ActuatorConfig],
    predicted_pmv: float = 0.0,
    predicted_demand_kw: float = 0.0,
    peak_demand_threshold_kw: float = None,
) -> ValidationResult:
    """
    Validates a candidate setpoint action against hard actuator bounds, allow-list,
    hard comfort band (PMV in [-1.5, +1.5]), and peak demand limits.
    """
    reasons: List[str] = []

    try:
        # Convert to dictionary format
        if isinstance(candidate, CandidateAction):
            action_dict = candidate.to_dict()
        elif isinstance(candidate, dict):
            action_dict = candidate
        else:
            return ValidationResult(valid=False, reasons=["Candidate action must be a dict or CandidateAction object"])

        if not action_dict:
            return ValidationResult(valid=False, reasons=["Candidate action dictionary is empty"])

        # Create allow-list lookup map: logical_name -> ActuatorConfig
        allow_map: Dict[str, ActuatorConfig] = {a.logical_name: a for a in allow_list}

        # 1. Allow-list check: every key in candidate action MUST be in allow_list (SR-2)
        for name, value in action_dict.items():
            if name not in allow_map:
                reasons.append(f"Actuator '{name}' is not in the allow-list")
                continue

            act_cfg = allow_map[name]

            # 2. Hard min/max bound check (SR-1)
            try:
                val_float = float(value)
                if val_float < act_cfg.min:
                    reasons.append(f"Actuator '{name}' value {val_float} below allow-listed min {act_cfg.min}")
                elif val_float > act_cfg.max:
                    reasons.append(f"Actuator '{name}' value {val_float} above allow-listed max {act_cfg.max}")
            except (ValueError, TypeError):
                reasons.append(f"Actuator '{name}' value '{value}' is not a valid number")

        # 3. Hard PMV band check (CC-2: PMV must remain in [-1.5, +1.5])
        if not (-1.5 <= predicted_pmv <= 1.5):
            reasons.append(f"Predicted PMV {predicted_pmv:.2f} violates hard comfort band [-1.5, +1.5]")

        # 4. Hard Peak Demand constraint check (EC-2)
        if peak_demand_threshold_kw is not None:
            if predicted_demand_kw > peak_demand_threshold_kw:
                reasons.append(f"Predicted demand {predicted_demand_kw:.1f}kW exceeds peak threshold {peak_demand_threshold_kw:.1f}kW")

        return ValidationResult(valid=(len(reasons) == 0), reasons=reasons)

    except Exception as e:
        # Guarantee function is total and never propagates exceptions
        return ValidationResult(valid=False, reasons=[f"Internal validator error: {str(e)}"])
