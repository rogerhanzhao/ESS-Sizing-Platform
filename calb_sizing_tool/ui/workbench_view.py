from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from calb_sizing_tool.domain.enums import StageScope
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.repositories.case_repository import CaseRepository
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
    return f"#{index} {ts}"


def _fmt_value(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "-"
    return f"{value}{suffix}"


def _fmt_margin(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f} MWh"
    except Exception:
        return f"{value} MWh"


def _render_workbench_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.55rem !important; }
        .block-container h1,
        .block-container h2,
        .block-container h3,
        .block-container p,
        .block-container label {
            text-align: left !important;
        }
        .block-container a.anchor-link,
        .block-container [data-testid="stHeaderActionElements"] {
            display: none !important;
        }
        .block-container > div:first-child {
            gap: 0.55rem !important;
        }
        .wb-page-header {
            margin: 0 0 1.05rem;
            overflow: visible;
        }
        .wb-page-title {
            color: #1A2635;
            display: block;
            font-size: 2.25rem !important;
            font-weight: 800 !important;
            font-family: Arial, "Segoe UI", sans-serif;
            font-variant-caps: normal;
            letter-spacing: 0;
            line-height: 1.28 !important;
            margin: 0 0 0.55rem;
            min-height: 3.05rem;
            overflow: visible;
            padding: 0.28rem 0 0.08rem;
            text-transform: none !important;
            text-align: left;
        }
        .wb-page-subtitle {
            color: #778494;
            font-size: 0.9rem;
            line-height: 1.35;
            margin: 0;
            text-align: left;
        }
        .wb-toolbar-build {
            display: none;
        }
        .wb-latest-grid {
            display: grid;
            gap: 0.75rem;
        }
        .wb-compact-status {
            background: #F4F7FB;
            border-left: 3px solid #1E4172;
            border-radius: 4px;
            min-height: 2.75rem;
        }
        .wb-compact-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .wb-compact-item {
            border-left: 1px solid #DDE5EF;
            min-height: 2.75rem;
            padding: 0.46rem 0.72rem;
            text-align: left;
        }
        .wb-compact-item:first-child {
            border-left: 0;
        }
        .wb-compact-label {
            color: #506F94;
            font-size: 0.56rem;
            font-weight: 700;
            letter-spacing: 0.07em;
            margin-bottom: 0.06rem;
            text-transform: uppercase;
        }
        .wb-compact-value {
            color: #1A2635;
            font-size: 0.84rem;
            font-weight: 700;
            line-height: 1.18;
            overflow-wrap: anywhere;
        }
        .wb-section-rule {
            background: #D8E1EC;
            height: 1px;
            margin: 1.2rem 0 1.9rem;
            width: 100%;
        }
        .wb-latest-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-bottom: 0.2rem;
        }
        .wb-tile {
            background: #EDF1F7;
            border-left: 3px solid #1E4172;
            border-radius: 4px;
            padding: 0.78rem 0.9rem;
            min-height: 4.45rem;
            display: flex;
            flex-direction: column;
            justify-content: center;
            text-align: left;
        }
        .wb-tile-label {
            color: #506F94;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }
        .wb-tile-value {
            color: #1A2635;
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.25;
            overflow-wrap: anywhere;
            text-align: left;
        }
        .wb-section-note {
            color: #778494;
            font-size: 0.86rem;
            margin-top: -0.2rem;
            margin-bottom: 0.55rem;
            text-align: left;
        }
        .wb-action-spacer { height: 0.75rem; }
        .block-container div[data-testid="stButton"] {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        /* Toolbar bordered container: CALB blue border, subtle background */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1.5px solid #C2D3E8 !important;
            border-radius: 8px !important;
            padding: 0.5rem 0.75rem !important;
            background: #F8FAFD !important;
        }
        /* Button columns inside the toolbar: align top with compact-status label row */
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stButton"] {
            margin-top: 0.42rem !important;
            margin-bottom: 0 !important;
        }

        /* ── All workbench buttons: CALB navy chip style ─────────────────── */
        .block-container .stButton > button {
            background: #F5F8FC !important;
            border: 1.5px solid #2A527A !important;
            border-radius: 6px !important;
            box-shadow: none !important;
            color: #1E4172 !important;
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            height: 2.48rem !important;
            min-height: 2.48rem !important;
            justify-content: center !important;
            letter-spacing: 0.01em !important;
            padding: 0 0.6rem !important;
            text-align: center !important;
            transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease !important;
        }
        .block-container .stButton > button p {
            text-align: center !important;
            width: 100%;
        }
        .block-container .stButton > button:hover:not(:disabled) {
            background: #1E4172 !important;
            border-color: #1E4172 !important;
            color: #FFFFFF !important;
        }
        .block-container .stButton > button:disabled {
            background: #F5F8FC !important;
            border-color: #CDD8E6 !important;
            color: #9AAEC0 !important;
            opacity: 1 !important;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid #D7DEE8;
            border-radius: 6px;
        }
        @media (max-width: 900px) {
            .block-container {
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
            .wb-page-title { font-size: 2rem; }
            .wb-page-subtitle { font-size: 0.86rem; }
            .wb-latest-grid { grid-template-columns: 1fr; }
            .wb-compact-grid { grid-template-columns: 1fr; }
            .wb-compact-status { min-height: auto; }
            .wb-compact-item { border-left: 0; border-top: 1px solid #DDE5EF; min-height: 2.25rem; }
            .wb-compact-item:first-child { border-top: 0; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _tile_html(label: str, value: str) -> str:
    return (
        '<div class="wb-tile">'
        f'<div class="wb-tile-label">{escape(label)}</div>'
        f'<div class="wb-tile-value">{escape(value)}</div>'
        "</div>"
    )


def _page_header_html() -> str:
    return (
        '<div class="wb-page-header" data-wb-build="workbench-toolbar-20260502-0006">'
        '<div class="wb-toolbar-build">workbench-toolbar-20260502-0006</div>'
        '<div class="wb-page-title" style="text-transform:none!important">Workbench</div>'
        "</div>"
    )


def _compact_context_html(context: dict, active_run_label: str) -> str:
    items = [
        ("Project", str(context.get("project_name") or "-")),
        ("Case", str(context.get("case_name") or "-")),
        ("Run", str(active_run_label or "None")),
    ]
    cells = "".join(
        '<div class="wb-compact-item">'
        f'<div class="wb-compact-label">{escape(label)}</div>'
        f'<div class="wb-compact-value">{escape(value)}</div>'
        "</div>"
        for label, value in items
    )
    return f'<div class="wb-compact-status"><div class="wb-compact-grid">{cells}</div></div>'


def _restore_run(run_id: str, auth_user) -> None:
    with session_scope() as session:
        bundle = AccessControlService(session, auth_user).load_dc_run_bundle(run_id)
    if not bundle:
        st.error("Run not found.")
        return
    restore_run_bundle_to_session(bundle, run_id)
    st.rerun()


def _load_projects(auth_user) -> list[dict]:
    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        return [
            {
                "project_id": p.project_id,
                "project_code": p.project_code,
                "project_name": p.project_name,
                "created_at": p.created_at,
            }
            for p in access.list_projects()
        ]


def _load_cases(auth_user, project_id: str | None) -> list[dict]:
    if not project_id:
        return []
    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        try:
            return [
                {
                    "sizing_case_id": c.sizing_case_id,
                    "case_code": c.case_code,
                    "case_name": c.case_name,
                    "scenario_mode": c.scenario_mode,
                    "created_at": c.created_at,
                }
                for c in access.list_cases_by_project(project_id)
            ]
        except PermissionError:
            return []


def _load_runs(auth_user, case_id: str | None) -> list[dict]:
    if not case_id:
        return []
    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        try:
            return [
                {
                    "sizing_run_id": r.sizing_run_id,
                    "created_at": r.created_at,
                    "scenario_id": (r.input_summary_json or {}).get("scenario_id"),
                    "poi_power_req_mw": (r.input_summary_json or {}).get("poi_power_req_mw"),
                    "poi_energy_req_mwh": (r.input_summary_json or {}).get("poi_energy_req_mwh"),
                    "margin_mwh": (r.output_summary_json or {}).get("margin_mwh"),
                    "converged": (r.output_summary_json or {}).get("converged"),
                }
                for r in access.list_runs_by_case(case_id)
            ]
        except PermissionError:
            return []


def _active_run_label(active_run_id: str | None, runs: list[dict]) -> str:
    if not active_run_id:
        return "None"
    for idx, item in enumerate(runs, start=1):
        if item["sizing_run_id"] == active_run_id:
            return _run_label(idx, item["created_at"])
    return f"..{active_run_id[-8:]}" if len(active_run_id) >= 8 else active_run_id


def _render_workspace_toolbar(context: dict, active_run_label: str) -> None:
    with st.container(border=True):
        status_col, dc_col, ac_col, sld_col, report_col = st.columns(
            [3.0, 1.1, 1.1, 0.85, 1.3], gap="small", vertical_alignment="top"
        )
        status_col.markdown(_compact_context_html(context, active_run_label), unsafe_allow_html=True)
        if dc_col.button("DC Sizing", use_container_width=True, disabled=not context.get("case_id")):
            navigate_to("DC Sizing")
            st.rerun()
        if ac_col.button("AC Sizing", use_container_width=True, disabled=not context.get("run_id")):
            navigate_to("AC Sizing")
            st.rerun()
        if sld_col.button("SLD", use_container_width=True, disabled=not context.get("run_id")):
            navigate_to("Single Line Diagram")
            st.rerun()
        if report_col.button("Report Export", use_container_width=True, disabled=not context.get("run_id")):
            navigate_to("Report Export")
            st.rerun()


def _render_project_picker(projects: list[dict], context: dict, auth_user) -> None:
    st.caption("Project")
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
            if st.form_submit_button("Create Project", use_container_width=True):
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
        with st.expander("Project List", expanded=False):
            for p in projects[:8]:
                is_active = p["project_id"] == context.get("project_id")
                c_name, c_btn = st.columns([3, 1])
                c_name.write(("Active: " if is_active else "") + p["project_name"])
                if is_active:
                    c_btn.button("Active", key=f"proj_act_{p['project_id']}", disabled=True, use_container_width=True)
                elif c_btn.button("Use", key=f"proj_sw_{p['project_id']}", use_container_width=True):
                    set_active_project(
                        project_id=p["project_id"],
                        project_code=p["project_code"],
                        project_name=p["project_name"],
                    )
                    st.rerun()


def _render_case_picker(cases: list[dict], context: dict, auth_user) -> None:
    st.caption("Case")
    if not context.get("project_id"):
        st.info("Select a project first.")
        return

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
            if st.form_submit_button("Create Case", use_container_width=True):
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
        with st.expander("Case List", expanded=False):
            for c in cases[:10]:
                is_active = c["sizing_case_id"] == context.get("case_id")
                c_name, c_btn = st.columns([3, 1])
                scen = SCENARIO_LABELS.get(c["scenario_mode"], "")
                c_name.write(("Active: " if is_active else "") + c["case_name"])
                c_name.caption(scen)
                if is_active:
                    c_btn.button("Active", key=f"case_act_{c['sizing_case_id']}", disabled=True, use_container_width=True)
                elif c_btn.button("Use", key=f"case_sw_{c['sizing_case_id']}", use_container_width=True):
                    set_active_case(
                        case_id=c["sizing_case_id"],
                        case_code=c["case_code"],
                        case_name=c["case_name"],
                    )
                    st.rerun()


def _render_latest_run(runs: list[dict], context: dict, auth_user) -> None:
    st.subheader("Latest Run")
    if not context.get("case_id"):
        st.info("Select a case to see the latest run.")
        return
    if not runs:
        st.info("No runs yet. Start with DC Sizing.")
        return

    latest = runs[0]
    st.markdown(f'<div class="wb-section-note">{escape(_run_label(1, latest["created_at"]))}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="wb-latest-grid">'
        + _tile_html("POI Power", _fmt_value(latest["poi_power_req_mw"], " MW"))
        + _tile_html("POI Energy", _fmt_value(latest["poi_energy_req_mwh"], " MWh"))
        + _tile_html("Margin", _fmt_margin(latest["margin_mwh"]))
        + _tile_html("Converged", "Yes" if latest["converged"] else "No")
        + "</div>",
        unsafe_allow_html=True,
    )

    is_latest_active = latest["sizing_run_id"] == context.get("run_id")
    st.markdown('<div class="wb-action-spacer"></div>', unsafe_allow_html=True)
    if st.button(
        "Latest Run Active" if is_latest_active else "Restore Latest Run",
        disabled=is_latest_active,
        use_container_width=True,
        key="workbench_restore_latest",
    ):
        _restore_run(latest["sizing_run_id"], auth_user)


def _render_run_registry(runs: list[dict], context: dict, auth_user) -> None:
    st.subheader("Run Registry")
    if not context.get("case_id"):
        st.info("Select a case to see runs.")
        return
    if not runs:
        st.info("No runs yet. Start with DC Sizing.")
        return

    visible_runs = runs[:10]
    st.caption(f"Showing latest {len(visible_runs)} of {len(runs)} runs for the active case.")
    rows = []
    options: dict[str, str] = {}
    for idx, item in enumerate(visible_runs, start=1):
        label = _run_label(idx, item["created_at"])
        scenario_str = SCENARIO_LABELS.get(item["scenario_id"], item["scenario_id"] or "-")
        is_active_run = item["sizing_run_id"] == context.get("run_id")
        rows.append(
            {
                "Run": label,
                "Power": _fmt_value(item["poi_power_req_mw"], " MW"),
                "Energy": _fmt_value(item["poi_energy_req_mwh"], " MWh"),
                "Scenario": scenario_str,
                "OK": "Yes" if item["converged"] else "No",
                "Status": "Active" if is_active_run else "",
            }
        )
        options[label] = item["sizing_run_id"]

    table_height = min(430, 40 + 34 * (len(rows) + 1))
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        height=table_height,
        column_config={
            "Run": st.column_config.TextColumn(width="small"),
            "Power": st.column_config.TextColumn(width="small"),
            "Energy": st.column_config.TextColumn(width="small"),
            "Scenario": st.column_config.TextColumn(width="medium"),
            "OK": st.column_config.TextColumn(width="small"),
            "Status": st.column_config.TextColumn(width="small"),
        },
    )

    restore_col, button_col = st.columns([3, 1])
    selected_label = restore_col.selectbox(
        "Restore run",
        list(options.keys()),
        key="workbench_restore_run_select",
        label_visibility="collapsed",
    )
    selected_run_id = options[selected_label]
    is_selected_active = selected_run_id == context.get("run_id")
    if button_col.button(
        "Active" if is_selected_active else "Restore",
        disabled=is_selected_active,
        use_container_width=True,
        key="workbench_restore_selected",
    ):
        _restore_run(selected_run_id, auth_user)


def show() -> None:
    init_project_state()
    _render_workbench_css()

    auth_context = get_auth_context()
    if auth_context is None:
        st.error("Login required.")
        return
    auth_user = get_auth_user()

    st.markdown(_page_header_html(), unsafe_allow_html=True)

    projects = _load_projects(auth_user)
    context = get_workspace_context()

    if context["project_id"] and not any(p["project_id"] == context["project_id"] for p in projects):
        st.warning("Previously active project is no longer accessible. Please select another.")
        set_active_project(project_id=None, project_code=None, project_name=None)
        context = get_workspace_context()

    if context["project_id"] is None and projects:
        first = projects[0]
        set_active_project(
            project_id=first["project_id"],
            project_code=first["project_code"],
            project_name=first["project_name"],
        )
        st.rerun()

    cases = _load_cases(auth_user, context["project_id"])
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
        st.rerun()

    runs = _load_runs(auth_user, context["case_id"])
    active_run_label = _active_run_label(context.get("run_id"), runs)

    _render_workspace_toolbar(context, active_run_label)
    st.markdown('<div class="wb-section-rule"></div>', unsafe_allow_html=True)

    setup_col, latest_col = st.columns([1.15, 1.0])
    with setup_col:
        st.subheader("Workspace Setup")
        project_col, case_col = st.columns(2)
        with project_col:
            _render_project_picker(projects, context, auth_user)
        with case_col:
            _render_case_picker(cases, context, auth_user)

    with latest_col:
        _render_latest_run(runs, context, auth_user)

    st.markdown('<div class="wb-section-rule"></div>', unsafe_allow_html=True)
    _render_run_registry(runs, context, auth_user)
