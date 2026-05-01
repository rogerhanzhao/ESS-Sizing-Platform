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

from pathlib import Path

import streamlit as st
from calb_sizing_tool.reporting.export_docx import (
    make_proposal_filename,
)
from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import export_report_v2_1
from calb_sizing_tool.runtime_paths import get_outputs_dir
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.session_state import init_shared_state
from calb_sizing_tool.state.workspace_state import get_workspace_context
from calb_sizing_tool.services.sld_data_source_service import load_persisted_ac_snapshot
from calb_sizing_tool.services.artifact_service import load_artifact_bytes_from_db


def _extract_block_identity(stage2_raw):
    block_code = None
    block_name = None
    block_table = stage2_raw.get("block_config_table") if isinstance(stage2_raw, dict) else None
    if block_table is not None and not block_table.empty:
        first_row = block_table.iloc[0]
        block_code = first_row.get("Block Code")
        block_name = first_row.get("Block Name")
    return block_code, block_name


def _extract_artifact_bytes(artifact_bundle) -> tuple[bytes | None, bytes | None]:
    """Extract (png_bytes, svg_bytes) from a DiagramArtifactBundle stored in session state.

    The bundle's .artifacts is a list[dict] with keys artifact_kind / content / file_name.
    Returns (None, None) if the bundle is absent or has no matching items.
    """
    png_bytes = svg_bytes = None
    if artifact_bundle is None:
        return png_bytes, svg_bytes
    artifact_list = getattr(artifact_bundle, "artifacts", None)
    if not isinstance(artifact_list, list):
        return png_bytes, svg_bytes
    for item in artifact_list:
        if not isinstance(item, dict):
            continue
        kind = item.get("artifact_kind", "")
        content = item.get("content")
        if not content:
            continue
        if kind.endswith("_png") and png_bytes is None:
            png_bytes = content
        elif kind.endswith("_svg") and svg_bytes is None:
            svg_bytes = content
    return png_bytes, svg_bytes


