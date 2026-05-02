from __future__ import annotations

import streamlit as st

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.domain.enums import StageScope
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import (
    get_workspace_context,
    navigate_to,
    restore_run_bundle_to_session,
    set_active_case,
    set_active_project,
)
from calb_sizing_tool.utils.text import SCENARIO_LABELS, fmt_dt, slugify


def _run_label(index: int, created_at) -> str:
    try:
        ts = created_at.strftime("%m-%d %H:%M")
    except Exception:
        ts = str(created_at)
    return f"#{index}  {ts}"


def show() -> None:
    init_project_state()

    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    auth_user = get_auth_user()

    st.title("Workbench")
    st.caption("Project = physical opportunity/site.  Case = technical option set.  Run = one calculation snapshot.")

    # ── Load accessible projects ──────────────────────────────────────────────
    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        projects = [
            {
                "project_id": p.project_id,
                "project_code": p.project_code,
                "project_name": p.project_name,
                "created_at": p.created_at,
            }
            for p in access.list_projects()
        ]

    context = get_workspace_context()

    # If the previously active project is no longer accessible, clear it and warn.
    if context["project_id"] and not any(p["project_id"] == context["project_id"] for p in projects):
        st.warning("Previously active project is no longer accessible. Please select another.")
        set_active_project(project_id=None, project_code=None, project_name=None)
        context = get_workspace_context()

    # Auto-select first project only when nothing is active yet (first-time UX).
    if context["project_id"] is None and projects:
        first = projects[0]
        set_active_project(
            project_id=first["project_id"],
            project_code=first["project_code"],
            project_name=first["project_name"],
        )
        context = get_workspace_context()

    # ── Load cases for active project ─────────────────────────────────────────
    cases: list[dict] = []
    if context["project_id"]:
        with session_scope() as session:
            access = AccessControlService(session, auth_user)
            try:
                cases = [
                    {
                        "sizing_case_id": c.sizing_case_id,
                        "case_code": c.case_code,
                        "case_name": c.case_name,
                        "scenario_mode": c.scenario_mode,
                        "created_at": c.created_at,
                    }
                    for c in access.list_cases_by_project(context["project_id"])
                ]
            except PermissionError:
                cases = []

    if context["case_id"] and not any(c["sizing_case_id"] == context["case_id"] for c in cases):
        set_active_case(case_id=None, case_code=None, case_name=None)
        context = get_workspace_context()

    if context["case_id"] is None and cases:
        first = cases[0]
        set_active_case(
            case_id=first["sizing_case_id"],
            case_code=first["case_code"],
            case_name=first["case_name"],
        )
        context = get_workspace_context()

    # ── Load runs for active case ──────────────────────────────────────────────
    runs: list[dict] = []
    if context["case_id"]:
        with session_scope() as session:
            access = AccessControlService(session, auth_user)
            try:
                runs = [
                    {
                        "sizing_run_id": r.sizing_run_id,
                        "created_at": r.created_at,
                        "scenario_id": (r.input_summary_json or {}).get("scenario_id"),
                        "poi_power_req_mw": (r.input_summary_json or {}).get("poi_power_req_mw"),
                        "poi_energy_req_mwh": (r.input_summary_json or {}).get("poi_energy_req_mwh"),
                        "margin_mwh": (r.output_summary_json or {}).get("margin_mwh"),
                        "converged": (r.output_summary_json or {}).get("converged"),
                    }
                    for r in access.list_runs_by_case(context["case_id"])
                ]
            except PermissionError:
                runs = []

    # ── Workspace status bar ───────────────────────────────────────────────────
    _active_run_id = context.get("run_id")
    active_run_label = "None"
    if _active_run_id:
        _idx = next((i + 1 for i, r in enumerate(runs) if r["sizing_run_id"] == _active_run_id), None)
        _match = next((r for r in runs if r["sizing_run_id"] == _active_run_id), None)
        if _match and _idx:
            active_run_label = _run_label(_idx, _match["created_at"])
        else:
            active_run_label = f"··{_active_run_id[-8:]}" if len(_active_run_id) >= 8 else _active_run_id

    m1, m2, m3 = st.columns(3)
    m1.metric("Active Project", context.get("project_name") or "—")
    m2.metric("Active Case", context.get("case_name") or "—")
    m3.metric("Active Run", active_run_label)

    # ── Quick-action navigation buttons ───────────────────────────────────────
    a1, a2, a3, a4 = st.columns(4)
    if a1.button("▶  DC Sizing", use_container_width=True, disabled=not context.get("case_id")):
        navigate_to("DC Sizing")
        st.rerun()
    if a2.button("▶  AC Sizing", use_container_width=True, disabled=not context.get("run_id")):
        navigate_to("AC Sizing")
        st.rerun()
    if a3.button("▶  SLD", use_container_width=True, disabled=not context.get("run_id")):
        navigate_to("Single Line Diagram")
        st.rerun()
    if a4.button("▶  Report Export", use_container_width=True, disabled=not context.get("run_id")):
        navigate_to("Report Export")
        st.rerun()

    st.divider()

    # ── Three-column workspace manager ────────────────────────────────────────
    # Run registry gets more space (1.8) since its inner rows need button room.
    project_col, case_col, run_col = st.columns([1.0, 1.0, 1.8])

    # ── Projects column ────────────────────────────────────────────────────────
    with project_col:
        st.subheader("Projects")

        if projects:
            project_ids = [p["project_id"] for p in projects]
            current_pid = context.get("project_id") if context.get("project_id") in project_ids else project_ids[0]
            selected_pid = st.selectbox(
                "Active Project",
                project_ids,
                index=project_ids.index(current_pid),
                format_func=lambda pid: next(p["project_name"] for p in projects if p["project_id"] == pid),
                key="workbench_project_select",
                label_visibility="collapsed",
            )
            if selected_pid != context.get("project_id"):
                sel = next(p for p in projects if p["project_id"] == selected_pid)
                set_active_project(
                    project_id=sel["project_id"],
                    project_code=sel["project_code"],
                    project_name=sel["project_name"],
                )
                st.rerun()
        else:
            st.info("No projects yet.")

        with st.expander("+ New Project", expanded=not projects):
            with st.form("workbench_create_project"):
                proj_name = st.text_input("Project Name")
                proj_desc = st.text_area("Description (optional)", height=60)
                if st.form_submit_button("Create", use_container_width=True):
                    if not proj_name.strip():
                        st.error("Name is required.")
                    else:
                        with session_scope() as session:
                            auth_repo = AuthRepository(session)
                            repo = CaseRepository(session)
                            project = repo.get_or_create_project(
                                project_code=slugify(proj_name, fallback="project"),
                                project_name=proj_name.strip(),
                                description=proj_desc.strip() or None,
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
                        st.rerun()

        if len(projects) > 1:
            st.caption("All projects")
            for p in projects[:8]:
                is_active = p["project_id"] == context.get("project_id")
                c_name, c_btn = st.columns([3, 1])
                c_name.write(("▶ " if is_active else "  ") + p["project_name"])
                if is_active:
                    c_btn.button("✓", key=f"proj_act_{p['project_id']}", disabled=True, use_container_width=True)
                elif c_btn.button("↗", key=f"proj_sw_{p['project_id']}", use_container_width=True):
                    set_active_project(
                        project_id=p["project_id"],
                        project_code=p["project_code"],
                        project_name=p["project_name"],
                    )
                    st.rerun()

    # ── Cases column ───────────────────────────────────────────────────────────
    with case_col:
        st.subheader("Cases")

        if not context.get("project_id"):
            st.info("Select a project first.")
        else:
            if cases:
                case_ids = [c["sizing_case_id"] for c in cases]
                current_cid = context.get("case_id") if context.get("case_id") in case_ids else case_ids[0]
                selected_cid = st.selectbox(
                    "Active Case",
                    case_ids,
                    index=case_ids.index(current_cid),
                    format_func=lambda cid: next(c["case_name"] for c in cases if c["sizing_case_id"] == cid),
                    key="workbench_case_select",
                    label_visibility="collapsed",
                )
                if selected_cid != context.get("case_id"):
                    sel = next(c for c in cases if c["sizing_case_id"] == selected_cid)
                    set_active_case(
                        case_id=sel["sizing_case_id"],
                        case_code=sel["case_code"],
                        case_name=sel["case_name"],
                    )
                    st.rerun()
            else:
                st.info("No cases yet.")

            with st.expander("+ New Case", expanded=not cases):
                with st.form("workbench_create_case"):
                    case_name_input = st.text_input("Case Name")
                    scenario_mode = st.selectbox(
                        "Scenario",
                        list(SCENARIO_LABELS.keys()),
                        index=0,
                        format_func=lambda k: SCENARIO_LABELS[k],
                    )
                    if st.form_submit_button("Create", use_container_width=True):
                        if not case_name_input.strip():
                            st.error("Name is required.")
                        else:
                            proj_code = context.get("project_code") or slugify(
                                context.get("project_name") or "project", fallback="project"
                            )
                            with session_scope() as session:
                                repo = CaseRepository(session)
                                AccessControlService(session, auth_user).ensure_project_access(context["project_id"])
                                case = repo.create_case(
                                    project_id=context["project_id"],
                                    case_code=f"{proj_code}-{slugify(case_name_input, fallback='case')}",
                                    case_name=case_name_input.strip(),
                                    stage_scope=StageScope.DC,
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
                            st.rerun()

            if len(cases) > 1:
                st.caption("Cases in this project")
                for c in cases[:10]:
                    is_active = c["sizing_case_id"] == context.get("case_id")
                    c_name, c_btn = st.columns([3, 1])
                    scen = SCENARIO_LABELS.get(c["scenario_mode"], "")
                    c_name.write(("▶ " if is_active else "  ") + c["case_name"])
                    c_name.caption(scen)
                    if is_active:
                        c_btn.button("✓", key=f"case_act_{c['sizing_case_id']}", disabled=True, use_container_width=True)
                    elif c_btn.button("↗", key=f"case_sw_{c['sizing_case_id']}", use_container_width=True):
                        set_active_case(
                            case_id=c["sizing_case_id"],
                            case_code=c["case_code"],
                            case_name=c["case_name"],
                        )
                        st.rerun()

    # ── Run Registry column ────────────────────────────────────────────────────
    with run_col:
        st.subheader("Run Registry")
        if not context.get("case_id"):
            st.info("Select a case to see runs.")
        elif not runs:
            st.info("No runs yet. Start with DC Sizing.")
        else:
            # Header row
            h0, h1, h2, h3, h4 = st.columns([2.0, 1.8, 1.8, 0.6, 1.6])
            h0.caption("Run")
            h1.caption("MW / MWh")
            h2.caption("Scenario")
            h3.caption("OK")
            h4.caption("")

            for idx, item in enumerate(runs[:12], start=1):
                label = _run_label(idx, item["created_at"])
                mw = item["poi_power_req_mw"]
                mwh = item["poi_energy_req_mwh"]
                power_str = f"{mw} / {mwh}" if mw else "—"
                scenario_str = SCENARIO_LABELS.get(item["scenario_id"], item["scenario_id"] or "—")
                is_active_run = item["sizing_run_id"] == _active_run_id

                c0, c1, c2, c3, c4 = st.columns([2.0, 1.8, 1.8, 0.6, 1.6])
                c0.write(("**" + label + "**") if is_active_run else label)
                c1.write(power_str)
                c2.write(scenario_str)
                c3.write("✓" if item["converged"] else "✗")
                btn_label = "Active" if is_active_run else "Restore"
                if c4.button(btn_label, key=f"wb_restore_{item['sizing_run_id']}",
                             disabled=is_active_run, use_container_width=True):
                    with session_scope() as session:
                        bundle = AccessControlService(session, auth_user).load_dc_run_bundle(item["sizing_run_id"])
                    if not bundle:
                        st.error("Run not found.")
                    else:
                        restore_run_bundle_to_session(bundle, item["sizing_run_id"])
                        st.rerun()

            # Latest run compact summary
            latest = runs[0]
            st.divider()
            st.caption(f"Latest run — {_run_label(1, latest['created_at'])}")
            s1, s2 = st.columns(2)
            s1.metric("POI Power", f"{latest['poi_power_req_mw']} MW" if latest["poi_power_req_mw"] else "—")
            s2.metric("POI Energy", f"{latest['poi_energy_req_mwh']} MWh" if latest["poi_energy_req_mwh"] else "—")
            s3, s4 = st.columns(2)
            s3.metric("Margin", f"{latest['margin_mwh']} MWh" if latest["margin_mwh"] is not None else "—")
            s4.metric("Converged", "Yes ✓" if latest["converged"] else "No ✗")
