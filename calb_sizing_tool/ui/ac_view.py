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
Supports 1:1, 1:2, 1:4, and 1:8 grouping options.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from calb_sizing_tool.common.nameplate import get_standard_container_mwh
from calb_sizing_tool.models import DCBlockResult
from calb_sizing_tool.reporting.export_docx import make_report_filename
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1
from calb_sizing_tool.services.ac_sizing_service import (
    build_simplified_ac_block_models,
    build_dc_allocation_plan,
    dc_grouping_has_feeder_capacity,
    evaluate_ac_sizing_feasibility,
    generate_ac_sizing_options,
    minimum_dc_blocks_for_pcs_feeders,
    select_ac_block_container_type,
)
from calb_sizing_tool.services.ac_mixed_station import (
    build_mixed_dc_allocation_plan,
    default_uniform_rows,
    is_mixed_station,
    summarize_ac_block_rows,
    validate_ac_block_rows,
)
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.services.ac_run_service import persist_ac_run
from calb_sizing_tool.services.sld_data_source_service import persist_ac_runtime_snapshot, resolve_preferred_ac_snapshot
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import bump_run_id_ac, get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state, set_run_time
from calb_sizing_tool.state.workspace_state import get_workspace_context

# Transformer topology is now selected explicitly. A two-winding transformer
# can serve any supported PCS count on one common LV busbar; a three-winding
# transformer balances the PCS feeders across two independent LV secondaries.
_CUSTOM_PCS_COUNT_CHOICES = (1, 2, 3, 4, 5, 6, 8)
_TRANSFORMER_TOPOLOGIES = ("two_winding", "three_winding")
_TOPOLOGY_CONFIRMATION = "confirmed_by_user"


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


def _positive_float(*values, default: float) -> float:
    """First positive numeric value, keeping legacy state as a fallback only."""
    for value in values:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return float(default)


def _resolve_authoritative_poi_requirements(
    stage13_output: dict | None,
    dc_data: dict | None,
) -> tuple[float, float]:
    """Resolve POI power/energy from the Stage 1/3 handoff before legacy UI data.

    ``dc_data["mwh"]`` is retained only as a compatibility fallback.  It must
    never outrank the Stage 1/3 POI value because legacy callers can use ``mwh``
    for a DC-side quantity.
    """
    stage13 = stage13_output if isinstance(stage13_output, dict) else {}
    dc_summary = dc_data if isinstance(dc_data, dict) else {}
    poi_power_mw = _positive_float(
        stage13.get("poi_power_req_mw"),
        dc_summary.get("poi_power_req_mw"),
        dc_summary.get("target_mw"),
        default=10.0,
    )
    poi_energy_mwh = _positive_float(
        stage13.get("poi_energy_req_mwh"),
        dc_summary.get("poi_energy_mwh"),
        dc_summary.get("target_mwh"),
        dc_summary.get("mwh"),
        default=0.0,
    )
    return poi_power_mw, poi_energy_mwh


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


def _snapshot_output_matches_run(ac_output: dict | None, run_id: str | None) -> bool:
    if not isinstance(ac_output, dict) or not ac_output:
        return False
    expected = str(run_id or "").strip()
    if not expected:
        return True
    return str(ac_output.get("source_run_id") or "").strip() == expected


def _hydrate_ac_runtime_snapshot(
    snapshot: AcSnapshot,
    *,
    ac_inputs: dict,
    ac_results: dict,
    project_state: dict,
) -> None:
    if isinstance(snapshot.inputs, dict):
        ac_inputs.update(snapshot.inputs)
    if isinstance(snapshot.output, dict):
        ac_output = dict(snapshot.output)
        st.session_state["ac_output"] = ac_output
        ac_results.update(ac_output)
        project_state["ac_results"] = ac_output
        ac_state = project_state.setdefault("ac", {})
        ac_state["run_id"] = ac_output.get("source_ac_run_id")
        ac_state["results"] = ac_output


def _render_saved_ac_snapshot(ac_output: dict, *, section_header) -> None:
    with st.container(border=True):
        section_header("Saved AC Runtime Snapshot", "Current AC configuration restored from persisted run data.")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("AC Blocks", int(ac_output.get("num_blocks") or 0))
        col2.metric("PCS per Block", int(ac_output.get("pcs_per_block") or 0))
        col3.metric("PCS Rating", f"{_format_float(ac_output.get('pcs_kw'), 0)} kW")
        col4.metric("Total AC Power", f"{_format_float(ac_output.get('total_ac_mw'), 2)} MW")
        model_name = ac_output.get("ac_block_model_name") or ac_output.get("ac_block_template_id")
        if model_name:
            st.caption(f"Saved AC Block model: {model_name}")


