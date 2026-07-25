"""
Unit tests for propose_setpoints_solver.
"""

import pytest
from src.optimizer.solver import propose_setpoints_solver
from src.shared.types import SensorSnapshot, ZoneState
from src.config.schema import ActuatorConfig


@pytest.fixture
def allow_list():
    return [
        ActuatorConfig(
            logical_name="htg_sp",
            component_type="Zone Temperature Control",
            control_type="Heating Setpoint Schedule Value",
            key="SCH_HTG",
            min=15.0,
            max=23.0,
        ),
        ActuatorConfig(
            logical_name="clg_sp",
            component_type="Zone Temperature Control",
            control_type="Cooling Setpoint Schedule Value",
            key="SCH_CLG",
            min=22.0,
            max=30.0,
        ),
    ]


@pytest.fixture
def current_snapshot():
    return SensorSnapshot(
        sim_time="Day_1_Hour_14.00",
        zones=[ZoneState("Zone1", 24.0, 50.0, None, 0.0, 5.0, {"htg_sp": 20.0, "clg_sp": 25.0})],
        meters={"facility_electricity_kw": 20.0},
    )


def test_solver_proposes_valid_candidate(allow_list, current_snapshot):
    res = propose_setpoints_solver(
        objective_weights={"w_energy": 0.5, "w_comfort_penalty": 0.5},
        horizon_steps=4,
        current_snapshot=current_snapshot,
        allow_list=allow_list,
    )

    assert res["status"] == "success"
    cand = res["candidate"]
    assert cand is not None
    assert 15.0 <= cand["htg_sp"] <= 23.0
    assert 22.0 <= cand["clg_sp"] <= 30.0
    assert cand["clg_sp"] >= cand["htg_sp"] + 1.0
    assert "energy_savings_priority" in res["rationale_tags"] or "comfort_priority" in res["rationale_tags"]


def test_solver_handles_comfort_priority(allow_list, current_snapshot):
    res = propose_setpoints_solver(
        objective_weights={"w_energy": 0.1, "w_comfort_penalty": 0.9},
        horizon_steps=4,
        current_snapshot=current_snapshot,
        allow_list=allow_list,
    )

    assert res["status"] == "success"
    assert "comfort_priority" in res["rationale_tags"]
