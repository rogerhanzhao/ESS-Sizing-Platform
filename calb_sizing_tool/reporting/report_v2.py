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

from calb_sizing_tool.reporting.export_docx import (
    _add_page_number_footer,
    _add_table,
    _doc_to_bytes,
    _keep_next_para,
    _setup_header,
    _setup_margins,
)
from calb_diagrams.ac_block_arrangement_v2 import (
    US_NFPA_OIL as ARRANGEMENT_PROFILE,
    render_plan_svg as render_ac_block_plan_svg,
)
from calb_diagrams.site_array_concept import (
    US_NFPA_SITE as SITE_PROFILE,
    compute_site_array,
    render_site_svg,
)
from calb_sizing_tool.reporting.brand_profiles import (
    BrandProfile,
    CALB_BRAND,
    neutralize_equipment_text,
    require_brand_assets,
)
from calb_sizing_tool.reporting.formatter import format_percent, format_value
from calb_sizing_tool.reporting.report_context import ReportContext

try:
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

try:
    import cairosvg

    CAIROSVG_AVAILABLE = True
except Exception:
    CAIROSVG_AVAILABLE = False

from calb_sizing_tool.common.render_lock import RENDER_LOCK


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
    numeric_cols = [
        j for j, col in enumerate(columns)
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col])
    ]
    _add_table(doc, rows, headers, keep_together=keep_together, align_right_cols=numeric_cols)


def _plot_poi_usable_png(df: pd.DataFrame, poi_target: float, title: str) -> Optional[io.BytesIO]:
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        data = df.sort_values("Year_Index").copy()
        x = data["Year_Index"].astype(int).tolist()
        y = data["POI_Usable_Energy_MWh"].astype(float).tolist()

        fig = Figure(figsize=(7.0, 3.2))
        ax = fig.add_subplot(111)
        ax.bar(x, y, color="#5cc3e4")
        ax.axhline(poi_target, linewidth=2, color="#ff0000")
        ax.set_title(title)
        ax.set_xlabel("Year (from COD)")
        ax.set_ylabel("POI Usable Energy (MWh)")
        ax.set_xticks(x)
        # Headroom above the tallest bar / target line so the red guarantee
        # line never sits on the plot border.
        top = max(max(y) if y else 0.0, float(poi_target or 0.0))
        if top > 0:
            ax.set_ylim(0, top * 1.12)
        ax.grid(True, axis="y", linestyle="--", alpha=0.35)

        buf = io.BytesIO()
        fig.tight_layout()
        with RENDER_LOCK:
            fig.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        return buf
    except Exception:
        return None


