"""
Unit tests for config schema loading and validation.
Implements Stage 1 checklist requirements and FC-10 edge cases.
"""

import pytest
import os
import tempfile
import yaml
from src.config.loader import load_config, ConfigValidationError


@pytest.fixture
def valid_baseline_dict():
    return {
        "building_id": "test_building_01",
        "simulation": {
            "idf_path": "data/idf/baseline.idf",
            "epw_path": "data/epw/test.epw",
            "run_mode": "baseline",
        },
        "actuators": [
            {
                "logical_name": "htg_sp",
                "component_type": "Zone Temperature Control",
                "control_type": "Heating Setpoint Schedule Value",
                "key": "SCH_HTG",
                "min": 15.0,
                "max": 22.0,
            }
        ],
        "llm": {
            "model_name": "test-model",
            "endpoint": None,
        },
    }


def write_temp_yaml(data_dict) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.dump(data_dict, f)
    return path


def test_valid_baseline_config_loads(valid_baseline_dict):
    path = write_temp_yaml(valid_baseline_dict)
    try:
        cfg = load_config(path)
        assert cfg.building_id == "test_building_01"
        assert cfg.simulation.run_mode == "baseline"
        assert len(cfg.actuators) == 1
        assert cfg.actuators[0].logical_name == "htg_sp"
        assert cfg.llm.max_tool_calls_per_cycle == 6
    finally:
        os.remove(path)


def test_agent_mode_without_endpoint_fails(valid_baseline_dict):
    valid_baseline_dict["simulation"]["run_mode"] = "agent"
    valid_baseline_dict["llm"]["endpoint"] = None
    path = write_temp_yaml(valid_baseline_dict)
    try:
        with pytest.raises(ConfigValidationError, match="requires a non-empty 'llm.endpoint'"):
            load_config(path)
    finally:
        os.remove(path)


def test_agent_mode_with_endpoint_succeeds(valid_baseline_dict):
    valid_baseline_dict["simulation"]["run_mode"] = "agent"
    valid_baseline_dict["llm"]["endpoint"] = "http://localhost:11434/v1"
    path = write_temp_yaml(valid_baseline_dict)
    try:
        cfg = load_config(path)
        assert cfg.simulation.run_mode == "agent"
        assert cfg.llm.endpoint == "http://localhost:11434/v1"
    finally:
        os.remove(path)


def test_missing_building_id_fails(valid_baseline_dict):
    del valid_baseline_dict["building_id"]
    path = write_temp_yaml(valid_baseline_dict)
    try:
        with pytest.raises(ConfigValidationError, match="'building_id'"):
            load_config(path)
    finally:
        os.remove(path)


def test_actuator_min_ge_max_fails(valid_baseline_dict):
    valid_baseline_dict["actuators"][0]["min"] = 25.0
    valid_baseline_dict["actuators"][0]["max"] = 20.0
    path = write_temp_yaml(valid_baseline_dict)
    try:
        with pytest.raises(ConfigValidationError, match="strictly less than max"):
            load_config(path)
    finally:
        os.remove(path)


def test_actuator_idf_cross_validation_fc10(valid_baseline_dict):
    path = write_temp_yaml(valid_baseline_dict)
    try:
        # Cross validate against a list that does not contain the actuator
        resolvable = [
            {"component_type": "Other Type", "control_type": "Other Control", "key": "OTHER_KEY"}
        ]
        with pytest.raises(ConfigValidationError, match="absent from the loaded .idf"):
            load_config(path, resolvable_actuators=resolvable)

        # Cross validate against a list that DOES contain the actuator
        resolvable_match = [
            {
                "component_type": "Zone Temperature Control",
                "control_type": "Heating Setpoint Schedule Value",
                "key": "SCH_HTG",
            }
        ]
        cfg = load_config(path, resolvable_actuators=resolvable_match)
        assert cfg.building_id == "test_building_01"
    finally:
        os.remove(path)
