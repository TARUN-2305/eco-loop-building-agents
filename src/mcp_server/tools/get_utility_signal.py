"""
MCP tool: get_utility_signal.
Implements 09_MCP_Architecture.md §2.3.
"""

from typing import Dict, Any


def execute_get_utility_signal(enabled: bool = False) -> Dict[str, Any]:
    """
    Returns utility grid carbon intensity and price signal.
    When enabled is False, returns null values.
    """
    if not enabled:
        return {
            "enabled": False,
            "carbon_intensity_gco2_kwh": None,
            "price_signal_relative": None,
        }

    return {
        "enabled": True,
        "carbon_intensity_gco2_kwh": 250.0,
        "price_signal_relative": 1.0,
    }
