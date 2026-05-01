from __future__ import annotations

import math

import pandas as pd

from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle
from calb_sizing_tool.schemas.stage1 import Stage1Result
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.schemas.stage3 import Stage3Meta, Stage3Result, Stage3YearRecord
from calb_sizing_tool.services.stage1_service import clamp01, safe_div, to_float, to_frac


def select_soh_profile(effective_c_rate: float, cycles_per_year: int, df_soh_profile: pd.DataFrame):
    df = df_soh_profile.copy()
    df["c_rate_diff"] = (df["C_Rate"] - effective_c_rate).abs()
    df["cycles_diff"] = (df["Cycles_Per_Year"] - cycles_per_year).abs()
    df["score"] = df["c_rate_diff"] * 10.0 + df["cycles_diff"] / 365.0
    best = df.sort_values("score").iloc[0]
    return int(best["Profile_Id"]), float(best["C_Rate"]), int(best["Cycles_Per_Year"])


def select_rte_profile(effective_c_rate: float, df_rte_profile: pd.DataFrame):
    df = df_rte_profile.copy()
    df["c_rate_diff"] = (df["C_Rate"] - effective_c_rate).abs()
    best = df.sort_values("c_rate_diff").iloc[0]
    return int(best["Profile_Id"]), float(best["C_Rate"])


