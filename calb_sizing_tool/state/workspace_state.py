from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st

from calb_sizing_tool.adapters.session_state_adapter import build_dc_result_summary, build_stage13_output
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.services.sld_data_source_service import load_persisted_ac_snapshot

MAIN_NAV_KEY = "main_nav"
PENDING_MAIN_NAV_KEY = "_pending_main_nav"
PENDING_DC_INPUT_RESTORE_KEY = "_pending_dc_input_restore"

# These are the editable DC form fields persisted in the run input snapshot.
# Keep this list aligned with the DC form and SizingCaseInput schema so restore
# remains an input restore, not just a result restore.
_DC_INPUT_FIELDS = (
    "project_name",
    "poi_power_req_mw",
    "poi_energy_req_mwh",
    "project_life_years",
    "poi_nominal_voltage_kv",
    "cycles_per_year",
    "poi_guarantee_year",
    "sc_time_months",
    "dod_pct",
    "dc_round_trip_efficiency_pct",
    "rte_curve_adjust_pp",
    "rte_monotonic_enforce",
    "enable_hybrid",
    "enable_cabinet_only",
    "hybrid_disable_threshold_mwh",
    "poi_is_dc_side",
    "eff_dc_cables",
    "eff_pcs",
    "eff_mvt",
    "eff_ac_cables_sw_rmu",
    "eff_hvt_others",
)


def _clear_sld_runtime_state() -> None:
    # These controls are keyed widgets. Their values otherwise win over the
    # current active-run default after a workspace/run switch.
    st.session_state.pop("sld_run_id_override", None)
    st.session_state.pop("sld_artifacts", None)
    st.session_state.pop("sld_pipeline_meta", None)

    diagram_outputs = st.session_state.get("diagram_outputs")
    if diagram_outputs is not None:
        for field_name in ("sld_svg", "sld_png", "sld_svg_path", "sld_png_path"):
            if hasattr(diagram_outputs, field_name):
                setattr(diagram_outputs, field_name, None)

    artifacts = st.session_state.get("artifacts")
    if isinstance(artifacts, dict):
        artifacts["sld_png_bytes"] = None
        artifacts["sld_svg_bytes"] = None
        artifacts["sld_meta"] = {}


def _clear_layout_runtime_state() -> None:
    """Remove layout output and its explicit run selector on run changes."""
    st.session_state.pop("layout_run_id_override", None)
    st.session_state.pop("layout_artifacts", None)


def _clear_ac_runtime_state() -> None:
    st.session_state.pop("ac_output", None)
    st.session_state.pop("selected_ac_ratio", None)

    for key in ("ac_inputs", "ac_results"):
        value = st.session_state.get(key)
        if isinstance(value, dict):
            value.clear()

    project_state = st.session_state.get("project_state")
    if isinstance(project_state, dict):
        for key in ("ac_inputs", "ac_results"):
            value = project_state.get(key)
            if isinstance(value, dict):
                value.clear()
        ac_state = project_state.get("ac")
        if isinstance(ac_state, dict):
            ac_state["run_id"] = None
            ac_state["results"] = {}


def _clear_downstream_runtime_state() -> None:
    _clear_ac_runtime_state()
    _clear_sld_runtime_state()
    _clear_layout_runtime_state()


def _clear_dc_input_state() -> None:
    """Remove editable DC form state when the active Case changes."""
    dc_inputs = st.session_state.get("dc_inputs")
    if isinstance(dc_inputs, dict):
        dc_inputs.clear()

    project_state = st.session_state.get("project_state")
    if isinstance(project_state, dict):
        project_dc_inputs = project_state.get("dc_inputs")
        if isinstance(project_dc_inputs, dict):
            project_dc_inputs.clear()

    for key in list(st.session_state):
        if str(key).startswith("dc_inputs."):
            st.session_state.pop(key, None)

    for key in ("poi_nominal_voltage_kv", "poi_frequency_hz", "grid_kv"):
        st.session_state.pop(key, None)

    st.session_state.pop(PENDING_DC_INPUT_RESTORE_KEY, None)


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
    """Set the target page for both immediate and next-run routing."""
    st.session_state[MAIN_NAV_KEY] = page_name
    st.session_state[PENDING_MAIN_NAV_KEY] = page_name


