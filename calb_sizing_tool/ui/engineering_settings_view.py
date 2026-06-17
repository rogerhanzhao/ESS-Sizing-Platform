from __future__ import annotations

from typing import Any

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.schemas.sld_render_input import legacy_sld_override_preset
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.sld_engineering_settings_service import (
    build_persisted_sld_project_settings,
    list_case_sld_project_settings_history,
    load_case_sld_project_settings_record,
    save_case_sld_project_settings,
)
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.workspace_state import get_workspace_context, navigate_now
from calb_sizing_tool.ui._ui import page_header, section_header, workspace_status_bar
from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs


def _resolve_active_case(auth_user, case_id: str | None) -> dict[str, Any] | None:
    resolved_case_id = str(case_id or "").strip()
    if not resolved_case_id:
        return None
    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        case_row = access.case_repo.get_case_by_id(resolved_case_id)
        if case_row is None:
            return None
        access.ensure_project_access(case_row.project_id)
        return {
            "sizing_case_id": case_row.sizing_case_id,
            "project_id": case_row.project_id,
            "case_code": case_row.case_code,
            "case_name": case_row.case_name,
        }


def _resolve_mv_nominal_voltage_kv(auth_user, run_id: str | None) -> float | None:
    resolved_run_id = str(run_id or "").strip()
    if resolved_run_id:
        try:
            with session_scope() as session:
                bundle = AccessControlService(session, auth_user).load_dc_run_bundle(resolved_run_id)
            if bundle and bundle.input_snapshot and isinstance(bundle.input_snapshot.payload, dict):
                case_input = bundle.input_snapshot.payload.get("case_input")
                if isinstance(case_input, dict):
                    value = case_input.get("poi_nominal_voltage_kv")
                    if value is not None:
                        return float(value)
        except Exception:
            pass
    for key in ("poi_nominal_voltage_kv", "grid_kv"):
        value = st.session_state.get(key)
        try:
            parsed = float(value)
        except Exception:
            continue
        if parsed > 0:
            return parsed
    return None


def _source_label(source: str) -> str:
    if source == "dedicated_table":
        return "Dedicated settings table"
    if source == "legacy_case_json":
        return "Legacy case JSON fallback"
    return "Not saved"


def _render_history(rows: list[dict[str, Any]]) -> None:
    section_header("Change History", "Recent saved settings events for the active case.")
    if not rows:
        st.info("No saved settings history for this case.")
        return
    st.dataframe(
        [
            {
                "Saved At": row.get("created_at"),
                "Actor": row.get("actor") or "-",
                "Source": row.get("source_ref") or "-",
                "Version": row.get("version_tag") or "-",
            }
            for row in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def show() -> None:
    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    if auth_context.is_guest:
        st.error("Engineering settings require a registered account.")
        return

    auth_user = get_auth_user()
    workspace = get_workspace_context()
    page_header("Engineering Settings", "Formal SLD project settings and review history")
    workspace_status_bar(
        [
            ("Project", workspace.get("project_name") or "None"),
            ("Case", workspace.get("case_name") or "None"),
            ("Run", workspace.get("run_id") or "None"),
        ]
    )

    case_info = _resolve_active_case(auth_user, workspace.get("case_id"))
    if case_info is None:
        st.warning("Select an active project case before editing formal engineering settings.")
        if st.button("Go to Workbench", use_container_width=False):
            navigate_now("Workbench")
        return

    record = load_case_sld_project_settings_record(case_info["sizing_case_id"])
    settings = record.get("project_settings") if isinstance(record.get("project_settings"), dict) else {}
    source = str(record.get("source") or "none")
    mv_nominal_voltage_kv = _resolve_mv_nominal_voltage_kv(auth_user, workspace.get("run_id"))

    with st.container(border=True):
        section_header("Current Source", "Settings used by formal SLD generation for the active case.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Settings Source", _source_label(source))
        c2.metric("MV Voltage Basis", f"{mv_nominal_voltage_kv:.1f} kV" if mv_nominal_voltage_kv else "Unavailable")
        c3.metric("Case", case_info["case_code"])
        if source == "legacy_case_json":
            st.warning(
                "This case is still reading legacy JSON settings. Saving from this page will move the active settings "
                "to the dedicated settings table."
            )
        elif source == "none":
            st.info("No formal SLD engineering settings are saved for this case yet.")

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
    section_header("Edit Formal Settings", "Saved values are used by strict/formal SLD mode.")
    with st.form("engineering_settings_form"):
        formal_settings_input = render_electrical_inputs(
            settings or legacy_sld_override_preset(),
            key_prefix="engineering_settings",
            mv_nominal_voltage_kv=mv_nominal_voltage_kv,
            section_title="Formal SLD Engineering Settings",
            section_caption="Persisted case-level settings used by formal / strict SLD mode.",
        )
        submitted = st.form_submit_button("Save Engineering Settings", use_container_width=True)

    if submitted:
        try:
            project_settings = build_persisted_sld_project_settings(
                formal_settings_input,
                mv_nominal_voltage_kv=mv_nominal_voltage_kv,
            )
            save_case_sld_project_settings(
                case_info["sizing_case_id"],
                project_settings,
                actor=auth_user.username,
                source_ref="engineering_settings_view",
            )
        except Exception as exc:
            st.error(f"Saving engineering settings failed: {exc}")
        else:
            st.success("Engineering settings saved.")
            st.rerun()

    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
    _render_history(list_case_sld_project_settings_history(case_info["sizing_case_id"]))

    if st.button("Go to Single Line Diagram", use_container_width=False):
        navigate_now("Single Line Diagram")
