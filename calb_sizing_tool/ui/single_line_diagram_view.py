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

from dataclasses import dataclass
from typing import Any

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_render_input import legacy_sld_override_preset
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.ac_mixed_station import head_fleet_ac_output_for_sld
from calb_sizing_tool.services.sld_data_source_service import AcSnapshotResolution, resolve_preferred_ac_snapshot
from calb_sizing_tool.services.sld_engineering_settings_service import (
    load_case_sld_project_settings,
    load_run_sld_project_settings,
)
from calb_sizing_tool.services.sld_pipeline_service import run_sld_pipeline_from_run_bundle
from calb_sizing_tool.services.sld_renderer_mode_service import (
    AVAILABLE_SLD_RENDERER_MODES,
    sld_renderer_mode_label,
)
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import get_project_state, init_project_state
from calb_sizing_tool.state.session_state import init_shared_state
from calb_sizing_tool.ui._ui import render_static_table
from calb_sizing_tool.state.workspace_state import get_workspace_context, navigate_now
from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs


@dataclass(frozen=True)
class SldRuntimeSourceStatus:
    source: str
    mode: str
    is_authoritative: bool
    force_draft: bool
    message: str


SLD_PREVIEW_CONTROL_SIGNATURE_KEY = "sld_preview_control_signature"


def _build_guest_dc_bundle() -> DcRunBundle | None:
    """Build a DcRunBundle from session state for guest users (no DB access)."""
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


def _positive_float(value: Any) -> float | None:
    try:
        resolved = float(value)
    except Exception:
        return None
    if resolved <= 0:
        return None
    return resolved


def _resolve_mv_nominal_voltage_kv(state, project_state, ac_snapshot: AcSnapshot | None) -> float | None:
    """Resolve the single visible MV voltage used by SLD settings.

    The resolved AC snapshot already carries the runtime source priority. Keep
    that value ahead of Streamlit/session fallbacks so stale page state cannot
    make RMU rated voltage drift away from the active MV value.
    """
    candidates = [
        ac_snapshot.output.get("mv_voltage_kv") if ac_snapshot and isinstance(ac_snapshot.output, dict) else None,
        ac_snapshot.output.get("grid_kv") if ac_snapshot and isinstance(ac_snapshot.output, dict) else None,
        ac_snapshot.output.get("mv_kv") if ac_snapshot and isinstance(ac_snapshot.output, dict) else None,
        ac_snapshot.output.get("source_poi_nominal_voltage_kv") if ac_snapshot and isinstance(ac_snapshot.output, dict) else None,
        ac_snapshot.inputs.get("grid_kv") if ac_snapshot and isinstance(ac_snapshot.inputs, dict) else None,
        ac_snapshot.inputs.get("mv_kv") if ac_snapshot and isinstance(ac_snapshot.inputs, dict) else None,
        ac_snapshot.inputs.get("poi_nominal_voltage_kv") if ac_snapshot and isinstance(ac_snapshot.inputs, dict) else None,
        (project_state.get("dc_inputs") or {}).get("poi_nominal_voltage_kv") if isinstance(project_state, dict) else None,
        getattr(state, "dc_inputs", {}).get("poi_nominal_voltage_kv") if hasattr(state, "dc_inputs") else None,
        st.session_state.get("poi_nominal_voltage_kv"),
    ]
    for raw in candidates:
        value = _positive_float(raw)
        if value is not None:
            return value
    return None


