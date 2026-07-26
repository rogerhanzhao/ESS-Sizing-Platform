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
    build_simplified_ac_block_models,
    build_dc_allocation_plan,
    evaluate_ac_sizing_feasibility,
    generate_ac_sizing_options,
    select_ac_block_container_type,
)
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.services.sld_data_source_service import persist_ac_runtime_snapshot, resolve_preferred_ac_snapshot
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import bump_run_id_ac, get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state, set_run_time
from calb_sizing_tool.state.workspace_state import get_workspace_context

# Transformer topology is now selected explicitly. A two-winding transformer
# can serve any supported PCS count on one common LV busbar; a three-winding
# transformer balances the PCS feeders across two independent LV secondaries.
_CUSTOM_PCS_COUNT_CHOICES = (1, 2, 3, 4, 5, 6)


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
        if dc_cabinet_count > 0:
            compact_note(
                f"DC side used a hybrid packaging: {dc_container_count} container(s) + "
                f"{dc_cabinet_count} cabinet(s) as the DC tail. The AC mixed station (in the "
                "standard product preset) is the AC-side counterpart that places the remainder "
                "into smaller AC Blocks."
            )

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

    saved_ac_output = st.session_state.get("ac_output") if isinstance(st.session_state.get("ac_output"), dict) else ac_results
    if _snapshot_output_matches_run(saved_ac_output, active_run_id):
        _render_saved_ac_snapshot(saved_ac_output, section_header=section_header)
        st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

    # ========== Governed Product (Phase A, optional) ==========
    # A fixed, owner-confirmed product identity. When selected it overrides the
    # generic grouping/model flow below and drives AC->SLD->Layout->Report by
    # configuration_code / layout_variant instead of an average DC-per-AC ratio.
    from calb_sizing_tool.schemas.governed_ac_block_config import (
        ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as _GOVERNED,
    )
    from calb_sizing_tool.services.governed_ac_block_service import (
        build_governed_ac_output_from_product,
        build_governed_site_ac_output,
        eligible_products_for,
        unresolved_provisional_fields,
    )
    from calb_sizing_tool.services.sld_engineering_settings_service import (
        load_case_sld_project_settings,
    )

    from calb_sizing_tool.services.governed_ac_block_service import (
        build_governed_primary_ac_output,
        build_governed_site_plan,
    )

    selected_product_code = None
    num_units = 0

    # ONE AC Sizing flow (auto-recommend ratio + PCS, then power/energy validation
    # → pass/hold) is the trunk below. A real productized AC Block (the 10 MW /
    # 8-DC bilateral standard block + its 5/2.5/1.25 MW tails) is an OPTIONAL
    # preset on top — a shortcut to a confirmed catalogue product, never a second
    # engine. Feasibility is validated by the existing power/energy check.
    with st.container(border=True):
        use_governed = bool(st.checkbox(
            "Use a standard product AC Block preset (real catalogue: 10 MW / 8-DC bilateral + tails)",
            value=False,
            key="use_product_preset",
            help=(
                "Optional shortcut to a real productized AC Block with a confirmed "
                "transformer nameplate, vector group and layout. Leave unchecked for the "
                "auto-recommended sizing below."
            ),
        ))
        # Mixed AC Block station toggle — the AC parallel of DC Sizing's "Enable
        # Hybrid Mode": places any non-multiple-of-8 remainder into smaller
        # governed AC Blocks (10 MW head + 5/2.5/1.25 MW tails), just as DC hybrid
        # places a remainder into cabinets after full containers. Auto-on only when
        # a tail is actually needed. Off + a remainder cannot form a uniform site
        # (an AC Block's DC count is a hard constraint), so it is refused with a
        # clear message rather than silently padded.
        _head_dc = int(_GOVERNED.dc_block_count)
        _remainder = (dc_blocks_total % _head_dc) if dc_blocks_total > 0 else 0
        _mixed_ok = True
        if use_governed:
            enable_mixed = bool(st.checkbox(
                "Enable mixed AC Block station (place the remainder in smaller AC Blocks)",
                value=(_remainder != 0),
                key="enable_mixed_ac_station",
                help=(
                    "Symmetric to DC Sizing's Hybrid Mode. On: a 10 MW head block plus "
                    "smaller 5 / 2.5 / 1.25 MW tail blocks cover any remainder (mixed station). "
                    "Off: uniform 10 MW blocks only — needs a DC total that is a multiple of 8."
                ),
            ))
            if (not enable_mixed) and _remainder != 0:
                _mixed_ok = False
                st.warning(
                    f"Mixed station disabled and {_remainder} remainder DC Block(s) cannot form a "
                    f"full {_head_dc}-DC (10 MW) AC Block. Enable the mixed station above, or set "
                    f"DC Sizing to a multiple of {_head_dc} DC Blocks."
                )
        governed_ready = use_governed and _mixed_ok
        if governed_ready:
            section_header(
                "Standard Product AC Block",
                "Real productized AC Block (1:1–1:8 DC-per-block) matched to the project; "
                "any non-multiple-of-8 remainder is placed into smaller blocks (mixed "
                "station), never an average split.",
                eyebrow="Optional preset",
            )
        if governed_ready:
            project_settings = load_case_sld_project_settings(workspace.get("case_id"))
            _plan = build_governed_site_plan(dc_blocks_total)
            num_units = _plan.ac_blocks_total
            is_mixed = len(_plan.groups) > 1
            head_is_10mw = dc_blocks_total >= _GOVERNED.dc_block_count

            # Bind the 10 MW head to a real catalogue product (transformer / LV /
            # vector / cooling from the datasheet instead of TBD). Only shown when
            # the site actually contains a 10 MW governed head. Phase B tails
            # auto-bind their own eligible product.
            if head_is_10mw:
                try:
                    catalogue = eligible_products_for(_GOVERNED.configuration_code)
                except Exception:
                    catalogue = []
                product_labels = ["(none — Engineering Settings only)"] + [
                    f"{p.get('vendor') or ''} · {p['block_code']} · "
                    f"{(p.get('transformer_kva') or 0) / 1000:.1f} MVA"
                    for p in catalogue
                ]
                product_choice = st.selectbox(
                    "Bind 10 MW head to catalogue product (fills confirmed transformer/LV values)",
                    range(len(product_labels)),
                    index=0,
                    format_func=lambda i: product_labels[i],
                    key="governed_product_choice",
                    help="Datasheet-derived product record. Uk% is never published on "
                    "these datasheets and still comes from Engineering Settings.",
                )
                selected_product_code = (
                    catalogue[product_choice - 1]["block_code"] if product_choice > 0 else None
                )

            primary_preview = build_governed_primary_ac_output(
                dc_blocks_total,
                project_settings=project_settings,
                head_product_block_code=selected_product_code,
            )
            unresolved = list(primary_preview.get("provisional_unresolved", []))

            gc1, gc2, gc3, gc4 = st.columns(4)
            gc1.metric("Governed AC Blocks", num_units)
            gc2.metric("Governed Groups", len(_plan.groups))
            gc3.metric("Site AC Power", f"{_plan.ac_power_mw_total:.1f} MW")
            gc4.metric("DC Blocks", dc_blocks_total)
            if is_mixed:
                compact_note(
                    f"Mixed governed site (Phase B): {dc_blocks_total} DC → "
                    + " + ".join(
                        f"{g.ac_block_count}×{g.configuration_code}" for g in _plan.groups
                    )
                    + ". Each governed group keeps its own SLD topology; the SLD below "
                    "shows the 10 MW bilateral head."
                )
            else:
                compact_note(
                    "Central vertical 40 ft AC Block; west 4-DC + east 4-DC mirrored 田 fields; "
                    "DC-1..8 -> PCS-1..8; two independent LV secondaries (4+4)."
                )
        if governed_ready:
            if governed_ready:

                with st.expander("Site composition (Phase B decomposition)", expanded=False):
                    try:
                        from calb_sizing_tool.services.governed_ac_block_service import (
                            build_governed_site_run,
                        )

                        # Orchestrate the mixed site: one runnable AC output per
                        # governed group, auto-binding a catalogue product where
                        # one qualifies. Each group renders its own SLD (each is
                        # internally uniform under the SLD V1 contract).
                        _run = build_governed_site_run(
                            dc_blocks_total, bind_products=True
                        )
                        st.caption(
                            f"{_run.dc_blocks_total} DC Blocks → {_run.ac_blocks_total} AC Block(s) "
                            f"in {len(_run.groups)} governed group(s) · "
                            f"{_run.ac_power_mw_total:.2f} MW total. A total that is not a multiple "
                            "of 8 is placed into smaller governed AC Blocks (8/4/2/1), never an "
                            "average split. Each governed group renders its own SLD."
                        )
                        render_static_table(
                            [
                                {
                                    "Governed group": _g.configuration_code,
                                    "Count": _g.ac_block_count,
                                    "DC/PCS": f"{_g.dc_blocks_per_ac_block}/{_g.pcs_per_ac_block}",
                                    "MW": _g.ac_power_mw_total,
                                    "Bound product": _g.bound_product_code or "—",
                                    "Transformer MVA": (
                                        f"{_g.ac_output['transformer_mva']:g} MVA"
                                        if _g.ac_output.get("transformer_mva")
                                        else "TBD (confirm in Engineering Settings)"
                                    ),
                                }
                                for _g in _run.groups
                            ]
                        )
                        if _run.provisional_unresolved:
                            st.caption(
                                "Unresolved across groups (never inferred): "
                                + ", ".join(_run.provisional_unresolved)
                            )
                    except Exception as _exc:  # pragma: no cover - defensive UI guard
                        st.caption(f"Site composition unavailable: {_exc}")

                if unresolved:
                    st.warning(
                        "Provisional engineering values still unresolved (never inferred): "
                        + ", ".join(unresolved)
                        + ". Enter them in Engineering Settings — the SLD stays gated until the "
                        "transformer MVA is confirmed."
                    )
                if st.button(
                    "Run AC Sizing (Governed)",
                    type="primary",
                    use_container_width=True,
                    key="run_governed_ac",
                ):
                    bump_run_id_ac()
                    ac_run_id = project_state.get("ac", {}).get("run_id")
                    mv_kv = float(mv_kv_value or 33.0)
                    lv_v = float(st.session_state.get("pcs_lv_v", 690.0))
                    source_run_id = (
                        workspace.get("run_id")
                        or dc_results.get("last_run_id")
                        or project_state.get("dc", {}).get("run_id")
                    )
                    source_fields = {
                        "project_name": project_name,
                        "grid_kv": mv_kv,
                        "mv_kv": mv_kv,
                        "mv_voltage_kv": mv_kv,
                        "lv_v": lv_v,
                        "lv_voltage_v": lv_v,
                        "inverter_lv_v": lv_v,
                        "dc_total_mwh": total_energy_mwh,
                        "poi_power_mw": target_mw,
                        "poi_energy_mwh": target_mwh,
                        "ac_block_container_type": _GOVERNED.ac_container_type,
                        "ac_block_template_id": f"{_GOVERNED.pcs_count}x{_GOVERNED.pcs_rating_kw}kw",
                        "ac_block_model_name": _GOVERNED.configuration_code,
                        "ac_block_model_source": "governed_product",
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
                    if selected_product_code:
                        source_fields["governed_product_block_code"] = selected_product_code
                    try:
                        # Single governed entry for ANY DC total: a multiple of 8
                        # yields one uniform bilateral output; any remainder is
                        # decomposed (Phase B) with the true site rollup carried on
                        # the output. The head stays a uniform, SLD-renderable block.
                        gov_output = build_governed_primary_ac_output(
                            dc_blocks_total,
                            project_settings=project_settings,
                            source_fields=source_fields,
                            head_product_block_code=selected_product_code,
                        )
                    except ValueError as exc:
                        st.error(f"Governed AC sizing failed: {exc}")
                        st.stop()
                    st.session_state["ac_output"] = gov_output
                    ac_results.update(gov_output)
                    set_run_time("ac_results")
                    _site_mw = gov_output.get("governed_site_total_ac_mw") or gov_output.get("total_ac_mw", 0.0)
                    st.success(
                        f"Governed AC sizing complete — {num_units} governed AC Block(s) "
                        f"across {len(_plan.groups)} group(s), {_site_mw:.0f} MW total."
                    )
                    _auth_ctx = get_auth_context()
                    if _auth_ctx and not _auth_ctx.is_guest:
                        persist_ac_runtime_snapshot(
                            run_id=source_run_id,
                            ac_inputs=ac_inputs,
                            ac_output=gov_output,
                            results={},
                            source_ref="ac_view_governed",
                            actor=_auth_ctx.username,
                        )
                        st.info("Configuration saved.")

    if use_governed:
        st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
        _latest = st.session_state.get("ac_output") if isinstance(st.session_state.get("ac_output"), dict) else ac_results
        if _snapshot_output_matches_run(_latest, active_run_id):
            _auth_ctx = get_auth_context()
            render_pipeline_next_steps("AC Sizing", is_guest=bool(_auth_ctx and _auth_ctx.is_guest))
        return

    # ================= AC SIZING (auto-recommend trunk) =================
    # The single duration-aware sizing flow: POI power minus losses → AC:DC ratio →
    # PCS count × rating (auto-recommended for the project duration) → transformer
    # windings → power/energy validation, all manually adjustable, any duration.
    st.caption(
        "Auto-recommended for the project duration; adjust the AC:DC grouping, PCS and "
        "transformer below, then run to validate against the POI requirement. The "
        "transformer here is an AC Block MW ÷ PF estimate — tick the standard product "
        "preset above to bind a real catalogue product (confirmed nameplate, vector "
        "group and layout) when one matches."
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
                "Choose the simplified AC Block model. This sets PCS count, PCS rating, and container basis.",
                eyebrow="Step 2",
            )
            compact_note(
                f"Selected AC/DC block grouping: {_ac_block_grouping_label(selected_option.ratio)}. "
                "AC Block quantity comes from Step 1; the model below defines one AC Block only."
            )
            model_options = build_simplified_ac_block_models(selected_option.pcs_recommendations)

            # Model selection lives outside any st.form so a change reruns
            # immediately: picking "Custom..." must reveal the PCS inputs
            # before anything is executed (FT-20260714-12).
            model_labels = [model.readable for model in model_options]
            model_labels.append("Custom AC Block Model...")

            model_choice = st.selectbox(
                "Select AC Block Model",
                range(len(model_labels)),
                index=_saved_ac_block_model_choice_index(
                    saved_ac_output,
                    model_options,
                    custom_index=len(model_options),
                ),
                format_func=lambda i: model_labels[i],
                key="ac_block_model_choice",
                help="Simplified dropdown model derived from PCS count and rating; not a governed Product DB record.",
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
            saved_transformer_topology = str((saved_ac_output or {}).get("transformer_topology") or "")
            if saved_transformer_topology not in {"two_winding", "three_winding"}:
                saved_transformer_topology = "three_winding" if pcs_per_ac > 2 else "two_winding"
            transformer_topology = electrical_col1.selectbox(
                "Transformer LV Topology",
                ("two_winding", "three_winding"),
                index=(0 if saved_transformer_topology == "two_winding" else 1),
                format_func=lambda value: (
                    "2-winding — one common LV busbar for all PCS"
                    if value == "two_winding"
                    else "3-winding — two independent LV secondary busbars"
                ),
                key="ac_transformer_topology",
                help="Select the actual transformer secondary arrangement. It is not inferred from PCS count.",
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
            compact_note(
                "Electrical topology: "
                + ("one common LV busbar" if transformer_topology == "two_winding" else "two independent LV secondary busbars")
                + f"; each DC Block has {dc_block_output_circuits} protected PCS output branch(es)."
            )

            # Container size info - based on single AC block size
            compact_note(
                f"AC Block Container: {auto_container} "
                f"(single block {single_block_ac_power:.2f} MW, "
                f"total AC {selected_option.ac_block_count * single_block_ac_power:.2f} MW)."
            )

            # OPTIONAL — bind a real catalogue product that matches this spec (same
            # PCS count × rating) so the transformer nameplate / vector group come
            # from the datasheet instead of the MW ÷ PF estimate. This is a lookup
            # by the spec already computed — it introduces no new parameter.
            bound_ac_product = None
            try:
                from calb_sizing_tool.services.ac_block_product_match import match_ac_block_products
                _matches = match_ac_block_products(pcs_per_ac, pcs_kw)
            except Exception:
                _matches = []
            if _matches:
                _labels = ["(none — transformer estimated as MW ÷ PF)"] + [
                    f"{m.get('vendor') or ''} · {m['block_code']} · "
                    f"{(m.get('transformer_kva') or 0) / 1000:.2f} MVA"
                    + (f" · {m['transformer_vector_group']}" if m.get("transformer_vector_group") else "")
                    for m in _matches
                ]
                _bind_choice = st.selectbox(
                    "Bind catalogue product (optional — confirmed transformer / LV values)",
                    range(len(_labels)),
                    index=0,
                    format_func=lambda i: _labels[i],
                    key="ac_trunk_product_bind",
                    help="Catalogue products whose PCS count and unit rating match this AC "
                    "Block. Binding one replaces the MW ÷ PF transformer estimate with the "
                    "real product nameplate; unmatched specs stay on the estimate.",
                )
                bound_ac_product = _matches[_bind_choice - 1] if _bind_choice > 0 else None

            submitted = st.button("Run AC Sizing", use_container_width=True, type="primary")

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
                f"AC Block model: {ac_block_model_name}. Container type: {auto_container} per AC Block."
            )

            # --- DETAILED DC ALLOCATION ---
            try:
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
                "pcs_count_by_block": [pcs_per_block for _ in range(num_blocks)],
                "pcs_kw": pcs_kw,
                "pcs_power_kw": pcs_kw,
                "pcs_rating_kw_each": pcs_kw,
                "block_size_mw": block_size_mw,
                "total_ac_mw": total_ac_mw,
                "overhead_mw": overhead,
                "dc_blocks_per_ac": selected_option.dc_blocks_per_ac,
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
                "lv_winding_count": 1 if transformer_topology == "two_winding" else 2,
                "lv_busbar_topology": (
                    "common_single_lv_busbar"
                    if transformer_topology == "two_winding"
                    else "independent_lv_busbars"
                ),
                "dc_block_output_circuits": dc_block_output_circuits,
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

            # If a catalogue product was bound, replace the MW ÷ PF transformer
            # estimate with the real product nameplate / vector group / cooling.
            if bound_ac_product:
                from calb_sizing_tool.services.ac_block_product_match import product_transformer_overrides
                ac_output.update(product_transformer_overrides(bound_ac_product))

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
                st.info("Configuration saved.")
            else:
                st.success("AC sizing complete (guest mode — session only).")

    latest_ac_output = st.session_state.get("ac_output") if isinstance(st.session_state.get("ac_output"), dict) else ac_results
    if _snapshot_output_matches_run(latest_ac_output, active_run_id):
        auth_ctx = get_auth_context()
        render_pipeline_next_steps("AC Sizing", is_guest=bool(auth_ctx and auth_ctx.is_guest))
