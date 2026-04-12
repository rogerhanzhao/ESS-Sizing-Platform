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

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import legacy_sld_override_preset
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.sld_pipeline_service import run_sld_pipeline_from_run_bundle
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state
from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs


def _build_ac_snapshot(state, project_state) -> AcSnapshot | None:
    ac_output = st.session_state.get("ac_output") or project_state.get("ac_results") or state.ac_results
    if not isinstance(ac_output, dict) or not ac_output:
        return None
    ac_inputs = project_state.get("ac_inputs") or state.ac_inputs
    if not isinstance(ac_inputs, dict):
        ac_inputs = {}
    return AcSnapshot(inputs=ac_inputs, output=ac_output, results={})


def _resolve_ac_blocks_total(ac_output: dict) -> int:
    if not isinstance(ac_output, dict):
        return 1
    value = ac_output.get("num_blocks") or ac_output.get("ac_blocks_total")
    try:
        value = int(value)
    except Exception:
        value = 1
    return max(1, value)


def _execute_sld_pipeline(*, bundle, ac_snapshot, options, plugin_id: str, actor: str):
    return run_sld_pipeline_from_run_bundle(
        bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        plugin_id=plugin_id,
        actor=actor,
    )


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

    st.header("Single Line Diagram")
    st.caption("Read runtime run data, execute the SLD pipeline, preview the result, and download artifacts.")

    run_id_default = st.session_state.get("dc_last_run_id", "")
    run_id = st.text_input("Run ID", value=str(run_id_default or "")).strip()

    ac_snapshot = _build_ac_snapshot(state, project_state)
    if ac_snapshot is None:
        st.warning("AC snapshot not found. Run AC sizing before generating SLD.")

    ac_blocks_total = _resolve_ac_blocks_total(ac_snapshot.output if ac_snapshot else {})
    group_index = st.selectbox(
        "AC Block Group",
        list(range(1, ac_blocks_total + 1)),
        index=0,
        disabled=not ac_snapshot,
    )

    display_col1, display_col2, display_col3 = st.columns(3)
    theme = display_col1.selectbox("Theme", ["dark", "light"], index=0)
    compact_mode = display_col2.checkbox("Compact Mode", value=False)
    draw_summary = display_col3.checkbox("Draw Summary", value=False)

    override_mode = st.checkbox(
        "Enable Engineering Override Mode",
        value=False,
        help="Draft-only mode. Use explicit engineering overrides only when authoritative inputs are incomplete.",
    )
    overrides = None
    if override_mode:
        st.warning("Engineering override mode is active. The generated SLD will be treated as a non-official draft.")
        with st.expander("SLD Override Inputs", expanded=True):
            overrides = render_electrical_inputs(legacy_sld_override_preset(), key_prefix="sld_override")
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

    if st.button("Generate SLD", disabled=not run_id or not ac_snapshot):
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