def show():
    state = init_shared_state()
    init_project_state()
    dc_results = state.dc_results or {}
    ac_results = state.ac_results or {}
    artifacts = state.artifacts
    outputs_dir = get_outputs_dir()
    _active_run_id = (
        st.session_state.get("active_run_id")
        or st.session_state.get("dc_last_run_id")
    )

    # --- SLD bytes: new plugin bundle → old artifacts dict → old diagram_results → file → DB ---
    sld_png, sld_svg = _extract_artifact_bytes(st.session_state.get("sld_artifacts"))
    if sld_png is None:
        sld_png = artifacts.get("sld_png_bytes")
    if sld_svg is None:
        sld_svg = artifacts.get("sld_svg_bytes")
    if sld_png is None:
        # legacy diagram_results structure (older sessions)
        diagram_results = st.session_state.get("diagram_results") or {}
        for style_key in (diagram_results.get("last_style"), "raw_v05", "pro_v10", "jp_v08"):
            entry = diagram_results.get(style_key) if style_key else None
            if isinstance(entry, dict):
                sld_png = sld_png or entry.get("png")
                sld_svg = sld_svg or entry.get("svg")
                if sld_png:
                    break
    if sld_png is None:
        candidate = outputs_dir / "sld_latest.png"
        if candidate.exists():
            sld_png = candidate.read_bytes()
    if sld_svg is None:
        candidate = outputs_dir / "sld_latest.svg"
        if candidate.exists():
            sld_svg = candidate.read_bytes()
    # DB fallback: recover from artifact_registry after run restore
    if sld_png is None and _active_run_id:
        _db_sld = load_artifact_bytes_from_db(_active_run_id, ["sld_png", "sld_svg"])
        sld_png = sld_png or _db_sld.get("sld_png")
        sld_svg = sld_svg or _db_sld.get("sld_svg")

    # --- Layout bytes: same priority chain ---
    layout_png, layout_svg = _extract_artifact_bytes(st.session_state.get("layout_artifacts"))
    if layout_png is None:
        layout_png = artifacts.get("layout_png_bytes") or st.session_state.get("layout_png_bytes")
    if layout_svg is None:
        layout_svg = artifacts.get("layout_svg_bytes") or st.session_state.get("layout_svg_bytes")
    if layout_png is None:
        layout_results = st.session_state.get("layout_results") or {}
        for style_key in (layout_results.get("last_style"), "raw_v05"):
            entry = layout_results.get(style_key) if style_key else None
            if isinstance(entry, dict):
                layout_png = layout_png or entry.get("png")
                layout_svg = layout_svg or entry.get("svg")
                if layout_png:
                    break
    if layout_png is None:
        candidate = outputs_dir / "layout_latest.png"
        if candidate.exists():
            layout_png = candidate.read_bytes()
    if layout_svg is None:
        candidate = outputs_dir / "layout_latest.svg"
        if candidate.exists():
            layout_svg = candidate.read_bytes()
    if layout_png is None and _active_run_id:
        _db_layout = load_artifact_bytes_from_db(_active_run_id, ["layout_png", "layout_svg"])
        layout_png = layout_png or _db_layout.get("layout_png")
        layout_svg = layout_svg or _db_layout.get("layout_svg")

    # Write resolved bytes back into the artifacts dict so build_report_context() picks them up
    if sld_png:
        artifacts["sld_png_bytes"] = sld_png
    if sld_svg:
        artifacts["sld_svg_bytes"] = sld_svg
    if layout_png:
        artifacts["layout_png_bytes"] = layout_png
    if layout_svg:
        artifacts["layout_svg_bytes"] = layout_svg

    st.header("Report Export")
    st.caption("Generate unified V2.1 DOCX report with full AC and DC analysis.")

    stage13_output = (
        dc_results.get("stage13_output")
        or st.session_state.get("stage13_output")
        or {}
    )
    ac_output = {}
    if isinstance(ac_results, dict):
        ac_output.update(ac_results)
    ss_ac_output = st.session_state.get("ac_output")
    if isinstance(ss_ac_output, dict):
        ac_output.update(ss_ac_output)

    # Fallback: if AC output is absent from session (e.g. after a run restore),
    # attempt to reload the persisted AC snapshot from DB using the active run ID.
    if not ac_output:
        _active_run_id = (
            st.session_state.get("active_run_id")
            or st.session_state.get("dc_last_run_id")
        )
        if _active_run_id:
            try:
                _ac_snap = load_persisted_ac_snapshot(_active_run_id)
                if _ac_snap is not None and isinstance(_ac_snap.output, dict) and _ac_snap.output:
                    ac_output = _ac_snap.output
                    st.session_state["ac_output"] = ac_output
            except Exception:
                pass

    if not stage13_output or not ac_output:
        st.warning("Run DC sizing and AC sizing first to enable report export.")
        if stage13_output and not ac_output:
            st.info(
                "DC results found but AC sizing is missing. "
                "Run AC Sizing on this project/case, or restore a run that includes AC results."
            )
        return

    project_name = None
    project = st.session_state.get("project")
    if isinstance(project, dict):
        project_name = project.get("name")
    project_name = (
        project_name
        or st.session_state.get("project_name")
        or stage13_output.get("project_name")
        or ac_output.get("project_name")
        or "CALB ESS Project"
    )
    st.session_state["project_name"] = project_name

    grid_kv = (
        ac_output.get("grid_kv")
        or ac_output.get("mv_kv")
        or stage13_output.get("poi_nominal_voltage_kv")
    )
    pcs_lv_v = (
        ac_output.get("inverter_lv_v")
        or ac_output.get("lv_voltage_v")
        or ac_output.get("lv_v")
    )
    inputs = {
        "Project Name": project_name,
        "POI Power Requirement (MW)": ac_output.get("poi_power_mw"),
        "POI Energy Requirement (MWh)": ac_output.get("poi_energy_mwh"),
        "Grid Voltage (kV)": grid_kv,
        "PCS AC Output Voltage (V_LL,rms)": pcs_lv_v,
        "Standard AC Block Size (MW)": ac_output.get("block_size_mw"),
    }

    report_context = {
        "project_name": project_name,
        "inputs": inputs,
        "tool_version": "V1.0",
        "sld_png_bytes": sld_png,
        "sld_svg_bytes": sld_svg,
        "layout_png_bytes": layout_png,
        "layout_svg_bytes": layout_svg,
    }

    st.subheader("Report Content Preview")
    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.success("✓  DC Sizing")
    rc2.success("✓  AC Sizing")
    if sld_png or sld_svg:
        rc3.success("✓  SLD Image")
    else:
        rc3.info("○  SLD (not generated)")
    if layout_png or layout_svg:
        rc4.success("✓  Site Layout")
    else:
        rc4.info("○  Layout (not generated)")

    # --- Database Provenance Panel ---
    workspace = get_workspace_context()
    active_run_id = workspace.get("run_id")
    active_project_code = workspace.get("project_code")
    active_case_code = workspace.get("case_code")
    active_case_name = workspace.get("case_name")
    active_project_name = workspace.get("project_name")

    with st.expander("Database Provenance", expanded=True):
        p1, p2 = st.columns(2)
        with p1:
            st.caption("Project")
            st.write(active_project_name or project_name)
            st.caption("Project Code")
            st.write(active_project_code or "—")
        with p2:
            st.caption("Case")
            st.write(active_case_name or "—")
            st.caption("Case Code")
            st.write(active_case_code or "—")

        if active_run_id:
            st.success(f"DC Run ID: `{active_run_id}`  — linked to database")
            # Show AC snapshot linkage
            _ac_run_id = ac_output.get("source_ac_run_id") if ac_output else None
            if _ac_run_id:
                st.success(f"AC Run ID: `{_ac_run_id}`  — AC sizing persisted")
            elif ac_output:
                st.info("AC results loaded from snapshot attached to DC run (fully traceable).")
            else:
                st.warning("AC sizing not yet performed for this run.")
        else:
            st.warning(
                "No database run linked. Run DC Sizing and persist the run first. "
                "The report will be generated from the current session only and will "
                "carry a provenance warning."
            )
    st.divider()

    st.subheader("Downloads")

    # V2.1 is now the standard report format (with an optional Guoxia branded variant)
    report_template = st.selectbox(
        "Report Template",
        ["V2.1 (Beta)", "V2.1 (Guoxia)"],
        index=0,
    )
    
    c_d1, c_d2 = st.columns(2)

    with c_d1:
        st.info("AC Report generation moved to V2.1 format only.")

    with c_d2:
        stage2_raw = stage13_output.get("stage2_raw", {})
        block_code, block_name = _extract_block_identity(stage2_raw)

        # Build comprehensive project inputs from stage13_output
        project_inputs_for_report = {
            "project_name": project_name,
            "poi_power_mw": stage13_output.get("poi_power_req_mw"),
            "poi_energy_mwh": stage13_output.get("poi_energy_req_mwh"),
            "poi_energy_guarantee_mwh": stage13_output.get("poi_energy_req_mwh"),
            "poi_guarantee_year": stage13_output.get("poi_guarantee_year"),
            "poi_frequency_hz": stage13_output.get("poi_frequency_hz"),
        }
        ctx = build_report_context(
            session_state=st.session_state,
            stage_outputs={
                "stage13_output": stage13_output,
                "stage2": stage13_output.get("stage2_raw", {}),
                "ac_output": ac_output,
                "sld_snapshot": st.session_state.get("sld_snapshot"),
            },
            project_inputs=project_inputs_for_report,
            scenario_ids=stage13_output.get("selected_scenario", "container_only"),
        )
        brand = None
        version = "V2.1"
        filename_prefix = "CALB"
        button_label = "Download Combined Report V2.1"

        if report_template == "V2.1 (Guoxia)":
            guoxia_logo = Path("GUOXIA-LOGO.png")
            if not guoxia_logo.exists():
                st.warning("GUOXIA-LOGO.png not found. Falling back to default logo.")
                guoxia_logo = None

            brand = {
                "logo_path": guoxia_logo,
                "header_title": "Confidential Sizing Report (V2.1 Guoxia)",
                "header_lines": [
                    "Guoxia Technology Co., Ltd.",
                    "HKEX: 02655 (GUOXIA TECH)",
                    "Confidential Sizing Report (V2.1 Guoxia)",
                ],
                "footer_lines": [
                    "(c) 2026 Guoxia Technology Co., Ltd. All rights reserved.",
                    "HKEX: 02655 (GUOXIA TECH) | Document Classification: Confidential",
                ],
                "cover_title": "Guoxia Technology Utility-Scale ESS Sizing Report (V2.1)",
                "tool_version": "V2.1 Guoxia",
            }
            version = "V2.1-GUOXIA"
            filename_prefix = "GUOXIA"
            button_label = "Download Combined Report V2.1 (Guoxia)"

        comb_bytes = export_report_v2_1(ctx, brand=brand)
        proposal_filename = make_proposal_filename(
            project_name, version=version, prefix=filename_prefix
        )
        st.download_button(
            button_label,
            comb_bytes,
            proposal_filename,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
        )

    if not sld_png and not sld_svg:
        st.info("SLD image not found. Generate it in Single Line Diagram.")
    if not layout_png and not layout_svg:
        st.info("Layout image not found. Generate it in Site Layout.")


