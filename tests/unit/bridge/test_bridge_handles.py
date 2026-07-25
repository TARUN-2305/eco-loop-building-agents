"""
Unit tests for HandleManager, sensor snapshots, handle caching, actuator commits, and fallback paths.
"""

import pytest
from unittest.mock import MagicMock
from src.bridge.handles import HandleManager
from src.config.schema import (
    Config, SimulationConfig, ActuatorConfig, LLMConfig, ComfortConfig, EnergyConfig, StorageConfig, DecisionCadenceConfig
)


@pytest.fixture
def mock_config():
    return Config(
        building_id="test_bldg",
        simulation=SimulationConfig(idf_path="test.idf", epw_path="test.epw", run_mode="agent"),
        actuators=[
            ActuatorConfig(
                logical_name="htg_sp",
                component_type="Zone Temperature Control",
                control_type="Heating Setpoint Schedule Value",
                key="SCH_HTG",
                min=15.0,
                max=23.0,
            )
        ],
        llm=LLMConfig(model_name="test", endpoint="http://localhost:11434/v1"),
    )


def test_handle_manager_lazy_resolution(mock_config):
    hm = HandleManager()
    assert not hm.handles_resolved

    mock_api = MagicMock()
    mock_state = MagicMock()

    # api_data_fully_ready returns False -> Should not resolve handles
    mock_api.exchange.api_data_fully_ready.return_value = False
    assert not hm.resolve_handles_if_ready(mock_api, mock_state, mock_config)
    assert not hm.handles_resolved

    # api_data_fully_ready returns True -> Resolves handles
    mock_api.exchange.api_data_fully_ready.return_value = True
    mock_api.exchange.get_actuator_handle.return_value = 42

    assert hm.resolve_handles_if_ready(mock_api, mock_state, mock_config)
    assert hm.handles_resolved
    mock_api.exchange.get_actuator_handle.assert_called_once_with(
        mock_state, "Zone Temperature Control", "Heating Setpoint Schedule Value", "SCH_HTG"
    )


def test_commit_actuator_idempotency_and_bounds(mock_config):
    hm = HandleManager()
    mock_api = MagicMock()
    mock_state = MagicMock()

    # Enable handles
    hm._handles_resolved = True
    hm._actuator_handles["htg_sp"] = 42

    # 1. Out of bounds commit -> fails
    assert not hm.commit_actuator(mock_api, mock_state, "htg_sp", 25.0, "cycle_1", mock_config)

    # 2. Valid commit -> succeeds
    assert hm.commit_actuator(mock_api, mock_state, "htg_sp", 20.0, "cycle_1", mock_config)
    mock_api.exchange.set_actuator_value.assert_called_once_with(mock_state, 42, 20.0)

    # 3. Repeat commit with same cycle_id & value -> succeeds (idempotent no-op)
    mock_api.exchange.set_actuator_value.reset_mock()
    assert hm.commit_actuator(mock_api, mock_state, "htg_sp", 20.0, "cycle_1", mock_config)
    mock_api.exchange.set_actuator_value.assert_not_called()

    # 4. Repeat commit with same cycle_id & DIFFERENT value -> fails (mismatch)
    assert not hm.commit_actuator(mock_api, mock_state, "htg_sp", 21.0, "cycle_1", mock_config)


def test_hold_last_known_good_fallback(mock_config):
    hm = HandleManager()
    mock_api = MagicMock()
    mock_state = MagicMock()

    hm._handles_resolved = True
    hm._actuator_handles["htg_sp"] = 42

    # Commit a value first
    hm.commit_actuator(mock_api, mock_state, "htg_sp", 21.5, "cycle_1", mock_config)
    mock_api.exchange.set_actuator_value.reset_mock()

    # Fallback re-asserts last known good (21.5)
    held = hm.hold_last_known_good(mock_api, mock_state, mock_config, "cycle_2")
    assert held["htg_sp"] == 21.5
    mock_api.exchange.set_actuator_value.assert_called_once_with(mock_state, 42, 21.5)
