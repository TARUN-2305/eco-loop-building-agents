"""
MCP tool: get_weather_forecast.
Implements 09_MCP_Architecture.md §2.2.
"""

from typing import Dict, Any, List


def execute_get_weather_forecast(horizon_hours: int = 24) -> Dict[str, Any]:
    """
    Returns synthetic / EPW-derived forecast series for the requested horizon (1-48 hours).
    """
    if not (1 <= horizon_hours <= 48):
        return {"isError": True, "reason": "horizon_out_of_range", "detail": "horizon_hours must be between 1 and 48"}

    series: List[Dict[str, Any]] = []
    # Diurnal temperature cycle stub (20°C min night to 30°C max afternoon)
    for hr in range(horizon_hours):
        t_out = round(25.0 + 5.0 * ((hr % 24) / 12.0 - 1.0), 1)
        rh_out = round(50.0 - 10.0 * ((hr % 24) / 12.0 - 1.0), 1)
        solar = max(0.0, round(600.0 * max(0.0, 1.0 - ((hr % 24 - 12) / 6.0) ** 2), 1))
        series.append(
            {
                "hour_offset": hr,
                "outdoor_temp_c": t_out,
                "outdoor_rh_pct": rh_out,
                "solar_wm2": solar,
            }
        )

    return {"series": series}
