# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

import datetime
import io
import re
from typing import Optional

import pandas as pd
from docx import Document
from docx.shared import Inches

from calb_sizing_tool.reporting.export_docx import _add_cover_page, _add_table, _doc_to_bytes, _keep_next_para, _setup_header, _setup_margins
from calb_sizing_tool.reporting.formatter import format_percent, format_value
from calb_sizing_tool.reporting.report_context import ReportContext

try:
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

try:
    import cairosvg

    CAIROSVG_AVAILABLE = True
except Exception:
    CAIROSVG_AVAILABLE = False


def _format_percent_with_fraction(value, input_is_fraction=None, fraction_decimals=4) -> str:
    """Legacy helper retained for compatibility; prefer format_percent() in new code."""
    if value is None:
        return ""
    try:
        numeric = float(value)
    except Exception:
        return str(value)

    if input_is_fraction is None:
        is_fraction = numeric <= 1.2
    else:
        is_fraction = bool(input_is_fraction)

    fraction = numeric if is_fraction else numeric / 100.0
    percent_text = format_percent(numeric, input_is_fraction=is_fraction)
    return f"{percent_text} ({fraction:.{fraction_decimals}f})"


def _default_formatter(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value)


def _add_dataframe_table(doc: Document, df: Optional[pd.DataFrame], columns, headers_map, formatters, *, keep_together: bool | None = None):
    if df is None or df.empty:
        doc.add_paragraph("No data available.")
        return

    rows = []
    for _, row in df.iterrows():
        rows.append([formatters.get(col, _default_formatter)(row.get(col)) for col in columns])

    headers = [headers_map.get(col, col) for col in columns]
    _add_table(doc, rows, headers, keep_together=keep_together)


def _plot_poi_usable_png(df: pd.DataFrame, poi_target: float, title: str) -> Optional[io.BytesIO]:
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        data = df.sort_values("Year_Index").copy()
        x = data["Year_Index"].astype(int).tolist()
        y = data["POI_Usable_Energy_MWh"].astype(float).tolist()

        fig = plt.figure(figsize=(7.0, 3.2))
        ax = fig.add_subplot(111)
        ax.bar(x, y, color="#5cc3e4")
        ax.axhline(poi_target, linewidth=2, color="#ff0000")
        ax.set_title(title)
        ax.set_xlabel("Year (from COD)")
        ax.set_ylabel("POI Usable Energy (MWh)")
        ax.set_xticks(x)
        ax.grid(True, axis="y", linestyle="--", alpha=0.35)

        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        return None