def _saved_pcs_choice_index(ac_output: dict | None, recommendations: list) -> int:
    if not isinstance(ac_output, dict):
        return 0
    try:
        saved_pcs_per_block = int(ac_output.get("pcs_per_block") or 0)
        saved_pcs_kw = float(ac_output.get("pcs_kw") or ac_output.get("pcs_rating_kw_each") or 0)
    except Exception:
        return 0
    if saved_pcs_per_block <= 0 or saved_pcs_kw <= 0:
        return 0
    for idx, rec in enumerate(recommendations):
        if int(getattr(rec, "pcs_count", 0) or 0) != saved_pcs_per_block:
            continue
        try:
            rec_pcs_kw = float(getattr(rec, "pcs_kw", 0) or 0)
        except Exception:
            continue
        if abs(rec_pcs_kw - saved_pcs_kw) < 1e-6:
            return idx
    return 0


def _saved_confirmed_transformer_topology(ac_output: dict | None) -> str | None:
    """Return only a topology that an operator explicitly confirmed.

    Earlier generic AC runs silently selected three windings for more than two
    PCS.  That legacy default is not engineering evidence and must not be
    restored as though it were an owner/OEM-confirmed transformer design.
    """
    if not isinstance(ac_output, dict):
        return None
    topology = str(ac_output.get("transformer_topology") or "").strip()
    confirmation = str(ac_output.get("transformer_topology_confirmation") or "").strip()
    if topology in _TRANSFORMER_TOPOLOGIES and confirmation == _TOPOLOGY_CONFIRMATION:
        return topology
    return None


def _saved_ac_block_model_choice_index(
    ac_output: dict | None,
    model_options: list,
    *,
    custom_index: int | None = None,
) -> int:
    if not isinstance(ac_output, dict):
        return 0

    saved_code = str(ac_output.get("ac_block_model_code") or "").strip()
    if saved_code:
        for idx, model in enumerate(model_options):
            if str(getattr(model, "model_code", "")).strip() == saved_code:
                return idx

    try:
        saved_pcs_per_block = int(ac_output.get("pcs_per_block") or 0)
        saved_pcs_kw = float(ac_output.get("pcs_kw") or ac_output.get("pcs_rating_kw_each") or 0)
    except Exception:
        return 0
    if saved_pcs_per_block <= 0 or saved_pcs_kw <= 0:
        return 0

    for idx, model in enumerate(model_options):
        if int(getattr(model, "pcs_count", 0) or 0) != saved_pcs_per_block:
            continue
        try:
            model_pcs_kw = float(getattr(model, "pcs_kw", 0) or 0)
        except Exception:
            continue
        if abs(model_pcs_kw - saved_pcs_kw) < 1e-6:
            return idx

    if custom_index is not None:
        return custom_index
    return 0


