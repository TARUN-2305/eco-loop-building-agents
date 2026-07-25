"""
Shared record types for Eco-Loop Building Agents.
Implements data schemas defined in 04_Dataflow.md §1 and MODULE_BREAKDOWN.md.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ZoneState:
    zone_id: str
    air_temp_c: float
    rh_pct: float
    co2_ppm: Optional[float]
    pmv: float
    ppd_pct: float
    current_setpoints: Dict[str, float]  # e.g., {"heating_c": 21.0, "cooling_c": 24.0}


@dataclass
class SensorSnapshot:
    sim_time: str
    zones: List[ZoneState]
    meters: Dict[str, float]  # e.g., {"facility_electricity_kw": 45.2, ...}
    phase: str = "run"        # "warmup" or "run"
    timestamp: str = field(default_factory=utc_now_iso)


@dataclass
class WeatherForecastSeries:
    hour_offset: int
    outdoor_temp_c: float
    outdoor_rh_pct: float
    solar_wm2: float


@dataclass
class ForecastWindow:
    series: List[WeatherForecastSeries]


@dataclass
class UtilitySignal:
    enabled: bool
    carbon_intensity_gco2_kwh: Optional[float] = None
    price_signal_relative: Optional[float] = None


@dataclass
class CandidateAction:
    heating_c: float
    cooling_c: float
    additional_setpoints: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, float]:
        res = {"heating_c": self.heating_c, "cooling_c": self.cooling_c}
        res.update(self.additional_setpoints)
        return res


@dataclass
class ValidationResult:
    valid: bool
    reasons: List[str] = field(default_factory=list)


@dataclass
class ActuatorCommit:
    committed: bool
    applied_action: Dict[str, float]
    cycle_id: str


@dataclass
class Incident:
    cycle_id: str
    reason: str
    severity: str  # "info", "warning", "critical"
    raised_at: str = field(default_factory=utc_now_iso)


@dataclass
class ToolTrace:
    tool: str
    args: Dict[str, Any]
    result_summary: str


@dataclass
class DecisionLog:
    run_id: str
    cycle_id: str
    sim_time: str
    rationale: str
    action_or_incident: Dict[str, Any]
    outcome: str  # "committed" or "fallback"
    trace: List[ToolTrace] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_now_iso)


@dataclass
class RunSummary:
    run_id: str
    run_mode: str  # "baseline" or "agent"
    total_kwh: float
    pmv_band_compliance_pct: float
    pct_cycles_fallback: float
    status: str = "completed"  # "completed" or "incomplete"
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