def run_stage3(stage1: Stage1Result, stage2: Stage2Result, bundle: DcExcelMasterDataBundle) -> Stage3Result:
    dc_nameplate_bol_mwh = stage2.dc_nameplate_bol_mwh
    if dc_nameplate_bol_mwh <= 0:
        raise ValueError("DC nameplate @BOL must be > 0 for Stage 3.")

    poi_mw = stage1.poi_power_req_mw
    poi_energy_mwh = stage1.poi_energy_req_mwh
    project_life_years = int(stage1.project_life_years)
    cycles_per_year = int(stage1.cycles_per_year)
    sc_loss_frac = stage1.sc_loss_frac
    dod_frac = stage1.dod_frac
    eff_chain = stage1.eff_dc_to_poi_frac
    guarantee_year = int(stage1.poi_guarantee_year)
    rte_adjust_frac = to_float(stage1.rte_adjust_frac, 0.0)
    rte_monotonic_enforce = bool(stage1.rte_monotonic_enforce)

    dc_power_mw = safe_div(poi_mw, eff_chain, default=0.0) if eff_chain > 0 else 0.0
    effective_c_rate = safe_div(dc_power_mw, dc_nameplate_bol_mwh, default=0.0)

    soh_profile_id, chosen_soh_c_rate, chosen_cycles_per_year = select_soh_profile(
        effective_c_rate, cycles_per_year, bundle.df_soh_profile
    )
    rte_profile_id, chosen_rte_c_rate = select_rte_profile(effective_c_rate, bundle.df_rte_profile)

    soh_curve_sel = bundle.df_soh_curve[bundle.df_soh_curve["Profile_Id"] == soh_profile_id].copy()
    soh_curve_sel["Soh_Dc_Pct"] = soh_curve_sel["Soh_Dc_Pct"].apply(lambda value: to_frac(value))
    soh_curve_sel = soh_curve_sel.sort_values("Life_Year_Index")

    rte_curve_sel = bundle.df_rte_curve[bundle.df_rte_curve["Profile_Id"] == rte_profile_id].copy()
    rte_curve_sel["Soh_Band_Min_Pct"] = rte_curve_sel["Soh_Band_Min_Pct"].apply(lambda value: to_frac(value))
    rte_curve_sel["Rte_Dc_Pct"] = rte_curve_sel["Rte_Dc_Pct"].apply(lambda value: to_frac(value))
    rte_curve_sel = rte_curve_sel.sort_values("Soh_Band_Min_Pct", ascending=False)
    if rte_monotonic_enforce:
        rte_curve_sel["Rte_Dc_Pct"] = pd.to_numeric(rte_curve_sel["Rte_Dc_Pct"], errors="coerce")
        rte_curve_sel["Rte_Dc_Pct"] = rte_curve_sel["Rte_Dc_Pct"].ffill().bfill()
        rte_curve_sel["Rte_Dc_Pct"] = rte_curve_sel["Rte_Dc_Pct"].cummin()

    rows: list[Stage3YearRecord] = []
    dc_usable_bol_mwh = None
    dc_usable_cod_mwh = None

    for year_index in range(0, project_life_years + 1):
        row = soh_curve_sel[soh_curve_sel["Life_Year_Index"] == year_index]
        soh_rel = float(row["Soh_Dc_Pct"].iloc[0]) if not row.empty else float(soh_curve_sel["Soh_Dc_Pct"].iloc[-1])
        soh_rel_calc = round(soh_rel * 100.0, 1) / 100.0
        soh_abs = soh_rel * (1.0 - sc_loss_frac)

        rte_row = rte_curve_sel[rte_curve_sel["Soh_Band_Min_Pct"] <= soh_rel].head(1)
        if rte_row.empty:
            rte_row = rte_curve_sel.tail(1)
        raw_rte = float(rte_row["Rte_Dc_Pct"].iloc[0])
        dc_rte_frac_year = clamp01(raw_rte + rte_adjust_frac)

        if year_index == 0:
            dc_usable_bol_mwh = dc_nameplate_bol_mwh * dod_frac * math.sqrt(dc_rte_frac_year)
            dc_usable_cod_mwh = dc_usable_bol_mwh * (1.0 - sc_loss_frac)
        if dc_usable_bol_mwh is None:
            dc_usable_bol_mwh = dc_nameplate_bol_mwh * dod_frac
        if dc_usable_cod_mwh is None:
            dc_usable_cod_mwh = dc_usable_bol_mwh * (1.0 - sc_loss_frac)

        dc_gross_capacity_mwh_year = dc_nameplate_bol_mwh * (1.0 - sc_loss_frac) * soh_rel_calc
        dc_usable_mwh_year = dc_usable_cod_mwh * soh_rel_calc
        poi_usable_mwh_year = max(dc_usable_mwh_year * eff_chain, 0.0)
        system_rte_frac_year = min(1.0, max(0.0, dc_rte_frac_year * (eff_chain ** 2)))

        rows.append(
            Stage3YearRecord(
                year_index=year_index,
                soh_relative=soh_rel_calc,
                soh_absolute=soh_abs,
                dc_nameplate_bol_mwh=dc_nameplate_bol_mwh,
                dc_gross_capacity_mwh=dc_gross_capacity_mwh_year,
                dc_usable_mwh=dc_usable_mwh_year,
                dc_rte_frac=dc_rte_frac_year,
                system_rte_frac=system_rte_frac_year,
                poi_usable_energy_mwh=poi_usable_mwh_year,
                meets_poi_req=poi_usable_mwh_year >= poi_energy_mwh,
                is_guarantee_year=(year_index == guarantee_year),
                soh_display_pct=soh_rel_calc * 100.0,
                soh_absolute_pct=soh_abs * 100.0,
                dc_rte_pct=dc_rte_frac_year * 100.0,
                system_rte_pct=system_rte_frac_year * 100.0,
            )
        )

    meta = Stage3Meta(
        poi_power_mw=poi_mw,
        dc_power_mw=dc_power_mw,
        effective_c_rate=effective_c_rate,
        soh_profile_id=soh_profile_id,
        rte_profile_id=rte_profile_id,
        chosen_soh_c_rate=chosen_soh_c_rate,
        chosen_soh_cycles_per_year=chosen_cycles_per_year,
        chosen_rte_c_rate=chosen_rte_c_rate,
        rte_adjust_pp=stage1.rte_curve_adjust_pp,
        rte_monotonic_enforce=rte_monotonic_enforce,
        dc_usable_bol_mwh=dc_usable_bol_mwh or 0.0,
        dc_usable_cod_mwh=dc_usable_cod_mwh or 0.0,
    )
    return Stage3Result(rows=rows, meta=meta)
