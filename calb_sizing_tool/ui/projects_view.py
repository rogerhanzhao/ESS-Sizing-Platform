from __future__ import annotations

import re

import streamlit as st

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.project_state import init_project_state


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "project"


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

    st.title("Projects")

    with st.form("create_project"):
        name = st.text_input("Project Name")
        description = st.text_area("Description", height=80)
        submitted = st.form_submit_button("Create Project")
        if submitted:
            if not name.strip():
                st.error("Project name is required.")
            else:
                code = _slug(name)
                with session_scope() as session:
                    auth_repo = AuthRepository(session)
                    repo = CaseRepository(session)
                    project = repo.get_or_create_project(
                        project_code=code,
                        project_name=name.strip(),
                        description=description.strip() or None,
                        source_ref="ui",
                    )
                    session.flush()
                    auth_repo.ensure_system_roles()
                    auth_repo.add_project_member(
                        project_id=project.project_id,
                        user_id=auth_user.user_id,
                        role_code="normal_user",
                    )
                    session.flush()
                    st.session_state["active_project_id"] = project.project_id
                    st.session_state["active_project_code"] = project.project_code
                    st.session_state["active_project_name"] = project.project_name
                st.success(f"Project created: {name.strip()}")

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        projects = [
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "project_code": project.project_code,
                "created_at": project.created_at,
            }
            for project in access.list_projects()
        ]

    st.subheader("Project List")
    if not projects:
        st.info("No projects found.")
        return

    for project in projects:
        cols = st.columns([3, 3, 2, 1.5])
        cols[0].write(project["project_name"])
        cols[1].write(project["project_code"])
        cols[2].write(project["created_at"].strftime("%Y-%m-%d %H:%M"))
        if cols[3].button("Open", key=f"project_open_{project['project_id']}"):
            st.session_state["active_project_id"] = project["project_id"]
            st.session_state["active_project_code"] = project["project_code"]
            st.session_state["active_project_name"] = project["project_name"]
            st.success(f"Active project set: {project['project_name']}")
