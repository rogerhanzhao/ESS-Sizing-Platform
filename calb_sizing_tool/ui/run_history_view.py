from __future__ import annotations

import pandas as pd
import streamlit as st

from calb_sizing_tool.common.arrow_safe import arrow_safe
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.state.auth_state import get_auth_context, get_auth_user
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.workspace_state import get_workspace_context, restore_run_bundle_to_session
from calb_sizing_tool.utils.text import SCENARIO_LABELS, fmt_dt


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

    workspace = get_workspace_context()
    project_id = workspace.get("project_id")
    project_name = workspace.get("project_name")
    case_id = workspace.get("case_id")
    case_name = workspace.get("case_name")

    from calb_sizing_tool.ui._ui import page_header
    page_header("Run Registry", "Sizing run history")

    if not project_id or not case_id:
        st.warning("Select a project and case first.")
        return

    st.markdown(f"**Project:** {project_name}   **Case:** {case_name}")

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        try:
            runs = [
                {
                    "sizing_run_id": r.sizing_run_id,
                    "created_at": r.created_at,
                    "input_summary_json": r.input_summary_json or {},
                    "output_summary_json": r.output_summary_json or {},
                }
                for r in access.list_runs_by_case(case_id)
            ]
        except PermissionError:
            st.error("You do not have access to this case.")
            return

    if not runs:
        st.info("No runs found for this case.")
        return

    # Summary table
    rows = []
    for idx, run in enumerate(runs, start=1):
        label = _run_label(idx, run["created_at"])
        summary = run["output_summary_json"]
        inp = run["input_summary_json"]
        rows.append({
            "Run": label,
            "Scenario": SCENARIO_LABELS.get(inp.get("scenario_id"), inp.get("scenario_id") or "—"),
            "POI MW": inp.get("poi_power_req_mw") or "—",
            "POI MWh": inp.get("poi_energy_req_mwh") or "—",
            "DC Req MWh": summary.get("dc_energy_capacity_required_mwh") or "—",
            "Guarantee MWh": summary.get("guarantee_year_poi_usable_mwh") or "—",
            "Margin MWh": summary.get("margin_mwh") or "—",
            "Converged": "Yes" if summary.get("converged") else "No",
        })

    st.dataframe(arrow_safe(pd.DataFrame(rows)), hide_index=True, use_container_width=True)

    # Per-run detail expanders with restore action
    st.markdown('<div class="calb-muted-line"></div>', unsafe_allow_html=True)
    for idx, run in enumerate(runs, start=1):
        label = _run_label(idx, run["created_at"])
        summary = run["output_summary_json"]
        inp = run["input_summary_json"]
        with st.expander(f"Run {label} — details", expanded=False):
            st.write(
                {
                    "Project": inp.get("project_name"),
                    "Case": inp.get("case_name"),
                    "Scenario": SCENARIO_LABELS.get(inp.get("scenario_id"), inp.get("scenario_id")),
                    "POI Power (MW)": inp.get("poi_power_req_mw"),
                    "POI Energy (MWh)": inp.get("poi_energy_req_mwh"),
                    "DC Required (MWh)": summary.get("dc_energy_capacity_required_mwh"),
                    "Guarantee Year (MWh)": summary.get("guarantee_year_poi_usable_mwh"),
                    "Margin (MWh)": summary.get("margin_mwh"),
                    "Effective C-Rate": summary.get("effective_c_rate"),
                    "SOH Profile": summary.get("soh_profile_id"),
                    "RTE Profile": summary.get("rte_profile_id"),
                    "Iterations": summary.get("iterations"),
                    "Converged": summary.get("converged"),
                    "Created": fmt_dt(run["created_at"]),
                }
            )
            if st.button("Restore Run", key=f"restore_{run['sizing_run_id']}"):
                with session_scope() as session:
                    access = AccessControlService(session, auth_user)
                    try:
                        bundle = access.load_dc_run_bundle(run["sizing_run_id"])
                    except PermissionError:
                        st.error("You do not have access to this run.")
                        return
                if not bundle:
                    st.error("Run not found.")
                    return
                restore_run_bundle_to_session(bundle, run["sizing_run_id"])
                st.success(f"Run {label} restored.")
