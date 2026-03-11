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
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from calb_diagrams.layout_block_renderer import render_layout_block_svg
from calb_diagrams.specs import build_layout_block_spec
from calb_sizing_tool.common.dependencies import check_dependencies
from calb_sizing_tool.common.preferences import load_preferences, save_preferences
from calb_sizing_tool.runtime_paths import ensure_outputs_dir
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


def show():
    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()
    st.header("Site Layout")
    st.caption("Template block layout (abstract engineering view).")

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
    layout_inputs = project_state.get("layout_inputs") or st.session_state.setdefault(
        "layout_inputs", {}
    )
    layout_results = project_state.get("layout_outputs") or st.session_state.setdefault(
        "layout_results", {}
    )
    artifacts = state.artifacts

    stage13_output = st.session_state.get("stage13_output") or dc_results.get("stage13_output") or {}
    dc_summary = st.session_state.get("dc_result_summary") or dc_results.get("dc_result_summary") or {}
    ac_output = st.session_state.get("ac_output") or ac_results or {}

    has_prereq = bool(stage13_output) and bool(ac_output)
    if not has_prereq:
        st.warning("Run DC sizing and AC sizing first to generate layout inputs.")

    st.subheader("Data Status")
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
    dc_blocks_total = stage13_output.get("dc_block_total_qty")
    if dc_blocks_total is None:
        dc_blocks_total = _safe_int(stage13_output.get("container_count"), 0) + _safe_int(
            stage13_output.get("cabinet_count"), 0
        )
    # If DC run exists but count is 0, show 0 instead of TBD
    if bool(stage13_output) and dc_blocks_total == 0:
        pass 

    c_status1, c_status2, c_status3 = st.columns(3)
    c_status1.metric("DC Run", dc_time)
    c_status2.metric("AC Run", ac_time)
    c_status3.metric("MV/LV", f"{mv_kv_status} kV / {lv_v_status} V")
    c_status4, c_status5 = st.columns(2)
    c_status4.metric("DC Blocks (total)", dc_blocks_total if dc_blocks_total is not None else "TBD")
    c_status5.metric("AC Blocks", ac_output.get("num_blocks") or "TBD")

    if not svgwrite_ok:
        st.error(
            "Missing dependency: svgwrite. Install with `pip install svgwrite` or "
            "`pip install -r requirements.txt`."
        )

    def _init_input(field: str, default_value):
        key = f"layout_inputs.{field}"
        if key not in st.session_state:
            st.session_state[key] = default_value
        if field not in layout_inputs:
            layout_inputs[field] = st.session_state[key]
        return key

    ac_blocks_total = max(_safe_int(ac_output.get("num_blocks"), 0), 1)
    block_default = _safe_int(layout_inputs.get("block_index"), 1)
    block_default = max(1, min(block_default, ac_blocks_total))
    block_index = st.selectbox(
        "AC Block Group",
        list(range(1, ac_blocks_total + 1)),
        index=block_default - 1,
        key=_init_input("block_index", block_default),
        disabled=not has_prereq,
    )
    layout_inputs["block_index"] = block_index

    arrangement_options = ["Auto", "2x2", "1x4", "4x1"]
    arrangement_default = layout_inputs.get("arrangement") or "Auto"
    if arrangement_default not in arrangement_options:
        arrangement_default = "Auto"
    arrangement = st.selectbox(
        "DC Block arrangement",
        arrangement_options,
        index=arrangement_options.index(arrangement_default),
        key=_init_input("arrangement", arrangement_default),
        disabled=not has_prereq,
    )
    layout_inputs["arrangement"] = arrangement
    show_skid = st.checkbox(
        "Show PCS&MVT SKID",
        key=_init_input("show_skid", bool(layout_inputs.get("show_skid", True))),
        disabled=not has_prereq,
    )
    layout_inputs["show_skid"] = show_skid
    dc_block_mirrored = st.checkbox(
        "Mirror DC block interior hints",
        key=_init_input("dc_block_mirrored", bool(layout_inputs.get("dc_block_mirrored", False))),
        disabled=not has_prereq,
    )
    layout_inputs["dc_block_mirrored"] = dc_block_mirrored

    st.subheader("Clearances (m)")
    c_clear1, c_clear2, c_clear3 = st.columns(3)
    dc_to_dc_default = layout_inputs.get("dc_to_dc_clearance_m")
    if dc_to_dc_default is None:
        dc_to_dc_default = 0.3
    dc_to_dc_clearance = c_clear1.number_input(
        "DC to DC",
        min_value=0.0,
        key=_init_input("dc_to_dc_clearance_m", float(dc_to_dc_default)),
        step=0.1,
        help="Set to 0 for TBD.",
        disabled=not has_prereq,
    )
    layout_inputs["dc_to_dc_clearance_m"] = dc_to_dc_clearance

    dc_to_ac_default = layout_inputs.get("dc_to_ac_clearance_m")
    if dc_to_ac_default is None:
        dc_to_ac_default = 2.0
    dc_to_ac_clearance = c_clear2.number_input(
        "DC to AC",
        min_value=0.0,
        key=_init_input("dc_to_ac_clearance_m", float(dc_to_ac_default)),
        step=0.1,
        help="Set to 0 for TBD.",
        disabled=not has_prereq,
    )
    layout_inputs["dc_to_ac_clearance_m"] = dc_to_ac_clearance

    perimeter_default = layout_inputs.get("perimeter_clearance_m")
    if perimeter_default is None:
        perimeter_default = 0.0
    perimeter_clearance = c_clear3.number_input(
        "Perimeter",
        min_value=0.0,
        key=_init_input("perimeter_clearance_m", float(perimeter_default)),
        step=0.1,
        help="Optional; set to 0 to hide perimeter clearance.",
        disabled=not has_prereq,
    )
    layout_inputs["perimeter_clearance_m"] = perimeter_clearance

    mv_kv = _safe_float(mv_kv_value, None)
    lv_v = _safe_float(lv_v_value, None)

    transformer_mva = _safe_float(ac_output.get("transformer_mva"), 0.0)
    if transformer_mva <= 0:
        transformer_mva = _safe_float(ac_output.get("transformer_kva"), 0.0) / 1000.0
    if transformer_mva <= 0 and _safe_float(ac_output.get("block_size_mw"), 0.0) > 0:
        transformer_mva = _safe_float(ac_output.get("block_size_mw"), 5.0) / 0.9

    st.subheader("Labels")
    block_title = st.text_input(
        "Block title template",
        key=_init_input("block_title", layout_inputs.get("block_title") or "Block {index}: DC Blocks={dc_blocks}"),
        disabled=not has_prereq,
    )
    layout_inputs["block_title"] = block_title
    bess_range_text = st.text_input(
        "BESS range text template",
        key=_init_input("bess_range_text", layout_inputs.get("bess_range_text") or "BESS {start}~{end}"),
        disabled=not has_prereq,
    )
    layout_inputs["bess_range_text"] = bess_range_text
    skid_text = st.text_input(
        "SKID label",
        key=_init_input("skid_text", layout_inputs.get("skid_text") or "PCS&MVT SKID (AC Block)"),
        disabled=not has_prereq,
    )
    layout_inputs["skid_text"] = skid_text
    mv_text = f"{mv_kv:.1f} kV" if isinstance(mv_kv, (int, float)) and mv_kv > 0 else "TBD"
    lv_text = f"{lv_v:.0f} V" if isinstance(lv_v, (int, float)) and lv_v > 0 else "TBD"
    mva_text = f"{transformer_mva:.1f} MVA" if transformer_mva > 0 else "TBD"
    skid_subtext_default = f"{mv_text} / {lv_text}, {mva_text}"
    skid_subtext = st.text_input(
        "SKID subtext",
        key=_init_input("skid_subtext", layout_inputs.get("skid_subtext") or skid_subtext_default),
        disabled=not has_prereq,
    )
    layout_inputs["skid_subtext"] = skid_subtext

    # Setting default values for layout parameters.
    prefs = load_preferences()
    scale_factor = float(layout_inputs.get("scale", prefs.get("layout_scale", 0.04)))
    left_margin = int(layout_inputs.get("left_margin", prefs.get("layout_left_margin", 40)))
    top_margin = int(layout_inputs.get("top_margin", prefs.get("layout_top_margin", 40)))
    
    layout_inputs["scale"] = scale_factor
    layout_inputs["left_margin"] = left_margin
    layout_inputs["top_margin"] = top_margin

    labels = {
        "block_title": block_title,
        "bess_range_text": bess_range_text,
        "skid_text": skid_text,
        "skid_subtext": skid_subtext,
    }

    # --- NEW: Simplified and reliable DC block count resolution ---
    dc_block_counts_by_block = {}
    allocation_plan = ac_output.get("dc_allocation_plan")
    if isinstance(allocation_plan, list):
        for plan_item in allocation_plan:
            idx = plan_item.get("ac_block_index")
            count = plan_item.get("dc_blocks_total")
            if isinstance(idx, int) and idx > 0 and isinstance(count, int):
                dc_block_counts_by_block[idx] = count

    # Determine the DC block count for the currently selected AC Block group
    # Fallback to 0 if the plan is missing or doesn't contain the selected index.
    block_dc_count = dc_block_counts_by_block.get(block_index, 0)
    if block_dc_count == 0 and dc_block_counts_by_block:
        # If lookup fails, try to use the first available value as a guess.
        block_dc_count = next(iter(dc_block_counts_by_block.values()))

    # Auto-determine arrangement based on the now-correct count
    if arrangement == "Auto":
        # A simple heuristic for arrangement
        if block_dc_count <= 1:
            layout_arrangement = "1x4"
        elif block_dc_count == 2:
            layout_arrangement = "1x4"
        elif block_dc_count <= 4:
            layout_arrangement = "2x2"
        elif block_dc_count <= 8:
            layout_arrangement = "4x2" # A more sensible default for larger counts
        else:
            layout_arrangement = "4x4"
    else:
        layout_arrangement = arrangement

    # Define selected_blocks for use in the generator
    selected_blocks = [block_index]

    style_id = "raw_v05"
    if style_id not in layout_results:
        layout_results[style_id] = {}

    generate_disabled = not has_prereq

    generate = st.button("Generate Layout", disabled=generate_disabled)

    if generate and style_id == "raw_v05":
        try:
            # --- Get PCS count for the selected block ---
            pcs_count = _safe_int(ac_output.get("pcs_per_block"), 4)

            spec = build_layout_block_spec(
                ac_output=ac_output,
                block_indices_to_render=selected_blocks,
                labels=labels,
                pcs_count=pcs_count,
                dc_blocks_per_block=block_dc_count,
                dc_block_counts_by_block=dc_block_counts_by_block,
                arrangement=layout_arrangement,
                show_skid=show_skid,
                dc_to_dc_clearance_m=dc_to_dc_clearance,
                dc_to_ac_clearance_m=dc_to_ac_clearance,
                perimeter_clearance_m=perimeter_clearance,
                dc_block_mirrored=dc_block_mirrored,
                use_template=False,
                scale=scale_factor,
                left_margin=left_margin,
                top_margin=top_margin,
                theme="light",
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                svg_path = tmp_path / "layout_block.svg"
                svg_result, warning = render_layout_block_svg(spec, svg_path)
                if svg_result is None:
                    st.error(warning or "Layout renderer unavailable.")
                    st.code("pip install svgwrite")
                else:
                    if warning:
                        st.warning(warning)
                        if "cairosvg" in warning.lower():
                            st.code("pip install cairosvg")

                    svg_bytes = svg_path.read_bytes() if svg_path.exists() else None
                    png_bytes = _svg_bytes_to_png(svg_bytes) if svg_bytes and cairosvg_ok else None
                    if svg_bytes and png_bytes is None and not cairosvg_ok:
                        st.warning("Missing dependency: cairosvg. PNG export skipped.")
                    if svg_bytes or png_bytes:
                        meta = {
                            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                            "style": style_id,
                            "block_index": block_index,
                            "dc_blocks_total": block_dc_count,
                            "arrangement": layout_arrangement,
                            "clearances_m": {
                                "dc_to_dc": dc_to_dc_clearance,
                                "dc_to_ac": dc_to_ac_clearance,
                                "perimeter": perimeter_clearance,
                            },
                            "show_skid": show_skid,
                            "mv_kv": mv_kv,
                            "lv_v": lv_v,
                            "transformer_mva": transformer_mva,
                        }
                        layout_results[style_id] = {
                            "svg": svg_bytes,
                            "png": png_bytes,
                            "meta": meta,
                        }
                        layout_results["last_style"] = style_id
                        st.session_state["layout_results"] = layout_results
                        if svg_bytes:
                            st.session_state["layout_svg_bytes"] = svg_bytes
                            artifacts["layout_svg_bytes"] = svg_bytes
                            diagram_outputs.layout_svg = svg_bytes
                        if png_bytes:
                            st.session_state["layout_png_bytes"] = png_bytes
                            artifacts["layout_png_bytes"] = png_bytes
                            diagram_outputs.layout_png = png_bytes
                            if isinstance(layout_results[style_id].get("meta"), dict):
                                layout_results[style_id]["meta"]["hash"] = __import__("hashlib").sha256(png_bytes).hexdigest()[:12]
                        artifacts["layout_meta"] = meta
                        try:
                            outputs_dir = ensure_outputs_dir()
                        except Exception as exc:
                            st.warning(f"Could not create outputs directory: {exc}")
                        else:
                            if svg_bytes:
                                try:
                                    svg_path = outputs_dir / "layout_latest.svg"
                                    svg_path.write_bytes(svg_bytes)
                                    diagram_outputs.layout_svg_path = str(svg_path)
                                    st.session_state["layout_svg_path"] = str(svg_path)
                                except Exception as exc:
                                    st.warning(f"Could not write layout SVG: {exc}")
                            if png_bytes:
                                try:
                                    png_path = outputs_dir / "layout_latest.png"
                                    png_path.write_bytes(png_bytes)
                                    diagram_outputs.layout_png_path = str(png_path)
                                    st.session_state["layout_png_path"] = str(png_path)
                                except Exception as exc:
                                    st.warning(f"Could not write layout PNG: {exc}")
                    st.session_state["layout_spec_json"] = json.dumps(
                        asdict(spec), indent=2, sort_keys=True
                    )
        except Exception as exc:
            st.error(f"Layout generation failed: {exc}")

    cached = layout_results.get(style_id) or {}
    layout_png = cached.get("png") or st.session_state.get("layout_png_bytes")
    layout_svg = cached.get("svg") or st.session_state.get("layout_svg_bytes")
    if layout_png or layout_svg:
        st.subheader("Preview")
        if layout_png:
            st.image(layout_png, use_container_width=True)
        else:
            st.components.v1.html(layout_svg.decode("utf-8"), height=640, scrolling=True)

        st.subheader("Configuration Summary")
        pcs_counts = ac_output.get("pcs_count_by_block")
        if isinstance(pcs_counts, list) and pcs_counts:
            pcs_count = pcs_counts[block_index - 1] if block_index - 1 < len(pcs_counts) else pcs_counts[0]
        else:
            pcs_count = _safe_int(
                ac_output.get("pcs_count_per_ac_block") or ac_output.get("pcs_per_block"), 0
            )
        mv_text = f"{mv_kv:.1f} kV" if isinstance(mv_kv, (int, float)) and mv_kv > 0 else "TBD"
        lv_text = f"{lv_v:.0f} V" if isinstance(lv_v, (int, float)) and lv_v > 0 else "TBD"
        tr_text = f"{transformer_mva:.1f} MVA" if transformer_mva > 0 else "TBD"
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("DC Blocks (group)", block_dc_count or "TBD")
        s2.metric("PCS Count", pcs_count or "TBD")
        s3.metric("MV/LV", f"{mv_text} / {lv_text}")
        s4.metric("Transformer", tr_text)

        st.subheader("Downloads")
        if st.session_state.get("layout_spec_json"):
            st.download_button(
                "Download layout_spec.json",
                st.session_state.get("layout_spec_json"),
                "layout_spec.json",
                "application/json",
            )
        if layout_svg:
            st.download_button(
                "Download layout_block.svg",
                layout_svg,
                "layout_block.svg",
                "image/svg+xml",
            )
        if layout_png:
            st.download_button(
                "Download layout_block.png",
                layout_png,
                "layout_block.png",
                "image/png",
            )
