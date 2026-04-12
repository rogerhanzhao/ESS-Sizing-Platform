from __future__ import annotations

from typing import Any

import streamlit as st

from calb_sizing_tool.adapters.session_state_adapter import build_dc_result_summary, build_stage13_output
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


def get_workspace_context() -> dict[str, Any]:
    return {
        "project_id": st.session_state.get("active_project_id"),
        "project_code": st.session_state.get("active_project_code"),
        "project_name": st.session_state.get("active_project_name"),
        "case_id": st.session_state.get("active_case_id"),
        "case_code": st.session_state.get("active_case_code"),
        "case_name": st.session_state.get("active_case_name"),
        "run_id": st.session_state.get("active_run_id") or st.session_state.get("dc_last_run_id"),
    }


def navigate_to(page_name: str) -> None:
    st.session_state["main_nav"] = page_name


def clear_active_run() -> None:
    st.session_state.pop("active_run_id", None)


def clear_active_case() -> None:
    st.session_state.pop("active_case_id", None)
    st.session_state.pop("active_case_code", None)
    st.session_state.pop("active_case_name", None)
    clear_active_run()


def set_active_project(*, project_id: str | None, project_code: str | None, project_name: str | None) -> None:
    changed = (
        st.session_state.get("active_project_id") != project_id
        or st.session_state.get("active_project_code") != project_code
        or st.session_state.get("active_project_name") != project_name
    )
    st.session_state["active_project_id"] = project_id
    st.session_state["active_project_code"] = project_code
    st.session_state["active_project_name"] = project_name
    if changed:
        clear_active_case()


def set_active_case(*, case_id: str | None, case_code: str | None, case_name: str | None) -> None:
    changed = (
        st.session_state.get("active_case_id") != case_id
        or st.session_state.get("active_case_code") != case_code
        or st.session_state.get("active_case_name") != case_name
    )
    st.session_state["active_case_id"] = case_id
    st.session_state["active_case_code"] = case_code
    st.session_state["active_case_name"] = case_name
    if changed:
        clear_active_run()


def set_active_run(run_id: str | None) -> None:
    st.session_state["active_run_id"] = run_id
    st.session_state["dc_last_run_id"] = run_id


def restore_run_bundle_to_session(bundle: DcRunBundle, run_id: str) -> None:
    snapshot = bundle.snapshot
    case_input = (
        bundle.input_snapshot.payload.get("case_input")
        if bundle.input_snapshot and isinstance(bundle.input_snapshot.payload, dict)
        else {}
    )
    poi_nominal_voltage_kv = case_input.get("poi_nominal_voltage_kv", 33.0)
    poi_frequency_hz = case_input.get("poi_frequency_hz")

    set_active_project(
        project_id=bundle.project_id,
        project_code=bundle.project_code,
        project_name=bundle.project_name,
    )
    set_active_case(
        case_id=bundle.sizing_case_id,
        case_code=bundle.case_code,
        case_name=bundle.case_name,
    )
    set_active_run(run_id)

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
        dc_results["last_run_id"] = run_id

    project_state = st.session_state.get("project_state")
    if isinstance(project_state, dict):
        project_state.setdefault("dc", {})["run_id"] = run_id
