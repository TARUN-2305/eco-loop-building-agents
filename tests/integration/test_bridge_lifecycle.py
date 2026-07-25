"""
Integration tests for EnergyPlusBridge execution lifecycle in fallback / simulated mode.
"""

import pytest
from src.bridge.lifecycle import EnergyPlusBridge, RunResult
from src.config.schema import (
    Config, SimulationConfig, ActuatorConfig, LLMConfig, ComfortConfig, EnergyConfig, StorageConfig, DecisionCadenceConfig
)


@pytest.fixture
def test_config():
    return Config(
        building_id="test_integration_bldg",
        simulation=SimulationConfig(idf_path="data/idf/baseline.idf", epw_path="data/epw/USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw", run_mode="agent"),
        actuators=[
            ActuatorConfig(
                logical_name="zone1_heating_setpoint",
                component_type="Schedule:Compact",
                control_type="Schedule Value",
                key="HTGSETP_SCH",
                min=15.0,
                max=23.0,
            ),
            ActuatorConfig(
                logical_name="zone1_cooling_setpoint",
                component_type="Schedule:Compact",
                control_type="Schedule Value",
                key="CLGSETP_SCH",
                min=22.0,
                max=30.0,
            )
        ],
        llm=LLMConfig(model_name="test", endpoint="http://localhost:11434/v1"),
        decision_cadence=DecisionCadenceConfig(interval_minutes=15),
    )


def test_bridge_simulated_fallback_run(test_config):
    bridge = EnergyPlusBridge(test_config)

    telemetry_count = 0
    decision_count = 0

    def mock_telemetry_sink(snapshot):
        nonlocal telemetry_count
        telemetry_count += 1

    def mock_decision_cycle(snapshot, cycle_id):
        nonlocal decision_count
        decision_count += 1
        return {"outcome": "committed", "action": {"htg_sp": 20.0}}

    res = bridge.run(
        on_decision_cycle_fn=mock_decision_cycle,
        telemetry_sink_fn=mock_telemetry_sink,
    )

    assert res.status == "completed"
    assert res.total_timesteps == 96
    assert telemetry_count == 96
    # 96 timesteps at 15-min cadence = 96 decision cycles
    assert decision_count == 96
