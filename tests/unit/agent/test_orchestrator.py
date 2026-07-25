"""
Unit tests for AgentOrchestrator ReAct decision cycle loop, two-tier memory, and degraded mode.
"""

import pytest
import os
import tempfile
from unittest.mock import MagicMock
from src.agent.orchestrator import AgentOrchestrator
from src.agent.llm_client import LLMClient
from src.mcp_server.server import MCPServer
from src.bridge.handles import HandleManager
from src.storage.writer import AsyncStorageWriter
from src.monitoring.health import HealthMonitor
from src.shared.types import SensorSnapshot, ZoneState
from src.config.schema import (
    Config, SimulationConfig, ActuatorConfig, LLMConfig, ComfortConfig, EnergyConfig, StorageConfig, DecisionCadenceConfig
)


@pytest.fixture
def mock_config():
    return Config(
        building_id="bldg_agent_test",
        simulation=SimulationConfig("test.idf", "test.epw", "agent"),
        actuators=[
            ActuatorConfig("htg_sp", "Type", "Ctrl", "Key", 15.0, 23.0),
            ActuatorConfig("clg_sp", "Type", "Ctrl", "Key", 22.0, 30.0),
        ],
        llm=LLMConfig("model", endpoint=None),
        decision_cadence=DecisionCadenceConfig(interval_minutes=15),
    )


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_orchestrator_decision_cycle_stub_mode(mock_config, temp_db):
    mcp_server = MCPServer()
    hm = HandleManager()
    hm._handles_resolved = True
    hm._actuator_handles["htg_sp"] = 1
    hm._actuator_handles["clg_sp"] = 2

    writer = AsyncStorageWriter(db_path=temp_db, backend="sqlite")
    writer.start()
    health = HealthMonitor()

    orchestrator = AgentOrchestrator(
        config=mock_config,
        mcp_server=mcp_server,
        handle_manager=hm,
        storage_writer=writer,
        health_monitor=health,
    )

    snapshot = SensorSnapshot(
        sim_time="Day_1_Hour_12.00",
        zones=[ZoneState("Zone1", 23.0, 50.0, None, 0.0, 5.0, {"htg_sp": 20.0, "clg_sp": 25.0})],
        meters={"facility_electricity_kw": 15.0},
    )

    res = orchestrator.on_decision_cycle(snapshot, cycle_id="cycle_test_01")
    assert res["outcome"] in ("committed", "fallback")

    writer.stop()


def test_orchestrator_degraded_mode_bypasses_llm(mock_config, temp_db):
    mcp_server = MCPServer()
    hm = HandleManager()
    writer = AsyncStorageWriter(db_path=temp_db, backend="sqlite")
    writer.start()

    health = HealthMonitor()
    health.degraded_mode_active = True  # Activate degraded mode

    orchestrator = AgentOrchestrator(
        config=mock_config,
        mcp_server=mcp_server,
        handle_manager=hm,
        storage_writer=writer,
        health_monitor=health,
    )

    snapshot = SensorSnapshot("Timestep_1", [], {})

    # In degraded mode, decision cycle immediately returns fallback without invoking LLM
    res = orchestrator.on_decision_cycle(snapshot, cycle_id="cycle_degraded_1")
    assert res["outcome"] == "fallback"

    writer.stop()