def _resolve_sld_runtime_source_status(ac_resolution: AcSnapshotResolution) -> SldRuntimeSourceStatus:
    source = str(ac_resolution.source or "none").strip() or "none"
    if ac_resolution.snapshot is None:
        return SldRuntimeSourceStatus(
            source="none",
            mode="unavailable",
            is_authoritative=False,
            force_draft=False,
            message="SLD runtime data source: unavailable. Generate or restore run data before creating SLD.",
        )
    if source == "persisted_run_snapshot":
        return SldRuntimeSourceStatus(
            source=source,
            mode="authoritative_persisted",
            is_authoritative=True,
            force_draft=False,
            message="SLD runtime data source: authoritative persisted mode (persisted run AC snapshot).",
        )
    if source == "compatibility_adapter":
        return SldRuntimeSourceStatus(
            source=source,
            mode="draft_session",
            is_authoritative=False,
            force_draft=True,
            message=(
                "SLD runtime data source: draft/session mode (compatibility adapter). "
                "No persisted AC runtime snapshot was found for this run."
            ),
        )
    if source == "session_cache":
        return SldRuntimeSourceStatus(
            source=source,
            mode="draft_session",
            is_authoritative=False,
            force_draft=True,
            message=(
                "SLD runtime data source: draft/session mode (session cache fallback). "
                "Persist the AC runtime snapshot before using formal SLD output."
            ),
        )
    return SldRuntimeSourceStatus(
        source=source,
        mode="draft_session",
        is_authoritative=False,
        force_draft=True,
        message=f"SLD runtime data source: draft/session mode ({source}).",
    )


def _build_sld_render_options(
    *,
    group_index: int,
    theme: str,
    compact_mode: bool,
    draw_summary: bool,
    user_override_mode: bool,
    overrides,
    runtime_status: SldRuntimeSourceStatus,
    renderer_mode: str = "engineering_v2",
) -> SldRenderOptions:
    return SldRenderOptions(
        group_index=group_index,
        theme=theme,
        compact_mode=compact_mode,
        draw_summary=draw_summary,
        override_mode=bool(user_override_mode or runtime_status.force_draft),
        renderer_mode=renderer_mode,
        overrides=overrides,
    )


