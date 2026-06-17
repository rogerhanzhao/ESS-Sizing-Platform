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
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.services.layout_service import render_layout_from_run_bundle
from calb_sizing_tool.services.sld_data_source_service import AcSnapshotResolution, resolve_preferred_ac_snapshot
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state
from calb_sizing_tool.state.workspace_state import get_workspace_context


def _resolve_layout_ac_snapshot(
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


def _layout_ac_source_message(resolution: AcSnapshotResolution) -> tuple[str, str]:
    if resolution.snapshot is None:
        return (
            "warning",
            "AC snapshot not found. Run AC sizing before generating layout.",
        )
    if resolution.source == "persisted_run_snapshot":
        return (
            "caption",
            "Layout runtime data source: persisted AC snapshot attached to the active run.",
        )
    return (
        "warning",
        "Layout runtime data source: session compatibility fallback. Persist AC sizing before using layout as formal output.",
    )


def _resolve_ac_blocks_total(ac_output: dict) -> int:
    if not isinstance(ac_output, dict):
        return 1
    value = ac_output.get("num_blocks") or ac_output.get("ac_blocks_total")
    try:
        value = int(value)
    except Exception:
        value = 1
    return max(1, value)


def _build_guest_dc_bundle() -> DcRunBundle | None:
    snapshot = st.session_state.get("guest_dc_run_snapshot")
    if snapshot is None:
        return None
    run_id = st.session_state.get("dc_last_run_id") or "guest-session"
    return DcRunBundle(
        run_id=run_id,
        project_id=None,
        project_code=None,
        project_name="Guest Session",
        sizing_case_id=None,
        case_code=None,
        case_name="Guest Session",
        scenario_mode=None,
        input_snapshot=None,
        output_snapshot=None,
        snapshot=snapshot,
    )


def show() -> None:
    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()

    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    auth_user = get_auth_user()
    _is_guest = auth_context.is_guest
    workspace = get_workspace_context()

    from calb_sizing_tool.ui._ui import page_header, section_header, workspace_status_bar
    page_header("Site Layout", "Block Arrangement & Site Planning")

    if _is_guest:
        st.info("👁 **Guest mode** — layout runs from session data. AI prompt and external submission are disabled.", icon=None)

    run_id_default = (
        st.session_state.get("dc_last_run_id", "")
        if _is_guest
        else (workspace.get("run_id") or st.session_state.get("dc_last_run_id", ""))
    )
    workspace_status_bar(
        [
            ("Project", workspace.get("project_name") or "None"),
            ("Case", workspace.get("case_name") or "None"),
            ("Run", run_id_default or "None"),
        ]
    )
    if _is_guest:
        run_id = str(run_id_default or "")
        if run_id:
            st.caption(f"Session run: `{run_id}`")
        else:
            st.warning("No DC sizing results in session. Run DC sizing first.")
    else:
        run_id = str(run_id_default or "").strip()
        with st.expander("Run source", expanded=False):
            run_id = st.text_input(
                "Run ID",
                value=str(run_id_default or ""),
                key="layout_run_id_override",
                help="Use the current DC sizing run by default. Override only for restore or trace checks.",
            ).strip()

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)

    ac_resolution = _resolve_layout_ac_snapshot(
        state,
        project_state,
        run_id=run_id or workspace.get("run_id"),
    )
    ac_snapshot = ac_resolution.snapshot
    message_level, message = _layout_ac_source_message(ac_resolution)
    if message_level == "caption":
        st.caption(message)
    else:
        st.warning(message)

    section_header(
        "Render Options",
        "Select AC group, DC block arrangement, skid visibility, and renderer plugin.",
        eyebrow="Step 1",
    )
    ac_blocks_total = _resolve_ac_blocks_total(ac_snapshot.output if ac_snapshot else {})
    layout_col1, layout_col2 = st.columns(2)
    block_index = layout_col1.selectbox(
        "AC Block Group",
        list(range(1, ac_blocks_total + 1)),
        index=0,
        disabled=not ac_snapshot,
    )
    arrangement = layout_col2.selectbox(
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

    if st.button("Generate Layout", disabled=not run_id or not ac_snapshot, use_container_width=True):
        if _is_guest:
            bundle = _build_guest_dc_bundle()
            if not bundle:
                st.error("No DC sizing results in session. Run DC sizing first.")
                return
        else:
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

        section_header("Preview", eyebrow="Output")
        if png_item and png_item.get("content"):
            st.image(png_item["content"], use_container_width=True)
        elif svg_item and svg_item.get("content"):
            st.components.v1.html(svg_item["content"].decode("utf-8"), height=640, scrolling=True)

        section_header("Downloads", eyebrow="Output")
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

    if not _is_guest:
        st.divider()
        with st.expander("AI Layout Prompt", expanded=False):
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

        with st.expander("External AI Submission", expanded=False):
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

    if not _is_guest and run_id:
        submissions = list_external_submissions(run_id)
    else:
        submissions = []

    if submissions:
        with st.expander("AI Submission History", expanded=bool(submissions)):
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
