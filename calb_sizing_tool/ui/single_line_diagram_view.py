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

from __future__ import annotations

from typing import Any

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import legacy_sld_override_preset
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.sld_data_source_service import AcSnapshotResolution, resolve_preferred_ac_snapshot
from calb_sizing_tool.services.sld_engineering_settings_service import (
    build_persisted_sld_project_settings,
    load_case_sld_project_settings,
    load_run_sld_project_settings,
    save_case_sld_project_settings,
)
from calb_sizing_tool.services.sld_pipeline_service import run_sld_pipeline_from_run_bundle
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state
from calb_sizing_tool.state.workspace_state import get_workspace_context
from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs


def _resolve_ac_snapshot(
    state,
    project_state,
    *,
    run_id: str | None,
    db_url: str | None = None,
) -> AcSnapshotResolution:
    return resolve_preferred_ac_snapshot(
        run_id,
        project_state=project_state,
        shared_state=state,
        session_state=st.session_state,
        db_url=db_url,
    )


def _resolve_mv_nominal_voltage_kv(state, project_state, ac_snapshot: AcSnapshot | None) -> float | None:
    candidates = [
        st.session_state.get("poi_nominal_voltage_kv"),
        (project_state.get("dc_inputs") or {}).get("poi_nominal_voltage_kv") if isinstance(project_state, dict) else None,
        getattr(state, "dc_inputs", {}).get("poi_nominal_voltage_kv") if hasattr(state, "dc_inputs") else None,
        ac_snapshot.output.get("mv_voltage_kv") if ac_snapshot and isinstance(ac_snapshot.output, dict) else None,
        ac_snapshot.inputs.get("grid_kv") if ac_snapshot and isinstance(ac_snapshot.inputs, dict) else None,
    ]
    for raw in candidates:
        try:
            value = float(raw)
        except Exception:
            continue
        if value > 0:
            return value
    return None


def _validate_ac_snapshot_context(
    ac_output: dict[str, Any] | None,
    *,
    expected_run_id: str | None,
    expected_case_id: str | None = None,
    expected_project_id: str | None = None,
) -> str | None:
    if not isinstance(ac_output, dict) or not ac_output:
        return "AC snapshot not found. Run AC sizing before generating SLD."

    source_run_id = str(ac_output.get("source_run_id") or "").strip()
    if not source_run_id:
        return "AC snapshot is missing source_run_id provenance. Re-run AC sizing from the active database run."

    expected_run_id = str(expected_run_id or "").strip()
    if expected_run_id and source_run_id != expected_run_id:
        return (
            f"AC snapshot belongs to run `{source_run_id}` instead of active run `{expected_run_id}`. "
            "Re-run AC sizing for the current run before generating SLD."
        )

    expected_case_id = str(expected_case_id or "").strip()
    source_case_id = str(ac_output.get("source_case_id") or "").strip()
    if expected_case_id and source_case_id and source_case_id != expected_case_id:
        return (
            f"AC snapshot belongs to case `{source_case_id}` instead of active case `{expected_case_id}`. "
            "Re-run AC sizing for the current case before generating SLD."
        )

    expected_project_id = str(expected_project_id or "").strip()
    source_project_id = str(ac_output.get("source_project_id") or "").strip()
    if expected_project_id and source_project_id and source_project_id != expected_project_id:
        return (
            f"AC snapshot belongs to project `{source_project_id}` instead of active project `{expected_project_id}`. "
            "Re-run AC sizing for the current project before generating SLD."
        )

    return None


def _resolve_ac_blocks_total(ac_output: dict) -> int:
    if not isinstance(ac_output, dict):
        return 0
    value = ac_output.get("num_blocks")
    try:
        value = int(value)
    except Exception:
        value = 0
    return max(0, value)


def _execute_sld_pipeline(*, bundle, ac_snapshot, options, plugin_id: str, actor: str, project_settings: dict[str, Any] | None):
    return run_sld_pipeline_from_run_bundle(
        bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        plugin_id=plugin_id,
        actor=actor,
    )


def _clear_sld_preview() -> None:
    st.session_state.pop("sld_artifacts", None)
    st.session_state.pop("sld_pipeline_meta", None)