def _validate_ac_snapshot_context(
    ac_output: dict[str, Any] | None,
    *,
    expected_run_id: str | None,
    expected_case_id: str | None = None,
    expected_project_id: str | None = None,
) -> str | None:
    if not isinstance(ac_output, dict) or not ac_output:
        return "AC snapshot not found. Run AC sizing before generating SLD."

    # Governed product output is allowed to reach the SLD only after the AC
    # product mix has been checked at the POI.  Historical governed snapshots
    # predate this contract and may have one PCS per aging-energy DC Block,
    # which can materially overbuild power; force a fresh AC run instead of
    # rendering that old topology as a current engineering selection.
    from calb_sizing_tool.services.governed_ac_block_service import (
        governed_poi_power_closure_issue,
    )

    power_closure_issue = governed_poi_power_closure_issue(ac_output)
    if power_closure_issue:
        return power_closure_issue

    source_run_id = str(ac_output.get("source_run_id") or "").strip()
    if not source_run_id:
        return "AC snapshot is missing source_run_id provenance. Re-run AC sizing from the active database run."

    def _short(uid: str) -> str:
        return f"··{uid[-8:]}" if uid and len(uid) >= 8 else uid

    expected_run_id = str(expected_run_id or "").strip()
    if expected_run_id and source_run_id != expected_run_id:
        return (
            f"AC snapshot is from a different run ({_short(source_run_id)}) "
            f"than the active run ({_short(expected_run_id)}). "
            "Re-run AC sizing for the current run before generating SLD."
        )

    expected_case_id = str(expected_case_id or "").strip()
    source_case_id = str(ac_output.get("source_case_id") or "").strip()
    if expected_case_id and source_case_id and source_case_id != expected_case_id:
        return (
            "AC snapshot belongs to a different case than the active case. "
            "Re-run AC sizing for the current case before generating SLD."
        )

    expected_project_id = str(expected_project_id or "").strip()
    source_project_id = str(ac_output.get("source_project_id") or "").strip()
    if expected_project_id and source_project_id and source_project_id != expected_project_id:
        return (
            "AC snapshot belongs to a different project than the active project. "
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


def _execute_sld_pipeline(
    *,
    bundle,
    ac_snapshot,
    options,
    plugin_id: str,
    actor: str,
    project_settings: dict[str, Any] | None = None,
    register_artifacts: bool = True,
):
    return run_sld_pipeline_from_run_bundle(
        bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        plugin_id=plugin_id,
        actor=actor,
        register_artifacts=register_artifacts,
    )


def _clear_sld_preview() -> None:
    st.session_state.pop("sld_artifacts", None)
    st.session_state.pop("sld_pipeline_meta", None)


def _build_sld_preview_control_signature(
    *,
    run_id: str | None,
    group_index: int,
    theme: str,
    compact_mode: bool,
    draw_summary: bool,
    renderer_mode: str,
    plugin_id: str,
) -> dict[str, Any]:
    return {
        "run_id": str(run_id or "").strip(),
        "group_index": int(group_index),
        "theme": str(theme or "").strip(),
        "compact_mode": bool(compact_mode),
        "draw_summary": bool(draw_summary),
        "renderer_mode": str(renderer_mode or "").strip(),
        "plugin_id": str(plugin_id or "").strip(),
    }


def _sync_sld_preview_control_signature(signature: dict[str, Any]) -> bool:
    previous = st.session_state.get(SLD_PREVIEW_CONTROL_SIGNATURE_KEY)
    st.session_state[SLD_PREVIEW_CONTROL_SIGNATURE_KEY] = dict(signature)
    if previous is None or previous == signature:
        return False
    had_preview = bool(st.session_state.get("sld_artifacts") or st.session_state.get("sld_pipeline_meta"))
    if had_preview:
        _clear_sld_preview()
    return had_preview


def show() -> None:
    state = init_shared_state()
    init_project_state()
    project_state = get_project_state()

    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    auth_user = get_auth_user()

    workspace = get_workspace_context()

    from calb_sizing_tool.ui._ui import (
        compact_note,
        page_header,
        render_pipeline_next_steps,
        section_header,
        workspace_status_bar,
    )
    page_header("Single Line Diagram", "System Schematic & Engineering Export")

    _is_guest = auth_context.is_guest

    if _is_guest:
        st.info(
            "👁 **Guest mode** — SLD generation runs from your session data. "
            "Formal engineering settings and artifact persistence are disabled.",
            icon=None,
        )

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
        # Show the session run_id as read-only info — no editable input needed
        run_id = str(run_id_default or "")
        if run_id:
            st.caption(f"Session run: `{run_id}`")
        else:
            st.warning("No DC sizing results found in this session. Run DC sizing first.")
    else:
        run_id = str(run_id_default or "").strip()
        with st.expander("Run source", expanded=False):
            run_id = st.text_input(
                "Run ID",
                value=str(run_id_default or ""),
                key="sld_run_id_override",
                help="Use the active workspace run by default. Override only for restore or trace checks.",
            ).strip()

    ac_resolution = _resolve_ac_snapshot(
        state,
        project_state,
        run_id=run_id or workspace.get("run_id"),
    )
    ac_snapshot = ac_resolution.snapshot
    if not _is_guest:
        # For registered users: enforce strict run/case/project cross-validation
        ac_snapshot_issue = _validate_ac_snapshot_context(
            ac_snapshot.output if ac_snapshot else None,
            expected_run_id=run_id or workspace.get("run_id"),
            expected_case_id=workspace.get("case_id"),
            expected_project_id=workspace.get("project_id"),
        )
        if ac_snapshot_issue:
            st.warning(ac_snapshot_issue)
            ac_snapshot = None
            ac_resolution = AcSnapshotResolution(snapshot=None, source="none")

    runtime_status = _resolve_sld_runtime_source_status(ac_resolution)
    if runtime_status.is_authoritative:
        st.caption(runtime_status.message)
    elif runtime_status.mode == "draft_session":
        st.warning(runtime_status.message)
    else:
        st.warning(runtime_status.message)

    # Mixed AC Block station: the SLD authoritative contract is uniform-only
    # (SLD V1 requires a uniform PCS count per AC Block), so a head+tail station
    # cannot be rendered directly. Project it onto its HEAD AC-Block fleet — a
    # real uniform sub-station of the site — and render that, while the report's
    # §6.1 schedule carries the full head + tail composition. This keeps the SLD
    # coherent front-to-back instead of failing the AC->SLD adapter.
    if ac_snapshot is not None and bool((ac_snapshot.output or {}).get("ac_block_mixed")):
        representative = head_fleet_ac_output_for_sld(ac_snapshot.output or {})
        if representative is not None:
            head_count = int(representative.get("sld_head_fleet_block_count") or 0)
            head_mw = float(representative.get("block_size_mw") or 0.0)
            head_pcs = int(representative.get("pcs_per_block") or 0)
            head_kw = float(representative.get("pcs_kw") or 0.0)
            ac_snapshot = ac_snapshot.model_copy(update={"output": representative})
            st.info(
                f"🔀 **Mixed AC Block station** — the SLD renders the representative "
                f"**head AC Block fleet** ({head_count} × {head_mw:.2f} MW, "
                f"{head_pcs}×{head_kw:.0f} kW). Tail AC Block model(s) differ and are "
                f"listed in the report's AC Block schedule (§6.1). A per-model SLD is a "
                f"planned SLD V2 enhancement.",
                icon=None,
            )
        else:
            st.warning(
                "Mixed AC Block station detected, but no head AC Block fleet could be "
                "resolved for the SLD. See the report's AC Block schedule for the full "
                "per-block composition."
            )
            ac_snapshot = None
            ac_resolution = AcSnapshotResolution(snapshot=None, source="none")

    ac_blocks_total = _resolve_ac_blocks_total(ac_snapshot.output if ac_snapshot else {})
    mv_nominal_voltage_kv = _resolve_mv_nominal_voltage_kv(state, project_state, ac_snapshot)
    persisted_project_settings = load_case_sld_project_settings(workspace.get("case_id"))
    group_choices = list(range(1, ac_blocks_total + 1)) if ac_blocks_total > 0 else [1]
    section_header(
        "Generation Setup",
        "Select the AC block group, visual density, renderer mode, and output plugin.",
        eyebrow="Step 1",
    )
    group_index = st.selectbox(
        "AC Block Group",
        group_choices,
        index=0,
        disabled=not ac_snapshot or ac_blocks_total <= 0,
    )

    section_header("Display Settings", eyebrow="Step 2")
    theme = st.selectbox("Theme", ["dark", "light"], index=0)
    display_flag_col1, display_flag_col2 = st.columns(2)
    compact_mode = display_flag_col1.checkbox("Compact Mode", value=False)
    draw_summary = display_flag_col2.checkbox("Draw Summary", value=False)
    renderer_mode_choices = list(AVAILABLE_SLD_RENDERER_MODES)
    renderer_mode_default_index = 0
    renderer_mode = st.selectbox(
        "SLD Renderer Mode",
        renderer_mode_choices,
        index=renderer_mode_default_index,
        format_func=sld_renderer_mode_label,
        key="sld_renderer_mode_public_v2",
        help=(
            "Engineering V2 is the professional SLD candidate. Legacy compatibility "
            "is kept only as an old-style comparison path."
        ),
    )
    if renderer_mode == "legacy_server":
        st.warning("Renderer mode: legacy compatibility path; this is an old-style comparison drawing.")
    elif renderer_mode == "engineering_v2":
        st.caption("Renderer mode: engineering_v2 professional SLD candidate.")
    else:
        st.warning("Renderer mode is retired and should only be used for internal compatibility checks.")

    if not _is_guest:
        if workspace.get("case_id"):
            if persisted_project_settings:
                st.caption("Formal engineering settings source: persisted case settings")
            else:
                st.warning(
                    "Formal engineering settings are not yet saved for this case. "
                    "Open Engineering Settings before using strict mode, or switch to draft override mode."
                )
            if st.button("Open Engineering Settings", use_container_width=False):
                navigate_now("Engineering Settings")
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
        if runtime_status.force_draft:
            st.warning(
                "Formal / strict generation is disabled for the current AC source. "
                "Generate SLD will force draft/session mode until a persisted AC runtime snapshot exists."
            )
        else:
            compact_note("Formal mode uses strict runtime inputs only. Missing required engineering inputs will fail fast.")

    registry = get_plugin_registry()
    plugins = registry.list_by_artifact("sld_svg")
    plugin_ids = [plugin.metadata.plugin_id for plugin in plugins]
    section_header("Renderer", eyebrow="Step 3")
    selected_plugin = st.selectbox(
        "Renderer",
        plugin_ids,
        index=0,
        format_func=lambda pid: registry.get(pid).metadata.plugin_name if registry.get(pid) else pid,
    )
    preview_control_signature = _build_sld_preview_control_signature(
        run_id=run_id,
        group_index=group_index,
        theme=theme,
        compact_mode=compact_mode,
        draw_summary=draw_summary,
        renderer_mode=renderer_mode,
        plugin_id=selected_plugin,
    )
    if _sync_sld_preview_control_signature(preview_control_signature):
        st.info("SLD preview cleared because run, group, theme, renderer mode, or renderer plugin changed.")

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
        if _is_guest:
            bundle = _build_guest_dc_bundle()
            if not bundle:
                st.error("No DC sizing results in session. Run DC sizing first.")
                return
            persisted_project_settings = None  # guests have no persisted settings
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

        options = _build_sld_render_options(
            group_index=group_index,
            theme=theme,
            compact_mode=compact_mode,
            draw_summary=draw_summary,
            user_override_mode=override_mode,
            renderer_mode=renderer_mode,
            overrides=overrides,
            runtime_status=runtime_status,
        )
        try:
            execution = _execute_sld_pipeline(
                bundle=bundle,
                ac_snapshot=ac_snapshot,
                options=options,
                project_settings=persisted_project_settings,
                plugin_id=selected_plugin,
                actor=auth_user.username,
                register_artifacts=not _is_guest,
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
            "renderer_mode": artifact_bundle.metadata.get("renderer_mode"),
            "renderer_lineage": artifact_bundle.metadata.get("renderer_lineage"),
            "preview_control_signature": preview_control_signature,
            "formal_readiness": artifact_bundle.metadata.get("formal_readiness"),
            "document_status": artifact_bundle.metadata.get("document_status"),
            "not_for_construction": artifact_bundle.metadata.get("not_for_construction"),
            "engineering_v2_graph_hash": artifact_bundle.metadata.get("engineering_v2_graph_hash"),
            "engineering_v2_layout_hash": artifact_bundle.metadata.get("engineering_v2_layout_hash"),
            "artifact_mode": artifact_bundle.metadata.get("artifact_mode"),
            "input_hash": artifact_bundle.metadata.get("input_hash"),
            "topology_hash": artifact_bundle.metadata.get("topology_hash"),
            "render_spec_hash": artifact_bundle.metadata.get("render_spec_hash"),
            "artifact_hashes": artifact_hashes,
            "artifacts_registered": bool(artifact_bundle.metadata.get("artifacts_registered", True)),
            "ac_runtime_source": runtime_status.source,
            "runtime_source_mode": runtime_status.mode,
            "forced_draft_by_source": bool(runtime_status.force_draft),
            "representative_of_mixed": bool((ac_snapshot.output or {}).get("sld_representative_of_mixed")),
        }
        artifacts_registered = bool(artifact_bundle.metadata.get("artifacts_registered", True))
        if not artifacts_registered:
            st.warning(
                "Concept SLD generated for this session preview. "
                "It is not registered or persisted; sign in to create a traceable run artifact."
            )
        elif artifact_bundle.metadata.get("document_status") == "official":
            st.success("Formal SLD generated and artifacts registered.")
        else:
            st.warning(
                "Concept SLD generated and artifacts registered. "
                "It is marked NOT FOR CONSTRUCTION until the readiness gate passes."
            )

    artifact_bundle = st.session_state.get("sld_artifacts")
    pipeline_meta = st.session_state.get("sld_pipeline_meta") or {}
    if pipeline_meta:
        document_status = str(pipeline_meta.get("document_status") or pipeline_meta.get("artifact_mode") or "concept")
        mode_label = {
            "official": "Formal / Released",
            "concept": "Concept / Not for construction",
            "draft_override": "Draft / Override",
        }.get(document_status, document_status)
        st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
        section_header("Pipeline Status", eyebrow="Result")
        _meta_run = pipeline_meta.get("run_id") or ""
        _meta_run_short = f"··{_meta_run[-8:]}" if len(_meta_run) >= 8 else (_meta_run or "—")
        st.caption(
            f"Run {_meta_run_short} | Group {pipeline_meta.get('group_index')} | "
            f"Document: {mode_label} | Topology {pipeline_meta.get('topology_nodes')} nodes / {pipeline_meta.get('topology_edges')} edges"
        )
        if pipeline_meta.get("runtime_source_mode"):
            st.caption(
                f"Runtime source `{pipeline_meta.get('ac_runtime_source')}` | "
                f"Source mode `{pipeline_meta.get('runtime_source_mode')}`"
            )
        renderer_version = pipeline_meta.get("renderer_version") or "n/a"
        renderer_mode = pipeline_meta.get("renderer_mode") or "n/a"
        st.caption(
            f"Renderer `{renderer_version}` | Mode `{renderer_mode}` | Input hash `{pipeline_meta.get('input_hash')}` | "
            f"Topology hash `{pipeline_meta.get('topology_hash')}`"
        )
        if renderer_mode == "engineering_v2":
            st.caption(
                f"Engineering V2 graph `{pipeline_meta.get('engineering_v2_graph_hash')}` | "
                f"layout `{pipeline_meta.get('engineering_v2_layout_hash')}`"
            )
        if document_status == "concept":
            st.warning("This SLD is a concept document and must not be used for construction or formal issue.")
        elif document_status == "draft_override":
            st.warning("This SLD was produced in draft/override mode and must not replace the formal baseline result.")
        elif pipeline_meta.get("draft_warnings"):
            st.info("No draft fallback was applied in formal mode.")
        formal_readiness = pipeline_meta.get("formal_readiness") or {}
        if formal_readiness:
            if formal_readiness.get("ready"):
                st.caption("Formal SLD readiness: passed.")
            else:
                st.warning(
                    "Formal SLD readiness: not passed. "
                    f"{formal_readiness.get('error_count', 0)} error(s), "
                    f"{formal_readiness.get('warning_count', 0)} warning(s)."
                )
        preview_run_id = str(pipeline_meta.get("run_id") or "").strip()
        if run_id and preview_run_id and preview_run_id != run_id:
            _prev_short = f"··{preview_run_id[-8:]}" if len(preview_run_id) >= 8 else preview_run_id
            _curr_short = f"··{run_id[-8:]}" if len(run_id) >= 8 else run_id
            st.warning(
                f"Current preview is from run {_prev_short}, but active run is {_curr_short}. "
                "Click Generate SLD to refresh."
            )
    if artifact_bundle:
        artifacts = {item["artifact_kind"]: item for item in artifact_bundle.artifacts}
        svg_item = artifacts.get("sld_svg")
        png_item = artifacts.get("sld_png")
        manifest_item = artifacts.get("sld_readiness_manifest_json")
        site_index_png_item = artifacts.get("site_electrical_index_png")
        site_index_svg_item = artifacts.get("site_electrical_index_svg")
        site_index_json_item = artifacts.get("site_electrical_index_json")
        design_basis_png_item = artifacts.get("sld_design_basis_schedule_png")
        design_basis_svg_item = artifacts.get("sld_design_basis_schedule_svg")
        design_basis_json_item = artifacts.get("sld_design_basis_schedule_json")
        interface_scope_png_item = artifacts.get("sld_interface_scope_png")
        interface_scope_svg_item = artifacts.get("sld_interface_scope_svg")
        interface_scope_json_item = artifacts.get("sld_interface_scope_json")

        section_header("Preview", eyebrow="Output")
        zoom = st.slider(
            "Zoom (%)",
            min_value=50,
            max_value=200,
            value=100,
            step=10,
            key="sld_zoom_level",
        )
        if png_item and png_item.get("content"):
            st.image(png_item["content"], width=int(1200 * zoom / 100))
        elif svg_item and svg_item.get("content"):
            scale = zoom / 100.0
            height = int(860 * scale)
            svg_html = (
                f"<div style='transform: scale({scale}); transform-origin: 0 0; overflow: visible;'>"
                f"{svg_item['content'].decode('utf-8')}"
                f"</div>"
            )
            st.components.v1.html(svg_html, height=height + 40, scrolling=True)

        if site_index_png_item or design_basis_png_item or interface_scope_png_item:
            section_header("Proposal Package Sheets", eyebrow="Output")
            st.caption(
                "SLD-01 indexes the complete AC Block population; SLD-02 is the selected typical block; "
                "SLD-03 records the sizing-derived design basis and formal-issue register; SLD-04 makes "
                "interface locations and project-confirmation boundaries explicit. "
                "These sheets are not a site layout or construction package."
            )
            if site_index_png_item:
                with st.expander("SLD-01 Site Electrical Index", expanded=False):
                    st.image(site_index_png_item["content"], width=1200)
            if design_basis_png_item:
                with st.expander("SLD-03 Electrical Design Basis Schedule", expanded=False):
                    st.image(design_basis_png_item["content"], width=1200)
            if interface_scope_png_item:
                with st.expander("SLD-04 Concept Interface / Scope", expanded=False):
                    st.image(interface_scope_png_item["content"], width=1200)

        hash_rows = []
        for artifact_kind, artifact_hash in (pipeline_meta.get("artifact_hashes") or {}).items():
            hash_rows.append({"artifact_kind": artifact_kind, "content_hash": artifact_hash})
        if hash_rows:
            section_header("Traceability", eyebrow="Output")
            render_static_table(hash_rows)
        section_header("Downloads", eyebrow="Output")
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
        if manifest_item:
            st.download_button(
                "Download SLD readiness manifest",
                manifest_item["content"],
                manifest_item.get("file_name") or "sld_readiness_manifest.json",
                "application/json",
            )
        for label, item, fallback_name, media_type in (
            ("Download Site Electrical Index SVG", site_index_svg_item, "site_electrical_index.svg", "image/svg+xml"),
            ("Download Site Electrical Index PNG", site_index_png_item, "site_electrical_index.png", "image/png"),
            ("Download Site Electrical Index JSON", site_index_json_item, "site_electrical_index.json", "application/json"),
            (
                "Download Electrical Design Basis SVG",
                design_basis_svg_item,
                "sld_design_basis_schedule.svg",
                "image/svg+xml",
            ),
            (
                "Download Electrical Design Basis PNG",
                design_basis_png_item,
                "sld_design_basis_schedule.png",
                "image/png",
            ),
            (
                "Download Electrical Design Basis JSON",
                design_basis_json_item,
                "sld_design_basis_schedule.json",
                "application/json",
            ),
            (
                "Download Concept Interface / Scope SVG",
                interface_scope_svg_item,
                "sld_interface_scope.svg",
                "image/svg+xml",
            ),
            (
                "Download Concept Interface / Scope PNG",
                interface_scope_png_item,
                "sld_interface_scope.png",
                "image/png",
            ),
            (
                "Download Concept Interface / Scope JSON",
                interface_scope_json_item,
                "sld_interface_scope.json",
                "application/json",
            ),
        ):
            if item:
                st.download_button(
                    label,
                    item["content"],
                    item.get("file_name") or fallback_name,
                    media_type,
                )

    render_pipeline_next_steps("Single Line Diagram", is_guest=_is_guest)
