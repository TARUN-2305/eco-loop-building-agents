"""
Configuration module exposing Config schema and loader function.
"""

from src.config.schema import (
    Config,
    SimulationConfig,
    DecisionCadenceConfig,
    ComfortConfig,
    EnergyConfig,
    ActuatorConfig,
    LLMConfig,
    StorageConfig,
)
from src.config.loader import load_config, ConfigValidationError

__all__ = [
    "Config",
    "SimulationConfig",
    "DecisionCadenceConfig",
    "ComfortConfig",
    "EnergyConfig",
    "ActuatorConfig",
    "LLMConfig",
    "StorageConfig",
    "load_config",
    "ConfigValidationError",
]
