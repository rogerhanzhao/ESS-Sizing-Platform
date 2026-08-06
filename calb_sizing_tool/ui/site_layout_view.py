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

import json

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.services.layout_service import ARRANGEMENT_PLUGIN_ID
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
from calb_sizing_tool.services.site_constraint_readiness_service import (
    assess_site_constraint_readiness,
    build_site_constraint_template,
)
from calb_sizing_tool.services.site_constraint_set_service import (
    load_persisted_site_constraint_set,
    register_site_constraint_set,
)
from calb_sizing_tool.ui._ui import render_static_table
from calb_sizing_tool.services.sld_data_source_service import AcSnapshotResolution, resolve_preferred_ac_snapshot
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state
from calb_sizing_tool.state.workspace_state import artifact_run_id, get_workspace_context
from calb_sizing_tool.utils.files import human_bytes, upload_exceeds_limit


_CONSTRAINT_JSON_UPLOAD_LIMIT = 2 * 1024 * 1024  # 2 MiB — constraint-set JSON is tiny
_PERSISTED_CONSTRAINT_CACHE_KEY = "_persisted_site_constraint_cache"


def _load_persisted_constraint_set_cached(run_id: str) -> dict | None:
    """Session-cached read of the per-run persisted Site Constraint Set.

    Avoids a DB round-trip on every Streamlit rerun of this page. Keyed on
    run_id (switching runs reloads) and explicitly invalidated after a new set
    is registered — see _invalidate_persisted_constraint_cache.
    """
    cache = st.session_state.get(_PERSISTED_CONSTRAINT_CACHE_KEY)
    if isinstance(cache, dict) and cache.get("run_id") == run_id:
        return cache.get("data")
    data = load_persisted_site_constraint_set(run_id)
    st.session_state[_PERSISTED_CONSTRAINT_CACHE_KEY] = {"run_id": run_id, "data": data}
    return data


