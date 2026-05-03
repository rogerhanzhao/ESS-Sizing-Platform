from __future__ import annotations

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import navigate_to, set_active_project
from calb_sizing_tool.utils.text import fmt_dt, slugify


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
            navigate_to("Workbench")
            st.rerun()
        return

    h0, h1, h2, h3 = st.columns([3, 2.5, 2, 1.5])
    h0.caption("Project Name")
    h1.caption("Code")
    h2.caption("Created")
    h3.caption("")

    for p in projects:
        c0, c1, c2, c3 = st.columns([3, 2.5, 2, 1.5])
        c0.write(p["project_name"])
        c1.write(p["project_code"])
        c2.write(fmt_dt(p["created_at"]))
        if c3.button("Open", key=f"proj_dir_open_{p['project_id']}", use_container_width=True):
            set_active_project(
                project_id=p["project_id"],
                project_code=p["project_code"],
                project_name=p["project_name"],
            )
            navigate_to("Workbench")
            st.rerun()
