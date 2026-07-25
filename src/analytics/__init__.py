"""
Analytics module exposing KPI calculations and run comparison.
"""

from src.analytics.kpi import (
    calculate_total_energy,
    calculate_pmv_compliance,
    calculate_fallback_rate,
    generate_kpi_report,
    compare_runs,
)

__all__ = [
    "calculate_total_energy",
    "calculate_pmv_compliance",
    "calculate_fallback_rate",
    "generate_kpi_report",
    "compare_runs",
]
