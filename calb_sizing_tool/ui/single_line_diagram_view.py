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
import inspect
import math
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from calb_diagrams.specs import build_sld_group_spec
from calb_diagrams.sld_pro_renderer import render_sld_pro_svg
from calb_sizing_tool.common.allocation import allocate_dc_blocks, evenly_distribute
from calb_sizing_tool.common.nameplate import get_standard_container_mwh
from calb_sizing_tool.common.dependencies import check_dependencies
from calb_sizing_tool.common.preferences import load_preferences
from calb_sizing_tool.runtime_paths import ensure_outputs_dir
from calb_sizing_tool.sld.snapshot_single_unit import (
    build_single_unit_snapshot,
    validate_single_unit_snapshot,
)
from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _rmu_class_kv(mv_kv: float) -> float:
    if mv_kv <= 24:
        return 24.0
    if mv_kv <= 36:
        return 36.0
    return round(mv_kv)


def _estimate_lv_current_a(transformer_mva: float, lv_v: float) -> float:
    if transformer_mva <= 0 or lv_v <= 0:
        return 0.0
    return transformer_mva * 1_000_000.0 / (math.sqrt(3) * lv_v)


def _seed_sld_defaults(
    diagram_inputs: dict,
    stage13_output: dict,
    ac_output: dict,
    dc_summary: dict,
    mv_kv: float,
    lv_v: float,
    transformer_mva: float,
):
    if not isinstance(diagram_inputs, dict):
        return

    mv_labels = diagram_inputs.get("mv_labels")
    if not isinstance(mv_labels, dict):
        mv_labels = {}
    if "to_switchgear" not in mv_labels:
        mv_labels["to_switchgear"] = f"To {mv_kv:.0f}kV Switchgear" if mv_kv else "To Switchgear"
    if "to_other_rmu" not in mv_labels:
        mv_labels["to_other_rmu"] = "To Other RMU"
    diagram_inputs["mv_labels"] = mv_labels

    rmu = diagram_inputs.get("rmu")
    if not isinstance(rmu, dict):
        rmu = {}
    rmu.setdefault("rated_kv", _rmu_class_kv(mv_kv) if mv_kv else 24.0)
    rmu.setdefault("rated_a", 630.0)
    rmu.setdefault("short_circuit_ka_3s", 25.0)
    rmu.setdefault("ct_ratio", "300/1")
    rmu.setdefault("ct_class", "5P20")
    rmu.setdefault("ct_va", 5.0)
    diagram_inputs["rmu"] = rmu

    transformer = diagram_inputs.get("transformer")
    if not isinstance(transformer, dict):
        transformer = {}
    transformer.setdefault("vector_group", ac_output.get("vector_group") or "Dyn11")
    transformer.setdefault("uk_percent", ac_output.get("transformer_uk_percent") or 7.0)
    transformer.setdefault("tap_range", "+/-2x2.5%")
    transformer.setdefault("cooling", "ONAN")
    diagram_inputs["transformer"] = transformer

    lv_busbar = diagram_inputs.get("lv_busbar")
    if not isinstance(lv_busbar, dict):
        lv_busbar = {}
    if "rated_a" not in lv_busbar:
        lv_current = _estimate_lv_current_a(transformer_mva, lv_v)
        lv_busbar["rated_a"] = round(lv_current / 10.0) * 10 if lv_current > 0 else 2500.0
    lv_busbar.setdefault("short_circuit_ka", 25.0)
    diagram_inputs["lv_busbar"] = lv_busbar

    if "dc_block_voltage_v" not in diagram_inputs:
        dc_block_voltage_v = 0.0
        if isinstance(dc_summary, dict):
            dc_block = dc_summary.get("dc_block")
            if dc_block is not None:
                dc_block_voltage_v = _safe_float(getattr(dc_block, "voltage_v", 0.0), 0.0)
        if dc_block_voltage_v <= 0:
            dc_block_voltage_v = _safe_float(stage13_output.get("dc_block_voltage_v"), 0.0)
        if dc_block_voltage_v > 0:
            diagram_inputs["dc_block_voltage_v"] = dc_block_voltage_v


