from __future__ import annotations

import streamlit as st

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.state.workspace_state import get_workspace_context, restore_run_bundle_to_session


def _ensure_schema() -> None:
    with session_scope() as session:
        Base.metadata.create_all(bind=session.get_bind())


_SCENARIO_LABELS: dict[str, str] = {
    "container_only": "Container Only",
    "cabinet_only": "Cabinet Only",
    "hybrid": "Container + Cabinet",
}


def _format_dt(value) -> str:
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def _run_label(index: int, created_at) -> str:
    try:
        ts = created_at.strftime("%m-%d %H:%M")
    except Exception:
        ts = str(created_at)
    return f"#{index}  {ts}"


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
    case_id = workspace.get("case_id")
    case_name = workspace.get("case_name")

    st.title("Run History")
    st.caption("Detailed run registry. Use Workbench for faster restore and continuation.")

    if not project_id or not case_id:
        st.warning("Select a project and case first.")
        return

    st.caption(f"Active Project: {project_name}")
    st.caption(f"Active Case: {case_name}")

    with session_scope() as session:
        access = AccessControlService(session, auth_user)
        try:
            runs = [
                {
                    "sizing_run_id": run.sizing_run_id,
                    "created_at": run.created_at,
                    "input_summary_json": run.input_summary_json or {},
                    "output_summary_json": run.output_summary_json or {},
                }
                for run in access.list_runs_by_case(case_id)
            ]
        except PermissionError:
            st.error("You do not have access to this case.")
            return

    if not runs:
        st.info("No runs found for this case.")
        return

    st.subheader("Runs")
    header_cols = st.columns([2.0, 2.0, 2.0, 1.4, 1.2, 1.2, 1.4, 1.4, 1.2, 1.2])
    header_cols[0].write("Run")
    header_cols[1].write("Project")
    header_cols[2].write("Case")
    header_cols[3].write("Scenario")
    header_cols[4].write("POI MW")
    header_cols[5].write("POI MWh")
    header_cols[6].write("DC MWh Req")
    header_cols[7].write("Guarantee MWh")
    header_cols[8].write("Margin MWh")
    header_cols[9].write("Converged")

    for idx, run in enumerate(runs, start=1):
        label = _run_label(idx, run["created_at"])
        summary = run["output_summary_json"]
        input_summary = run["input_summary_json"]
        cols = st.columns([2.0, 2.0, 2.0, 1.4, 1.2, 1.2, 1.4, 1.4, 1.2, 1.2])
        cols[0].write(label)
        cols[1].write(input_summary.get("project_name") or "—")
        cols[2].write(input_summary.get("case_name") or "—")
        cols[3].write(_SCENARIO_LABELS.get(input_summary.get("scenario_id"), input_summary.get("scenario_id") or "—"))
        cols[4].write(input_summary.get("poi_power_req_mw") or "—")
        cols[5].write(input_summary.get("poi_energy_req_mwh") or "—")
        cols[6].write(summary.get("dc_energy_capacity_required_mwh") or "—")
        cols[7].write(summary.get("guarantee_year_poi_usable_mwh") or "—")
        cols[8].write(summary.get("margin_mwh") or "—")
        cols[9].write("Yes" if summary.get("converged") else "No")

        with st.expander(f"Run {label} — details", expanded=False):
            st.write(
                {
                    "Project": input_summary.get("project_name"),
                    "Case": input_summary.get("case_name"),
                    "Scenario": _SCENARIO_LABELS.get(input_summary.get("scenario_id"), input_summary.get("scenario_id")),
                    "POI Power (MW)": input_summary.get("poi_power_req_mw"),
                    "POI Energy (MWh)": input_summary.get("poi_energy_req_mwh"),
                    "DC Required (MWh)": summary.get("dc_energy_capacity_required_mwh"),
                    "Guarantee Year (MWh)": summary.get("guarantee_year_poi_usable_mwh"),
                    "Margin (MWh)": summary.get("margin_mwh"),
                    "Effective C-Rate": summary.get("effective_c_rate"),
                    "SOH Profile": summary.get("soh_profile_id"),
                    "RTE Profile": summary.get("rte_profile_id"),
                    "Iterations": summary.get("iterations"),
                    "Converged": summary.get("converged"),
                    "Created": _format_dt(run["created_at"]),
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
                st.success(f"Run {label} restored. Open DC Sizing to view results.")
