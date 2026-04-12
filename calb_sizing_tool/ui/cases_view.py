from __future__ import annotations

import re

import streamlit as st

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import get_workspace_context, set_active_case


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "case"


def _ensure_schema() -> None:
    with session_scope() as session:
        Base.metadata.create_all(bind=session.get_bind())


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

    workspace = get_workspace_context()
    project_id = workspace.get("project_id")
    project_name = workspace.get("project_name")
    project_code = workspace.get("project_code")

    st.title("Cases")
    st.caption("Detailed case directory. Daily use is faster from Workbench.")
    if not project_id:
        st.warning("Select a project first.")
        return

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        try:
            access.ensure_project_access(project_id)
        except PermissionError:
            st.error("You do not have access to this project.")
            return

    st.caption(f"Active Project: {project_name} ({project_code})")

    with st.form("create_case"):
        name = st.text_input("Case Name")
        scenario_mode = st.selectbox(
            "Scenario Mode",
            ["container_only", "cabinet_only", "hybrid"],
            index=0,
        )
        submitted = st.form_submit_button("Create Case")
        if submitted:
            if not name.strip():
                st.error("Case name is required.")
            else:
                case_code = f"{project_code}-{_slug(name)}"
                with session_scope() as session:
                    repo = CaseRepository(session)
                    access = AccessControlService(session, auth_user)
                    try:
                        access.ensure_project_access(project_id)
                    except PermissionError:
                        st.error("You do not have access to this project.")
                        return
                    case = repo.create_case(
                        project_id=project_id,
                        case_code=case_code,
                        case_name=name.strip(),
                        stage_scope="dc",
                        scenario_mode=scenario_mode,
                        input_json={},
                        source_ref="ui",
                    )
                    session.flush()
                    set_active_case(
                        case_id=case.sizing_case_id,
                        case_code=case.case_code,
                        case_name=case.case_name,
                    )
                st.success(f"Case created: {name.strip()}")

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        cases = [
            {
                "sizing_case_id": case.sizing_case_id,
                "case_name": case.case_name,
                "case_code": case.case_code,
                "created_at": case.created_at,
            }
            for case in access.list_cases_by_project(project_id)
        ]

    st.subheader("Case List")
    if not cases:
        st.info("No cases found.")
        return

    for case in cases:
        cols = st.columns([3, 3, 2, 1.5])
        cols[0].write(case["case_name"])
        cols[1].write(case["case_code"])
        cols[2].write(case["created_at"].strftime("%Y-%m-%d %H:%M"))
        if cols[3].button("Open", key=f"case_open_{case['sizing_case_id']}"):
            set_active_case(
                case_id=case["sizing_case_id"],
                case_code=case["case_code"],
                case_name=case["case_name"],
            )
            st.success(f"Active case set: {case['case_name']}")
