from __future__ import annotations

import re

import streamlit as st

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.state.project_state import init_project_state


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "case"


def _ensure_schema() -> None:
    with session_scope() as session:
        Base.metadata.create_all(bind=session.get_bind())


def show() -> None:
    init_project_state()
    _ensure_schema()

    project_id = st.session_state.get("active_project_id")
    project_name = st.session_state.get("active_project_name")
    project_code = st.session_state.get("active_project_code")

    st.title("Cases")
    if not project_id:
        st.warning("Select a project first.")
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
                    st.session_state["active_case_id"] = case.sizing_case_id
                    st.session_state["active_case_code"] = case.case_code
                    st.session_state["active_case_name"] = case.case_name
                st.success(f"Case created: {name.strip()}")

    with session_scope() as session:
        repo = CaseRepository(session)
        cases = repo.list_cases_by_project(project_id)

    st.subheader("Case List")
    if not cases:
        st.info("No cases found.")
        return

    for case in cases:
        cols = st.columns([3, 3, 2, 1.5])
        cols[0].write(case.case_name)
        cols[1].write(case.case_code)
        cols[2].write(case.created_at.strftime("%Y-%m-%d %H:%M"))
        if cols[3].button("Open", key=f"case_open_{case.sizing_case_id}"):
            st.session_state["active_case_id"] = case.sizing_case_id
            st.session_state["active_case_code"] = case.case_code
            st.session_state["active_case_name"] = case.case_name
            st.success(f"Active case set: {case.case_name}")
