"""
Configuration schema for Eco-Loop Building Agents.
Implements 12_API_Design.md §3 and NFR-3.
"""

from typing import List, Optional
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimulationConfig:
    idf_path: str
    epw_path: str
    run_mode: str  # "baseline" or "agent"
    primary_zone_name: str = "SPACE1-1"
    representative_days: Optional[List[str]] = None


@dataclass(frozen=True)
class DecisionCadenceConfig:
    interval_minutes: int = 15


@dataclass(frozen=True)
class ComfortConfig:
    target_pmv_band: List[float] = field(default_factory=lambda: [-0.5, 0.5])
    hard_pmv_band: List[float] = field(default_factory=lambda: [-1.5, 1.5])


@dataclass(frozen=True)
class EnergyConfig:
    peak_demand_threshold_kw: Optional[float] = None
    carbon_aware: bool = False


@dataclass(frozen=True)
class ActuatorConfig:
    logical_name: str
    component_type: str
    control_type: str
    key: str
    min: float
    max: float


@dataclass(frozen=True)
class LLMConfig:
    model_name: str
    endpoint: Optional[str] = None
    max_tool_calls_per_cycle: int = 6
    cycle_timeout_seconds: float = 8.0


@dataclass(frozen=True)
class StorageConfig:
    backend: str = "duckdb"  # "duckdb" or "sqlite"
    path: str = "data/eco_loop.duckdb"


@dataclass(frozen=True)
class Config:
    building_id: str
    simulation: SimulationConfig
    actuators: List[ActuatorConfig]
    llm: LLMConfig
    decision_cadence: DecisionCadenceConfig = field(default_factory=DecisionCadenceConfig)
    comfort: ComfortConfig = field(default_factory=ComfortConfig)
    energy: EnergyConfig = field(default_factory=EnergyConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