def show() -> None:
    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()

    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    auth_user = AuthUser(
        user_id=auth_context.user_id,
        username=auth_context.username,
        display_name=auth_context.display_name,
        roles=auth_context.roles,
    )

    workspace = get_workspace_context()

    st.header("Single Line Diagram")
    st.caption("Read runtime run data, execute the SLD pipeline, preview the result, and download artifacts.")
    st.caption(
        "Preview is session-scoped. Change the run or AC result, then click Generate SLD again to refresh the formal diagram."
    )
    st.caption(
        f"Active Workspace: Project `{workspace.get('project_name') or 'None'}` | "
        f"Case `{workspace.get('case_name') or 'None'}` | Run `{workspace.get('run_id') or 'None'}`"
    )

    run_id_default = workspace.get("run_id") or st.session_state.get("dc_last_run_id", "")
    run_id = st.text_input("Run ID", value=str(run_id_default or "")).strip()

    ac_resolution = _resolve_ac_snapshot(
        state,
        project_state,
        run_id=run_id or workspace.get("run_id"),
    )
    ac_snapshot = ac_resolution.snapshot
    ac_snapshot_issue = _validate_ac_snapshot_context(
        ac_snapshot.output if ac_snapshot else None,
        expected_run_id=run_id or workspace.get("run_id"),
        expected_case_id=workspace.get("case_id"),
        expected_project_id=workspace.get("project_id"),
    )
    if ac_snapshot_issue:
        st.warning(ac_snapshot_issue)
        ac_snapshot = None
    elif ac_resolution.source == "persisted_run_snapshot":
        st.caption("AC runtime source: persisted run snapshot")
    elif ac_resolution.source == "compatibility_adapter":
        st.caption("AC runtime source: compatibility adapter")
    elif ac_resolution.source == "session_cache":
        st.caption("AC runtime source: session cache fallback")

    ac_blocks_total = _resolve_ac_blocks_total(ac_snapshot.output if ac_snapshot else {})
    mv_nominal_voltage_kv = _resolve_mv_nominal_voltage_kv(state, project_state, ac_snapshot)
    persisted_project_settings = load_case_sld_project_settings(workspace.get("case_id"))
    group_choices = list(range(1, ac_blocks_total + 1)) if ac_blocks_total > 0 else [1]
    group_index = st.selectbox(
        "AC Block Group",
        group_choices,
        index=0,
        disabled=not ac_snapshot or ac_blocks_total <= 0,
    )

    display_col1, display_col2, display_col3 = st.columns(3)
    theme = display_col1.selectbox("Theme", ["dark", "light"], index=0)
    compact_mode = display_col2.checkbox("Compact Mode", value=False)
    draw_summary = display_col3.checkbox("Draw Summary", value=False)

    if workspace.get("case_id"):
        if persisted_project_settings:
            st.caption("Formal engineering settings source: persisted case settings")
        else:
            st.warning(
                "Formal engineering settings are not yet saved for this case. "
                "Save them below before using strict mode, or switch to draft override mode."
            )
        with st.expander("Formal Engineering Settings", expanded=not bool(persisted_project_settings)):
            formal_settings_input = render_electrical_inputs(
                persisted_project_settings or legacy_sld_override_preset(),
                key_prefix="sld_formal_settings",
                mv_nominal_voltage_kv=mv_nominal_voltage_kv,
                section_title="Formal SLD Engineering Settings",
                section_caption="Persisted case-level settings used by formal / strict SLD mode.",
            )
            if st.button("Save Formal Engineering Settings", use_container_width=True):
                try:
                    with session_scope() as session:
                        access = AccessControlService(session, auth_user)
                        case_row = access.case_repo.get_case_by_id(str(workspace.get("case_id")))
                        if case_row is None:
                            raise ValueError("Active case not found.")
                        access.ensure_project_access(case_row.project_id)
                    formal_project_settings = build_persisted_sld_project_settings(
                        formal_settings_input,
                        mv_nominal_voltage_kv=mv_nominal_voltage_kv,
                    )
                    save_case_sld_project_settings(
                        str(workspace.get("case_id")),
                        formal_project_settings,
                        actor=auth_user.username,
                    )
                except Exception as exc:
                    st.error(f"Saving formal engineering settings failed: {exc}")
                else:
                    st.success("Formal engineering settings saved to the active case.")
                    st.rerun()
    else:
        st.info("Select an active case to save formal engineering settings.")

    override_mode = st.checkbox(
        "Enable Engineering Override Mode",
        value=False,
        help="Draft-only mode. Use explicit engineering overrides only when authoritative inputs are incomplete.",
    )
    overrides = None
    if override_mode:
        st.warning("Engineering override mode is active. The generated SLD will be treated as a non-official draft.")
        with st.expander("SLD Override Inputs", expanded=True):
            overrides = render_electrical_inputs(
                legacy_sld_override_preset(),
                key_prefix="sld_override",
                mv_nominal_voltage_kv=mv_nominal_voltage_kv,
            )
    else:
        st.info("Formal mode uses strict runtime inputs only. Missing required engineering inputs will fail fast.")

    registry = get_plugin_registry()
    plugins = registry.list_by_artifact("sld_svg")
    plugin_ids = [plugin.metadata.plugin_id for plugin in plugins]
    selected_plugin = st.selectbox(
        "Renderer",
        plugin_ids,
        index=0,
        format_func=lambda pid: registry.get(pid).metadata.plugin_name if registry.get(pid) else pid,
    )

    action_col1, action_col2 = st.columns([1.3, 1.0])
    generate_sld = action_col1.button("Generate SLD", disabled=not run_id or not ac_snapshot, use_container_width=True)
    clear_preview = action_col2.button(
        "Clear Preview",
        disabled=not st.session_state.get("sld_artifacts"),
        use_container_width=True,
    )
    if clear_preview:
        _clear_sld_preview()
        st.info("SLD preview cleared.")

    if generate_sld:
        with session_scope() as session:
            access = AccessControlService(session, auth_user)
            try:
                bundle = access.load_dc_run_bundle(run_id)
            except PermissionError:
                st.error("You do not have access to this run.")
                return
        if not bundle:
            st.error("Run not found.")
            return
        ac_context_error = _validate_ac_snapshot_context(
            ac_snapshot.output if ac_snapshot else None,
            expected_run_id=bundle.run_id,
            expected_case_id=bundle.sizing_case_id,
            expected_project_id=bundle.project_id,
        )
        if ac_context_error:
            st.error(ac_context_error)
            return
        persisted_project_settings = load_run_sld_project_settings(bundle.run_id)

        options = SldRenderOptions(
            group_index=group_index,
            theme=theme,
            compact_mode=compact_mode,
            draw_summary=draw_summary,
            override_mode=override_mode,
            overrides=overrides,
        )
        try:
            execution = _execute_sld_pipeline(
                bundle=bundle,
                ac_snapshot=ac_snapshot,
                options=options,
                project_settings=persisted_project_settings,
                plugin_id=selected_plugin,
                actor=auth_user.username,
            )
        except Exception as exc:
            st.error(f"SLD generation failed: {exc}")
            return

        artifact_bundle = execution.artifact_bundle
        st.session_state["sld_artifacts"] = artifact_bundle
        artifact_hashes = {
            item["artifact_kind"]: (item.get("metadata") or {}).get("content_hash")
            for item in artifact_bundle.artifacts
        }
        st.session_state["sld_pipeline_meta"] = {
            "validation_mode": execution.prepared.validation_mode,
            "override_mode": bool(options.override_mode),
            "draft_warnings": list(execution.prepared.render_input.canonical_input.draft_warnings),
            "group_index": execution.prepared.topology.summary.group_index,
            "topology_nodes": len(execution.prepared.topology.nodes),
            "topology_edges": len(execution.prepared.topology.edges),
            "run_id": bundle.run_id,
            "renderer_version": artifact_bundle.metadata.get("renderer_version"),
            "artifact_mode": artifact_bundle.metadata.get("artifact_mode"),
            "input_hash": artifact_bundle.metadata.get("input_hash"),
            "topology_hash": artifact_bundle.metadata.get("topology_hash"),
            "render_spec_hash": artifact_bundle.metadata.get("render_spec_hash"),
            "artifact_hashes": artifact_hashes,
        }
        if execution.prepared.validation_mode == "draft":
            st.warning("SLD draft generated and artifacts registered.")
        else:
            st.success("Formal SLD generated and artifacts registered.")

    artifact_bundle = st.session_state.get("sld_artifacts")
    pipeline_meta = st.session_state.get("sld_pipeline_meta") or {}
    if pipeline_meta:
        mode_label = "Draft / Override" if pipeline_meta.get("validation_mode") == "draft" else "Formal / Strict"
        st.subheader("Pipeline Status")
        st.caption(
            f"Run `{pipeline_meta.get('run_id')}` | Group {pipeline_meta.get('group_index')} | "
            f"Mode: {mode_label} | Topology {pipeline_meta.get('topology_nodes')} nodes / {pipeline_meta.get('topology_edges')} edges"
        )
        renderer_version = pipeline_meta.get("renderer_version") or "n/a"
        st.caption(
            f"Renderer `{renderer_version}` | Input hash `{pipeline_meta.get('input_hash')}` | "
            f"Topology hash `{pipeline_meta.get('topology_hash')}`"
        )
        if pipeline_meta.get("validation_mode") == "draft":
            st.warning("This SLD was produced in draft mode and must not replace the formal baseline result.")
        elif pipeline_meta.get("draft_warnings"):
            st.info("No draft fallback was applied in formal mode.")
        preview_run_id = str(pipeline_meta.get("run_id") or "").strip()
        if run_id and preview_run_id and preview_run_id != run_id:
            st.warning(
                f"Current preview belongs to run `{preview_run_id}`. Click Generate SLD to refresh the diagram for `{run_id}`."
            )
    if artifact_bundle:
        artifacts = {item["artifact_kind"]: item for item in artifact_bundle.artifacts}
        svg_item = artifacts.get("sld_svg")
        png_item = artifacts.get("sld_png")

        st.subheader("Preview")
        if png_item and png_item.get("content"):
            st.image(png_item["content"], use_container_width=True)
        elif svg_item and svg_item.get("content"):
            st.components.v1.html(svg_item["content"].decode("utf-8"), height=640, scrolling=True)

        st.subheader("Downloads")
        hash_rows = []
        for artifact_kind, artifact_hash in (pipeline_meta.get("artifact_hashes") or {}).items():
            hash_rows.append({"artifact_kind": artifact_kind, "content_hash": artifact_hash})
        if hash_rows:
            st.subheader("Traceability")
            st.dataframe(hash_rows, use_container_width=True, hide_index=True)
        if svg_item:
            st.download_button(
                "Download SLD SVG",
                svg_item["content"],
                svg_item.get("file_name") or "sld_render.svg",
                "image/svg+xml",
            )
        if png_item:
            st.download_button(
                "Download SLD PNG",
                png_item["content"],
                png_item.get("file_name") or "sld_render.png",
                "image/png",
            )