def _plot_dc_capacity_bar_png(
    bol_mwh: Optional[float],
    s3_df: Optional[pd.DataFrame],
    guarantee_year: int,
    title: str,
) -> Optional[io.BytesIO]:
    """Bar chart: DC Nameplate (BOL) vs POI Usable at COD and at guarantee year.

    Note: BOL is a DC-side metric; COD and Yx values are POI-side.
    This chart is retained for internal/debugging use; the main report uses
    _plot_poi_usable_png which shows a consistent POI-only view.
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        cod = None
        yx = None
        if s3_df is not None and not s3_df.empty:
            year0 = s3_df[s3_df["Year_Index"] == 0]
            if not year0.empty:
                cod = float(year0["POI_Usable_Energy_MWh"].iloc[0])
            g_row = s3_df[s3_df["Year_Index"] == int(guarantee_year)]
            if not g_row.empty:
                yx = float(g_row["POI_Usable_Energy_MWh"].iloc[0])

        labels = ["DC Nameplate\n(BOL)", "POI Usable\n(COD)", f"POI Usable\n(Y{int(guarantee_year)})"]
        values = [
            float(bol_mwh) if bol_mwh is not None else 0.0,
            float(cod) if cod is not None else 0.0,
            float(yx) if yx is not None else 0.0,
        ]

        fig = plt.figure(figsize=(6.6, 3.0))
        ax = fig.add_subplot(111)
        ax.bar(labels, values, color="#5cc3e4")
        ax.set_title(title)
        ax.set_xlabel("Stage")
        ax.set_ylabel("Energy (MWh)")
        ax.grid(True, axis="y", linestyle="--", alpha=0.35)

        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        return None


def _format_or_tbd(value, unit: str) -> str:
    if value is None:
        return "TBD"
    try:
        numeric = float(value)
    except Exception:
        return str(value) if value else "TBD"
    if numeric <= 0:
        return "TBD"
    return format_value(numeric, unit)


def _format_transformer_rating(value) -> str:
    if value is None:
        return "TBD"
    try:
        kva = float(value)
    except Exception:
        return "TBD"
    if kva <= 0:
        return "TBD"
    mva = kva / 1000.0
    return f"{mva:.2f} MVA ({kva:.0f} kVA)"


def _svg_bytes_to_png(svg_bytes: bytes, width_px: int = 900) -> Optional[bytes]:
    if not svg_bytes or not CAIROSVG_AVAILABLE:
        return None
    try:
        return cairosvg.svg2png(bytestring=svg_bytes, output_width=width_px)
    except Exception:
        return None


def _validate_efficiency_chain(ctx: ReportContext) -> list[str]:
    """Validate efficiency chain completeness and internal consistency.

    Returns advisory warning messages; does not block export.
    """
    warnings = []

    if not isinstance(ctx.stage1, dict) or not ctx.stage1:
        warnings.append(
            "Cannot validate efficiency: stage1 (DC SIZING output) is missing or invalid. "
            "Ensure DC SIZING was completed before exporting."
        )

    components = [
        ("DC Cables", ctx.efficiency_components_frac.get("eff_dc_cables_frac")),
        ("PCS", ctx.efficiency_components_frac.get("eff_pcs_frac")),
        ("Transformer (MVT)", ctx.efficiency_components_frac.get("eff_mvt_frac")),
        ("RMU/Switchgear/AC Cables", ctx.efficiency_components_frac.get("eff_ac_cables_sw_rmu_frac")),
        ("HVT/Others", ctx.efficiency_components_frac.get("eff_hvt_others_frac")),
    ]

    has_all_components = True
    for name, value in components:
        if value is None or value <= 0:
            warnings.append(f"Efficiency component '{name}' is missing or zero: {value}.")
            has_all_components = False
        elif value > 1.2:
            warnings.append(f"Efficiency component '{name}' exceeds 120%: {value}")

    if ctx.efficiency_chain_oneway_frac is None or ctx.efficiency_chain_oneway_frac <= 0:
        warnings.append(f"Total one-way efficiency chain is missing or zero: {ctx.efficiency_chain_oneway_frac}.")
    elif ctx.efficiency_chain_oneway_frac > 1.2:
        warnings.append(f"Total one-way efficiency exceeds 120%: {ctx.efficiency_chain_oneway_frac}")

    if has_all_components and ctx.efficiency_chain_oneway_frac and ctx.efficiency_chain_oneway_frac > 0:
        product = 1.0
        for name, value in components:
            if value and value > 0:
                product *= value
        relative_error = abs(product - ctx.efficiency_chain_oneway_frac) / ctx.efficiency_chain_oneway_frac
        if relative_error > 0.02:
            warnings.append(
                f"Total efficiency ({ctx.efficiency_chain_oneway_frac:.6f}) "
                f"does not match product of components ({product:.6f}); "
                f"relative error: {relative_error * 100:.2f}%."
            )

    if ctx.efficiency_chain_oneway_frac is not None and ctx.efficiency_chain_oneway_frac < 0.001:
        warnings.append("Efficiency chain appears uninitialized; ensure DC SIZING was completed.")

    return warnings


def _aggregate_ac_block_configs(ctx: ReportContext) -> list[dict]:
    """Aggregate AC Block configurations by signature (PCS count, rating, power per block).

    Returns list of dicts with keys: pcs_per_block, pcs_kw, ac_block_power_mw, count.
    """
    if ctx.ac_blocks_total == 0:
        return []

    pcs_per_block = ctx.pcs_per_block
    pcs_kw = None
    if isinstance(ctx.ac_output, dict) and ctx.ac_output.get("pcs_kw"):
        pcs_kw = ctx.ac_output.get("pcs_kw")
    if pcs_kw is None and isinstance(ctx.ac_output, dict):
        pcs_kw = ctx.ac_output.get("pcs_power_kw")

    ac_block_power_mw = ctx.ac_block_size_mw
    if pcs_kw is None and ac_block_power_mw and pcs_per_block and pcs_per_block > 0:
        pcs_kw = int((ac_block_power_mw * 1000) / pcs_per_block)

    return [
        {
            "pcs_per_block": pcs_per_block,
            "pcs_kw": pcs_kw,
            "ac_block_power_mw": ac_block_power_mw,
            "count": ctx.ac_blocks_total,
        }
    ]


def _validate_report_consistency(ctx: ReportContext) -> list[str]:
    """Validate overall report consistency (power/energy/efficiency).

    Returns advisory warning messages; does not block export.
    """
    warnings = []

    warnings.extend(_validate_efficiency_chain(ctx))

    if ctx.ac_blocks_total > 0 and ctx.dc_blocks_total == 0:
        warnings.append("AC Blocks present but DC Blocks count is zero.")

    expected_pcs = ctx.ac_blocks_total * ctx.pcs_per_block
    if ctx.pcs_modules_total > 0 and ctx.pcs_modules_total != expected_pcs:
        warnings.append(
            f"PCS module count mismatch: expected {expected_pcs} "
            f"(AC blocks={ctx.ac_blocks_total} x PCS/block={ctx.pcs_per_block}), "
            f"got {ctx.pcs_modules_total}."
        )

    if ctx.ac_blocks_total > 0 and ctx.ac_block_size_mw and ctx.ac_block_size_mw > 0:
        total_ac_power = ctx.ac_blocks_total * ctx.ac_block_size_mw
        poi_requirement = ctx.poi_power_requirement_mw
        overage = total_ac_power - poi_requirement
        overage_pct = (overage / poi_requirement * 100) if poi_requirement > 0 else 0
        if overage > 0.5 and overage_pct > 10:
            warnings.append(
                f"AC power overbuild is {overage_pct:.1f}% "
                f"(total {total_ac_power:.2f} MW vs requirement {poi_requirement:.2f} MW)."
            )

    if ctx.dc_total_energy_mwh is not None and ctx.poi_energy_requirement_mwh is not None:
        if ctx.dc_total_energy_mwh < ctx.poi_energy_requirement_mwh:
            warnings.append(
                f"DC nameplate ({ctx.dc_total_energy_mwh:.2f} MWh) is less than "
                f"POI requirement ({ctx.poi_energy_requirement_mwh:.2f} MWh); "
                f"degradation modeling determines actual delivery."
            )

    if (ctx.poi_usable_energy_mwh_at_guarantee_year is not None
            and ctx.poi_energy_guarantee_mwh is not None):
        if ctx.poi_usable_energy_mwh_at_guarantee_year + 0.1 < ctx.poi_energy_guarantee_mwh:
            warnings.append(
                f"POI usable at guarantee year ({ctx.poi_usable_energy_mwh_at_guarantee_year:.2f} MWh) "
                f"is below guarantee target ({ctx.poi_energy_guarantee_mwh:.2f} MWh)."
            )

    if ctx.poi_guarantee_year > ctx.project_life_years:
        warnings.append(
            f"Guarantee year ({ctx.poi_guarantee_year}) exceeds project life ({ctx.project_life_years} years)."
        )

    return warnings


def export_report_v2_1(ctx: ReportContext, brand: dict | None = None) -> bytes:
    doc = Document()
    _setup_margins(doc)
    if brand:
        _setup_header(
            doc,
            title=brand.get("header_title", "Confidential Sizing Report (V2.1 Beta)"),
            logo_path=brand.get("logo_path"),
            header_lines=brand.get("header_lines"),
            footer_lines=brand.get("footer_lines"),
        )
        cover_title = brand.get(
            "cover_title", "CALB Utility-Scale ESS Sizing Report (V2.1 Beta)"
        )
        tool_version = brand.get("tool_version", "V2.1 Beta")
    else:
        _setup_header(doc, title="Confidential Sizing Report (V2.1 Beta)")
        cover_title = "CALB Utility-Scale ESS Sizing Report (V2.1 Beta)"
        tool_version = "V2.1 Beta"

    _add_cover_page(
        doc,
        cover_title,
        ctx.project_name,
        {"tool_version": tool_version},
    )

    # Shared derived values used across multiple sections
    gyr_target = ctx.poi_energy_guarantee_mwh
    poi_usable_at_gyr = ctx.poi_usable_energy_mwh_at_guarantee_year
    meets_guarantee = (
        "Yes"
        if (poi_usable_at_gyr is not None and gyr_target is not None
            and poi_usable_at_gyr >= gyr_target - 0.1)
        else "No"
    )

    # --- Document Provenance (DB linkage) ---
    # _add_cover_page already ends with a page break; no second break needed here.
    doc.add_heading("Document Provenance", level=2)
    dc_source = "Saved (database)" if ctx.run_id else "Live session (unsaved)"
    ac_source = (
        "Saved (database)" if ctx.ac_run_id
        else ("Linked to DC run" if ctx.run_id else "Live session (unsaved)")
    )
    prov_rows = [
        ("Project", ctx.project_name),
        ("Case", ctx.case_name or "—"),
        ("DC Sizing Data", dc_source),
        ("AC Sizing Data", ac_source),
        ("Report Generated", ctx.report_generated_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    _add_table(doc, prov_rows, ["Field", "Value"])
    if not ctx.run_id:
        doc.add_paragraph(
            "NOTE: Sizing data has not been saved to the database. "
            "Save the DC run before issuing this report for full traceability."
        )

    # --- Section 1: Executive Summary ---
    # Flows on the same page as Document Provenance (no forced page break).
    doc.add_heading("1.  Executive Summary", level=2)
    exec_rows = [
        ("POI Power Requirement (MW)", format_value(ctx.poi_power_requirement_mw, "MW")),
        ("POI Energy Requirement (MWh)", format_value(ctx.poi_energy_requirement_mwh, "MWh")),
        ("POI Energy Guarantee Target (MWh)", format_value(gyr_target, "MWh")),
        ("Guarantee Year (from COD)", f"{ctx.poi_guarantee_year:d}"),
        ("POI Usable @ Guarantee Year (MWh)", format_value(poi_usable_at_gyr, "MWh")),
        ("Guarantee Compliance", meets_guarantee),
        ("DC Blocks Total", f"{ctx.dc_blocks_total:d}"),
        ("DC Nameplate Energy @BOL (MWh)", format_value(ctx.dc_total_energy_mwh, "MWh")),
        ("AC Block Template", ctx.ac_block_template_id),
        ("AC Blocks Total", f"{ctx.ac_blocks_total:d}"),
        ("Total PCS Modules", f"{ctx.pcs_modules_total:d}"),
        ("Transformer Rating", _format_transformer_rating(ctx.transformer_rating_kva)),
    ]
    _add_table(doc, exec_rows, ["Metric", "Value"])
    if ctx.dc_blocks_allocation:
        doc.add_paragraph("")
        _keep_next_para(doc.add_paragraph("DC Blocks per AC Block Allocation:"))
        alloc_rows = [
            (entry.get("dc_blocks_per_ac_block"), entry.get("ac_blocks_count"))
            for entry in ctx.dc_blocks_allocation
        ]
        _add_table(doc, alloc_rows, ["DC Blocks per AC Block", "Number of AC Blocks"])

    # --- Section 2: Project Inputs & Assumptions ---
    # Flows on the same page as Section 1 when space allows (no forced page break).
    # Note: POI power/energy/guarantee values are already in Section 1 — not repeated here.
    doc.add_heading("2.  Project Inputs & Assumptions", level=2)
    _keep_next_para(doc.add_paragraph(
        "Key design parameters assumed in this sizing. "
        "Efficiency values are one-way (DC → POI). Loss and DoD values exclude auxiliary loads."
    ))
    _dod = ctx.stage1.get("dod_frac") if isinstance(ctx.stage1, dict) else None
    _sc = ctx.stage1.get("sc_loss_frac") if isinstance(ctx.stage1, dict) else None
    _cyc = ctx.cycles_per_year or (ctx.stage1.get("cycles_per_year") if isinstance(ctx.stage1, dict) else None)
    _sc_months = ctx.stage1.get("sc_time_months") if isinstance(ctx.stage1, dict) else None
    site_rows = [
        ("Grid MV Voltage (kV)", format_value(ctx.grid_mv_voltage_kv_ac, "kV")),
        ("Grid Frequency (Hz)", _format_or_tbd(ctx.project_inputs.get("poi_frequency_hz"), "Hz")),
        ("Grid Power Factor", format_value(ctx.grid_power_factor, "PF")),
        ("Project Life (Years)", f"{ctx.project_life_years}"),
        ("Cycles per Year (Assumed)", f"{int(_cyc)}" if _cyc else "—"),
        ("Depth of Discharge (DoD)", format_percent(_dod, input_is_fraction=True) if _dod is not None else "—"),
        ("Self-Consumption (SC) Loss", format_percent(_sc, input_is_fraction=True) if _sc is not None else "—"),
    ]
    if _sc_months is not None:
        site_rows.append(("FAT-to-COD Duration", f"{int(round(_sc_months))} months"))
    _add_table(doc, site_rows, ["Parameter", "Value"])

    # --- Section 3: Stage 1 - DC Energy Sizing ---
    doc.add_page_break()
    doc.add_heading("3.  Stage 1 – DC Energy Sizing", level=2)
    _keep_next_para(doc.add_paragraph(
        "DC Energy Required (MWh) = POI Energy Requirement ÷ "
        "((1 − SC loss) × DoD × DC RTEᴰᴵˢᶜʰᵃʳᵏᵉ × One-way Efficiency)"
    ))
    _keep_next_para(doc.add_paragraph(
        f"One-way Efficiency (DC→POI): {format_percent(ctx.efficiency_chain_oneway_frac, input_is_fraction=True)}  |  "
        f"SC loss: {format_percent(ctx.stage1.get('sc_loss_frac') or 0.0, input_is_fraction=True)}  |  "
        f"DoD: {format_percent(ctx.stage1.get('dod_frac') or 0.0, input_is_fraction=True)}  |  "
        f"DC RTE: {format_percent(ctx.stage1.get('dc_round_trip_efficiency_frac') or 0.0, input_is_fraction=True)}"
    ))
    rte_adj = float(ctx.stage1.get("rte_curve_adjust_pp") or 0.0)
    if rte_adj != 0.0:
        _keep_next_para(doc.add_paragraph(f"RTE Curve Adjustment: {rte_adj:+.1f} pp"))
    s1_rows = [
        ("DC Energy Capacity Required (MWh)", format_value(ctx.stage1.get("dc_energy_capacity_required_mwh") or 0.0, "MWh")),
        ("DC Power Required (MW)", format_value(ctx.stage1.get("dc_power_required_mw") or 0.0, "MW")),
    ]
    _add_table(doc, s1_rows, ["Metric", "Value"])

    doc.add_heading("3.1  Efficiency Chain (One-way, DC → POI)", level=3)
    _keep_next_para(doc.add_paragraph(
        "Component efficiencies represent the one-way conversion path from DC terminals to POI. "
        "Their product equals the total one-way efficiency shown in the first row."
    ))
    eff_rows = [
        ("Total One-way Efficiency", format_percent(ctx.efficiency_chain_oneway_frac, input_is_fraction=True)),
        ("DC Cables", format_percent(ctx.efficiency_components_frac.get("eff_dc_cables_frac"), input_is_fraction=True)),
        ("PCS", format_percent(ctx.efficiency_components_frac.get("eff_pcs_frac"), input_is_fraction=True)),
        ("Transformer (MVT)", format_percent(ctx.efficiency_components_frac.get("eff_mvt_frac"), input_is_fraction=True)),
        ("RMU / Switchgear / AC Cables", format_percent(ctx.efficiency_components_frac.get("eff_ac_cables_sw_rmu_frac"), input_is_fraction=True)),
        ("HVT / Others", format_percent(ctx.efficiency_components_frac.get("eff_hvt_others_frac"), input_is_fraction=True)),
    ]
    _add_table(doc, eff_rows, ["Component", "Efficiency"])

    # --- Section 4: Stage 2 - DC Block Configuration ---
    doc.add_page_break()
    doc.add_heading("4.  Stage 2 – DC Block Configuration", level=2)
    dc_table = ctx.stage2.get("block_config_table") if isinstance(ctx.stage2, dict) else None

    def _format_mwh_3(value):
        try:
            return f"{float(value):.3f}"
        except Exception:
            return "" if value is None else str(value)

    if dc_table is not None and not dc_table.empty:
        drop_cols = {"Config Adjustment (%)", "Oversize (MWh)", "Busbars Needed (K=10)", "Busbars Needed"}
        dc_columns = [c for c in dc_table.columns if c not in drop_cols]
        headers_map = {c: c for c in dc_columns}
        formatters = {}
        for col in dc_columns:
            if col in ("Unit Capacity (MWh)", "Subtotal (MWh)", "Total DC Nameplate @BOL (MWh)"):
                formatters[col] = _format_mwh_3
            else:
                formatters[col] = lambda v: "" if v is None else str(v)
        _add_dataframe_table(doc, dc_table, dc_columns, headers_map, formatters)
    else:
        doc.add_paragraph("DC block configuration table unavailable.")
    oversize_mwh = ctx.stage2.get("oversize_mwh") if isinstance(ctx.stage2, dict) else None
    doc.add_paragraph(
        f"DC total nameplate @BOL: {_format_mwh_3(ctx.dc_total_energy_mwh)} MWh   |   "
        f"Oversize margin: {_format_mwh_3(oversize_mwh)} MWh"
    )

    # --- Section 5: Stage 3 - Lifetime Degradation & POI Deliverable ---
    doc.add_page_break()
    doc.add_heading("5.  Stage 3 – Lifetime Degradation & POI Deliverable", level=2)
    s3_meta = ctx.stage3_meta if isinstance(ctx.stage3_meta, dict) else {}
    if s3_meta:
        def _fmt_float(value, decimals=2, default=""):
            try:
                return f"{float(value):.{decimals}f}"
            except Exception:
                return default

        poi_power = s3_meta.get("poi_power_mw", ctx.poi_power_requirement_mw)
        dc_power = s3_meta.get("dc_power_mw")
        if dc_power is None and isinstance(ctx.stage1, dict):
            dc_power = ctx.stage1.get("dc_power_required_mw")
        eff_c_rate = s3_meta.get("effective_c_rate")
        chosen_soh_c_rate = s3_meta.get("chosen_soh_c_rate")
        chosen_cycles_per_year = s3_meta.get("chosen_soh_cycles_per_year")

        model_rows = [
            ("POI Power (MW)", f"{_fmt_float(poi_power, 2)} MW"),
            ("DC-equivalent Power (MW)", f"{_fmt_float(dc_power, 2)} MW"),
            ("Effective C-rate (DC side)", f"{_fmt_float(eff_c_rate, 3)} C"),
            ("SOH Modelling C-rate", f"≤ {chosen_soh_c_rate}" if chosen_soh_c_rate else "—"),
            ("SOH Modelling Cycles/Year", f"{chosen_cycles_per_year}" if chosen_cycles_per_year else "—"),
            ("Guarantee Year (from COD)", f"{ctx.poi_guarantee_year}"),
            ("POI Energy Guarantee Target (MWh)", format_value(gyr_target, "MWh")),
        ]
        _add_table(doc, model_rows, ["Parameter", "Value"])
        doc.add_paragraph("")

    s3_df = ctx.stage3_df
    if s3_df is not None and not s3_df.empty:
        doc.add_paragraph(
            "System RTE = DC RTE × (One-way Efficiency)², "
            "where one-way efficiency is the DC→POI chain defined in Section 3.1."
        )
        rte_dc = s3_df["DC_RTE_Pct"].astype(float)
        rte_sys = s3_df["System_RTE_Pct"].astype(float)
        rte_dc_min, rte_dc_max = float(rte_dc.min()), float(rte_dc.max())
        rte_sys_min, rte_sys_max = float(rte_sys.min()), float(rte_sys.max())

        if abs(rte_dc_min - rte_dc_max) < 1e-6:
            doc.add_paragraph(f"DC RTE: {format_percent(rte_dc_min, input_is_fraction=False)} (constant over project life)")
        else:
            doc.add_paragraph(
                f"DC RTE: {format_percent(rte_dc_min, input_is_fraction=False)} "
                f"to {format_percent(rte_dc_max, input_is_fraction=False)} over project life"
            )
        if abs(rte_sys_min - rte_sys_max) < 1e-6:
            doc.add_paragraph(f"System RTE: {format_percent(rte_sys_min, input_is_fraction=False)} (constant over project life)")
        else:
            doc.add_paragraph(
                f"System RTE: {format_percent(rte_sys_min, input_is_fraction=False)} "
                f"to {format_percent(rte_sys_max, input_is_fraction=False)} over project life"
            )
        doc.add_paragraph("")

        s3_df = s3_df.copy()
        s3_df["Meets_Guarantee"] = s3_df["POI_Usable_Energy_MWh"] >= float(gyr_target or 0.0)

        chart = _plot_poi_usable_png(
            s3_df,
            poi_target=gyr_target,
            title=f"POI Usable Energy vs. Year  (guarantee target = red line, Year {ctx.poi_guarantee_year})",
        )
        if chart is not None and chart.getbuffer().nbytes > 0:
            doc.add_picture(chart, width=Inches(6.7))
            _keep_next_para(doc.paragraphs[-1])  # keep picture paragraph with its caption
            _keep_next_para(doc.add_paragraph(
                f"Figure 1: POI Usable Energy (MWh) by year from COD. "
                f"Red line = guarantee target ({format_value(gyr_target, 'MWh')} MWh). "
                f"Guarantee evaluated at Year {ctx.poi_guarantee_year}."
            ))
        else:
            err = None
            try:
                err = ctx.stage3_meta.get("error") if isinstance(ctx.stage3_meta, dict) else None
            except Exception:
                err = None
            _keep_next_para(doc.add_paragraph(f"Stage 3 chart unavailable{': ' + err if err else '.'}"))

        _keep_next_para(doc.add_paragraph(""))
        _keep_next_para(doc.add_paragraph("Year-by-Year Degradation & POI Deliverable:"))
        s3_columns = [
            "Year_Index",
            "SOH_Display_Pct",
            "SOH_Absolute_Pct",
            "DC_Usable_MWh",
            "POI_Usable_Energy_MWh",
            "DC_RTE_Pct",
            "System_RTE_Pct",
            "Meets_Guarantee",
        ]
        s3_headers = {
            "Year_Index": "Year (From COD)",
            "SOH_Display_Pct": "SOH @ COD Baseline (%)",
            "SOH_Absolute_Pct": "SOH vs FAT (%)",
            "DC_Usable_MWh": "DC Usable (MWh)",
            "POI_Usable_Energy_MWh": "POI Usable (MWh)",
            "DC_RTE_Pct": "DC RTE (%)",
            "System_RTE_Pct": "System RTE (%)",
            "Meets_Guarantee": "Meets Target",
        }
        s3_formatters = {
            "Year_Index": lambda v: f"{int(v)}",
            "SOH_Display_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "SOH_Absolute_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "DC_Usable_MWh": lambda v: format_value(v, "MWh"),
            "POI_Usable_Energy_MWh": lambda v: format_value(v, "MWh"),
            "DC_RTE_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "System_RTE_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "Meets_Guarantee": lambda v: "Yes" if v else "No",
        }
        _add_dataframe_table(doc, s3_df, s3_columns, s3_headers, s3_formatters, keep_together=False)

    # --- Section 6: Stage 4 - AC Block Sizing ---
    doc.add_page_break()
    doc.add_heading("6.  Stage 4 – AC Block Sizing", level=2)
    ac_ratio = ctx.ac_output.get("selected_ratio") if isinstance(ctx.ac_output, dict) else None
    ac_pcs_kw = ctx.ac_output.get("pcs_kw") if isinstance(ctx.ac_output, dict) else None
    if ac_pcs_kw is None and isinstance(ctx.ac_output, dict):
        ac_pcs_kw = ctx.ac_output.get("pcs_power_kw")
    pcs_count_by_block = ctx.ac_output.get("pcs_count_by_block") if isinstance(ctx.ac_output, dict) else None
    pcs_by_block_text = ""
    if isinstance(pcs_count_by_block, list) and pcs_count_by_block:
        pcs_by_block_text = ", ".join(
            f"B{idx + 1}={int(v)}" for idx, v in enumerate(pcs_count_by_block)
        )
    transformer_mva = None
    if ctx.grid_power_factor and ctx.grid_power_factor > 0 and ctx.ac_block_size_mw:
        transformer_mva = ctx.ac_block_size_mw / ctx.grid_power_factor
    transformer_formula = "n/a"
    if transformer_mva is not None and ctx.ac_block_size_mw and ctx.grid_power_factor:
        transformer_formula = (
            f"{format_value(ctx.ac_block_size_mw, 'MW')} ÷ {format_value(ctx.grid_power_factor, 'PF')}"
            f" = {format_value(transformer_mva, 'MVA')}"
        )
    s4_rows = [
        ("AC:DC Ratio", ac_ratio or "—"),
        ("AC Block Template", ctx.ac_block_template_id),
        ("AC Block Size (MW)", format_value(ctx.ac_block_size_mw, "MW")),
        ("PCS per AC Block", f"{ctx.pcs_per_block:d}"),
    ]
    if pcs_by_block_text:
        s4_rows.append(("PCS Count by Block", pcs_by_block_text))
    if ac_pcs_kw:
        s4_rows.append(("PCS Unit Rating (kW)", f"{float(ac_pcs_kw):.0f} kW"))
    s4_rows += [
        ("Feeders per AC Block", f"{ctx.feeders_per_block:d}"),
        ("PCS AC Output Voltage (V_LL)", format_value(ctx.pcs_lv_voltage_v_ll_rms_ac, "V")),
        ("Total AC Blocks", f"{ctx.ac_blocks_total:d}"),
        ("Total PCS Modules", f"{ctx.pcs_modules_total:d}"),
        ("Transformer Rating (per block)", _format_transformer_rating(ctx.transformer_rating_kva)),
        ("Transformer Rating Formula", transformer_formula),
    ]
    _add_table(doc, s4_rows, ["Parameter", "Value"])

    # --- Section 7: Single Line Diagram ---
    doc.add_page_break()
    doc.add_heading("7.  Single Line Diagram", level=2)
    _keep_next_para(doc.add_paragraph(
        "System electrical configuration: MV bus → RMU → Step-up Transformer → AC Block (DC blocks attached)."
    ))
    figure_index = 2  # Figure 1 used by Stage 3 POI chart above
    sld_embedded = False
    if ctx.sld_pro_png_bytes:
        doc.add_picture(io.BytesIO(ctx.sld_pro_png_bytes), width=Inches(6.7))
        _keep_next_para(doc.paragraphs[-1])
        doc.add_paragraph(f"Figure {figure_index}: Single Line Diagram – System Electrical Configuration")
        figure_index += 1
        sld_embedded = True
    elif ctx.sld_preview_svg_bytes:
        png_bytes = _svg_bytes_to_png(ctx.sld_preview_svg_bytes)
        if png_bytes:
            doc.add_picture(io.BytesIO(png_bytes), width=Inches(6.7))
            _keep_next_para(doc.paragraphs[-1])
            doc.add_paragraph(f"Figure {figure_index}: Single Line Diagram – System Electrical Configuration")
            figure_index += 1
            sld_embedded = True
    if not sld_embedded:
        doc.add_paragraph("SLD not generated. Please generate in the Single Line Diagram page.")

    # --- Section 8: Site Layout ---
    doc.add_page_break()
    doc.add_heading("8.  Site Layout", level=2)
    layout_png_bytes = ctx.layout_png_bytes
    if not layout_png_bytes and ctx.layout_svg_bytes:
        layout_png_bytes = _svg_bytes_to_png(ctx.layout_svg_bytes)
    if layout_png_bytes:
        doc.add_picture(io.BytesIO(layout_png_bytes), width=Inches(6.7))
        _keep_next_para(doc.paragraphs[-1])
        doc.add_paragraph(f"Figure {figure_index}: Site Layout – Block Arrangement")
    else:
        doc.add_paragraph("Layout not generated. Please generate in the Site Layout page.")

    return _doc_to_bytes(doc)


export_report_v2 = export_report_v2_1
