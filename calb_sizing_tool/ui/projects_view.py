from __future__ import annotations

import pandas as pd
import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import navigate_now, set_active_project
from calb_sizing_tool.utils.text import fmt_dt


def show() -> None:
    init_project_state()

    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    auth_user = get_auth_user()

    from calb_sizing_tool.ui._ui import page_header
    page_header("Project Directory", "All accessible projects")

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        projects = [
            {
                "project_id": p.project_id,
                "project_name": p.project_name,
                "project_code": p.project_code,
                "created_at": p.created_at,
            }
            for p in access.list_projects()
        ]

    if not projects:
        st.info("No projects found.")
        if st.button("Go to Workbench to create one"):
            navigate_now("Workbench")
        return

    df = pd.DataFrame([
        {
            "Project Name": p["project_name"],
            "Code": p["project_code"],
            "Created": fmt_dt(p["created_at"]),
        }
        for p in projects
    ])
    st.dataframe(df, hide_index=True, use_container_width=True)

    project_names = [p["project_name"] for p in projects]
    selected_name = st.selectbox("Select project to open", project_names, label_visibility="collapsed")
    selected = next(p for p in projects if p["project_name"] == selected_name)
    if st.button("Open Project", use_container_width=True):
        set_active_project(
            project_id=selected["project_id"],
            project_code=selected["project_code"],
            project_name=selected["project_name"],
        )
        navigate_now("Workbench")
