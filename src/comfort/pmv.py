"""
Fanger PMV/PPD Comfort Model implementation.
Implements ISO 7730 / ASHRAE Standard 55 formula deterministically.
Ref: Fanger (1970), ISO 7730:2005.
Supports: FR-3, CC-1, CC-2, ADR-010.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PMVResult:
    pmv: float
    ppd_pct: float


class PMVInputValidationError(ValueError):
    """Raised when comfort model inputs exceed standard applicability bounds."""
    pass


def compute_pmv(
    air_temp_c: float,
    mean_radiant_temp_c: float,
    air_speed_ms: float,
    rh_pct: float,
    met_rate: float = 1.2,  # Met units (1 met = 58.15 W/m²)
    clo: float = 0.5,        # Clo units (1 clo = 0.155 m²K/W)
) -> PMVResult:
    """
    Computes Predicted Mean Vote (PMV) and Predicted Percentage Dissatisfied (PPD)
    using Fanger's analytical model per ISO 7730.

    Applicability bounds (ASHRAE 55 / ISO 7730):
      air_temp_c: 10 to 32 °C
      mean_radiant_temp_c: 10 to 40 °C
      air_speed_ms: 0.0 to 1.0 m/s
      rh_pct: 0 to 100 %
      met_rate: 0.8 to 4.0 met
      clo: 0.0 to 2.0 clo
    """
    # Boundary validation per ISO 7730 standard limits
    if not (10.0 <= air_temp_c <= 32.0):
        raise PMVInputValidationError(f"Air temperature {air_temp_c}°C outside valid range [10, 32]")
    if not (10.0 <= mean_radiant_temp_c <= 40.0):
        raise PMVInputValidationError(f"Mean radiant temperature {mean_radiant_temp_c}°C outside valid range [10, 40]")
    if not (0.0 <= air_speed_ms <= 1.0):
        raise PMVInputValidationError(f"Air speed {air_speed_ms} m/s outside valid range [0, 1.0]")
    if not (0.0 <= rh_pct <= 100.0):
        raise PMVInputValidationError(f"Relative humidity {rh_pct}% outside valid range [0, 100]")
    if not (0.8 <= met_rate <= 4.0):
        raise PMVInputValidationError(f"Metabolic rate {met_rate} met outside valid range [0.8, 4.0]")
    if not (0.0 <= clo <= 2.0):
        raise PMVInputValidationError(f"Clothing insulation {clo} clo outside valid range [0.0, 2.0]")

    # Saturation vapor pressure over water (Pa)
    # Antoine-like relation for p_sat in Pa
    p_sat = 1000.0 * 0.6105 * math.exp((17.27 * air_temp_c) / (air_temp_c + 237.3))
    # Water vapor pressure (Pa)
    p_a = (rh_pct / 100.0) * p_sat

    # Internal heat production per unit area (W/m²)
    m = met_rate * 58.15
    w = 0.0  # External work assumed 0
    h_met = m - w

    # Clothing thermal resistance (m²K/W)
    r_clo = 0.155 * clo
    f_clo = 1.05 + 0.645 * r_clo if r_clo > 0.078 else 1.00 + 1.29 * r_clo

    t_a = air_temp_c
    t_mr = mean_radiant_temp_c

    # Iteratively solve for clothing surface temperature (t_cl in °C)
    t_cl = t_a
    for _ in range(200):
        h_cf = 12.1 * math.sqrt(air_speed_ms)
        h_cn = 2.38 * math.pow(abs(t_cl - t_a), 0.25)
        h_c = max(h_cf, h_cn)

        t_cl_next = 35.7 - 0.028 * h_met - r_clo * (
            3.96e-8 * f_clo * (math.pow(t_cl + 273.0, 4) - math.pow(t_mr + 273.0, 4)) + f_clo * h_c * (t_cl - t_a)
        )

        if abs(t_cl_next - t_cl) < 0.0001:
            t_cl = t_cl_next
            break
        t_cl = 0.8 * t_cl + 0.2 * t_cl_next  # Relaxed update for stability

    h_cf = 12.1 * math.sqrt(air_speed_ms)
    h_cn = 2.38 * math.pow(abs(t_cl - t_a), 0.25)
    h_c = max(h_cf, h_cn)

    # Heat loss components (W/m²)
    hl_skin_diff = 3.05e-3 * (5733.0 - 6.99 * h_met - p_a)
    hl_sweat = 0.42 * (h_met - 58.15) if h_met > 58.15 else 0.0
    hl_resp_lat = 1.7e-5 * m * (5867.0 - p_a)
    hl_resp_dry = 0.0014 * m * (34.0 - t_a)
    hl_rad = 3.96e-8 * f_clo * (math.pow(t_cl + 273.0, 4) - math.pow(t_mr + 273.0, 4))
    hl_conv = f_clo * h_c * (t_cl - t_a)

    thermal_load = h_met - (hl_skin_diff + hl_sweat + hl_resp_lat + hl_resp_dry + hl_rad + hl_conv)

    # PMV index
    pmv = (0.303 * math.exp(-0.036 * m) + 0.028) * thermal_load
    pmv = round(pmv, 3)

    # PPD percentage per ISO 7730
    ppd_pct = 100.0 - 95.0 * math.exp(-0.03353 * math.pow(pmv, 4) - 0.2179 * math.pow(pmv, 2))
    ppd_pct = round(ppd_pct, 2)

    return PMVResult(pmv=pmv, ppd_pct=ppd_pct)
