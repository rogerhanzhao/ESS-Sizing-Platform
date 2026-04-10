from __future__ import annotations

import math
from typing import Any

from calb_sizing_tool.schemas.stage1 import Stage1Input, Stage1Result


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(to_float(value, default))
    except Exception:
        return default


def to_frac(value: Any, default: float = 1.0) -> float:
    numeric = to_float(value, default)
    if numeric > 1.5:
        return numeric / 100.0
    return numeric


def clamp01(value: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except Exception:
        return 0.0


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    try:
        if b is None or abs(float(b)) < 1e-12:
            return default
        return float(a) / float(b)
    except Exception:
        return default


def calc_sc_loss_pct(sc_months: float) -> float:
    months = to_int(sc_months, 0)
    if months <= 0:
        return 0.0
    mapping = {
        1: 2.0, 2: 2.0, 3: 2.0,
        4: 2.5, 5: 2.8, 6: 3.0,
        7: 3.2, 8: 3.5, 9: 3.8,
        10: 4.1, 11: 4.3, 12: 4.5,
    }
    if months in mapping:
        return mapping[months]
    if months > 12:
        return 4.5 + ((months - 12) * 0.05)
    return mapping.get(months, 2.0)


def stage1_input_from_sources(inputs: dict[str, Any], defaults: dict[str, Any]) -> Stage1Input:
    def get(name: str, fallback: Any = None) -> Any:
        if name in inputs and inputs[name] is not None:
            return inputs[name]
        if name in defaults:
            return defaults[name]
        return fallback

    return Stage1Input(
        project_name=str(get("project_name", "CALB ESS Project")),
        poi_power_req_mw=to_float(get("poi_power_req_mw", 100.0)),
        poi_energy_req_mwh=to_float(get("poi_energy_req_mwh", 400.0)),
        project_life_years=to_int(get("project_life_years", 20), 20),
        cycles_per_year=to_int(get("cycles_per_year", 365), 365),
        poi_guarantee_year=to_int(get("poi_guarantee_year", 0), 0),
        eff_dc_cables=to_frac(get("eff_dc_cables", 0.995)),
        eff_pcs=to_frac(get("eff_pcs", 0.985)),
        eff_mvt=to_frac(get("eff_mvt", 0.995)),
        eff_ac_cables_sw_rmu=to_frac(get("eff_ac_cables_sw_rmu", 0.992)),
        eff_hvt_others=to_frac(get("eff_hvt_others", 1.0)),
        sc_time_months=max(3, to_int(get("sc_time_months", 3), 3)),
        dod_pct=to_frac(get("dod_pct", 95.0)),
        dc_round_trip_efficiency_pct=to_frac(get("dc_round_trip_efficiency_pct", 94.0)),
        rte_curve_adjust_pp=to_float(get("rte_curve_adjust_pp", 0.0), 0.0),
        rte_monotonic_enforce=bool(get("rte_monotonic_enforce", True)),
    )


def run_stage1(inputs: dict[str, Any], defaults: dict[str, Any]) -> Stage1Result:
    request = stage1_input_from_sources(inputs, defaults)

    eff_chain = (
        request.eff_dc_cables
        * request.eff_pcs
        * request.eff_mvt
        * request.eff_ac_cables_sw_rmu
        * request.eff_hvt_others
    )
    sc_loss_pct = calc_sc_loss_pct(request.sc_time_months)
    sc_loss_frac = sc_loss_pct / 100.0
    rte_adjust_frac = request.rte_curve_adjust_pp / 100.0
    dc_rte_effective_frac = clamp01(request.dc_round_trip_efficiency_pct + rte_adjust_frac)
    dc_one_way_eff = math.sqrt(dc_rte_effective_frac) if dc_rte_effective_frac >= 0 else 0.0
    dc_usable_bol_frac = request.dod_pct * dc_one_way_eff
    denom = (1.0 - sc_loss_frac) * dc_usable_bol_frac * eff_chain
    dc_energy_required = safe_div(request.poi_energy_req_mwh, denom, default=0.0)
    dc_power_required_mw = safe_div(request.poi_power_req_mw, eff_chain, default=0.0) if eff_chain > 0 else 0.0

    return Stage1Result(
        project_name=request.project_name,
        poi_power_req_mw=request.poi_power_req_mw,
        poi_energy_req_mwh=request.poi_energy_req_mwh,
        project_life_years=request.project_life_years,
        cycles_per_year=request.cycles_per_year,
        poi_guarantee_year=request.poi_guarantee_year,
        eff_dc_cables_frac=request.eff_dc_cables,
        eff_pcs_frac=request.eff_pcs,
        eff_mvt_frac=request.eff_mvt,
        eff_ac_cables_sw_rmu_frac=request.eff_ac_cables_sw_rmu,
        eff_hvt_others_frac=request.eff_hvt_others,
        eff_dc_to_poi_frac=eff_chain,
        sc_time_months=request.sc_time_months,
        sc_loss_pct=sc_loss_pct,
        sc_loss_frac=sc_loss_frac,
        dod_frac=request.dod_pct,
        dc_round_trip_efficiency_frac=dc_rte_effective_frac,
        dc_rte_base_frac=request.dc_round_trip_efficiency_pct,
        dc_rte_effective_frac=dc_rte_effective_frac,
        rte_curve_adjust_pp=request.rte_curve_adjust_pp,
        rte_adjust_frac=rte_adjust_frac,
        rte_monotonic_enforce=request.rte_monotonic_enforce,
        dc_one_way_efficiency_frac=dc_one_way_eff,
        dc_usable_bol_frac=dc_usable_bol_frac,
        dc_energy_capacity_required_mwh=dc_energy_required,
        dc_power_required_mw=dc_power_required_mw,
    )
