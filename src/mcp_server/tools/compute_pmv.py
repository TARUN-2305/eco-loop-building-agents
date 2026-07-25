"""
MCP tool: compute_pmv.
Implements 09_MCP_Architecture.md §2.4.
"""

from typing import Dict, Any, Optional
from src.comfort.pmv import compute_pmv as calculate_pmv, PMVInputValidationError


def execute_compute_pmv(
    air_temp_c: Optional[float] = None,
    mean_radiant_temp_c: Optional[float] = None,
    air_speed_ms: float = 0.1,
    rh_pct: Optional[float] = 50.0,
    met_rate: float = 1.2,
    clo: float = 0.5,
    predicted_air_temp_c: Optional[float] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Computes analytical PMV/PPD using Fanger formula via comfort module.
    Surfaces domain errors inside normal result with isError: True per MCP spec.
    """
    temp = air_temp_c or predicted_air_temp_c or 23.0
    mrt = mean_radiant_temp_c or temp
    rh = rh_pct if rh_pct is not None else 50.0
    try:
        res = calculate_pmv(
            air_temp_c=temp,
            mean_radiant_temp_c=mrt,
            air_speed_ms=air_speed_ms,
            rh_pct=rh,
            met_rate=met_rate,
            clo=clo,
        )
        return {"pmv": res.pmv, "ppd_pct": res.ppd_pct}
    except PMVInputValidationError as e:
        return {"isError": True, "reason": "input_out_of_valid_range", "detail": str(e)}
