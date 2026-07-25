"""
Config loader with fail-fast validation rules.
Implements 12_API_Design.md §3, NFR-3, and FC-10.
"""

import os
import yaml
from typing import Dict, Any, List, Optional
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
from src.shared.logging import get_logger

logger = get_logger("config")


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


def load_config(config_path: str, resolvable_actuators: Optional[List[Dict[str, str]]] = None) -> Config:
    """
    Loads and validates configuration from a YAML file.
    Optionally cross-validates actuators against resolvable handles from a loaded .idf.
    """
    if not os.path.exists(config_path):
        raise ConfigValidationError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except Exception as e:
        raise ConfigValidationError(f"Failed to parse YAML configuration: {e}")

    if not isinstance(raw_data, dict):
        raise ConfigValidationError("Root configuration must be a dictionary")

    # 1. Validate building_id (SC-1)
    building_id = raw_data.get("building_id")
    if not building_id or not isinstance(building_id, str):
        raise ConfigValidationError("Missing or invalid required field: 'building_id'")

    # 2. Validate simulation
    sim_data = raw_data.get("simulation")
    if not sim_data or not isinstance(sim_data, dict):
        raise ConfigValidationError("Missing or invalid required section: 'simulation'")
    
    idf_path = sim_data.get("idf_path")
    epw_path = sim_data.get("epw_path")
    run_mode = sim_data.get("run_mode")

    if not idf_path or not isinstance(idf_path, str):
        raise ConfigValidationError("Missing or invalid 'simulation.idf_path'")
    if not epw_path or not isinstance(epw_path, str):
        raise ConfigValidationError("Missing or invalid 'simulation.epw_path'")
    if run_mode not in ("baseline", "agent"):
        raise ConfigValidationError("Field 'simulation.run_mode' must be 'baseline' or 'agent'")

    primary_zone_name = sim_data.get("primary_zone_name", "SPACE1-1")

    sim_cfg = SimulationConfig(
        idf_path=idf_path,
        epw_path=epw_path,
        run_mode=run_mode,
        primary_zone_name=str(primary_zone_name),
        representative_days=sim_data.get("representative_days"),
    )

    # 3. Validate LLM config
    llm_data = raw_data.get("llm")
    if not llm_data or not isinstance(llm_data, dict):
        raise ConfigValidationError("Missing or invalid required section: 'llm'")
    
    model_name = llm_data.get("model_name")
    endpoint = llm_data.get("endpoint")

    if not model_name or not isinstance(model_name, str):
        raise ConfigValidationError("Missing or invalid 'llm.model_name'")
    
    # Validation rule: if run_mode is agent, llm.endpoint MUST be specified and non-empty
    if run_mode == "agent" and not endpoint:
        raise ConfigValidationError("Configuration in 'agent' mode requires a non-empty 'llm.endpoint'")

    llm_cfg = LLMConfig(
        model_name=model_name,
        endpoint=endpoint,
        max_tool_calls_per_cycle=llm_data.get("max_tool_calls_per_cycle", 6),
        cycle_timeout_seconds=float(llm_data.get("cycle_timeout_seconds", 8.0)),
    )

    # 4. Validate Actuators
    actuators_data = raw_data.get("actuators")
    if not isinstance(actuators_data, list) or len(actuators_data) == 0:
        raise ConfigValidationError("Section 'actuators' must be a non-empty list")

    actuator_cfgs: List[ActuatorConfig] = []
    for idx, act in enumerate(actuators_data):
        if not isinstance(act, dict):
            raise ConfigValidationError(f"Actuator item at index {idx} is not a dictionary")
        
        logical_name = act.get("logical_name")
        comp_type = act.get("component_type")
        ctrl_type = act.get("control_type")
        key = act.get("key")
        act_min = act.get("min")
        act_max = act.get("max")

        if not all([logical_name, comp_type, ctrl_type, key]) or act_min is None or act_max is None:
            raise ConfigValidationError(f"Actuator item at index {idx} missing required fields")
        
        if act_min >= act_max:
            raise ConfigValidationError(f"Actuator '{logical_name}' min ({act_min}) must be strictly less than max ({act_max})")

        actuator_cfgs.append(
            ActuatorConfig(
                logical_name=str(logical_name),
                component_type=str(comp_type),
                control_type=str(ctrl_type),
                key=str(key),
                min=float(act_min),
                max=float(act_max),
            )
        )

    # Cross-validate against loaded .idf resolvable actuators if supplied (FC-10)
    if resolvable_actuators is not None:
        for act_cfg in actuator_cfgs:
            found = False
            for res in resolvable_actuators:
                if (
                    res.get("component_type") == act_cfg.component_type
                    and res.get("control_type") == act_cfg.control_type
                    and res.get("key") == act_cfg.key
                ):
                    found = True
                    break
            if not found:
                raise ConfigValidationError(
                    f"Configured actuator '{act_cfg.logical_name}' ({act_cfg.component_type}, {act_cfg.control_type}, {act_cfg.key}) is absent from the loaded .idf"
                )

    # 5. Optional / Defaulted sections
    cadence_data = raw_data.get("decision_cadence", {})
    cadence_cfg = DecisionCadenceConfig(
        interval_minutes=int(cadence_data.get("interval_minutes", 15))
    )

    comfort_data = raw_data.get("comfort", {})
    target_band = comfort_data.get("target_pmv_band", [-0.5, 0.5])
    hard_band = comfort_data.get("hard_pmv_band", [-1.5, 1.5])
    if target_band[0] >= target_band[1]:
        raise ConfigValidationError(f"Comfort target PMV band min must be < max: {target_band}")
    if hard_band[0] >= hard_band[1]:
        raise ConfigValidationError(f"Comfort hard PMV band min must be < max: {hard_band}")

    comfort_cfg = ComfortConfig(
        target_pmv_band=[float(x) for x in target_band],
        hard_pmv_band=[float(x) for x in hard_band],
    )

    energy_data = raw_data.get("energy", {})
    energy_cfg = EnergyConfig(
        peak_demand_threshold_kw=energy_data.get("peak_demand_threshold_kw"),
        carbon_aware=bool(energy_data.get("carbon_aware", False)),
    )

    storage_data = raw_data.get("storage", {})
    backend = storage_data.get("backend", "duckdb")
    if backend not in ("duckdb", "sqlite"):
        raise ConfigValidationError(f"Storage backend must be 'duckdb' or 'sqlite', got '{backend}'")

    storage_cfg = StorageConfig(
        backend=backend,
        path=storage_data.get("path", "data/eco_loop.duckdb"),
    )

    config_obj = Config(
        building_id=building_id,
        simulation=sim_cfg,
        actuators=actuator_cfgs,
        llm=llm_cfg,
        decision_cadence=cadence_cfg,
        comfort=comfort_cfg,
        energy=energy_cfg,
        storage=storage_cfg,
    )

    logger.info(f"Loaded valid configuration for building '{building_id}' in '{run_mode}' mode")
    return config_obj
