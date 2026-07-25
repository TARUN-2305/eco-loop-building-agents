"""
Integration tests for IDF/Config consistency and fail-fast handle validation.
Addresses Fix 8 & 9 (P2) from FIX.md.
"""

import os
import pytest
from src.config.loader import load_config
from src.bridge.handles import HandleManager


def test_idf_config_zone_name_consistency():
    """Asserts that primary_zone_name in config matches zone objects in IDF."""
    config = load_config("configs/agent.yaml")
    idf_path = config.simulation.idf_path

    assert os.path.exists(idf_path), f"IDF path {idf_path} does not exist"
    with open(idf_path, "r", encoding="utf-8") as f:
        idf_text = f.read()

    zone_name = config.simulation.primary_zone_name
    assert zone_name in idf_text, f"Zone '{zone_name}' specified in config not found in IDF"


def test_idf_config_actuator_schedule_names():
    """Asserts that schedule names configured in actuators exist in IDF."""
    config = load_config("configs/agent.yaml")
    idf_path = config.simulation.idf_path

    with open(idf_path, "r", encoding="utf-8") as f:
        idf_text = f.read()

    for act in config.actuators:
        assert act.key in idf_text, f"Actuator schedule '{act.key}' not found in IDF"


def test_handle_manager_fail_fast_on_missing_handle():
    """Asserts that HandleManager fails to commit when actuator handle is unresolved."""
    config = load_config("configs/agent.yaml")
    mgr = HandleManager()

    success = mgr.commit_actuator(None, None, "zone1_heating_setpoint", 20.0, "cycle_test_1", config)
    assert success is False