def navigate_now(page_name: str) -> None:
    """Route to a page from a button click and force Streamlit to rerender."""
    navigate_to(page_name)
    st.rerun()


def apply_pending_navigation(nav_options: Sequence[str], *, default_page: str = "Workbench") -> str:
    pending_page = st.session_state.pop(PENDING_MAIN_NAV_KEY, None)
    if pending_page in nav_options:
        st.session_state[MAIN_NAV_KEY] = pending_page

    fallback_page = default_page if default_page in nav_options else nav_options[0]
    if st.session_state.get(MAIN_NAV_KEY) not in nav_options:
        st.session_state[MAIN_NAV_KEY] = fallback_page
    return str(st.session_state[MAIN_NAV_KEY])


def clear_active_run() -> None:
    had_downstream_context = any(
        (
            st.session_state.get("active_run_id"),
            st.session_state.get("dc_last_run_id"),
            st.session_state.get("ac_output"),
            st.session_state.get("sld_artifacts"),
            st.session_state.get("sld_pipeline_meta"),
            st.session_state.get("layout_artifacts"),
            st.session_state.get("sld_run_id_override"),
            st.session_state.get("layout_run_id_override"),
        )
    )
    st.session_state.pop("active_run_id", None)
    st.session_state.pop("dc_last_run_id", None)
    if had_downstream_context:
        _clear_downstream_runtime_state()


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
        _clear_dc_input_state()
        clear_active_run()


def set_active_run(run_id: str | None) -> None:
    current_run_id = st.session_state.get("active_run_id") or st.session_state.get("dc_last_run_id")
    if current_run_id != run_id:
        _clear_downstream_runtime_state()
    st.session_state["active_run_id"] = run_id
    st.session_state["dc_last_run_id"] = run_id


def _case_input_from_bundle(bundle: DcRunBundle) -> dict[str, Any]:
    if not bundle.input_snapshot or not isinstance(bundle.input_snapshot.payload, dict):
        return {}
    case_input = bundle.input_snapshot.payload.get("case_input")
    return case_input if isinstance(case_input, dict) else {}


def _build_restored_dc_inputs(case_input: dict[str, Any]) -> dict[str, Any]:
    restored = {
        field: case_input[field]
        for field in _DC_INPUT_FIELDS
        if field in case_input and case_input[field] is not None
    }

    if "poi_frequency_option" in case_input and case_input["poi_frequency_option"] is not None:
        restored["poi_frequency_option"] = case_input["poi_frequency_option"]
    elif "poi_frequency_hz" in case_input:
        frequency = case_input.get("poi_frequency_hz")
        restored["poi_frequency_option"] = "TBD" if frequency is None else float(frequency)
    if "poi_frequency_hz" in case_input:
        restored["poi_frequency_hz"] = case_input.get("poi_frequency_hz")

    return restored


def apply_pending_dc_input_restore() -> dict[str, Any]:
    """Apply a pending restore before DC widgets are instantiated."""
    pending = st.session_state.pop(PENDING_DC_INPUT_RESTORE_KEY, None)
    if not isinstance(pending, dict) or not pending:
        return {}

    dc_inputs = st.session_state.setdefault("dc_inputs", {})
    if isinstance(dc_inputs, dict):
        dc_inputs.update(pending)

    project_state = st.session_state.get("project_state")
    if isinstance(project_state, dict):
        project_dc_inputs = project_state.setdefault("dc_inputs", {})
        if isinstance(project_dc_inputs, dict):
            project_dc_inputs.update(pending)

    for field, value in pending.items():
        st.session_state[f"dc_inputs.{field}"] = value

    return pending