@st.cache_data(show_spinner=False)
def _svg_bytes_to_png(svg_bytes: bytes) -> bytes | None:
    if not svg_bytes:
        return None
    try:
        import cairosvg
    except Exception:
        return None
    try:
        return cairosvg.svg2png(bytestring=svg_bytes, background_color="white")
    except Exception:
        return None


def _resolve_pcs_count_by_block(ac_output: dict) -> list[int]:
    pcs_counts = ac_output.get("pcs_count_by_block")
    if isinstance(pcs_counts, list) and pcs_counts:
        return [_safe_int(v, 0) for v in pcs_counts]

    pcs_units = ac_output.get("pcs_units")
    if isinstance(pcs_units, list) and pcs_units:
        return [len(pcs_units)]

    num_blocks = _safe_int(ac_output.get("num_blocks"), 0)
    total_pcs = _safe_int(ac_output.get("total_pcs"), 0)
    pcs_per_block = _safe_int(
        ac_output.get("pcs_count_per_ac_block") or ac_output.get("pcs_per_block"), 0
    )
    if num_blocks > 0 and total_pcs > 0:
        return evenly_distribute(total_pcs, num_blocks)
    if num_blocks > 0 and pcs_per_block > 0:
        return [pcs_per_block for _ in range(num_blocks)]
    return [4]


def _resolve_dc_blocks_per_feeder(
    stage13_output: dict,
    ac_output: dict,
    dc_summary: dict,
    pcs_count: int,
    group_index: int,
    override_total_blocks: int = 0,
) -> list[int]:
    """
    Resolves DC block allocation per feeder based on the detailed 'dc_allocation_plan'
    from the AC sizing output. This replaces complex fallback logic with a direct
    lookup, enforcing a clear data contract between the AC Sizing and SLD views.
    """
    allocation_plan = ac_output.get("dc_allocation_plan")

    if isinstance(allocation_plan, list):
        # Find the allocation for the selected AC block group
        group_plan = next(
            (plan for plan in allocation_plan if plan.get("ac_block_index") == group_index),
            None,
        )
        if group_plan and isinstance(group_plan.get("feeder_allocations"), list):
            return [_safe_int(v) for v in group_plan["feeder_allocations"]]

    # Fallback to a sensible default if the plan is missing or malformed.
    # This prevents crashes but indicates a data flow issue.
    st.warning("DC allocation plan not found in AC results. Using default of 0.")
    if pcs_count > 0:
        return [0] * pcs_count
    return [0, 0, 0, 0]


