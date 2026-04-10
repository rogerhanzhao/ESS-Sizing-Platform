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
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.diagram_service import render_sld_from_run_bundle
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state


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
    st.caption("Generate SLD from run_id via plugin renderer.")

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

    theme = st.selectbox("Theme", ["dark", "light"], index=0)

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

        options = SldRenderOptions(group_index=group_index, theme=theme)
        try:
            artifact_bundle = render_sld_from_run_bundle(
                bundle,
                ac_snapshot=ac_snapshot,
                options=options,
                plugin_id=selected_plugin,
                actor=auth_user.username,
            )
        except Exception as exc:
            st.error(f"SLD generation failed: {exc}")
            return

        st.session_state["sld_artifacts"] = artifact_bundle
        st.success("SLD generated and artifacts registered.")

    artifact_bundle = st.session_state.get("sld_artifacts")
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