def _invalidate_persisted_constraint_cache() -> None:
    st.session_state.pop(_PERSISTED_CONSTRAINT_CACHE_KEY, None)


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
            "AC snapshot not found. Run AC sizing before generating a Typical AC Block Arrangement.",
        )
    if resolution.source == "persisted_run_snapshot":
        return (
            "caption",
            "Arrangement data source: persisted AC snapshot attached to the active run.",
        )
    return (
        "warning",
        "Arrangement data source: session compatibility fallback. Persist AC sizing before using this concept output.",
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

    from calb_sizing_tool.ui._ui import (
        page_header,
        render_pipeline_next_steps,
        section_header,
        workspace_status_bar,
    )
    page_header(
        "Typical AC Block Arrangement",
        "Concept equipment relationship for one AC Block — not a site plan or construction drawing.",
    )
    st.info(
        "This output shows one typical AC Block. It does not model site boundary, access, fire lanes, "
        "maintenance clearances, POI routing, or by-others scope.",
        icon=None,
    )

    if _is_guest:
        st.info("👁 **Guest mode** — concept arrangements run from session data. AI prompt and external submission are disabled.", icon=None)

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

    constraint_template = build_site_constraint_template(
        run_id=run_id,
        project_context={
            "project_code": workspace.get("project_code"),
            "project_name": workspace.get("project_name"),
            "case_code": workspace.get("case_code"),
            "case_name": workspace.get("case_name"),
        },
        ac_output=ac_snapshot.output if ac_snapshot else {},
    )
    constraint_set_for_assessment = constraint_template
    constraint_source = "generated_template"
    uploaded_constraint_set_valid = False
    section_header(
        "Concept Master Layout Readiness",
        "A deterministic Master Layout remains blocked until project-specific site constraints are provided.",
        eyebrow="P2 Gate",
    )
    st.caption(
        "This is an input-completeness check, not a code-compliance or construction-design check. "
        "No boundary, POI location, access route or clearance is assumed by the tool."
    )
    if not _is_guest:
        persisted_constraint_set = _load_persisted_constraint_set_cached(run_id) if run_id else None
        if persisted_constraint_set is not None:
            constraint_set_for_assessment = persisted_constraint_set
            constraint_source = "persisted_run_artifact"
            st.caption("Loaded the latest registered Site Constraint Set for this run.")
        uploaded_constraint_set = st.file_uploader(
            "Assess or register Site Constraint Set JSON",
            type=["json"],
            key="site_constraint_set_assessment_upload",
            help="The upload is assessed in the current session. It is registered only when you click the explicit register button below.",
        )
        if uploaded_constraint_set is not None and upload_exceeds_limit(
            uploaded_constraint_set, limit=_CONSTRAINT_JSON_UPLOAD_LIMIT
        ):
            st.error(
                f"Constraint Set JSON exceeds the {human_bytes(_CONSTRAINT_JSON_UPLOAD_LIMIT)} limit."
            )
        elif uploaded_constraint_set is not None:
            try:
                uploaded_payload = json.loads(uploaded_constraint_set.getvalue().decode("utf-8"))
                if not isinstance(uploaded_payload, dict):
                    raise ValueError("The JSON root must be an object.")
                constraint_set_for_assessment = uploaded_payload
                constraint_source = "uploaded_session"
                uploaded_constraint_set_valid = True
                st.info("Uploaded Site Constraint Set assessed in this session. It has not been registered or used to generate a Master Layout.")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                st.error(f"Site Constraint Set cannot be assessed: {exc}")

    master_layout_readiness = assess_site_constraint_readiness(constraint_set_for_assessment)
    readiness_rows = [
        {"requirement": item["label"], "status": item["status"], "action": item["message"]}
        for item in master_layout_readiness["items"]
    ]
    if master_layout_readiness["ready"]:
        st.success("Site Constraint Set is complete enough for the next constraint-validation phase. A Master Layout renderer is not yet enabled.")
    else:
        st.warning(
            f"Concept Master Layout is blocked: {master_layout_readiness['provided_count']} of "
            f"{master_layout_readiness['required_count']} prerequisite groups are provided."
        )
    with st.expander("Site Constraint Set readiness details", expanded=False):
        render_static_table(readiness_rows)
        st.download_button(
            "Download Site Constraint Set template",
            json.dumps(constraint_template, indent=2, sort_keys=True),
            "site_constraint_set.template.json",
            "application/json",
        )
        if not _is_guest:
            st.caption(f"Assessment source: `{constraint_source}`")
            register_constraint_set = st.button(
                "Register uploaded Site Constraint Set to this run",
                disabled=not uploaded_constraint_set_valid or not run_id,
                help="Registers the uploaded JSON as a versioned run artifact with an audit record. Incomplete sets remain blocked from Master Layout generation.",
            )
            if register_constraint_set:
                try:
                    with session_scope() as session:
                        access = AccessControlService(session, auth_user)
                        if access.load_dc_run_bundle(run_id) is None:
                            raise ValueError("Run not found.")
                    registration = register_site_constraint_set(
                        run_id=run_id,
                        constraint_set=constraint_set_for_assessment,
                        actor=auth_user.username,
                    )
                    # A new versioned set is now persisted; drop the cached read
                    # so the next rerun reflects it instead of the stale value.
                    _invalidate_persisted_constraint_cache()
                    st.success(
                        "Site Constraint Set registered as "
                        f"`{registration['constraint_set_status']}`. "
                        f"Readiness: {registration['master_layout_readiness']['provided_count']}/"
                        f"{registration['master_layout_readiness']['required_count']} groups."
                    )
                except (PermissionError, ValueError) as exc:
                    st.error(f"Site Constraint Set registration failed: {exc}")

    section_header(
        "Concept Options",
        "Select the representative AC Block. The arrangement itself is not "
        "adjustable here — it is the same drawing the exported report carries.",
        eyebrow="Step 1",
    )
    ac_blocks_total = _resolve_ac_blocks_total(ac_snapshot.output if ac_snapshot else {})

    # ONE renderer is offered, deliberately. The legacy grid renderer stays
    # registered for programmatic callers, but a picker that can produce a
    # different footprint for the same AC Block is exactly what the report and
    # the page were asked to stop doing. Engine, spacing and station size come
    # from calb_diagrams.typical_ac_block_arrangement — the report's own call.
    selected_plugin = ARRANGEMENT_PLUGIN_ID
    registry = get_plugin_registry()
    _renderer = registry.get(selected_plugin)
    st.caption(
        f"Renderer: **{_renderer.metadata.plugin_name if _renderer else selected_plugin}** — "
        "DC Block arrangement, clearances and station size are resolved by the "
        "rule profile (IFC / NFPA 855 / NFPA 850 / UL 9540A) and the AC Block "
        "class. An 8-PCS / 8-DC block draws the 40 ft central station with "
        "mirrored west and east DC fields. The exported report renders this "
        "identical drawing."
    )

    block_index = st.selectbox(
        "Typical AC Block",
        list(range(1, ac_blocks_total + 1)),
        index=0,
        disabled=not ac_snapshot,
    )
    # Retained only to satisfy LayoutRenderOptions; the rule-based engine ignores
    # both, because neither has a code basis.
    arrangement = "Auto"
    show_skid = True

    if st.button("Generate Typical AC Block Arrangement", disabled=not run_id or not ac_snapshot, use_container_width=True):
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
                # The arrangement belongs to the AC alternative it was drawn
                # from; with none selected this is the DC run, as before.
                artifact_run_id=artifact_run_id(),
            )
        except Exception as exc:
            st.error(f"Typical AC Block Arrangement generation failed: {exc}")
            return

        st.session_state["layout_artifacts"] = artifact_bundle
        st.success("Typical AC Block Arrangement generated and registered as CONCEPT ONLY.")

    artifact_bundle = st.session_state.get("layout_artifacts")
    if artifact_bundle:
        artifacts = {item["artifact_kind"]: item for item in artifact_bundle.artifacts}
        svg_item = artifacts.get("layout_svg")
        png_item = artifacts.get("layout_png")
        spec_item = artifacts.get("layout_spec_json")
        master_readiness_item = artifacts.get("layout_master_readiness_manifest_json")

        section_header("Concept Preview", eyebrow="Output")
        st.caption("CONCEPT ONLY — NOT FOR CONSTRUCTION. Full Site Layout requires a site constraint model and project-specific design rules.")
        if png_item and png_item.get("content"):
            st.image(png_item["content"], use_container_width=True)
        elif svg_item and svg_item.get("content"):
            st.components.v1.html(svg_item["content"].decode("utf-8"), height=640, scrolling=True)

        section_header("Downloads", eyebrow="Output")
        if spec_item:
            st.download_button(
                "Download typical AC Block arrangement spec",
                spec_item["content"],
                spec_item.get("file_name") or "typical_ac_block_arrangement_spec.json",
                "application/json",
            )
        if svg_item:
            st.download_button(
                "Download typical AC Block arrangement SVG",
                svg_item["content"],
                svg_item.get("file_name") or "typical_ac_block_arrangement.concept.svg",
                "image/svg+xml",
            )
        if png_item:
            st.download_button(
                "Download typical AC Block arrangement PNG",
                png_item["content"],
                png_item.get("file_name") or "typical_ac_block_arrangement.concept.png",
                "image/png",
            )
        if master_readiness_item:
            st.download_button(
                "Download Concept Master Layout readiness manifest",
                master_readiness_item["content"],
                master_readiness_item.get("file_name") or "concept_master_layout_readiness_manifest.json",
                "application/json",
            )

    if not _is_guest:
        st.divider()
        with st.expander("AI Concept Arrangement Prompt", expanded=False):
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
                    json.dumps(prompt_payload, indent=2, sort_keys=True),
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

        with st.expander("External AI Concept Submission", expanded=False):
            upload = st.file_uploader("Upload AI-generated concept arrangement (PNG or SVG)", type=["png", "svg"])
            notes = st.text_area("Submission notes", height=80)
            if st.button("Submit AI Concept Arrangement", disabled=not run_id or upload is None):
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

    render_pipeline_next_steps("Typical AC Block Arrangement", is_guest=_is_guest)
