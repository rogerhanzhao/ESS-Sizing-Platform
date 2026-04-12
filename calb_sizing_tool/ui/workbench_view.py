from __future__ import annotations

import re

import streamlit as st

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import (
    get_workspace_context,
    navigate_to,
    restore_run_bundle_to_session,
    set_active_case,
    set_active_project,
)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "item"


def _ensure_schema() -> None:
    with session_scope() as session:
        Base.metadata.create_all(bind=session.get_bind())


def _format_dt(value) -> str:
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def _workspace_caption(context: dict) -> str:
    project = context.get("project_name") or "No project"
    case = context.get("case_name") or "No case"
    run_id = context.get("run_id") or "No run"
    return f"Project: {project} | Case: {case} | Run: {run_id}"


def show() -> None:
    init_project_state()
    _ensure_schema()

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

    st.title("Workbench")
    st.caption("Project = physical opportunity/site. Case = technical option set. Run = one calculation snapshot.")

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        projects = [
            {
                "project_id": project.project_id,
                "project_code": project.project_code,
                "project_name": project.project_name,
                "created_at": project.created_at,
            }
            for project in access.list_projects()
        ]

    context = get_workspace_context()
    if context["project_id"] and not any(item["project_id"] == context["project_id"] for item in projects):
        set_active_project(project_id=None, project_code=None, project_name=None)
        context = get_workspace_context()

    active_project = next((item for item in projects if item["project_id"] == context["project_id"]), None)
    if active_project is None and projects:
        active_project = projects[0]
        set_active_project(
            project_id=active_project["project_id"],
            project_code=active_project["project_code"],
            project_name=active_project["project_name"],
        )
        context = get_workspace_context()

    cases: list[dict] = []
    if context["project_id"]:
        with session_scope() as session:
            access = AccessControlService(session, auth_user)
            try:
                cases = [
                    {
                        "sizing_case_id": case.sizing_case_id,
                        "case_code": case.case_code,
                        "case_name": case.case_name,
                        "scenario_mode": case.scenario_mode,
                        "created_at": case.created_at,
                    }
                    for case in access.list_cases_by_project(context["project_id"])
                ]
            except PermissionError:
                cases = []

    active_case = next((item for item in cases if item["sizing_case_id"] == context["case_id"]), None)
    if active_case is None and cases:
        active_case = cases[0]
        set_active_case(
            case_id=active_case["sizing_case_id"],
            case_code=active_case["case_code"],
            case_name=active_case["case_name"],
        )
        context = get_workspace_context()

    runs: list[dict] = []
    if context["case_id"]:
        with session_scope() as session:
            access = AccessControlService(session, auth_user)
            try:
                runs = [
                    {
                        "sizing_run_id": run.sizing_run_id,
                        "created_at": run.created_at,
                        "scenario_id": (run.input_summary_json or {}).get("scenario_id"),
                        "poi_power_req_mw": (run.input_summary_json or {}).get("poi_power_req_mw"),
                        "poi_energy_req_mwh": (run.input_summary_json or {}).get("poi_energy_req_mwh"),
                        "margin_mwh": (run.output_summary_json or {}).get("margin_mwh"),
                        "converged": (run.output_summary_json or {}).get("converged"),
                    }
                    for run in access.list_runs_by_case(context["case_id"])
                ]
            except PermissionError:
                runs = []

    ctx_col1, ctx_col2, ctx_col3 = st.columns(3)
    ctx_col1.metric("Active Project", context.get("project_name") or "None")
    ctx_col2.metric("Active Case", context.get("case_name") or "None")
    ctx_col3.metric("Active Run", context.get("run_id") or "None")
    st.caption(_workspace_caption(context))

    action_cols = st.columns(4)
    if action_cols[0].button("Continue DC Sizing", use_container_width=True, disabled=not context.get("case_id")):
        navigate_to("DC Sizing")
        st.rerun()
    if action_cols[1].button("Open AC Sizing", use_container_width=True, disabled=not context.get("run_id")):
        navigate_to("AC Sizing")
        st.rerun()
    if action_cols[2].button("Open SLD", use_container_width=True, disabled=not context.get("run_id")):
        navigate_to("Single Line Diagram")
        st.rerun()
    if action_cols[3].button("Open Report Export", use_container_width=True, disabled=not context.get("run_id")):
        navigate_to("Report Export")
        st.rerun()

    project_col, case_col, run_col = st.columns([1.1, 1.1, 1.5])

    with project_col:
        st.subheader("Projects")
        if projects:
            project_ids = [item["project_id"] for item in projects]
            current_project_id = context.get("project_id") if context.get("project_id") in project_ids else project_ids[0]
            selected_project_id = st.selectbox(
                "Active Project",
                project_ids,
                index=project_ids.index(current_project_id),
                format_func=lambda item_id: next(
                    item["project_name"] for item in projects if item["project_id"] == item_id
                ),
                key="workbench_project_select",
            )
            if selected_project_id != context.get("project_id"):
                selected_project = next(item for item in projects if item["project_id"] == selected_project_id)
                set_active_project(
                    project_id=selected_project["project_id"],
                    project_code=selected_project["project_code"],
                    project_name=selected_project["project_name"],
                )
                st.rerun()
        else:
            st.info("No projects yet.")

        with st.form("workbench_create_project"):
            name = st.text_input("New Project Name")
            description = st.text_area("Project Description", height=80)
            submitted = st.form_submit_button("Create Project", use_container_width=True)
            if submitted:
                if not name.strip():
                    st.error("Project name is required.")
                else:
                    with session_scope() as session:
                        auth_repo = AuthRepository(session)
                        repo = CaseRepository(session)
                        project = repo.get_or_create_project(
                            project_code=_slug(name),
                            project_name=name.strip(),
                            description=description.strip() or None,
                            source_ref="workbench",
                        )
                        session.flush()
                        auth_repo.ensure_system_roles()
                        auth_repo.add_project_member(
                            project_id=project.project_id,
                            user_id=auth_user.user_id,
                            role_code="normal_user",
                        )
                        session.flush()
                        set_active_project(
                            project_id=project.project_id,
                            project_code=project.project_code,
                            project_name=project.project_name,
                        )
                    st.success(f"Project created: {name.strip()}")
                    st.rerun()

        if projects:
            st.caption("Accessible projects")
            for item in projects[:8]:
                prefix = "Active" if item["project_id"] == context.get("project_id") else "Open"
                st.write(f"{prefix}: {item['project_name']} | {item['project_code']} | {_format_dt(item['created_at'])}")

    with case_col:
        st.subheader("Cases")
        if not context.get("project_id"):
            st.info("Create or select a project first.")
        else:
            if cases:
                case_ids = [item["sizing_case_id"] for item in cases]
                current_case_id = context.get("case_id") if context.get("case_id") in case_ids else case_ids[0]
                selected_case_id = st.selectbox(
                    "Active Case",
                    case_ids,
                    index=case_ids.index(current_case_id),
                    format_func=lambda item_id: next(
                        item["case_name"] for item in cases if item["sizing_case_id"] == item_id
                    ),
                    key="workbench_case_select",
                )
                if selected_case_id != context.get("case_id"):
                    selected_case = next(item for item in cases if item["sizing_case_id"] == selected_case_id)
                    set_active_case(
                        case_id=selected_case["sizing_case_id"],
                        case_code=selected_case["case_code"],
                        case_name=selected_case["case_name"],
                    )
                    st.rerun()
            else:
                st.info("No cases under the current project.")

            with st.form("workbench_create_case"):
                name = st.text_input("New Case Name")
                scenario_mode = st.selectbox(
                    "Scenario Mode",
                    ["container_only", "cabinet_only", "hybrid"],
                    index=0,
                )
                submitted = st.form_submit_button("Create Case", use_container_width=True)
                if submitted:
                    if not name.strip():
                        st.error("Case name is required.")
                    else:
                        with session_scope() as session:
                            repo = CaseRepository(session)
                            access = AccessControlService(session, auth_user)
                            access.ensure_project_access(context["project_id"])
                            project_code = context.get("project_code") or _slug(context.get("project_name") or "project")
                            case = repo.create_case(
                                project_id=context["project_id"],
                                case_code=f"{project_code}-{_slug(name)}",
                                case_name=name.strip(),
                                stage_scope="dc",
                                scenario_mode=scenario_mode,
                                input_json={},
                                source_ref="workbench",
                            )
                            session.flush()
                            set_active_case(
                                case_id=case.sizing_case_id,
                                case_code=case.case_code,
                                case_name=case.case_name,
                            )
                        st.success(f"Case created: {name.strip()}")
                        st.rerun()

            if cases:
                st.caption("Cases under current project")
                for item in cases[:10]:
                    prefix = "Active" if item["sizing_case_id"] == context.get("case_id") else "Open"
                    st.write(
                        f"{prefix}: {item['case_name']} | {item['scenario_mode']} | {_format_dt(item['created_at'])}"
                    )

    with run_col:
        st.subheader("Run Registry")
        if not context.get("case_id"):
            st.info("Select a case to see runs.")
        elif not runs:
            st.info("No runs yet. Start with DC sizing.")
        else:
            st.caption("Recent runs for the active case")
            for item in runs[:12]:
                row_cols = st.columns([2.5, 1.4, 1.2, 1.2, 1.0])
                row_cols[0].write(item["sizing_run_id"])
                row_cols[1].write(_format_dt(item["created_at"]))
                row_cols[2].write(item["scenario_id"] or "-")
                row_cols[3].write("Yes" if item["converged"] else "No")
                if row_cols[4].button("Restore", key=f"workbench_restore_{item['sizing_run_id']}"):
                    with session_scope() as session:
                        access = AccessControlService(session, auth_user)
                        bundle = access.load_dc_run_bundle(item["sizing_run_id"])
                    if not bundle:
                        st.error("Run not found.")
                    else:
                        restore_run_bundle_to_session(bundle, item["sizing_run_id"])
                        st.success(f"Run restored: {item['sizing_run_id']}")
                        st.rerun()

            latest = runs[0]
            st.markdown("---")
            st.write("Latest run")
            st.write(
                {
                    "run_id": latest["sizing_run_id"],
                    "created_at": _format_dt(latest["created_at"]),
                    "scenario_id": latest["scenario_id"],
                    "poi_power_req_mw": latest["poi_power_req_mw"],
                    "poi_energy_req_mwh": latest["poi_energy_req_mwh"],
                    "margin_mwh": latest["margin_mwh"],
                    "converged": latest["converged"],
                }
            )