def show():
    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()

    st.header("Single Line Diagram")
    st.caption("Engineering-readable SLD for one AC block group.")

    deps = check_dependencies()
    svgwrite_ok = deps.get("svgwrite", False)
    cairosvg_ok = deps.get("cairosvg", False)

    def _pick_value(*values):
        for value in values:
            if value is not None:
                return value
        return None

    dc_results = project_state.get("dc_results") or state.dc_results
    ac_inputs = project_state.get("ac_inputs") or state.ac_inputs
    ac_results = project_state.get("ac_results") or state.ac_results
    diagram_outputs = state.diagram_outputs
    diagram_inputs = project_state.get("diagram_inputs") or st.session_state.setdefault(
        "diagram_inputs", {}
    )
    diagram_results = project_state.get("diagram_outputs") or st.session_state.setdefault(
        "diagram_results", {}
    )
    artifacts = state.artifacts

    stage13_output = st.session_state.get("stage13_output") or dc_results.get("stage13_output") or {}
    dc_summary = st.session_state.get("dc_result_summary") or dc_results.get("dc_result_summary") or {}
    ac_output = st.session_state.get("ac_output") or ac_results or {}
    if stage13_output.get("project_name"):
        st.session_state["project_name"] = stage13_output.get("project_name")

    has_prereq = bool(stage13_output) and bool(ac_output)

    st.subheader("Data Status")
    if not has_prereq:
        st.warning("Please run DC Sizing + AC Sizing first.")
    dc_time = dc_results.get("last_run_time") or "Not run"
    ac_time = ac_results.get("last_run_time") or "Not run"
    mv_kv_value = _pick_value(
        ac_inputs.get("grid_kv"),
        ac_inputs.get("mv_kv"),
        ac_output.get("mv_voltage_kv"),
        ac_output.get("mv_kv"),
        ac_output.get("grid_kv"),
    )
    lv_v_value = _pick_value(
        ac_inputs.get("lv_voltage_v"),
        ac_inputs.get("pcs_lv_v"),
        ac_output.get("lv_voltage_v"),
        ac_output.get("lv_v"),
        ac_output.get("inverter_lv_v"),
    )
    mv_kv_status = mv_kv_value if mv_kv_value is not None else "TBD"
    lv_v_status = lv_v_value if lv_v_value is not None else "TBD"
    pcs_counts = _resolve_pcs_count_by_block(ac_output)
    pcs_count_status = pcs_counts[0] if pcs_counts else "TBD"
    if isinstance(pcs_count_status, (list, tuple)):
        pcs_count_status = sum(pcs_count_status) if pcs_count_status else "TBD"
    dc_blocks_status = ac_output.get("dc_block_allocation", {}).get("total_dc_blocks")
    if dc_blocks_status is None:
        dc_blocks_status_raw = ac_output.get("dc_blocks_per_ac")
        if isinstance(dc_blocks_status_raw, (list, tuple)):
            try:
                dc_blocks_status = sum(int(x) for x in dc_blocks_status_raw if isinstance(x, (int, float)))
            except (ValueError, TypeError):
                dc_blocks_status = len(dc_blocks_status_raw) if dc_blocks_status_raw else "TBD"
        else:
            dc_blocks_status = dc_blocks_status_raw
            
    c_status1, c_status2, c_status3 = st.columns(3)
    c_status1.metric("DC Run", dc_time)
    c_status2.metric("AC Run", ac_time)
    c_status3.metric("MV/LV", f"{mv_kv_status} kV / {lv_v_status} V")
    c_status4, c_status5 = st.columns(2)
    c_status4.metric("PCS Count (group)", str(pcs_count_status) if pcs_count_status != "TBD" else pcs_count_status)
    c_status5.metric("DC Blocks (group)", str(dc_blocks_status) if dc_blocks_status != "TBD" else "TBD")

    if not svgwrite_ok:
        st.error(
            "Missing dependency: svgwrite. Install with `pip install svgwrite` or "
            "`pip install -r requirements.txt`."
        )

    scenario_default = diagram_inputs.get("scenario_id")
    if scenario_default is None:
        scenario_default = stage13_output.get("selected_scenario", "container_only")
    scenario_id = st.text_input(
        "Scenario ID",
        value=str(scenario_default) if scenario_default is not None else "",
        key="diagram_inputs.scenario_id",
    )
    diagram_inputs["scenario_id"] = scenario_id

    # Default to the verified compact SLD style.
    style_id = "raw_v05"
    diagram_inputs["style"] = "Raw V0.5 (Stable)"

    ac_blocks_total = max(len(pcs_counts), _safe_int(ac_output.get("num_blocks"), 0), 1)
    group_default = _safe_int(diagram_inputs.get("group_index"), 1)
    group_default = max(1, min(group_default, ac_blocks_total))
    group_index = st.selectbox(
        "AC Block Group",
        list(range(1, ac_blocks_total + 1)),
        index=group_default - 1,
        key="diagram_inputs.group_index",
        disabled=not has_prereq,
    )
    diagram_inputs["group_index"] = group_index

    pcs_count = pcs_counts[group_index - 1] if pcs_counts and group_index > 0 else 0
    st.caption(f"Selected group PCS count: {pcs_count or 'TBD'}")

    st.subheader("Chain Parameters")
    c1, c2, c3 = st.columns(3)
    mv_kv_default = diagram_inputs.get("mv_kv")
    if mv_kv_default is None:
        mv_kv_default = mv_kv_value if mv_kv_value is not None else 33.0
    mv_kv = c1.number_input(
        "MV nominal voltage (kV)",
        min_value=1.0,
        value=float(mv_kv_default),
        key="diagram_inputs.mv_kv",
        step=0.1,
        disabled=not has_prereq,
    )
    diagram_inputs["mv_kv"] = mv_kv

    lv_v_default = diagram_inputs.get("lv_v")
    if lv_v_default is None:
        lv_v_default = lv_v_value if lv_v_value is not None else 690.0
    pcs_lv_v = c2.number_input(
        "PCS LV voltage (V_LL,rms)",
        min_value=100.0,
        value=float(lv_v_default),
        key="diagram_inputs.lv_v",
        step=10.0,
        disabled=not has_prereq,
    )
    diagram_inputs["lv_v"] = pcs_lv_v

    transformer_mva_default = diagram_inputs.get("transformer_mva")
    if transformer_mva_default is None:
        transformer_mva_default = _safe_float(ac_output.get("transformer_mva"), 0.0)
    if transformer_mva_default <= 0:
        transformer_mva_default = _safe_float(ac_output.get("transformer_kva"), 0.0) / 1000.0
    if transformer_mva_default <= 0 and _safe_float(ac_output.get("block_size_mw"), 0.0) > 0:
        transformer_mva_default = _safe_float(ac_output.get("block_size_mw"), 5.0) / 0.9
    transformer_rating_mva = c3.number_input(
        "Transformer rating (MVA)",
        min_value=0.1,
        value=float(transformer_mva_default or 5.0),
        key="diagram_inputs.transformer_mva",
        step=0.1,
        disabled=not has_prereq,
    )
    diagram_inputs["transformer_mva"] = transformer_rating_mva

    d1, d2 = st.columns(2)
    pcs_rating_default = diagram_inputs.get("pcs_rating_kw")
    if pcs_rating_default is None:
        pcs_rating_default = _safe_float(ac_output.get("pcs_rating_kw_each"), 0.0)
    if pcs_rating_default <= 0:
        pcs_rating_default = _safe_float(ac_output.get("pcs_power_kw"), 0.0)
    if pcs_rating_default <= 0 and _safe_float(ac_output.get("block_size_mw"), 0.0) > 0 and pcs_count > 0:
        pcs_rating_default = _safe_float(ac_output.get("block_size_mw"), 5.0) * 1000 / pcs_count
    pcs_rating_each_kw = d1.number_input(
        "PCS rating each (kW)",
        min_value=0.0,
        value=float(pcs_rating_default or 1250.0),
        key="diagram_inputs.pcs_rating_kw",
        step=10.0,
        disabled=not has_prereq,
    )
    diagram_inputs["pcs_rating_kw"] = pcs_rating_each_kw

    dc_block_default = diagram_inputs.get("dc_block_energy_mwh")
    if dc_block_default is None:
        dc_block_default = _safe_float(ac_output.get("dc_block_energy_mwh_each"), 0.0)
    if dc_block_default <= 0:
        dc_block_default = _safe_float(ac_output.get("dc_block_mwh_each"), 0.0)
    if dc_block_default <= 0 and isinstance(dc_summary, dict):
        dc_block = dc_summary.get("dc_block")
        if dc_block is not None:
            dc_block_default = getattr(dc_block, "capacity_mwh", None)
    dc_block_energy_mwh = d2.number_input(
        "DC block energy (MWh)",
        min_value=0.0,
        value=float(dc_block_default or get_standard_container_mwh()),
        key="diagram_inputs.dc_block_energy_mwh",
        step=0.001,
        disabled=not has_prereq,
    )
    diagram_inputs["dc_block_energy_mwh"] = dc_block_energy_mwh

    _seed_sld_defaults(
        diagram_inputs,
        stage13_output,
        ac_output,
        dc_summary,
        mv_kv,
        pcs_lv_v,
        transformer_rating_mva,
    )

    st.subheader("DC Block Allocation (per feeder)")
    ac_blocks_override = _safe_int(diagram_inputs.get("ac_blocks_total_override"), 0)
    default_dc_blocks = _resolve_dc_blocks_per_feeder(
        stage13_output, ac_output, dc_summary, pcs_count or 0, group_index, ac_blocks_override
    )
    stored_blocks = diagram_inputs.get("dc_blocks_per_feeder")
    if isinstance(stored_blocks, list) and len(stored_blocks) == len(default_dc_blocks):
        dc_blocks_per_feeder = stored_blocks
    else:
        dc_blocks_per_feeder = default_dc_blocks
    dc_df = pd.DataFrame(
        {
            "feeder_id": [f"F{idx + 1}" for idx in range(len(dc_blocks_per_feeder))],
            "dc_block_count": dc_blocks_per_feeder,
        }
    )

    dc_df_key = "diagram_inputs.dc_blocks_df"
    stored_df = st.session_state.get(dc_df_key)
    if isinstance(stored_df, pd.DataFrame) and len(stored_df) != len(dc_df):
        st.session_state.pop(dc_df_key)
    st.session_state.setdefault(dc_df_key, dc_df)

    dc_df = st.data_editor(
        st.session_state[dc_df_key],
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=not has_prereq,
    )
    st.session_state[dc_df_key] = dc_df

    dc_blocks_per_feeder = [
        _safe_int(row.get("dc_block_count"), 0) for row in dc_df.to_dict("records")
    ]
    diagram_inputs["dc_blocks_per_feeder"] = dc_blocks_per_feeder

    prefs = load_preferences()
    svg_width = int(diagram_inputs.get("svg_width", prefs.get("sld_svg_width", 1400)))
    svg_height = int(diagram_inputs.get("svg_height", prefs.get("sld_svg_height", 900)))
    pcs_gap = int(diagram_inputs.get("pcs_gap", 60))
    busbar_gap = int(diagram_inputs.get("busbar_gap", 22))
    font_scale = float(diagram_inputs.get("font_scale", 1.0))
    
    diagram_inputs["svg_width"] = svg_width
    diagram_inputs["svg_height"] = svg_height
    diagram_inputs["pcs_gap"] = pcs_gap
    diagram_inputs["busbar_gap"] = busbar_gap
    diagram_inputs["font_scale"] = font_scale

    theme = diagram_inputs.get("theme") or "dark"
    diagram_inputs["theme"] = theme
    if diagram_inputs.get("draw_summary") is None:
        diagram_inputs["draw_summary"] = False

    if "key_prefix" in inspect.signature(render_electrical_inputs).parameters:
        electrical_inputs = render_electrical_inputs(
            diagram_inputs, key_prefix="diagram_inputs"
        )
    else:
        electrical_inputs = render_electrical_inputs(diagram_inputs)

    sld_inputs = {
        "group_index": group_index,
        "compact_mode": True,
        "theme": theme,
        "draw_summary": diagram_inputs.get("draw_summary"),
        "mv_nominal_kv_ac": mv_kv,
        "pcs_lv_voltage_v_ll": pcs_lv_v,
        "transformer_rating_mva": transformer_rating_mva,
        "pcs_rating_each_kw": pcs_rating_each_kw,
        "pcs_rating_each_kva": pcs_rating_each_kw,
        "pcs_rating_kw_list": [pcs_rating_each_kw for _ in range(pcs_count or 0)],
        "dc_block_energy_mwh": dc_block_energy_mwh,
        "dc_blocks_per_feeder": dc_blocks_per_feeder,
        "dc_block_voltage_v": diagram_inputs.get("dc_block_voltage_v"),
        "svg_width": svg_width,
        "svg_height": svg_height,
        "pcs_gap": pcs_gap,
        "busbar_gap": busbar_gap,
        "font_scale": font_scale,
        **electrical_inputs,
    }

    if style_id not in diagram_results:
        diagram_results[style_id] = {}

    generate_disabled = not has_prereq
    if not svgwrite_ok:
        generate_disabled = True

    generate = st.button(
        "Generate SLD",
        key="sld_generate_button",
        disabled=generate_disabled,
    )
    if generate:
        try:
            if not svgwrite_ok:
                st.error("Rendering requires svgwrite. Install with Requirement already satisfied: svgwrite in /usr/local/lib/python3.10/dist-packages (1.4.3).")
                svg_bytes = None
                png_bytes = None
            else:
                dc_blocks_by_feeder = []
                for idx, count in enumerate(dc_blocks_per_feeder, start=1):
                    dc_blocks_by_feeder.append(
                        {
                            "feeder_id": f"FDR-{idx:02d}",
                            "dc_block_count": int(count),
                            "dc_block_energy_mwh": float(count) * dc_block_energy_mwh,
                        }
                    )
                jp_inputs = dict(sld_inputs)
                jp_inputs["dc_blocks_by_feeder"] = dc_blocks_by_feeder
                jp_inputs["diagram_scope"] = "one_ac_block_group"
                snapshot = build_single_unit_snapshot(
                    stage13_output, ac_output, dc_summary, jp_inputs, scenario_id
                )
                validate_single_unit_snapshot(snapshot)
                sld_spec = build_sld_group_spec(
                    stage13_output, ac_output, dc_summary, sld_inputs, group_index
                )
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir)
                    svg_path = tmp_path / "sld_pro_v10.svg"
                    render_sld_pro_svg(sld_spec, svg_path)
                    svg_bytes = svg_path.read_bytes() if svg_path.exists() else None
                    png_bytes = _svg_bytes_to_png(svg_bytes) if svg_bytes and cairosvg_ok else None

            if svg_bytes or png_bytes:
                dc_blocks_total = sum(dc_blocks_per_feeder) if dc_blocks_per_feeder else 0
                meta = {
                    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "style": style_id,
                    "group_index": group_index,
                    "mv_kv": mv_kv,
                    "lv_v": pcs_lv_v,
                    "pcs_count": pcs_count,
                    "dc_blocks_total": dc_blocks_total,
                    "transformer_mva": transformer_rating_mva,
                    "pcs_rating_kw_each": pcs_rating_each_kw,
                    "dc_block_energy_mwh": dc_block_energy_mwh,
                }
                diagram_results[style_id] = {
                    "svg": svg_bytes,
                    "png": png_bytes,
                    "meta": meta,
                }
                diagram_results["last_style"] = style_id
                st.session_state["diagram_results"] = diagram_results
                if svg_bytes:
                    artifacts["sld_svg_bytes"] = svg_bytes
                    diagram_outputs.sld_svg = svg_bytes
                if png_bytes:
                    artifacts["sld_png_bytes"] = png_bytes
                    diagram_outputs.sld_png = png_bytes
                artifacts["sld_meta"] = meta
                try:
                    outputs_dir = ensure_outputs_dir()
                except Exception as exc:
                    st.warning(f"Could not create outputs directory: {exc}")
                else:
                    if svg_bytes:
                        try:
                            svg_path = outputs_dir / "sld_latest.svg"
                            svg_path.write_bytes(svg_bytes)
                            diagram_outputs.sld_svg_path = str(svg_path)
                            st.session_state["sld_svg_path"] = str(svg_path)
                        except Exception as exc:
                            st.warning(f"Could not write SLD SVG: {exc}")
                    if png_bytes:
                        try:
                            png_path = outputs_dir / "sld_latest.png"
                            png_path.write_bytes(png_bytes)
                            diagram_outputs.sld_png_path = str(png_path)
                            st.session_state["sld_png_path"] = str(png_path)
                        except Exception as exc:
                            st.warning(f"Could not write SLD PNG: {exc}")
        except Exception as exc:
            st.error(f"SLD generation failed: {exc}")

    cached = diagram_results.get(style_id) or {}
    svg_bytes = cached.get("svg")
    png_bytes = cached.get("png")
    if svg_bytes or png_bytes:
        st.subheader("Preview")
        zoom = st.slider(
            "Zoom (%)",
            min_value=50,
            max_value=200,
            value=int(diagram_inputs.get("zoom") if diagram_inputs.get("zoom") is not None else 100),
            key="diagram_inputs.zoom",
        )
        diagram_inputs["zoom"] = zoom
        if png_bytes:
            st.image(png_bytes, width=int(800 * zoom / 100))
        else:
            scale = zoom / 100.0
            height = int(720 * scale)
            svg_html = f"<div style='transform: scale({scale}); transform-origin: 0 0;'>{svg_bytes.decode('utf-8')}</div>"
            st.components.v1.html(svg_html, height=height, scrolling=True)

        st.subheader("Downloads")
        if svg_bytes:
            st.download_button(
                "Download SLD SVG",
                svg_bytes,
                f"sld_{style_id}.svg",
                "image/svg+xml",
            )
        if png_bytes:
            st.download_button(
                "Download SLD PNG",
                png_bytes,
                f"sld_{style_id}.png",
                "image/png",
            )
