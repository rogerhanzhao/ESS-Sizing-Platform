from __future__ import annotations

import pandas as pd
import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import get_workspace_context, navigate_now, set_active_case
from calb_sizing_tool.utils.text import SCENARIO_LABELS, fmt_dt


def show() -> None:
    init_project_state()

    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    auth_user = get_auth_user()

    workspace = get_workspace_context()
    project_id = workspace.get("project_id")
    project_name = workspace.get("project_name")
    project_code = workspace.get("project_code")

    from calb_sizing_tool.ui._ui import page_header
    page_header("Case Directory", "Cases for the active project")

    if not project_id:
        st.warning("No project is active. Go to Workbench to select or create one.")
        if st.button("Go to Workbench"):
            navigate_now("Workbench")
        return

    st.markdown(f"**Project:** {project_name} `{project_code}`")

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        try:
            cases = [
                {
                    "sizing_case_id": c.sizing_case_id,
                    "case_name": c.case_name,
                    "case_code": c.case_code,
                    "scenario_mode": c.scenario_mode,
                    "created_at": c.created_at,
                }
                for c in access.list_cases_by_project(project_id)
            ]
        except PermissionError:
            st.error("You do not have access to this project.")
            return

    if not cases:
        st.info("No cases yet for this project.")
        if st.button("Create a case in Workbench"):
            navigate_now("Workbench")
        return

    active_case_id = workspace.get("case_id")

    df = pd.DataFrame([
        {
            "Case Name": ("▶ " if c["sizing_case_id"] == active_case_id else "") + c["case_name"],
            "Scenario": SCENARIO_LABELS.get(c["scenario_mode"], c["scenario_mode"]),
            "Created": fmt_dt(c["created_at"]),
        }
        for c in cases
    ])
    st.dataframe(df, hide_index=True, use_container_width=True)

    case_options = [c["case_name"] for c in cases]
    active_index = next(
        (i for i, c in enumerate(cases) if c["sizing_case_id"] == active_case_id),
        0,
    )
    selected_name = st.selectbox(
        "Select case to open",
        case_options,
        index=active_index,
        label_visibility="collapsed",
    )
    selected = next(c for c in cases if c["case_name"] == selected_name)
    is_active = selected["sizing_case_id"] == active_case_id
    if st.button("Open Case", disabled=is_active, use_container_width=True):
        set_active_case(
            case_id=selected["sizing_case_id"],
            case_code=selected["case_code"],
            case_name=selected["case_name"],
        )
        navigate_now("Workbench")