def show():
    """AC SIZING V2 main entrypoint."""
    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()
    dc_results = state.dc_results
    ac_inputs = state.ac_inputs
    ac_results = state.ac_results
    workspace = get_workspace_context()
    active_run_id = (
        workspace.get("run_id")
        or state.dc_results.get("last_run_id")
        or st.session_state.get("dc_last_run_id")
        or project_state.get("dc", {}).get("run_id")
    )

    ac_resolution = resolve_preferred_ac_snapshot(
        active_run_id,
        project_state=project_state,
        shared_state=state,
        session_state=st.session_state,
    )
    if ac_resolution.source == "persisted_run_snapshot" and ac_resolution.snapshot is not None:
        _hydrate_ac_runtime_snapshot(
            ac_resolution.snapshot,
            ac_inputs=ac_inputs,
            ac_results=ac_results,
            project_state=project_state,
        )

    from calb_sizing_tool.ui._ui import (
        compact_note,
        page_header,
        render_pipeline_next_steps,
        render_static_table,
        section_header,
        workspace_status_bar,
    )
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
        target_mw, target_mwh = _resolve_authoritative_poi_requirements(
            stage13_output, dc_data
        )

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
        if dc_cabinet_count > 0:
            compact_note(
                f"DC side used a hybrid packaging: {dc_container_count} container(s) + "
                f"{dc_cabinet_count} cabinet(s) as the DC tail. The AC mixed station (in the "
                "AC configuration must be selected from the same grouping and PCS flow; "
                "the DC tail does not select a fixed AC product."
            )

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

    saved_ac_output = st.session_state.get("ac_output") if isinstance(st.session_state.get("ac_output"), dict) else ac_results
    if _snapshot_output_matches_run(saved_ac_output, active_run_id):
        _render_saved_ac_snapshot(saved_ac_output, section_header=section_header)
        st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

    # Historical governed product helpers remain available for reading old persisted
    # runs. They are deliberately not exposed in this UI: AC sizing now has one
    # trunk where grouping and PCS architecture are selected before any optional
    # catalogue binding.

    # ================= AC SIZING (auto-recommend trunk) =================
    # The single duration-aware sizing flow: POI power minus losses → AC:DC ratio →
    # PCS count × rating (auto-recommended for the project duration) → transformer
    # windings → power/energy validation, all manually adjustable, any duration.
    st.caption(
        "AC sizing first selects the DC grouping, PCS architecture and transformer topology, "
        "then validates the result against the POI requirement. Catalogue matching is optional "
        "and can only enrich the selected configuration with confirmed nameplate, vector-group "
        "and LV data; it never changes the grouping or PCS selection."
    )

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
        saved_ratio = (
            st.session_state.get("selected_ac_block_grouping")
            or st.session_state.get("selected_ac_ratio")
            or saved_ac_output.get("ac_block_grouping_ratio")
            or saved_ac_output.get("selected_ratio")
        )
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

    # ========== STEP 3: Configure AC Block model for Selected Ratio ==========
    if selected_option:
        with st.container(border=True):
            section_header(
                "AC Block Model per AC Block",
                "Choose the PCS architecture for one AC Block. This sets PCS count, PCS rating, and container basis.",
                eyebrow="Step 2",
            )
            compact_note(
                f"Selected AC/DC block grouping: {_ac_block_grouping_label(selected_option.ratio)}. "
                "AC Block quantity comes from Step 1; the model below defines one AC Block only."
            )
            model_options = build_simplified_ac_block_models(
                selected_option.pcs_recommendations,
                grouping_ratio=selected_option.ratio,
            )

            # Model selection lives outside any st.form so a change reruns
            # immediately: picking "Custom..." must reveal the PCS inputs
            # before anything is executed (FT-20260714-12).
            model_labels = [model.readable for model in model_options]
            model_labels.append("Custom AC Block Model...")
            model_widget_key = f"ac_block_model_choice_{selected_option.ratio.replace(':', 'to')}"

            model_choice = st.selectbox(
                "Select AC Block Model",
                range(len(model_labels)),
                index=_saved_ac_block_model_choice_index(
                    saved_ac_output,
                    model_options,
                    custom_index=len(model_options),
                ),
                format_func=lambda i: model_labels[i],
                key=model_widget_key,
                help="Sizing candidate derived from PCS count and rating. It is not a product record and does not lock a catalogue choice.",
            )

            if model_choice < len(model_options):
                chosen_model = model_options[model_choice]
                pcs_per_ac = int(chosen_model.pcs_count)
                pcs_kw = int(chosen_model.pcs_kw)
                single_block_ac_power = float(chosen_model.block_size_mw)
                auto_container = chosen_model.container_type
                ac_block_model_code = chosen_model.model_code
                ac_block_model_name = chosen_model.display_name
                ac_block_model_source = chosen_model.source
                compact_note(f"Selected AC Block model: {chosen_model.display_name}.")
            else:
                custom_col1, custom_col2 = st.columns(2)
                if st.session_state.get("custom_pcs_count") not in _CUSTOM_PCS_COUNT_CHOICES:
                    st.session_state.pop("custom_pcs_count", None)
                pcs_per_ac = int(
                    custom_col1.selectbox(
                        "PCS Count per AC Block",
                        _CUSTOM_PCS_COUNT_CHOICES,
                        index=0,
                        key="custom_pcs_count",
                        help="PCS count is independent of transformer topology. The LV busbar arrangement is selected below.",
                    )
                )
                pcs_kw = int(
                    custom_col2.number_input(
                        "PCS Rating (kW)",
                        min_value=1000,
                        max_value=5000,
                        value=1500,
                        step=100,
                        key="custom_pcs_kw",
                    )
                )
                single_block_ac_power = pcs_per_ac * pcs_kw / 1000.0
                auto_container = select_ac_block_container_type(single_block_ac_power, pcs_per_ac)
                ac_block_model_code = f"CUSTOM-{pcs_per_ac}X{pcs_kw}KW-{auto_container.upper()}"
                ac_block_model_name = (
                    f"Custom {single_block_ac_power:.2f} MW AC Block - "
                    f"{pcs_per_ac} x {pcs_kw} kW PCS - {auto_container}"
                )
                ac_block_model_source = "custom"

            electrical_col1, electrical_col2 = st.columns(2)
            saved_transformer_topology = _saved_confirmed_transformer_topology(saved_ac_output)
            topology_options = ("__confirm_actual_topology__", *_TRANSFORMER_TOPOLOGIES)
            topology_widget_key = "ac_transformer_topology"
            # One-time migration for a live Streamlit session: clear the old
            # widget value that was once auto-selected from PCS count.  Values
            # chosen after this gate remain intact across reruns.
            confirmation_gate_key = "ac_transformer_topology_confirmation_gate_v1"
            if saved_transformer_topology is None and not st.session_state.get(confirmation_gate_key):
                st.session_state[topology_widget_key] = "__confirm_actual_topology__"
                st.session_state[confirmation_gate_key] = True
            transformer_topology_choice = electrical_col1.selectbox(
                "Transformer LV Topology",
                topology_options,
                index=(
                    topology_options.index(saved_transformer_topology)
                    if saved_transformer_topology in _TRANSFORMER_TOPOLOGIES
                    else 0
                ),
                format_func=lambda value: (
                    "Select and confirm the actual transformer secondary arrangement"
                    if value == "__confirm_actual_topology__"
                    else "2-winding — one common LV busbar for all PCS"
                    if value == "two_winding"
                    else "3-winding — two independent LV secondary busbars"
                ),
                key=topology_widget_key,
                help=(
                    "Select the actual transformer secondary arrangement from the OEM/product design. "
                    "It is never inferred from PCS count; legacy automatic choices must be reconfirmed."
                ),
            )
            transformer_topology = (
                transformer_topology_choice
                if transformer_topology_choice in _TRANSFORMER_TOPOLOGIES
                else None
            )
            if transformer_topology is None:
                electrical_col1.info(
                    "AC sizing cannot be issued until the transformer LV topology is explicitly confirmed."
                )
            elif transformer_topology == "three_winding":
                electrical_col1.warning(
                    "Three-winding requires an OEM-declared vector group with two LV tokens. "
                    "A two-winding vector such as Dyn11 is not valid here."
                )
            saved_dc_outputs = int((saved_ac_output or {}).get("dc_block_output_circuits") or 2)
            if saved_dc_outputs not in (1, 2):
                saved_dc_outputs = 2
            dc_block_output_circuits = int(
                electrical_col2.selectbox(
                    "DC Block Output Circuits",
                    (1, 2),
                    index=(0 if saved_dc_outputs == 1 else 1),
                    format_func=lambda value: f"{value} protected PCS branch{'es' if value > 1 else ''} per DC Block",
                    key="ac_dc_block_output_circuits",
                    help="Default 2 for the 5 MWh DC Block. Select 1 only for a confirmed single-output product.",
                )
            )
            if transformer_topology:
                compact_note(
                    "Electrical topology: "
                    + (
                        "one common LV busbar"
                        if transformer_topology == "two_winding"
                        else "two independent LV secondary busbars"
                    )
                    + f"; each DC Block has {dc_block_output_circuits} protected PCS output branch(es)."
                )
            _minimum_dc_blocks = minimum_dc_blocks_for_pcs_feeders(
                pcs_per_ac,
                dc_block_output_circuits=dc_block_output_circuits,
            )
            if not dc_grouping_has_feeder_capacity(
                selected_option.dc_blocks_per_ac,
                pcs_per_ac,
                dc_block_output_circuits=dc_block_output_circuits,
            ):
                st.warning(
                    "Physical feeder check: this PCS selection needs at least "
                    f"{_minimum_dc_blocks} DC Blocks in every AC Block, but the selected "
                    f"grouping contains a {min(selected_option.dc_blocks_per_ac, default=0)}-DC tail. "
                    "Run is blocked until the PCS count or grouping is adjusted."
                )
            elif (
                selected_option.ratio == "1:8"
                and pcs_per_ac == 8
                and pcs_kw == 1250
                and transformer_topology == "three_winding"
                and all(dc_count == 8 for dc_count in selected_option.dc_blocks_per_ac)
            ):
                compact_note(
                    "Exact 1:8 / 8 x 1250 kW / 3-winding selection: downstream concept "
                    "layout and report will use the owner-confirmed central 40 ft, bilateral 4+4 arrangement."
                )

            # Container size info - based on single AC block size
            compact_note(
                f"AC Block Container: {auto_container} "
                f"(single block {single_block_ac_power:.2f} MW, "
                f"total AC {selected_option.ac_block_count * single_block_ac_power:.2f} MW)."
            )

            # Catalogue matching happens only after grouping / PCS / transformer
            # topology are chosen. It may enrich the selected configuration, but
            # it cannot select or rewrite those sizing choices.
            bound_ac_product = None
            try:
                from calb_sizing_tool.services.ac_block_product_match import (
                    match_ac_block_products,
                    preferred_catalogue_architecture,
                )
                _catalogue_preference = preferred_catalogue_architecture(selected_option.ratio)
                _matches = match_ac_block_products(
                    pcs_per_ac,
                    pcs_kw,
                    grouping_ratio=selected_option.ratio,
                    transformer_topology=transformer_topology,
                )
            except Exception:
                _catalogue_preference = None
                _matches = []
            if _catalogue_preference:
                compact_note(
                    "Catalogue comparison preference: "
                    + str(_catalogue_preference["label"])
                    + ". "
                    + str(_catalogue_preference["reason"])
                )
            if _matches:
                _labels = ["(none — transformer estimated as MW ÷ PF)"] + [
                    f"{m.get('vendor') or ''} · {m['block_code']} · "
                    f"{(m.get('transformer_kva') or 0) / 1000:.2f} MVA"
                    + (f" · {m['transformer_vector_group']}" if m.get("transformer_vector_group") else "")
                    + (" · preferred" if m.get("is_preferred_architecture") else "")
                    + (" · engineering data partial" if m.get("engineering_data_status") == "partial" else "")
                    for m in _matches
                ]
                _bind_choice = st.selectbox(
                    "Bind catalogue product (optional — confirmed transformer / LV values)",
                    range(len(_labels)),
                    index=0,
                    format_func=lambda i: _labels[i],
                    key=(
                        f"ac_trunk_product_bind_{selected_option.ratio.replace(':', 'to')}_"
                        f"{pcs_per_ac}x{pcs_kw}_{transformer_topology or 'unconfirmed'}"
                    ),
                    help="Only catalogue products matching the selected PCS count, unit rating and "
                    "declared transformer topology are shown. Binding replaces only the transformer "
                    "estimate with real nameplate data; unmatched specs remain valid sizing candidates.",
                )
                bound_ac_product = _matches[_bind_choice - 1] if _bind_choice > 0 else None
            else:
                st.caption(
                    "No compatible catalogue record for this selected PCS/topology combination. "
                    "The sizing candidate remains available with transformer values to be confirmed in Engineering Settings."
                )

            # ===== Optional: mixed AC Block station (manual adjustment) =====
            # Off by default: the clean uniform trunk stays the norm. This is the
            # AC-side counterpart of DC Sizing's "Hybrid Mode" (container + cabinet
            # tail) — a head AC Block plus smaller tail AC Blocks for an uneven DC
            # remainder or a deliberate product mix. Uniform is just the
            # single-model case of the same per-block table, so nothing forks.
            mixed_rows = None
            mixed_valid = None
            st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
            mixed_enabled = st.checkbox(
                "Enable mixed AC Block station (advanced manual adjustment)",
                value=bool(saved_ac_output.get("ac_block_mixed")),
                key=f"ac_mixed_enabled_{selected_option.ratio.replace(':', 'to')}",
                help=(
                    "By default every AC Block uses the single model above. Enable this only "
                    "to cover an uneven DC remainder, or to deliberately mix a smaller tail "
                    "AC Block — the AC-side counterpart of the DC container + cabinet tail."
                ),
            )
            if mixed_enabled:
                st.caption(
                    "Edit any AC Block row to make it different (the head model above pre-fills "
                    "every row). The grouping fixes how many AC Blocks there are; mixing changes "
                    "each block's PCS model and DC Blocks. Keep the DC Blocks assigned equal to the "
                    "DC total, and give each block enough DC Blocks to feed its PCS. Identical rows "
                    "are grouped into head / tail models downstream."
                )
                _mixed_ratio_key = selected_option.ratio.replace(":", "to")
                _saved_rows = saved_ac_output.get("ac_block_rows")
                if (
                    isinstance(_saved_rows, list)
                    and _saved_rows
                    and saved_ac_output.get("ac_block_grouping_ratio") == selected_option.ratio
                ):
                    _seed_rows = [dict(r) for r in _saved_rows]
                else:
                    _seed_rows = default_uniform_rows(
                        selected_option.dc_blocks_per_ac, pcs_per_ac, pcs_kw
                    )
                # Editable per-AC-Block grid built from number_input widgets.
                # st.data_editor/st.dataframe are banned in the UI (PyArrow crash
                # containment, tests/test_ui_table_rendering.py), so the grid is
                # rendered as one widget row per AC Block.
                _hdr = st.columns([1.4, 1.3, 1.6, 1.3])
                _hdr[0].caption("AC Block")
                _hdr[1].caption("PCS count")
                _hdr[2].caption("PCS rating (kW)")
                _hdr[3].caption("DC Blocks")
                mixed_rows = []
                for _i, _seed in enumerate(_seed_rows):
                    _row_cols = st.columns([1.4, 1.3, 1.6, 1.3])
                    _row_cols[0].markdown(f"**{_i + 1}**")
                    _pcs_i = _row_cols[1].number_input(
                        f"PCS count for AC Block {_i + 1}",
                        min_value=1, max_value=8, step=1,
                        value=int(_seed.get("pcs_count") or pcs_per_ac),
                        key=f"ac_mixed_pcs_{_mixed_ratio_key}_{_i}",
                        label_visibility="collapsed",
                    )
                    _kw_i = _row_cols[2].number_input(
                        f"PCS rating for AC Block {_i + 1}",
                        min_value=1000, max_value=5000, step=50,
                        value=int(_seed.get("pcs_kw") or pcs_kw),
                        key=f"ac_mixed_kw_{_mixed_ratio_key}_{_i}",
                        label_visibility="collapsed",
                    )
                    _dc_i = _row_cols[3].number_input(
                        f"DC Blocks for AC Block {_i + 1}",
                        min_value=1, step=1,
                        value=int(_seed.get("dc_blocks") or 1),
                        key=f"ac_mixed_dc_{_mixed_ratio_key}_{_i}",
                        label_visibility="collapsed",
                    )
                    mixed_rows.append(
                        {"pcs_count": int(_pcs_i), "pcs_kw": int(_kw_i), "dc_blocks": int(_dc_i)}
                    )
                mixed_valid = validate_ac_block_rows(
                    mixed_rows,
                    dc_blocks_total,
                    dc_block_output_circuits=dc_block_output_circuits,
                )
                _tally_col1, _tally_col2, _tally_col3 = st.columns(3)
                _tally_col1.metric(
                    "DC Blocks assigned",
                    f"{mixed_valid.total_dc_assigned} / {dc_blocks_total}",
                    delta=(
                        None
                        if mixed_valid.total_dc_assigned == dc_blocks_total
                        else mixed_valid.total_dc_assigned - dc_blocks_total
                    ),
                )
                _tally_col2.metric("AC Blocks", f"{len(mixed_rows)}")
                _tally_col3.metric("Total AC Power", f"{mixed_valid.total_ac_mw:.2f} MW")
                if mixed_valid.ok:
                    _distinct = summarize_ac_block_rows(mixed_rows)
                    if len(_distinct) > 1:
                        _head = next(e for e in _distinct if e["role"] == "Head")
                        _tails = [e for e in _distinct if e["role"] == "Tail"]
                        _tail_txt = ", ".join(
                            f"{e['count']}×{e['block_mw']:.2f} MW ({e['pcs_count']}×{e['pcs_kw']:.0f} kW)"
                            for e in _tails
                        )
                        compact_note(
                            f"Mixed station: head {_head['count']}×{_head['block_mw']:.2f} MW "
                            f"({_head['pcs_count']}×{_head['pcs_kw']:.0f} kW) + tail {_tail_txt}."
                        )
                    else:
                        compact_note(
                            "Table is uniform — every AC Block is identical, so this behaves "
                            "exactly like the standard (non-mixed) station."
                        )
                else:
                    for _msg in mixed_valid.messages:
                        st.warning(_msg)

            submitted = st.button("Run AC Sizing", use_container_width=True, type="primary")

        # ========== STEP 4: Calculation & Validation ==========
        if submitted:
            if transformer_topology not in _TRANSFORMER_TOPOLOGIES:
                st.error(
                    "Confirm the actual transformer LV topology before running AC sizing. "
                    "The system will not infer it from the PCS quantity."
                )
                st.stop()

            # A mixed station replaces the single uniform model with the per-block
            # table; it is pre-validated (feeder capacity + sum-to-total) in the
            # editor, so gate on that instead of the single-grouping feeder check.
            is_mixed_run = bool(mixed_enabled) and is_mixed_station(mixed_rows or [])
            if mixed_enabled and not (mixed_valid and mixed_valid.ok):
                st.error(
                    "Resolve the mixed AC Block station issues listed above before running "
                    "(DC Blocks must sum to the DC total and every AC Block must be feeder-feasible)."
                )
                st.stop()
            if not is_mixed_run:
                minimum_dc_blocks = minimum_dc_blocks_for_pcs_feeders(
                    pcs_per_ac,
                    dc_block_output_circuits=dc_block_output_circuits,
                )
                if not dc_grouping_has_feeder_capacity(
                    selected_option.dc_blocks_per_ac,
                    pcs_per_ac,
                    dc_block_output_circuits=dc_block_output_circuits,
                ):
                    smallest_group = min(selected_option.dc_blocks_per_ac, default=0)
                    st.error(
                        "Selected grouping cannot physically feed every PCS branch: "
                        f"{pcs_per_ac} PCS with {dc_block_output_circuits} protected output circuit(s) "
                        f"per DC Block needs at least {minimum_dc_blocks} DC Blocks in each AC Block, "
                        f"but this grouping includes a {smallest_group}-DC tail. Select a smaller PCS count "
                        "or a grouping without that tail."
                    )
                    st.stop()
            bump_run_id_ac()
            ac_run_id = project_state.get("ac", {}).get("run_id")

            # Station rows drive both the uniform and mixed cases through one path:
            # uniform = one model (however DC Blocks are distributed), mixed = the
            # edited per-block table. The head model provides the representative
            # scalars; the per-block lists carry the true composition.
            station_rows = (
                [dict(r) for r in mixed_rows]
                if is_mixed_run
                else default_uniform_rows(selected_option.dc_blocks_per_ac, pcs_per_ac, pcs_kw)
            )
            ac_block_breakdown = summarize_ac_block_rows(station_rows)
            _head_entry = next(
                (e for e in ac_block_breakdown if e.get("role") == "Head"),
                ac_block_breakdown[0] if ac_block_breakdown else None,
            )

            num_blocks = len(station_rows)
            pcs_per_block = int(_head_entry["pcs_count"]) if _head_entry else pcs_per_ac
            pcs_kw = int(_head_entry["pcs_kw"]) if _head_entry else pcs_kw
            block_size_mw = pcs_per_block * pcs_kw / 1000.0
            total_ac_mw = round(
                sum(int(r["pcs_count"]) * int(r["pcs_kw"]) / 1000.0 for r in station_rows), 3
            )
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
            if is_mixed_run:
                _tail_entries = [e for e in ac_block_breakdown if e.get("role") == "Tail"]
                col2.metric(
                    "AC Block models",
                    f"{len(ac_block_breakdown)}",
                    help="Distinct head + tail AC Block models in this mixed station.",
                )
                col3.metric("Head AC Block", f"{block_size_mw:.2f} MW")
                _tail_summary = " + ".join(
                    f"{e['count']}×{e['block_mw']:.2f} MW" for e in _tail_entries
                )
                col4.metric("Total AC Power", f"{total_ac_mw:.2f} MW", help=f"Tail: {_tail_summary}")
            else:
                col2.metric("PCS per Block", pcs_per_block)
                col3.metric("AC Power per Block", f"{block_size_mw:.2f} MW")
                col4.metric("Total AC Power", f"{total_ac_mw:.2f} MW")
            if is_mixed_run:
                _head_e = _head_entry or {}
                _tail_txt = ", ".join(
                    f"{e['count']}×{e['block_mw']:.2f} MW ({e['pcs_count']}×{e['pcs_kw']:.0f} kW)"
                    for e in ac_block_breakdown
                    if e.get("role") == "Tail"
                )
                compact_note(
                    f"Mixed AC Block station: head {_head_e.get('count')}×"
                    f"{block_size_mw:.2f} MW ({pcs_per_block}×{pcs_kw:.0f} kW) + tail {_tail_txt}. "
                    "The AC-side counterpart of the DC container + cabinet tail."
                )
                st.info(
                    "Concept/draft — this mixed station is a manual engineering adjustment. "
                    "Per-model OEM product and transformer data are not individually confirmed "
                    "(each model's transformer is a MW ÷ PF estimate), and the SLD renders the "
                    "representative Head AC Block fleet only. Tail model(s) are listed in the "
                    "report AC Block schedule (§6.1)."
                )
                if bound_ac_product:
                    st.warning(
                        "Catalogue product binding is disabled for a mixed station: a single "
                        "product matches only the head spec and would mis-attribute its nameplate "
                        "to differing tail blocks. Transformer ratings fall back to MW ÷ PF "
                        "estimates per model."
                    )

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
                f"AC Block model: {ac_block_model_name}. Container type: {auto_container} per AC Block."
            )

            # --- DETAILED DC ALLOCATION ---
            try:
                if is_mixed_run:
                    dc_allocation_plan = build_mixed_dc_allocation_plan(
                        station_rows,
                        dc_block_output_circuits=dc_block_output_circuits,
                    )
                else:
                    dc_allocation_plan = build_dc_allocation_plan(
                        dc_blocks_total,
                        num_blocks,
                        pcs_per_block,
                        dc_block_output_circuits=dc_block_output_circuits,
                    )
            except ValueError as exc:
                st.error(f"Invalid DC-to-PCS electrical topology: {exc}")
                st.stop()
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
                "ac_block_quantity_basis": "dc_block_grouping_ratio",
                "ac_block_model_code": ac_block_model_code,
                "ac_block_model_name": ac_block_model_name,
                "ac_block_model_source": ac_block_model_source,
                "ac_block_container_type": auto_container,
                "ac_block_template_id": f"{pcs_per_block}x{int(round(pcs_kw))}kw",
                "num_blocks": num_blocks,
                "pcs_per_block": pcs_per_block,
                "pcs_count_by_block": [int(r["pcs_count"]) for r in station_rows],
                "pcs_kw": pcs_kw,
                "pcs_power_kw": pcs_kw,
                "pcs_rating_kw_each": pcs_kw,
                "block_size_mw": block_size_mw,
                "total_ac_mw": total_ac_mw,
                "overhead_mw": overhead,
                "dc_blocks_per_ac": [int(r["dc_blocks"]) for r in station_rows],
                "dc_blocks_total_by_block": list(dc_blocks_per_ac_block_list),
                "dc_blocks_per_feeder_by_block": [
                    list(plan.get("feeder_allocations", [])) for plan in dc_allocation_plan
                ],
                "dc_block_connections_by_block": [
                    list(plan.get("dc_block_connections", [])) for plan in dc_allocation_plan
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
                "transformer_topology": transformer_topology,
                "transformer_topology_confirmation": _TOPOLOGY_CONFIRMATION,
                "lv_winding_count": 1 if transformer_topology == "two_winding" else 2,
                "lv_busbar_topology": (
                    "common_single_lv_busbar"
                    if transformer_topology == "two_winding"
                    else "independent_lv_busbars"
                ),
                "dc_block_output_circuits": dc_block_output_circuits,
                "transformer_count": num_blocks,
                "pcs_count_total": sum(int(r["pcs_count"]) for r in station_rows),
                # Mixed AC Block station (head + tail models). Uniform is the
                # single-entry case, so downstream reads one field either way.
                "ac_block_mixed": bool(is_mixed_run),
                "ac_block_rows": [dict(r) for r in station_rows],
                "ac_block_breakdown": ac_block_breakdown,
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

            # This is a concept-layout routing condition, not a standard-product
            # lock. It is available only for a physically homogeneous 1:8 block
            # with the selected 8 x 1250 kW small-PCS / 3-winding architecture.
            if (
                selected_option.ratio == "1:8"
                and pcs_per_block == 8
                and int(pcs_kw) == 1250
                and transformer_topology == "three_winding"
                and all(dc_count == 8 for dc_count in dc_blocks_per_ac_block_list)
            ):
                ac_output.update(
                    {
                        "layout_variant": "central_40ft_bilateral_4plus4",
                        "layout_variant_source": "owner_confirmed_1to8_small_pcs_concept",
                        "dc_field_split": [4, 4],
                        "ac_block_arrangement": "central_40ft_bilateral_4plus4",
                    }
                )

            # If a catalogue product was bound, replace the MW ÷ PF transformer
            # estimate with the real product nameplate / vector group / cooling.
            #
            # A single bound product only matches the HEAD spec. In a mixed
            # station a differing tail would inherit the head product's
            # transformer nameplate and the report would present it as
            # "per block" — a false attribution. So single-product binding is
            # disabled for a mixed station; each block falls back to the
            # MW ÷ PF estimate (per-model binding is future work). Uniform runs
            # keep the confirmed product nameplate exactly as before.
            if bound_ac_product and not is_mixed_run:
                from calb_sizing_tool.services.ac_block_product_match import product_transformer_overrides
                ac_output.update(product_transformer_overrides(bound_ac_product))
            elif bound_ac_product and is_mixed_run:
                ac_output["ac_block_product_binding_suppressed"] = "mixed_station"

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
                    actor=_auth_ctx.username,
                )
                # Record this AC alternative under the DC run. Identical
                # configurations reuse their run, so the history counts the
                # alternatives actually tried, not the times Save was pressed.
                #
                # Fail-soft on purpose: the configuration itself is already saved
                # by the call above, which is what SLD and the report read. This
                # is bookkeeping, and bookkeeping must never cost a user their
                # save.
                try:
                    _ac_run = persist_ac_run(
                        dc_run_id=source_run_id,
                        ac_inputs=ac_inputs,
                        ac_output=ac_output,
                        actor=_auth_ctx.username,
                        source_ref="ac_view",
                    )
                except Exception:
                    _ac_run = None
                if _ac_run is None:
                    st.info("Configuration saved.")
                elif _ac_run.reused:
                    st.info(
                        f"Configuration saved — unchanged, so it stays AC alternative "
                        f"1 of {_ac_run.alternatives} on this DC run."
                    )
                else:
                    st.info(
                        f"Configuration saved as a new AC alternative "
                        f"({_ac_run.alternatives} on this DC run)."
                    )
            else:
                st.success("AC sizing complete (guest mode — session only).")

    latest_ac_output = st.session_state.get("ac_output") if isinstance(st.session_state.get("ac_output"), dict) else ac_results
    if _snapshot_output_matches_run(latest_ac_output, active_run_id):
        auth_ctx = get_auth_context()
        render_pipeline_next_steps("AC Sizing", is_guest=bool(auth_ctx and auth_ctx.is_guest))
