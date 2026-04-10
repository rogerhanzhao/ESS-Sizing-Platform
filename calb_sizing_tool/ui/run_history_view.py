from __future__ import annotations

import streamlit as st

from calb_sizing_tool.adapters.session_state_adapter import build_dc_result_summary, build_stage13_output
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.state.project_state import init_project_state
from calb_sizing_tool.state.auth_state import get_auth_context


def _ensure_schema() -> None:
    with session_scope() as session:
        Base.metadata.create_all(bind=session.get_bind())


def _format_dt(value) -> str:
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


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

    project_id = st.session_state.get("active_project_id")
    project_name = st.session_state.get("active_project_name")
    case_id = st.session_state.get("active_case_id")
    case_name = st.session_state.get("active_case_name")

    st.title("Run History")

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
    header_cols = st.columns([2.6, 2.0, 2.0, 1.6, 1.4, 1.2, 1.2, 1.4, 1.4, 1.2, 1.2])
    header_cols[0].write("Run ID")
    header_cols[1].write("Project")
    header_cols[2].write("Case")
    header_cols[3].write("Created At")
    header_cols[4].write("Scenario")
    header_cols[5].write("POI MW")
    header_cols[6].write("POI MWh")
    header_cols[7].write("DC MWh Req")
    header_cols[8].write("Guarantee MWh")
    header_cols[9].write("Margin MWh")
    header_cols[10].write("Converged")

    for run in runs:
        summary = run["output_summary_json"]
        input_summary = run["input_summary_json"]
        cols = st.columns([2.6, 2.0, 2.0, 1.6, 1.4, 1.2, 1.2, 1.4, 1.4, 1.2, 1.2])
        cols[0].write(run["sizing_run_id"])
        cols[1].write(input_summary.get("project_name"))
        cols[2].write(input_summary.get("case_name"))
        cols[3].write(_format_dt(run["created_at"]))
        cols[4].write(input_summary.get("scenario_id"))
        cols[5].write(input_summary.get("poi_power_req_mw"))
        cols[6].write(input_summary.get("poi_energy_req_mwh"))
        cols[7].write(summary.get("dc_energy_capacity_required_mwh"))
        cols[8].write(summary.get("guarantee_year_poi_usable_mwh"))
        cols[9].write(summary.get("margin_mwh"))
        cols[10].write("Yes" if summary.get("converged") else "No")

        with st.expander(f"Run {run['sizing_run_id']} details", expanded=False):
            st.write(
                {
                    "project_name": input_summary.get("project_name"),
                    "case_name": input_summary.get("case_name"),
                    "scenario_mode": input_summary.get("scenario_id"),
                    "poi_power_req_mw": input_summary.get("poi_power_req_mw"),
                    "poi_energy_req_mwh": input_summary.get("poi_energy_req_mwh"),
                    "dc_energy_capacity_required_mwh": summary.get("dc_energy_capacity_required_mwh"),
                    "guarantee_year_poi_usable_mwh": summary.get("guarantee_year_poi_usable_mwh"),
                    "margin_mwh": summary.get("margin_mwh"),
                    "effective_c_rate": summary.get("effective_c_rate"),
                    "soh_profile_id": summary.get("soh_profile_id"),
                    "rte_profile_id": summary.get("rte_profile_id"),
                    "iterations": summary.get("iterations"),
                    "converged": summary.get("converged"),
                    "created_at": _format_dt(run["created_at"]),
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
                snapshot = bundle.snapshot
                case_input = (
                    bundle.input_snapshot.payload.get("case_input")
                    if bundle.input_snapshot and isinstance(bundle.input_snapshot.payload, dict)
                    else {}
                )
                poi_nominal_voltage_kv = case_input.get("poi_nominal_voltage_kv", 33.0)
                poi_frequency_hz = case_input.get("poi_frequency_hz")

                st.session_state["dc_last_run_id"] = run.sizing_run_id
                st.session_state["dc_result_summary"] = build_dc_result_summary(snapshot)
                st.session_state["stage13_output"] = build_stage13_output(
                    snapshot,
                    dc_block_total_qty=int(snapshot.stage2.container_count + snapshot.stage2.cabinet_count),
                    selected_scenario=str(bundle.scenario_mode or snapshot.stage2.mode or "container_only"),
                    poi_nominal_voltage_kv=float(poi_nominal_voltage_kv),
                    poi_frequency_hz=poi_frequency_hz,
                )
                dc_results = st.session_state.get("dc_results")
                if isinstance(dc_results, dict):
                    dc_results["dc_result_summary"] = st.session_state.get("dc_result_summary")
                    dc_results["stage13_output"] = st.session_state.get("stage13_output")
                    dc_results["last_run_id"] = run.sizing_run_id
                st.session_state["active_project_id"] = bundle.project_id
                st.session_state["active_project_name"] = bundle.project_name
                st.session_state["active_project_code"] = bundle.project_code
                st.session_state["active_case_id"] = bundle.sizing_case_id
                st.session_state["active_case_name"] = bundle.case_name
                st.session_state["active_case_code"] = bundle.case_code
                st.success("Run restored. Open DC Sizing to view results.")
