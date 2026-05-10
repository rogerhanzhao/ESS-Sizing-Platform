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

"""
AC SIZING V2 - DC block based recommendation engine.
Prioritizes 1:1, 1:2, and 1:4 ratio options.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from calb_sizing_tool.common.nameplate import get_standard_container_mwh
from calb_sizing_tool.models import DCBlockResult
from calb_sizing_tool.reporting.export_docx import make_report_filename
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1
from calb_sizing_tool.services.ac_sizing_service import (
    build_dc_allocation_plan,
    evaluate_ac_sizing_feasibility,
    generate_ac_sizing_options,
    select_ac_block_container_type,
    suggest_pcs_count_and_rating,
)
from calb_sizing_tool.services.sld_data_source_service import persist_ac_runtime_snapshot
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import bump_run_id_ac, get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state, set_run_time
from calb_sizing_tool.state.workspace_state import get_workspace_context, navigate_to


def _format_float(val, decimals=2) -> str:
    try:
        v = float(val or 0)
        return f"{v:.{decimals}f}"
    except Exception:
        return str(val)


def _resolve_mv_kv(stage13_output: dict, ac_inputs: dict) -> float:
    candidates = (
        stage13_output.get("poi_nominal_voltage_kv") if isinstance(stage13_output, dict) else None,
        st.session_state.get("poi_nominal_voltage_kv"),
        ac_inputs.get("grid_kv") if isinstance(ac_inputs, dict) else None,
        ac_inputs.get("mv_kv") if isinstance(ac_inputs, dict) else None,
        st.session_state.get("grid_kv"),
    )
    for value in candidates:
        if value is None:
            continue
        try:
            parsed = float(value)
        except Exception:
            continue
        if parsed > 0:
            return parsed
    return 33.0


def _ac_block_grouping_label(ratio: str) -> str:
    parts = str(ratio or "").split(":")
    if len(parts) == 2 and parts[0] == "1":
        return f"1 AC Block : {parts[1]} DC Block{'s' if parts[1] != '1' else ''}"
    return str(ratio or "-")


def _ac_block_grouping_note(selected_option, dc_blocks_total: int) -> str:
    dc_total = max(0, int(dc_blocks_total or 0))
    ac_count = max(0, int(getattr(selected_option, "ac_block_count", 0) or 0))
    distribution = ", ".join(str(v) for v in getattr(selected_option, "dc_blocks_per_ac", [])[:6])
    if len(getattr(selected_option, "dc_blocks_per_ac", [])) > 6:
        distribution += ", ..."
    basis = _ac_block_grouping_label(getattr(selected_option, "ratio", ""))
    if ac_count <= 0:
        return f"Grouping basis: {basis}. Run DC sizing first to calculate AC Block count."
    return (
        f"Grouping basis: {basis}. "
        f"{dc_total} DC Blocks are allocated into {ac_count} AC Blocks "
        f"(DC Blocks per AC Block: {distribution})."
    )


def show():
    """AC SIZING V2 main entrypoint."""
    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()
    dc_results = state.dc_results
    ac_inputs = state.ac_inputs
    ac_results = state.ac_results
    workspace = get_workspace_context()

    from calb_sizing_tool.ui._ui import compact_note, page_header, section_header, workspace_status_bar
    page_header("AC Sizing", "PCS & AC Block Configuration")
    workspace_status_bar(
        [
            ("Project", workspace.get("project_name") or "None"),
            ("Case", workspace.get("case_name") or "None"),
            ("Run", workspace.get("run_id") or state.dc_results.get("last_run_id") or "None"),
        ]
    )

    # ========== STEP 1: Dependency & DC Summary ==========
    dc_data = st.session_state.get("dc_result_summary") or dc_results.get("dc_result_summary")
    stage13_output = st.session_state.get("stage13_output") or dc_results.get("stage13_output") or {}

    if not dc_data:
        st.warning("DC sizing results not found.")
        st.info("Please run DC sizing first to determine DC Block count and capacity.")
        return

    dc_container_count = int(dc_data.get("container_count", 0) or 0)
    dc_cabinet_count = int(dc_data.get("cabinet_count", 0) or 0)
    dc_total_blocks_hint = int(dc_data.get("total_blocks", 0) or 0)
    dc_total_mwh_hint = float(dc_data.get("mwh", 0.0) or 0.0)

    mv_kv_value = _resolve_mv_kv(stage13_output, ac_inputs)
    st.session_state["grid_kv"] = mv_kv_value
    st.session_state["poi_nominal_voltage_kv"] = mv_kv_value
    ac_inputs["grid_kv"] = mv_kv_value
    ac_inputs["mv_kv"] = mv_kv_value

    try:
        dc_model = dc_data.get("dc_block")
        if not dc_model:
            dc_model = DCBlockResult(
                block_id="DC-Fallback",
                capacity_mwh=get_standard_container_mwh(),
                count=int(dc_data.get("container_count", 0)),
                voltage_v=1200,
            )

        # Key data from DC sizing
        dc_blocks_total = int(getattr(dc_model, "count", 0) or 0)
        if dc_total_blocks_hint > 0:
            dc_blocks_total = dc_total_blocks_hint
        dc_block_mwh = float(
            getattr(dc_model, "capacity_mwh", get_standard_container_mwh()) or get_standard_container_mwh()
        )
        if dc_total_mwh_hint > 0 and dc_blocks_total > 0:
            dc_block_mwh = dc_total_mwh_hint / dc_blocks_total
        target_mw = float(dc_data.get("target_mw", stage13_output.get("poi_power_req_mw", 10.0)))
        target_mwh = float(dc_data.get("mwh", stage13_output.get("poi_energy_req_mwh", 0.0)))

    except Exception as exc:
        st.error(f"Data structure mismatch: {exc}")
        return

    project_name = (
        st.session_state.get("project_name")
        or ac_inputs.get("project_name")
        or stage13_output.get("project_name")
        or "CALB ESS Project"
    )
    st.session_state["project_name"] = project_name

    total_energy_mwh = dc_total_mwh_hint if dc_total_mwh_hint > 0 else dc_blocks_total * dc_block_mwh

    # ========== Display DC System Summary ==========
    with st.container(border=True):
        section_header("DC Sizing Snapshot", "Locked input basis from the active DC sizing result.")
        col1, col2, col3, col4 = st.columns(4)
        if dc_cabinet_count > 0:
            col1.metric("DC Blocks", f"{dc_blocks_total} total (C{dc_container_count}+B{dc_cabinet_count})")
        else:
            col1.metric("DC Blocks", f"{dc_blocks_total} x 20ft")
        col2.metric("DC Capacity", f"{total_energy_mwh:.1f} MWh")
        col3.metric("POI Power Req.", f"{target_mw:.1f} MW")
        col4.metric("POI Energy Req.", f"{target_mwh:.0f} MWh")

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

    # ========== STEP 2: Generate Options & Auto-select Best ==========
    with st.container(border=True):
        section_header(
            "AC Block Grouping",
            "Select how DC Blocks are grouped under AC Blocks. This is separate from PCS count and rating.",
            eyebrow="Step 1",
        )

        options = generate_ac_sizing_options(dc_blocks_total, target_mw, target_mwh, dc_block_mwh)

        ratio_choices = [opt.ratio for opt in options]
        recommended_option = next((opt for opt in options if opt.is_recommended), None) or options[1]
        saved_ratio = st.session_state.get("selected_ac_block_grouping") or st.session_state.get("selected_ac_ratio")
        default_ratio = saved_ratio if saved_ratio in ratio_choices else recommended_option.ratio

        choice_ratio = st.segmented_control(
            "DC Blocks per AC Block",
            ratio_choices,
            default=default_ratio,
            format_func=_ac_block_grouping_label,
            key="selected_ac_block_grouping",
            width="stretch",
        ) or default_ratio
        selected_option = next((opt for opt in options if opt.ratio == choice_ratio), recommended_option)
        st.session_state["selected_ac_ratio"] = selected_option.ratio

        compact_note(_ac_block_grouping_note(selected_option, dc_blocks_total))

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

    # ========== STEP 3: Configure PCS for Selected Ratio ==========
    if selected_option:
        with st.container(border=True):
            section_header(
                "PCS Configuration per AC Block",
                "Choose PCS count and PCS rating inside each AC Block. This does not change the AC/DC block grouping.",
                eyebrow="Step 2",
            )
            compact_note(f"Selected AC/DC block grouping: {_ac_block_grouping_label(selected_option.ratio)}.")

            with st.form("ac_config_form"):
                # PCS rating selection from recommendations
                pcs_options = [f"{rec.readable}" for rec in selected_option.pcs_recommendations]
                pcs_options.append("Custom PCS Rating...")

                pcs_choice = st.selectbox(
                    "Select PCS Configuration",
                    range(len(pcs_options)),
                    format_func=lambda i: pcs_options[i],
                    help="Select from recommended configurations or enter custom PCS rating",
                )

                if pcs_choice < len(selected_option.pcs_recommendations):
                    chosen_rec = selected_option.pcs_recommendations[pcs_choice]
                    pcs_per_ac = chosen_rec.pcs_count
                    pcs_kw = chosen_rec.pcs_kw
                    compact_note(f"Selected PCS configuration: {pcs_per_ac} x {pcs_kw} kW.")
                else:
                    custom_col1, custom_col2 = st.columns(2)
                    pcs_per_ac = custom_col1.number_input(
                        "PCS Count per AC Block",
                        min_value=1,
                        max_value=6,
                        value=2,
                        step=1,
                        key="custom_pcs_count",
                    )
                    pcs_kw = custom_col2.number_input(
                        "PCS Rating (kW)",
                        min_value=1000,
                        max_value=5000,
                        value=1500,
                        step=100,
                        key="custom_pcs_kw",
                    )

                # Container size info - based on single AC block size
                single_block_ac_power = pcs_per_ac * pcs_kw / 1000
                auto_container = select_ac_block_container_type(single_block_ac_power, pcs_per_ac)
                compact_note(
                    f"AC Block Container: {auto_container} "
                    f"(single block {single_block_ac_power:.2f} MW, "
                    f"total AC {selected_option.ac_block_count * single_block_ac_power:.2f} MW)."
                )

                submitted = st.form_submit_button("Run AC Sizing", use_container_width=True)

        # ========== STEP 4: Calculation & Validation ==========
        if submitted:
            bump_run_id_ac()
            ac_run_id = project_state.get("ac", {}).get("run_id")

            num_blocks = selected_option.ac_block_count
            pcs_per_block = pcs_per_ac
            block_size_mw = pcs_per_block * pcs_kw / 1000.0
            total_ac_mw = num_blocks * block_size_mw
            overhead = total_ac_mw - target_mw

            total_energy = total_energy_mwh
            errors, warnings = evaluate_ac_sizing_feasibility(
                total_energy_mwh=total_energy,
                target_energy_mwh=target_mwh,
                total_ac_mw=total_ac_mw,
                target_power_mw=target_mw,
            )

            if errors:
                for err in errors:
                    st.error(err)
                st.stop()

            if warnings:
                with st.expander("Warnings"):
                    for warn in warnings:
                        st.warning(warn)

            # ========== Results Summary ==========
            st.success("AC Configuration Complete!")
            st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("AC Blocks", num_blocks)
            col2.metric("PCS per Block", pcs_per_block)
            col3.metric("AC Power per Block", f"{block_size_mw:.2f} MW")
            col4.metric("Total AC Power", f"{total_ac_mw:.2f} MW")

            st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
            section_header("DC Allocation", eyebrow="Detail")
            if dc_cabinet_count > 0:
                _dc_block_str = f"{dc_blocks_total} (C{dc_container_count}+B{dc_cabinet_count})"
            else:
                _dc_block_str = f"{dc_blocks_total} × 20ft"
            _dc1, _dc2, _dc3 = st.columns(3)
            _dc1.metric("DC Blocks", _dc_block_str)
            _dc2.metric("DC per AC Block (avg)", f"{dc_blocks_total / num_blocks:.1f}")
            _dc3.metric("Total DC Energy", f"{total_energy:.1f} MWh")
            compact_note(
                f"Container type: {select_ac_block_container_type(block_size_mw, pcs_per_block)} per AC Block."
            )

            # --- DETAILED DC ALLOCATION ---
            dc_allocation_plan = build_dc_allocation_plan(dc_blocks_total, num_blocks, pcs_per_block)
            dc_blocks_per_ac_block_list = [int(plan["dc_blocks_total"]) for plan in dc_allocation_plan]

            mv_kv = float(mv_kv_value or 33.0)
            lv_v = float(st.session_state.get("pcs_lv_v", 690.0))
            transformer_mva = block_size_mw / 0.9 if block_size_mw > 0 else 0.0
            source_run_id = (
                workspace.get("run_id")
                or dc_results.get("last_run_id")
                or project_state.get("dc", {}).get("run_id")
            )
            # Authoritative AC->SLD contract fields. Downstream SLD logic must normalize
            # through the dedicated adapter instead of re-guessing aliases in-place.
            ac_output = {
                "project_name": project_name,
                "selected_ratio": selected_option.ratio,
                "ac_block_grouping_ratio": selected_option.ratio,
                "ac_block_grouping_label": _ac_block_grouping_label(selected_option.ratio),
                "num_blocks": num_blocks,
                "pcs_per_block": pcs_per_block,
                "pcs_count_by_block": [pcs_per_block for _ in range(num_blocks)],
                "pcs_kw": pcs_kw,
                "pcs_rating_kw_each": pcs_kw,
                "block_size_mw": block_size_mw,
                "total_ac_mw": total_ac_mw,
                "overhead_mw": overhead,
                "dc_blocks_per_ac": selected_option.dc_blocks_per_ac,
                "dc_blocks_total_by_block": list(dc_blocks_per_ac_block_list),
                "dc_blocks_per_feeder_by_block": [
                    list(plan.get("feeder_allocations", [])) for plan in dc_allocation_plan
                ],
                "dc_allocation_plan": dc_allocation_plan,
                "dc_blocks_total": dc_blocks_total,
                "dc_total_mwh": total_energy,
                "poi_power_mw": target_mw,
                "poi_energy_mwh": target_mwh,
                "grid_kv": mv_kv,
                "mv_kv": mv_kv,
                "mv_voltage_kv": mv_kv,
                "lv_v": lv_v,
                "lv_voltage_v": lv_v,
                "inverter_lv_v": lv_v,
                "transformer_mva": transformer_mva,
                "transformer_count": num_blocks,
                "pcs_count_total": num_blocks * pcs_per_block,
                "source_project_id": workspace.get("project_id"),
                "source_project_code": workspace.get("project_code"),
                "source_project_name": workspace.get("project_name") or project_name,
                "source_case_id": workspace.get("case_id"),
                "source_case_code": workspace.get("case_code"),
                "source_case_name": workspace.get("case_name"),
                "source_run_id": source_run_id,
                "source_ac_run_id": ac_run_id,
                "source_poi_nominal_voltage_kv": mv_kv,
                "source_poi_frequency_hz": stage13_output.get("poi_frequency_hz"),
            }

            st.session_state["ac_output"] = ac_output
            ac_results.update(ac_output)
            set_run_time("ac_results")
            _auth_ctx = get_auth_context()
            if _auth_ctx and not _auth_ctx.is_guest:
                persist_ac_runtime_snapshot(
                    run_id=source_run_id,
                    ac_inputs=ac_inputs,
                    ac_output=ac_output,
                    results={},
                    source_ref="ac_view",
                )
                st.info("Configuration saved.")
            else:
                st.success("AC sizing complete (guest mode — session only).")

            st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
            section_header("Next Steps", eyebrow="Continue")
            _is_guest_cta = _auth_ctx and _auth_ctx.is_guest
            if _is_guest_cta:
                _cta1, _cta2 = st.columns(2)
                if _cta1.button("Single Line Diagram →", use_container_width=True, key="ac_cta_sld"):
                    navigate_to("Single Line Diagram")
                    st.rerun()
                if _cta2.button("Site Layout →", use_container_width=True, key="ac_cta_layout"):
                    navigate_to("Site Layout")
                    st.rerun()
            else:
                _cta1, _cta2, _cta3 = st.columns(3)
                if _cta1.button("Single Line Diagram →", use_container_width=True, key="ac_cta_sld"):
                    navigate_to("Single Line Diagram")
                    st.rerun()
                if _cta2.button("Site Layout →", use_container_width=True, key="ac_cta_layout"):
                    navigate_to("Site Layout")
                    st.rerun()
                if _cta3.button("Report Export →", use_container_width=True, key="ac_cta_report"):
                    navigate_to("Report Export")
                    st.rerun()
