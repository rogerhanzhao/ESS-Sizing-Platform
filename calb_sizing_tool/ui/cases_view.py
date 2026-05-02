from __future__ import annotations

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import get_workspace_context, navigate_to, set_active_case
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

    st.title("Case Directory")
    st.caption("Browse all cases for the active project. To create a new case, use the Workbench.")

    if not project_id:
        st.warning("No project is active. Go to Workbench to select or create one.")
        if st.button("Go to Workbench"):
            navigate_to("Workbench")
            st.rerun()
        return

    st.markdown(f"**Project:** {project_name} `{project_code}`")

    # Single session: check access and list cases together.
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
            navigate_to("Workbench")
            st.rerun()
        return

    active_case_id = workspace.get("case_id")

    # Column headers
    h0, h1, h2, h3 = st.columns([3, 2, 2, 1.5])
    h0.caption("Case Name")
    h1.caption("Scenario")
    h2.caption("Created")
    h3.caption("")

    for case in cases:
        is_active = case["sizing_case_id"] == active_case_id
        c0, c1, c2, c3 = st.columns([3, 2, 2, 1.5])
        c0.write(("**▶ **" if is_active else "") + case["case_name"])
        c1.write(SCENARIO_LABELS.get(case["scenario_mode"], case["scenario_mode"]))
        c2.write(fmt_dt(case["created_at"]))
        btn_label = "Active" if is_active else "Open"
        if c3.button(btn_label, key=f"case_dir_open_{case['sizing_case_id']}", disabled=is_active, use_container_width=True):
            set_active_case(
                case_id=case["sizing_case_id"],
                case_code=case["case_code"],
                case_name=case["case_name"],
            )
            navigate_to("Workbench")
            st.rerun()