def _plot_dc_capacity_bar_png(
    bol_mwh: Optional[float],
    s3_df: Optional[pd.DataFrame],
    guarantee_year: int,
    poi_target: Optional[float],
    title: str,
) -> Optional[io.BytesIO]:
    """Bar chart: installed DC nameplate vs deliverable POI energy at key milestones.

    BOL is a DC-side metric; all other bars are POI-side. The two measurement
    planes use distinct colors and an explicit legend so the DC/POI distinction
    is unambiguous, and the guarantee target line is drawn across the POI bars
    only (the target does not apply to the DC plane).
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch

        if s3_df is None or s3_df.empty or bol_mwh is None:
            return None

        def _poi_at(year: int) -> Optional[float]:
            row = s3_df[s3_df["Year_Index"] == int(year)]
            if row.empty:
                return None
            return float(row["POI_Usable_Energy_MWh"].iloc[0])

        g_year = int(guarantee_year)
        final_year = int(s3_df["Year_Index"].max())

        DC_COLOR = "#1f4e79"
        POI_COLOR = "#5cc3e4"

        labels = ["DC Nameplate\nBOL (DC side)"]
        values = [float(bol_mwh)]
        colors = [DC_COLOR]

        cod = _poi_at(0)
        if cod is not None:
            cod_label = "POI Usable\nY0 (COD)"
            if g_year == 0:
                cod_label = "POI Usable\nY0 (COD, guarantee)"
            labels.append(cod_label)
            values.append(cod)
            colors.append(POI_COLOR)

        if g_year > 0:
            yg = _poi_at(g_year)
            if yg is not None:
                labels.append(f"POI Usable\nY{g_year} (guarantee)")
                values.append(yg)
                colors.append(POI_COLOR)

        if final_year not in (0, g_year):
            y_end = _poi_at(final_year)
            if y_end is not None:
                labels.append(f"POI Usable\nY{final_year} (end of life)")
                values.append(y_end)
                colors.append(POI_COLOR)

        fig = Figure(figsize=(7.0, 3.4))
        ax = fig.add_subplot(111)
        bars = ax.bar(labels, values, color=colors, width=0.6)
        ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=9)

        legend_handles = [
            Patch(facecolor=DC_COLOR, label="DC side (installed nameplate)"),
            Patch(facecolor=POI_COLOR, label="POI side (deliverable energy)"),
        ]
        if poi_target is not None and float(poi_target) > 0 and len(values) > 1:
            ax.hlines(
                float(poi_target),
                xmin=0.7,
                xmax=len(values) - 1 + 0.3,
                linewidth=2,
                color="#ff0000",
            )
            legend_handles.append(
                Line2D([0], [0], color="#ff0000", linewidth=2, label="POI guarantee target")
            )

        ax.set_title(title)
        ax.set_ylabel("Energy (MWh)")
        ax.set_ylim(0, max(values) * 1.18)
        ax.grid(True, axis="y", linestyle="--", alpha=0.35)
        ax.legend(handles=legend_handles, loc="upper right", fontsize=8, framealpha=0.9)

        buf = io.BytesIO()
        fig.tight_layout()
        with RENDER_LOCK:
            fig.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        return buf
    except Exception:
        return None


def _add_cover_page_v2(doc: Document, ctx: ReportContext, brand: BrandProfile) -> None:
    """Proposal cover: title, project identity block, issuer, confidentiality note.

    All branded copy comes from the BrandProfile — no fallback strings here.
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    for _ in range(4):
        doc.add_paragraph("")

    heading = doc.add_heading(brand.cover_title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle = doc.add_paragraph("Battery Energy Storage System — Sizing Proposal")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if subtitle.runs:
        subtitle.runs[0].font.size = Pt(13)

    doc.add_paragraph("")
    generated = ctx.report_generated_at or datetime.datetime.now().strftime("%Y-%m-%d")
    info_lines = [
        f"Project: {ctx.project_name}",
        f"Case: {ctx.case_name or '—'}",
        f"Date: {generated}",
        f"Tool Version: {brand.tool_version_label}",
    ]
    info = doc.add_paragraph("\n".join(info_lines))
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph("")
    issuer = doc.add_paragraph("\n".join(brand.issuer_lines))
    issuer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for _ in range(8):
        doc.add_paragraph("")
    notice = doc.add_paragraph(brand.confidentiality_notice)
    notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in notice.runs:
        run.font.size = Pt(8)
        run.italic = True

    doc.add_page_break()


def _compute_site_layout(ctx: ReportContext):
    """Concept site-array layout from the sizing result (None if not sizeable)."""
    if ctx.ac_blocks_total <= 0 or ctx.dc_blocks_total <= 0:
        return None
    dc_per_ac = max(1, int(round(ctx.dc_blocks_total / ctx.ac_blocks_total)))
    try:
        return compute_site_array(
            ctx.ac_blocks_total, dc_per_ac, ARRANGEMENT_PROFILE, SITE_PROFILE
        )
    except Exception:
        return None


def _normalize_template_label(value) -> str:
    """Normalize AC block template ids like '4x1250kw' to '4×1250 kW' for display."""
    if value is None:
        return "—"
    text = str(value)
    match = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*[kK][wW]\s*", text)
    if match:
        return f"{match.group(1)}×{match.group(2)} kW"
    return text


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
        with RENDER_LOCK:
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


def export_report_v2_1(ctx: ReportContext, brand: BrandProfile | None = None) -> bytes:
    if brand is None:
        brand = CALB_BRAND
    require_brand_assets(brand)

    doc = Document()
    _setup_margins(doc)
    _setup_header(
        doc,
        title=brand.header_title,
        logo_path=brand.logo_path,
        header_lines=list(brand.header_lines),
        footer_lines=list(brand.footer_lines) or None,
    )

    _add_page_number_footer(doc)
    _add_cover_page_v2(doc, ctx, brand)

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
    if poi_usable_at_gyr is not None and gyr_target is not None:
        key_para = doc.add_paragraph()
        key_run = key_para.add_run(
            f"The proposed system delivers {format_value(poi_usable_at_gyr, 'MWh')} MWh at the POI "
            f"in Year {ctx.poi_guarantee_year} against a guarantee target of "
            f"{format_value(gyr_target, 'MWh')} MWh — guarantee "
            f"{'met' if meets_guarantee == 'Yes' else 'NOT met'}."
        )
        key_run.bold = True
        config_para = doc.add_paragraph(
            f"Configuration: {ctx.dc_blocks_total} DC Blocks "
            f"({format_value(ctx.dc_total_energy_mwh, 'MWh')} MWh nameplate @BOL) · "
            f"{ctx.ac_blocks_total} AC Blocks ({_normalize_template_label(ctx.ac_block_template_id)}) · "
            f"{ctx.pcs_modules_total} PCS modules."
        )
        _keep_next_para(key_para)
        _keep_next_para(config_para)
    exec_rows = [
        ("POI Power Requirement (MW)", format_value(ctx.poi_power_requirement_mw, "MW")),
        ("POI Energy Requirement (MWh)", format_value(ctx.poi_energy_requirement_mwh, "MWh")),
        ("POI Energy Guarantee Target (MWh)", format_value(gyr_target, "MWh")),
        ("Guarantee Year (from COD)", f"{ctx.poi_guarantee_year:d}"),
        ("POI Usable @ Guarantee Year (MWh)", format_value(poi_usable_at_gyr, "MWh")),
        ("Guarantee Compliance", meets_guarantee),
        ("DC Blocks Total", f"{ctx.dc_blocks_total:d}"),
        ("DC Nameplate Energy @BOL (MWh)", format_value(ctx.dc_total_energy_mwh, "MWh")),
        ("AC Block Template", _normalize_template_label(ctx.ac_block_template_id)),
        ("AC Blocks Total", f"{ctx.ac_blocks_total:d}"),
        ("Total PCS Modules", f"{ctx.pcs_modules_total:d}"),
        ("Transformer Rating", _format_transformer_rating(ctx.transformer_rating_kva)),
    ]
    site_layout = _compute_site_layout(ctx)
    if site_layout is not None:
        exec_rows.append((
            "Site Envelope (concept)",
            f"≈ {site_layout.envelope_w_m:.1f} × {site_layout.envelope_d_m:.1f} m",
        ))
    _add_table(doc, exec_rows, ["Metric", "Value"])
    if ctx.dc_blocks_allocation:
        alloc_parts = [
            f"{entry.get('dc_blocks_per_ac_block')} DC Blocks per AC Block × "
            f"{entry.get('ac_blocks_count')} AC Blocks"
            for entry in ctx.dc_blocks_allocation
        ]
        doc.add_paragraph(f"DC-to-AC allocation: {'; '.join(alloc_parts)}.")

    # --- Section 2: Project Inputs & Assumptions ---
    # Flows on the same page as Section 1 when space allows (no forced page break).
    # Note: POI power/energy/guarantee values are already in Section 1 — not repeated here.
    doc.add_heading("2.  Project Inputs & Assumptions", level=2)
    _keep_next_para(doc.add_paragraph(
        "Key design parameters assumed in this sizing. "
        "Efficiency values are one-way (DC → POI). Loss and DoD values exclude auxiliary loads."
    ))
    _keep_next_para(doc.add_paragraph(
        "The listed efficiency values do not include Auxiliary losses; no Auxiliary loss assumption is applied in this report."
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
        ("Shipping & Commissioning (S&C) Loss", format_percent(_sc, input_is_fraction=True) if _sc is not None else "—"),
    ]
    if _sc_months is not None:
        site_rows.append(("FAT-to-COD Duration", f"{int(round(_sc_months))} months"))
    _add_table(doc, site_rows, ["Parameter", "Value"])

    # --- Section 3: Stage 1 - DC Energy Sizing ---
    doc.add_page_break()
    doc.add_heading("3.  Stage 1 – DC Energy Sizing", level=2)
    _keep_next_para(doc.add_paragraph(
        "DC Energy Required (MWh) = POI Energy Requirement ÷ "
        "((1 − S&C loss) × DoD × DC RTE (discharge) × One-way Efficiency)"
    ))
    _keep_next_para(doc.add_paragraph(
        f"One-way Efficiency (DC→POI): {format_percent(ctx.efficiency_chain_oneway_frac, input_is_fraction=True)}  |  "
        f"S&C loss: {format_percent(ctx.stage1.get('sc_loss_frac') or 0.0, input_is_fraction=True)}  |  "
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
    # Flows after Stage 1 (no forced break): the section is one small table and
    # previously produced a nearly blank page of its own.
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
            elif col in ("Block Code", "Block Name"):
                formatters[col] = lambda v: neutralize_equipment_text(v, brand)
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
            ("POI Power (MW)", _fmt_float(poi_power, 2)),
            ("DC-equivalent Power (MW)", _fmt_float(dc_power, 2)),
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
        rte_columns = ["DC_RTE_Pct", "System_RTE_Pct"]
        rte_frame = (
            s3_df.loc[:, rte_columns].apply(pd.to_numeric, errors="coerce").dropna()
            if set(rte_columns).issubset(s3_df.columns)
            else pd.DataFrame()
        )
        if not rte_frame.empty:
            doc.add_paragraph(
                "System RTE = DC RTE × (One-way Efficiency)², "
                "where one-way efficiency is the DC→POI chain defined in Section 3.1."
            )
            rte_dc = rte_frame["DC_RTE_Pct"]
            rte_sys = rte_frame["System_RTE_Pct"]
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
        else:
            doc.add_paragraph("DC and system RTE ranges are unavailable for the supplied Stage 3 dataset.")
        doc.add_paragraph("")

        s3_df = s3_df.copy()
        guarantee_year_int = int(ctx.poi_guarantee_year or 0)
        # The contractual guarantee is evaluated at the guarantee year only;
        # showing Yes/No for every year misreads as a 20-year failure list.
        s3_df["Meets_Guarantee"] = [
            ("Yes" if float(poi) >= float(gyr_target or 0.0) else "No")
            if int(year) == guarantee_year_int else "—"
            for year, poi in zip(s3_df["Year_Index"], s3_df["POI_Usable_Energy_MWh"])
        ]

        capacity_chart = _plot_dc_capacity_bar_png(
            bol_mwh=ctx.dc_total_energy_mwh,
            s3_df=s3_df,
            guarantee_year=int(ctx.poi_guarantee_year or 0),
            poi_target=gyr_target,
            title="Installed DC Energy vs. Deliverable POI Energy at Key Milestones",
        )
        if capacity_chart is not None and capacity_chart.getbuffer().nbytes > 0:
            doc.add_picture(capacity_chart, width=Inches(6.7))
            _keep_next_para(doc.paragraphs[-1])  # keep picture paragraph with its caption
            _keep_next_para(doc.add_paragraph(
                f"Figure 1: Installed DC nameplate energy (dark, DC side) versus deliverable "
                f"energy at the point of interconnection (light, POI side). The step from BOL "
                f"to POI reflects the one-way DC→POI efficiency chain, depth of discharge, "
                f"and S&C/calendar/cycle degradation; later POI bars additionally reflect ageing. "
                f"Red line = POI energy guarantee target ({format_value(gyr_target, 'MWh')} MWh), "
                f"applicable to the POI bars only."
            ))
            _keep_next_para(doc.add_paragraph(""))

        chart = _plot_poi_usable_png(
            s3_df,
            poi_target=gyr_target,
            title=f"POI Usable Energy vs. Year  (guarantee target = red line, Year {ctx.poi_guarantee_year})",
        )
        if chart is not None and chart.getbuffer().nbytes > 0:
            doc.add_picture(chart, width=Inches(6.7))
            _keep_next_para(doc.paragraphs[-1])  # keep picture paragraph with its caption
            _keep_next_para(doc.add_paragraph(
                f"Figure 2: POI Usable Energy (MWh) by year from COD. "
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
            "Meets_Guarantee": f"Meets Target (Y{int(ctx.poi_guarantee_year or 0)})",
        }
        s3_formatters = {
            "Year_Index": lambda v: f"{int(v)}",
            "SOH_Display_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "SOH_Absolute_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "DC_Usable_MWh": lambda v: format_value(v, "MWh"),
            "POI_Usable_Energy_MWh": lambda v: format_value(v, "MWh"),
            "DC_RTE_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "System_RTE_Pct": lambda v: format_percent(v, input_is_fraction=False),
            "Meets_Guarantee": lambda v: "" if v is None else str(v),
        }
        s3_columns = [column for column in s3_columns if column in s3_df.columns]
        _add_dataframe_table(doc, s3_df, s3_columns, s3_headers, s3_formatters, keep_together=False)
        doc.add_paragraph(
            f"Note: the POI energy guarantee is contractually evaluated at Year "
            f"{int(ctx.poi_guarantee_year or 0)} only; later years are shown for reference "
            f"and carry no pass/fail meaning."
        )

    # --- Section 6: Stage 4 - AC Block Sizing ---
    # Flows after the Stage 3 lifetime table (no forced break) to avoid an
    # orphan page when the table ends near a page boundary.
    doc.add_heading("6.  Stage 4 – AC Block Sizing", level=2)
    ac_ratio = ctx.ac_output.get("selected_ratio") if isinstance(ctx.ac_output, dict) else None
    ac_pcs_kw = ctx.ac_output.get("pcs_kw") if isinstance(ctx.ac_output, dict) else None
    if ac_pcs_kw is None and isinstance(ctx.ac_output, dict):
        ac_pcs_kw = ctx.ac_output.get("pcs_power_kw")
    pcs_count_by_block = ctx.ac_output.get("pcs_count_by_block") if isinstance(ctx.ac_output, dict) else None
    pcs_by_block_text = ""
    if isinstance(pcs_count_by_block, list) and pcs_count_by_block:
        distinct_counts = {int(v) for v in pcs_count_by_block}
        if len(distinct_counts) == 1:
            pcs_by_block_text = (
                f"{distinct_counts.pop()} per block, uniform across all "
                f"{len(pcs_count_by_block)} AC Blocks"
            )
        else:
            from collections import Counter
            grouped = Counter(int(v) for v in pcs_count_by_block)
            pcs_by_block_text = "; ".join(
                f"{count} PCS × {n_blocks} blocks" for count, n_blocks in sorted(grouped.items(), reverse=True)
            )
    transformer_mva = None
    if ctx.grid_power_factor and ctx.grid_power_factor > 0 and ctx.ac_block_size_mw:
        transformer_mva = ctx.ac_block_size_mw / ctx.grid_power_factor
    transformer_formula = "n/a"
    if transformer_mva is not None and ctx.ac_block_size_mw and ctx.grid_power_factor:
        transformer_formula = (
            f"{format_value(ctx.ac_block_size_mw, 'MW')} MW ÷ {format_value(ctx.grid_power_factor, 'PF')} (PF)"
            f" = {format_value(transformer_mva, 'MVA')} MVA"
        )
    s4_rows = [
        ("AC:DC Ratio", ac_ratio or "—"),
        ("AC Block Template", _normalize_template_label(ctx.ac_block_template_id)),
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
        ("Transformer Sizing Basis (AC Block MW ÷ PF)", transformer_formula),
    ]
    _add_table(doc, s4_rows, ["Parameter", "Value"])

    # --- Section 7: Single Line Diagram ---
    doc.add_page_break()
    doc.add_heading("7.  Single Line Diagram", level=2)
    _keep_next_para(doc.add_paragraph(
        "System electrical configuration: MV bus → RMU → Step-up Transformer → AC Block (DC blocks attached)."
    ))
    figure_index = 3  # Figures 1-2 used by Stage 3 milestone + POI charts above
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

    # --- Section 8: Typical AC Block Arrangement ---
    # Primary figure is the rule-based L1 drawing (spacing from the
    # ArrangementRuleProfile). The legacy UI-generated artifact is embedded
    # only as a fallback when the rule-based render is unavailable, so the
    # report never shows two contradictory aisle dimensions.
    doc.add_page_break()
    doc.add_heading("8.  Typical AC Block Arrangement (Concept Only)", level=2)
    plan_png, plan_layout, dc_per_ac = None, None, 0
    if ctx.ac_blocks_total > 0 and ctx.dc_blocks_total > 0:
        dc_per_ac = max(1, int(round(ctx.dc_blocks_total / ctx.ac_blocks_total)))
        try:
            plan_svg, plan_layout = render_ac_block_plan_svg(
                dc_per_ac, ARRANGEMENT_PROFILE
            )
            plan_png = _svg_bytes_to_png(plan_svg.encode("utf-8"))
        except Exception:
            plan_png, plan_layout = None, None

    if plan_png and plan_layout is not None:
        _keep_next_para(doc.add_paragraph(
            f"Rule-based typical arrangement ({dc_per_ac} × DC per block, "
            f"mirrored back-to-back pairs, doors facing outward aisles):"
        ))
        doc.add_picture(io.BytesIO(plan_png), width=Inches(6.7))
        _keep_next_para(doc.paragraphs[-1])
        _keep_next_para(doc.add_paragraph(
            f"Figure {figure_index}: Typical AC Block Arrangement (rule-based) — "
            f"envelope ≈ {plan_layout.envelope_w_m:.2f} × "
            f"{plan_layout.envelope_d_m:.2f} m. Concept only."
        ))
        figure_index += 1
        basis_rows = [(item, f"{value} — {basis}")
                      for item, value, basis in ARRANGEMENT_PROFILE.basis]
        basis_rows.append((
            "Arrangement rule profile", ARRANGEMENT_PROFILE.market_label))
        _add_table(doc, basis_rows, ["Spacing parameter", "Value & code basis"])
    else:
        layout_png_bytes = ctx.layout_png_bytes
        if not layout_png_bytes and ctx.layout_svg_bytes:
            layout_png_bytes = _svg_bytes_to_png(ctx.layout_svg_bytes)
        if layout_png_bytes:
            doc.add_picture(io.BytesIO(layout_png_bytes), width=Inches(6.7))
            _keep_next_para(doc.paragraphs[-1])
            doc.add_paragraph(
                f"Figure {figure_index}: Typical AC Block Arrangement — Concept Only")
        else:
            doc.add_paragraph(
                "Typical AC Block Arrangement not generated. "
                "Generate it from the corresponding concept page.")

    # --- Section 9: Concept Site Arrangement (Layout Roadmap L2) ---
    # Whole-site concept: mirrored AC blocks share a central MV corridor;
    # envelope estimate only, not a Master Layout (site boundary is out of scope).
    site_layout = _compute_site_layout(ctx)
    if site_layout is not None:
        try:
            site_svg = render_site_svg(site_layout, SITE_PROFILE)
            site_png = _svg_bytes_to_png(site_svg.encode("utf-8"))
        except Exception:
            site_png = None
        if site_png:
            doc.add_page_break()
            doc.add_heading("9.  Concept Site Arrangement (Concept Only)", level=2)
            _keep_next_para(doc.add_paragraph(
                f"{site_layout.n_blocks} × AC Block "
                f"({site_layout.dc_per_block} × DC each) arranged in "
                f"{site_layout.rows} row(s). Within each row the two AC blocks are "
                f"mirrored so both PCS & MV stations face a shared central MV "
                f"corridor; feeders collect there and route one direction along the "
                f"fire access road to the substation."
            ))
            # Tall (portrait) sites would overflow a page at fixed width, so
            # cap by height when the envelope is deeper than it is wide.
            if site_layout.envelope_d_m > site_layout.envelope_w_m:
                doc.add_picture(io.BytesIO(site_png), height=Inches(8.0))
            else:
                doc.add_picture(io.BytesIO(site_png), width=Inches(6.7))
            _keep_next_para(doc.paragraphs[-1])
            _keep_next_para(doc.add_paragraph(
                f"Figure {figure_index}: Concept Site Arrangement — "
                f"site envelope ≈ {site_layout.envelope_w_m:.1f} × "
                f"{site_layout.envelope_d_m:.1f} m "
                f"({site_layout.total_power_mw:.0f} MW / "
                f"{site_layout.total_energy_mwh:.1f} MWh). Concept only — "
                f"a full Master Layout requires a registered site constraint set."
            ))
            figure_index += 1
            site_rows = [
                ("AC Blocks", f"{site_layout.n_blocks:d} × "
                              f"{site_layout.dc_per_block} DC/block"),
                ("Row allocation", " + ".join(str(n) for n in site_layout.blocks_per_row)
                 + " blocks per row"),
                ("Site envelope (concept)",
                 f"≈ {site_layout.envelope_w_m:.1f} × {site_layout.envelope_d_m:.1f} m"),
                ("Rated power / energy",
                 f"{site_layout.total_power_mw:.0f} MW / "
                 f"{site_layout.total_energy_mwh:.1f} MWh"),
            ]
            site_rows.extend(
                (item, f"{value} — {basis}")
                for item, value, basis in SITE_PROFILE.basis
            )
            _add_table(doc, site_rows, ["Site parameter", "Value & code basis"])

    return _doc_to_bytes(doc)


export_report_v2 = export_report_v2_1
