"""Business input guards for DC sizing (FT-20260714-07/09/11).

Pre-run sanity validation plus a data-driven degradation-curve support
check. These guards reject inputs the sizing logic cannot support; they
do not re-derive or alter any frozen sizing formula
(see docs/SIZING_LOGIC_CANON_V1.md — validation is allowed, formulas are
not). The curve support check uses the SOH profile actually selected by
the pipeline, so support is defined by the product library content, not
by a hard-coded C-rate list.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from calb_sizing_tool.services.stage1_service import to_float, to_int

# Minimum curve points for a SOH profile to be considered a real
# degradation basis. Placeholder profiles carry a single year-0 point and
# would otherwise extrapolate a flat 100% SOH for the whole project life.
MIN_SOH_CURVE_POINTS = 2


def validate_dc_inputs(case_input: dict[str, Any]) -> list[str]:
    """Return business-rule violations for the editable DC form payload.

    Empty list means the inputs may proceed to the sizing pipeline.
    Percent-style fields arrive from the form as percent numbers
    (e.g. 95.0 for 95%).
    """
    errors: list[str] = []

    power = to_float(case_input.get("poi_power_req_mw"), 0.0)
    energy = to_float(case_input.get("poi_energy_req_mwh"), 0.0)
    if power <= 0:
        errors.append(f"POI Required Power must be greater than 0 MW (got {power:g} MW).")
    if energy <= 0:
        errors.append(f"POI Required Capacity must be greater than 0 MWh (got {energy:g} MWh).")

    life = to_int(case_input.get("project_life_years"), 0)
    if life < 1:
        errors.append(f"Project Life must be at least 1 year (got {life}).")

    cycles = to_int(case_input.get("cycles_per_year"), 0)
    if cycles < 1:
        errors.append(f"Cycles Per Year must be at least 1 (got {cycles}).")

    guarantee = to_int(case_input.get("poi_guarantee_year"), 0)
    if guarantee < 0:
        errors.append(f"POI Guarantee Year cannot be negative (got {guarantee}).")
    elif life >= 1 and guarantee > life:
        errors.append(
            f"POI Guarantee Year ({guarantee}) cannot exceed Project Life ({life} years)."
        )

    sc_months = to_int(case_input.get("sc_time_months"), 0)
    if sc_months < 0:
        errors.append(f"S&C Time cannot be negative (got {sc_months} months).")

    percent_fields = {
        "dod_pct": "DOD",
        "dc_round_trip_efficiency_pct": "DC RTE",
        "eff_dc_cables": "DC Cables efficiency",
        "eff_pcs": "PCS efficiency",
        "eff_mvt": "MV Transformer efficiency",
        "eff_ac_cables_sw_rmu": "AC Cables + SW efficiency",
        "eff_hvt_others": "HVT efficiency",
    }
    for field, label in percent_fields.items():
        if field not in case_input or case_input[field] is None:
            continue
        value = to_float(case_input[field], -1.0)
        # Form values are percent numbers; fractions (<= 1.5) are also
        # accepted upstream by to_frac, so validate both notations.
        pct = value * 100.0 if 0 < value <= 1.5 else value
        if pct <= 0 or pct > 100:
            errors.append(f"{label} must be within (0, 100] % (got {value:g}).")

    return errors


def soh_curve_point_count(df_soh_curve: pd.DataFrame, soh_profile_id: Any) -> int:
    if df_soh_curve is None or "Profile_Id" not in df_soh_curve.columns:
        return 0
    return int((df_soh_curve["Profile_Id"] == soh_profile_id).sum())


def validate_soh_curve_support(
    df_soh_curve: pd.DataFrame,
    soh_profile_id: Any,
    *,
    chosen_c_rate: float | None = None,
    effective_c_rate: float | None = None,
) -> str | None:
    """Reject runs whose selected SOH profile has no real degradation curve.

    Returns an error message when the product library cannot support the
    requested duty (e.g. 1C / 1-hour systems whose profiles only carry a
    placeholder year-0 point), otherwise None.
    """
    points = soh_curve_point_count(df_soh_curve, soh_profile_id)
    if points >= MIN_SOH_CURVE_POINTS:
        return None
    rate_txt = f"{chosen_c_rate:g}C" if chosen_c_rate is not None else "the required C-rate"
    eff_txt = (
        f" (effective C-rate {effective_c_rate:.2f})" if effective_c_rate is not None else ""
    )
    return (
        f"The product library has no degradation curve for {rate_txt}{eff_txt}: "
        f"SOH profile {soh_profile_id} carries {points} curve point(s), so lifetime "
        "sizing cannot be supported. Adjust the POI power/capacity duty to a "
        "supported duration or import the missing SOH curve data."
    )
