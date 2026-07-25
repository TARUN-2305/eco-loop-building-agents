"""
Property-based fuzzing tests for validate_action using Hypothesis.
Implements 13_Testing.md §2, §8.
Asserts that validator is total (never raises) and catches 100% of out-of-bound or unlisted actions.
"""

import pytest
from hypothesis import given, strategies as st
from src.validator.bounds import validate_action
from src.config.schema import ActuatorConfig


@pytest.fixture
def sample_allow_list():
    return [
        ActuatorConfig(
            logical_name="zone1_heating_setpoint",
            component_type="Zone Temperature Control",
            control_type="Heating Setpoint Schedule Value",
            key="SCH_HTG",
            min=15.0,
            max=23.0,
        ),
        ActuatorConfig(
            logical_name="zone1_cooling_setpoint",
            component_type="Zone Temperature Control",
            control_type="Cooling Setpoint Schedule Value",
            key="SCH_CLG",
            min=22.0,
            max=30.0,
        ),
    ]


@given(
    htg_val=st.floats(min_value=5.0, max_value=35.0, allow_nan=False, allow_infinity=False),
    clg_val=st.floats(min_value=15.0, max_value=40.0, allow_nan=False, allow_infinity=False),
    predicted_pmv=st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
def test_property_validator_never_raises_and_enforces_bounds(htg_val, clg_val, predicted_pmv):
    allow_list = [
        ActuatorConfig("zone1_heating_setpoint", "Type", "Ctrl", "Key", min=15.0, max=23.0),
        ActuatorConfig("zone1_cooling_setpoint", "Type", "Ctrl", "Key", min=22.0, max=30.0),
    ]

    candidate = {
        "zone1_heating_setpoint": htg_val,
        "zone1_cooling_setpoint": clg_val,
    }

    # Must never raise an exception
    res = validate_action(candidate, allow_list, predicted_pmv=predicted_pmv)

    # Check expectations
    htg_ok = 15.0 <= htg_val <= 23.0
    clg_ok = 22.0 <= clg_val <= 30.0
    pmv_ok = -1.5 <= predicted_pmv <= 1.5

    expected_valid = htg_ok and clg_ok and pmv_ok
    assert res.valid == expected_valid
    if not expected_valid:
        assert len(res.reasons) > 0


@given(unlisted_key=st.text(min_size=1, max_size=20))
def test_property_unlisted_actuator_rejected(unlisted_key):
    if unlisted_key in ("zone1_heating_setpoint", "zone1_cooling_setpoint"):
        return

    allow_list = [
        ActuatorConfig("zone1_heating_setpoint", "Type", "Ctrl", "Key", min=15.0, max=23.0),
    ]

    candidate = {unlisted_key: 20.0}
    res = validate_action(candidate, allow_list)

    assert not res.valid
    assert any("not in the allow-list" in r for r in res.reasons)
