"""
MCP tool: get_zone_state.
Implements 09_MCP_Architecture.md §2.1.
"""

from typing import Dict, Any, List, Optional
from src.shared.types import SensorSnapshot


def execute_get_zone_state(
    snapshot: SensorSnapshot, zone_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Returns current snapshot zone state for requested zone_ids (or all if None).
    """
    requested_zones = zone_ids or []
    matched_zones = []

    for z in snapshot.zones:
        if not requested_zones or z.zone_id in requested_zones:
            matched_zones.append(
                {
                    "zone_id": z.zone_id,
                    "air_temp_c": z.air_temp_c,
                    "rh_pct": z.rh_pct,
                    "co2_ppm": z.co2_ppm,
                    "pmv": z.pmv,
                    "ppd_pct": z.ppd_pct,
                    "current_setpoints": z.current_setpoints,
                }
            )

    if requested_zones and not matched_zones:
        return {"isError": True, "reason": "unknown_zone_id", "zone_ids": requested_zones}

    return {
        "sim_time": snapshot.sim_time,
        "zones": matched_zones,
    }
