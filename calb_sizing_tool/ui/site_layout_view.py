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
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderOptions
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.external_layout_service import (
    generate_layout_prompt,
    list_external_submissions,
    review_external_layout,
    submit_external_layout_artifact,
)
from calb_sizing_tool.services.layout_service import render_layout_from_run_bundle
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
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
    auth_user = get_auth_user()

    st.header("Site Layout")
    st.caption("Generate layout from run_id via plugin renderer.")

    run_id_default = st.session_state.get("dc_last_run_id", "")
    run_id = st.text_input("Run ID", value=str(run_id_default or "")).strip()

    ac_snapshot = _build_ac_snapshot(state, project_state)
    if ac_snapshot is None:
        st.warning("AC snapshot not found. Run AC sizing before generating layout.")

    ac_blocks_total = _resolve_ac_blocks_total(ac_snapshot.output if ac_snapshot else {})
    block_index = st.selectbox(
        "AC Block Group",
        list(range(1, ac_blocks_total + 1)),
        index=0,
        disabled=not ac_snapshot,
    )
    arrangement = st.selectbox(
        "DC Block arrangement",
        ["Auto", "2x2", "1x4", "4x1"],
        index=0,
        disabled=not ac_snapshot,
    )
    show_skid = st.checkbox("Show PCS&MVT SKID", value=True, disabled=not ac_snapshot)

    registry = get_plugin_registry()
    plugins = registry.list_by_artifact("layout_svg")
    plugin_ids = [plugin.metadata.plugin_id for plugin in plugins]
    selected_plugin = st.selectbox(
        "Renderer",
        plugin_ids,
        index=0,
        format_func=lambda pid: registry.get(pid).metadata.plugin_name if registry.get(pid) else pid,
    )

    if st.button("Generate Layout", disabled=not run_id or not ac_snapshot):
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

        options = LayoutRenderOptions(
            block_index=block_index,
            arrangement=arrangement,
            show_skid=show_skid,
        )
        try:
            artifact_bundle = render_layout_from_run_bundle(
                bundle,
                ac_snapshot=ac_snapshot,
                options=options,
                plugin_id=selected_plugin,
                actor=auth_user.username,
            )
        except Exception as exc:
            st.error(f"Layout generation failed: {exc}")
            return

        st.session_state["layout_artifacts"] = artifact_bundle
        st.success("Layout generated and artifacts registered.")

    artifact_bundle = st.session_state.get("layout_artifacts")
    if artifact_bundle:
        artifacts = {item["artifact_kind"]: item for item in artifact_bundle.artifacts}
        svg_item = artifacts.get("layout_svg")
        png_item = artifacts.get("layout_png")
        spec_item = artifacts.get("layout_spec_json")

        st.subheader("Preview")
        if png_item and png_item.get("content"):
            st.image(png_item["content"], use_container_width=True)
        elif svg_item and svg_item.get("content"):
            st.components.v1.html(svg_item["content"].decode("utf-8"), height=640, scrolling=True)

        st.subheader("Downloads")
        if spec_item:
            st.download_button(
                "Download layout_spec.json",
                spec_item["content"],
                spec_item.get("file_name") or "layout_spec.json",
                "application/json",
            )
        if svg_item:
            st.download_button(
                "Download layout SVG",
                svg_item["content"],
                svg_item.get("file_name") or "layout_render.svg",
                "image/svg+xml",
            )
        if png_item:
            st.download_button(
                "Download layout PNG",
                png_item["content"],
                png_item.get("file_name") or "layout_render.png",
                "image/png",
            )

    st.markdown("---")
    st.subheader("AI Layout Prompt")
    if st.button("Generate Prompt Payload", disabled=not run_id):
        try:
            prompt_result = generate_layout_prompt(
                run_id=run_id,
                auth_user=auth_user,
                options=LayoutRenderOptions(block_index=block_index, arrangement=arrangement),
            )
            st.session_state["layout_prompt_payload"] = prompt_result["payload"]
            st.session_state["layout_prompt_text"] = prompt_result["prompt_text"]
            st.success("Prompt payload generated.")
        except Exception as exc:
            st.error(f"Prompt generation failed: {exc}")

    prompt_payload = st.session_state.get("layout_prompt_payload")
    prompt_text = st.session_state.get("layout_prompt_text")
    if prompt_payload:
        st.download_button(
            "Download layout_prompt_payload.json",
            __import__("json").dumps(prompt_payload, indent=2, sort_keys=True),
            "layout_prompt_payload.json",
            "application/json",
        )
    if prompt_text:
        st.download_button(
            "Download prompt.txt",
            prompt_text,
            "layout_prompt.txt",
            "text/plain",
        )

    st.subheader("External AI Submission")
    upload = st.file_uploader("Upload AI-generated layout (PNG or SVG)", type=["png", "svg"])
    notes = st.text_area("Submission notes", height=80)
    if st.button("Submit AI Layout", disabled=not run_id or upload is None):
        if upload is None:
            st.error("Please upload a file.")
        else:
            try:
                submission = submit_external_layout_artifact(
                    run_id=run_id,
                    auth_user=auth_user,
                    file_bytes=upload.getvalue(),
                    file_name=upload.name,
                    media_type=upload.type or "image/png",
                    notes=notes.strip() or None,
                )
                st.success(f"Submission created: {submission['submission_id']}")
            except Exception as exc:
                st.error(f"Submission failed: {exc}")

    if run_id:
        submissions = list_external_submissions(run_id)
    else:
        submissions = []

    if submissions:
        st.subheader("AI Submissions")
        for submission in submissions:
            cols = st.columns([2.5, 1.5, 1.5, 2.0])
            cols[0].write(submission["submission_id"])
            cols[1].write(submission["status"])
            cols[2].write(submission.get("ai_label"))
            cols[3].write(submission.get("actor"))
            if auth_user.is_admin:
                with st.expander(f"Review {submission['submission_id']}", expanded=False):
                    decision = st.selectbox(
                        "Decision",
                        ["approve", "reject", "request_revision"],
                        key=f"decision_{submission['submission_id']}",
                    )
                    comment = st.text_area(
                        "Review comments",
                        key=f"comment_{submission['submission_id']}",
                        height=60,
                    )
                    if st.button("Submit Review", key=f"review_{submission['submission_id']}"):
                        try:
                            result = review_external_layout(
                                submission_id=submission["submission_id"],
                                decision=decision,
                                reviewer=auth_user,
                                comments=comment.strip() or None,
                            )
                            st.success(f"Review saved: {result['status']}")
                        except Exception as exc:
                            st.error(f"Review failed: {exc}")
