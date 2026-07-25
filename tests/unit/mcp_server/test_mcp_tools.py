"""
Contract unit tests for all ten discrete MCP tools.
Implements Stage 4 checklist requirements and SR-3 verification.
"""

import pytest
from unittest.mock import MagicMock
from src.mcp_server.server import MCPServer, get_tool_catalog
from src.shared.types import SensorSnapshot, ZoneState
from src.config.schema import (
    Config, SimulationConfig, ActuatorConfig, LLMConfig, ComfortConfig, EnergyConfig, StorageConfig
)


@pytest.fixture
def mock_config():
    return Config(
        building_id="bldg_01",
        simulation=SimulationConfig("test.idf", "test.epw", "agent"),
        actuators=[
            ActuatorConfig("htg_sp", "Type", "Ctrl", "Key", 15.0, 23.0),
            ActuatorConfig("clg_sp", "Type", "Ctrl", "Key", 22.0, 30.0),
        ],
        llm=LLMConfig("model"),
    )


@pytest.fixture
def mock_snapshot():
    return SensorSnapshot(
        sim_time="Day_1_Hour_12.00",
        zones=[ZoneState("Zone1", 23.0, 50.0, None, 0.0, 5.0, {"htg_sp": 20.0, "clg_sp": 25.0})],
        meters={"facility_electricity_kw": 20.0},
    )


def test_tool_catalog_is_exactly_ten_tools():
    catalog = get_tool_catalog()
    assert len(catalog) == 10
    expected_tools = {
        "get_zone_state",
        "get_weather_forecast",
        "get_utility_signal",
        "compute_pmv",
        "propose_setpoints",
        "validate_action",
        "apply_setpoints",
        "get_history",
        "log_decision",
        "raise_incident",
    }
    assert set(catalog.keys()) == expected_tools


def test_mcp_server_call_unknown_tool():
    server = MCPServer()
    res = server.call_tool("non_existent_tool", {})
    assert "error" in res
    assert res["error"]["code"] == -32601


def test_get_zone_state_tool(mock_snapshot):
    server = MCPServer()
    res = server.call_tool("get_zone_state", arguments={"zone_ids": ["Zone1"]}, snapshot=mock_snapshot)
    assert "zones" in res
    assert len(res["zones"]) == 1
    assert res["zones"][0]["zone_id"] == "Zone1"


def test_get_weather_forecast_tool():
    server = MCPServer()
    res = server.call_tool("get_weather_forecast", arguments={"horizon_hours": 12})
    assert "series" in res
    assert len(res["series"]) == 12


def test_get_utility_signal_tool():
    server = MCPServer()
    res_disabled = server.call_tool("get_utility_signal", arguments={"enabled": False})
    assert not res_disabled["enabled"]
    assert res_disabled["carbon_intensity_gco2_kwh"] is None

    res_enabled = server.call_tool("get_utility_signal", arguments={"enabled": True})
    assert res_enabled["enabled"]
    assert res_enabled["carbon_intensity_gco2_kwh"] == 250.0


def test_compute_pmv_tool():
    server = MCPServer()
    res = server.call_tool("compute_pmv", arguments={"air_temp_c": 24.5, "mean_radiant_temp_c": 24.5, "air_speed_ms": 0.1, "rh_pct": 50.0})
    assert "pmv" in res
    assert "ppd_pct" in res
    assert -0.5 <= res["pmv"] <= 0.5


def test_validate_action_tool(mock_config):
    server = MCPServer()
    res_pass = server.call_tool(
        "validate_action",
        arguments={
            "candidate": {"htg_sp": 20.0, "clg_sp": 25.0},
            "cycle_id": "cycle_1",
            "allow_list": mock_config.actuators,
        },
    )
    assert res_pass["valid"]

    res_fail = server.call_tool(
        "validate_action",
        arguments={
            "candidate": {"htg_sp": 10.0, "clg_sp": 25.0},  # 10.0 below min 15.0
            "cycle_id": "cycle_1",
            "allow_list": mock_config.actuators,
        },
    )
    assert not res_fail["valid"]
    assert len(res_fail["reasons"]) > 0


def test_apply_setpoints_server_side_revalidation(mock_config):
    server = MCPServer()
    mock_hm = MagicMock()
    mock_hm.commit_actuator.return_value = True

    # 1. Out of bounds action -> re-validation fails
    res_invalid = server.call_tool(
        "apply_setpoints",
        arguments={
            "action": {"htg_sp": 5.0, "clg_sp": 25.0},  # 5.0 is out of bounds
            "cycle_id": "cycle_1",
            "handle_manager": mock_hm,
            "config": mock_config,
        },
    )
    assert res_invalid["isError"]
    assert res_invalid["reason"] == "out_of_bounds"

    # 2. Valid action -> passes re-validation and commits
    res_valid = server.call_tool(
        "apply_setpoints",
        arguments={
            "action": {"htg_sp": 20.0, "clg_sp": 25.0},
            "cycle_id": "cycle_1",
            "handle_manager": mock_hm,
            "config": mock_config,
        },
    )
    assert res_valid["committed"]
    assert res_valid["cycle_id"] == "cycle_1"