def restore_run_bundle_to_session(
    bundle: DcRunBundle,
    run_id: str,
    *,
    queue_widget_restore: bool = True,
) -> None:
    snapshot = bundle.snapshot
    case_input = _case_input_from_bundle(bundle)
    restored_dc_inputs = _build_restored_dc_inputs(case_input)
    poi_nominal_voltage_kv = case_input.get("poi_nominal_voltage_kv") or 33.0
    poi_frequency_hz = case_input.get("poi_frequency_hz")

    _clear_downstream_runtime_state()

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

    # Store the full editable form payload and apply it on the next DC page
    # render. The deferred widget update avoids mutating Streamlit widget keys
    # after a form has already been instantiated in the current script run.
    dc_inputs = st.session_state.setdefault("dc_inputs", {})
    if isinstance(dc_inputs, dict):
        dc_inputs.update(restored_dc_inputs)
    project_state = st.session_state.get("project_state")
    if isinstance(project_state, dict):
        project_dc_inputs = project_state.setdefault("dc_inputs", {})
        if isinstance(project_dc_inputs, dict):
            project_dc_inputs.update(restored_dc_inputs)
    if queue_widget_restore:
        st.session_state[PENDING_DC_INPUT_RESTORE_KEY] = restored_dc_inputs
    else:
        # Post-run refresh: the form widgets already hold exactly what the
        # user submitted. Queuing a widget overwrite here would stomp the
        # user's NEXT form edits on the submit rerun (edits silently revert
        # to this run's values). Only explicit restore flows queue it.
        st.session_state.pop(PENDING_DC_INPUT_RESTORE_KEY, None)

    st.session_state["dc_result_summary"] = build_dc_result_summary(snapshot)
    st.session_state["stage13_output"] = build_stage13_output(
        snapshot,
        dc_block_total_qty=int(snapshot.stage2.container_count + snapshot.stage2.cabinet_count),
        selected_scenario=str(bundle.scenario_mode or snapshot.stage2.mode or "container_only"),
        poi_nominal_voltage_kv=float(poi_nominal_voltage_kv),
        poi_frequency_hz=poi_frequency_hz,
    )
    st.session_state["poi_nominal_voltage_kv"] = float(poi_nominal_voltage_kv)
    st.session_state["grid_kv"] = float(poi_nominal_voltage_kv)
    if poi_frequency_hz is not None:
        st.session_state["poi_frequency_hz"] = float(poi_frequency_hz)

    dc_results = st.session_state.get("dc_results")
    if isinstance(dc_results, dict):
        dc_results["dc_result_summary"] = st.session_state.get("dc_result_summary")
        dc_results["stage13_output"] = st.session_state.get("stage13_output")
        dc_results["last_run_id"] = run_id

    ac_inputs = st.session_state.get("ac_inputs")
    if isinstance(ac_inputs, dict):
        ac_inputs["grid_kv"] = float(poi_nominal_voltage_kv)
        ac_inputs["mv_kv"] = float(poi_nominal_voltage_kv)
        if poi_frequency_hz is not None:
            ac_inputs["grid_frequency_hz"] = float(poi_frequency_hz)

    project_state = st.session_state.get("project_state")
    if isinstance(project_state, dict):
        project_state.setdefault("dc", {})["run_id"] = run_id
        inputs_state = project_state.setdefault("inputs", {})
        inputs_state["project_name"] = bundle.project_name
        inputs_state["mv_kv"] = float(poi_nominal_voltage_kv)
        if poi_frequency_hz is not None:
            inputs_state["poi_freq_hz"] = float(poi_frequency_hz)

    # Restore AC snapshot persisted against this DC run (if present in DB).
    # This allows the report export and SLD pages to work immediately after
    # a run restore, without requiring the user to re-run AC sizing.
    try:
        ac_snapshot = load_persisted_ac_snapshot(run_id)
        if ac_snapshot is not None and isinstance(ac_snapshot.output, dict) and ac_snapshot.output:
            ac_output = ac_snapshot.output
            st.session_state["ac_output"] = ac_output
            ac_results = st.session_state.get("ac_results")
            if isinstance(ac_results, dict):
                ac_results.update(ac_output)
            ac_inputs_restored = ac_snapshot.inputs
            if isinstance(ac_inputs_restored, dict) and ac_inputs_restored:
                ac_inputs_state = st.session_state.get("ac_inputs")
                if isinstance(ac_inputs_state, dict):
                    ac_inputs_state.update(ac_inputs_restored)
                if isinstance(project_state, dict):
                    project_state.setdefault("ac", {})["run_id"] = ac_output.get("source_ac_run_id")
                    project_state["ac_results"] = ac_output
    except Exception:
        pass  # DB not available or snapshot absent — silent; user can re-run AC sizing
