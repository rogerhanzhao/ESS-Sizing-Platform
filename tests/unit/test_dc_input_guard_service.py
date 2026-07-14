"""Guards for FT-20260714-07/09/11: reject inputs sizing cannot support."""

from __future__ import annotations

import pandas as pd

from calb_sizing_tool.services.dc_input_guard_service import (
    validate_dc_inputs,
    validate_soh_curve_support,
)


def _valid_case_input() -> dict:
    return {
        "poi_power_req_mw": 400.0,
        "poi_energy_req_mwh": 800.0,
        "project_life_years": 20,
        "cycles_per_year": 365,
        "poi_guarantee_year": 0,
        "sc_time_months": 3,
        "dod_pct": 95.0,
        "dc_round_trip_efficiency_pct": 94.0,
        "eff_dc_cables": 99.5,
        "eff_pcs": 98.5,
        "eff_mvt": 99.5,
        "eff_ac_cables_sw_rmu": 99.2,
        "eff_hvt_others": 100.0,
    }


def test_valid_inputs_pass():
    assert validate_dc_inputs(_valid_case_input()) == []


def test_fraction_notation_percent_fields_pass():
    case = _valid_case_input()
    case["dod_pct"] = 0.95
    case["eff_pcs"] = 0.985
    assert validate_dc_inputs(case) == []


def test_negative_power_rejected():
    case = _valid_case_input()
    case["poi_power_req_mw"] = -400.0
    errors = validate_dc_inputs(case)
    assert any("POI Required Power" in e for e in errors)


def test_zero_energy_rejected():
    case = _valid_case_input()
    case["poi_energy_req_mwh"] = 0.0
    errors = validate_dc_inputs(case)
    assert any("POI Required Capacity" in e for e in errors)


def test_dod_over_100_rejected():
    case = _valid_case_input()
    case["dod_pct"] = 150.0
    errors = validate_dc_inputs(case)
    assert any("DOD" in e for e in errors)


def test_efficiency_over_100_rejected():
    case = _valid_case_input()
    case["eff_pcs"] = 120.0
    errors = validate_dc_inputs(case)
    assert any("PCS efficiency" in e for e in errors)


def test_guarantee_year_beyond_life_rejected():
    case = _valid_case_input()
    case["poi_guarantee_year"] = 25
    errors = validate_dc_inputs(case)
    assert any("Guarantee Year" in e and "Project Life" in e for e in errors)


def test_guarantee_year_at_life_allowed():
    case = _valid_case_input()
    case["poi_guarantee_year"] = 20
    assert validate_dc_inputs(case) == []


def test_negative_life_and_cycles_rejected():
    case = _valid_case_input()
    case["project_life_years"] = 0
    case["cycles_per_year"] = -1
    errors = validate_dc_inputs(case)
    assert any("Project Life" in e for e in errors)
    assert any("Cycles Per Year" in e for e in errors)


def _curve(points_by_profile: dict) -> pd.DataFrame:
    rows = []
    for pid, n in points_by_profile.items():
        rows.extend({"Profile_Id": pid, "Life_Year_Index": i, "Soh_Dc_Pct": 1.0} for i in range(n))
    return pd.DataFrame(rows)


def test_soh_curve_with_full_points_supported():
    df = _curve({7: 21, 10: 1})
    assert validate_soh_curve_support(df, 7) is None


def test_soh_curve_with_placeholder_point_rejected():
    """1C placeholder profiles (single year-0 point) must reject the run."""
    df = _curve({7: 21, 10: 1})
    error = validate_soh_curve_support(df, 10, chosen_c_rate=1.0, effective_c_rate=0.89)
    assert error is not None
    assert "1C" in error
    assert "cannot be supported" in error


def test_soh_curve_missing_profile_rejected():
    df = _curve({7: 21})
    assert validate_soh_curve_support(df, 99) is not None
