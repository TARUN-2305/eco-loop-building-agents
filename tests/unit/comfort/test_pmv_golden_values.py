"""
Golden-value unit tests for Fanger PMV/PPD computation against ISO 7730 reference benchmarks.
"""

import pytest
from src.comfort.pmv import compute_pmv, PMVInputValidationError


def test_pmv_neutral_comfort_condition():
    # ISO 7730 typical neutral summer condition (24.5°C, 0.5 clo, 1.2 met)
    res = compute_pmv(
        air_temp_c=24.5,
        mean_radiant_temp_c=24.5,
        air_speed_ms=0.1,
        rh_pct=50.0,
        met_rate=1.2,
        clo=0.5,
    )
    # PMV should be near 0.0 (-0.2 to +0.2) and PPD ~ 5-6%
    assert -0.3 <= res.pmv <= 0.3
    assert 5.0 <= res.ppd_pct <= 10.0


def test_pmv_warm_condition():
    # Warm condition (28.0°C)
    res = compute_pmv(
        air_temp_c=28.0,
        mean_radiant_temp_c=28.0,
        air_speed_ms=0.1,
        rh_pct=60.0,
        met_rate=1.2,
        clo=0.5,
    )
    assert res.pmv > 0.5
    assert res.ppd_pct > 10.0


def test_pmv_cool_condition():
    # Cool condition (18.0°C)
    res = compute_pmv(
        air_temp_c=18.0,
        mean_radiant_temp_c=18.0,
        air_speed_ms=0.1,
        rh_pct=40.0,
        met_rate=1.2,
        clo=0.5,
    )
    assert res.pmv < -0.5
    assert res.ppd_pct > 10.0


def test_pmv_boundary_validation_raises():
    with pytest.raises(PMVInputValidationError, match="Air temperature"):
        compute_pmv(air_temp_c=5.0, mean_radiant_temp_c=20.0, air_speed_ms=0.1, rh_pct=50.0)

    with pytest.raises(PMVInputValidationError, match="Air speed"):
        compute_pmv(air_temp_c=23.0, mean_radiant_temp_c=23.0, air_speed_ms=3.0, rh_pct=50.0)

    with pytest.raises(PMVInputValidationError, match="Relative humidity"):
        compute_pmv(air_temp_c=23.0, mean_radiant_temp_c=23.0, air_speed_ms=0.1, rh_pct=105.0)
