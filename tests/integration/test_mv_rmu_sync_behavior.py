from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


def _override_form_app() -> None:
    import streamlit as st

    from calb_sizing_tool.schemas.sld_render_input import legacy_sld_override_preset
    from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs

    result = render_electrical_inputs(
        legacy_sld_override_preset(),
        key_prefix="phase1_mv_rmu",
        mv_nominal_voltage_kv=st.session_state.get("mv_nominal_voltage_kv"),
    )
    st.session_state["phase1_mv_rmu.result"] = result.model_dump(mode="python")


def _find_number_input(app: AppTest, label: str):
    for widget in app.number_input:
        if widget.label == label:
            return widget
    raise AssertionError(f"Number input not found: {label}")


def test_rmu_rated_voltage_directly_tracks_poi_mv_voltage_and_ignores_stale_session_values():
    app = AppTest.from_function(_override_form_app, default_timeout=10)
    app.session_state["mv_nominal_voltage_kv"] = 33.0
    app.session_state["phase1_mv_rmu.rmu_rated_kv"] = 24.0
    app.session_state["phase1_mv_rmu.rmu_rated_kv_auto"] = 24.0
    app.session_state["phase1_mv_rmu.rmu_rated_kv_manual"] = 24.0
    app.session_state["phase1_mv_rmu.rmu_rated_kv_manual_override"] = True
    app.run()

    payload = app.session_state["phase1_mv_rmu.result"]
    assert payload["equipment_ratings"]["rmu"]["rated_kv"] == pytest.approx(33.0)

    app.session_state["mv_nominal_voltage_kv"] = 22.0
    app.run()
    payload = app.session_state["phase1_mv_rmu.result"]
    assert payload["equipment_ratings"]["rmu"]["rated_kv"] == pytest.approx(22.0)

    app.session_state["mv_nominal_voltage_kv"] = 33.0
    app.run()
    payload = app.session_state["phase1_mv_rmu.result"]
    assert payload["equipment_ratings"]["rmu"]["rated_kv"] == pytest.approx(33.0)
    assert "phase1_mv_rmu.rmu_rated_kv_manual_override" not in app.session_state


def test_override_form_no_longer_exposes_separate_rmu_voltage_override():
    app = AppTest.from_function(_override_form_app, default_timeout=10)
    app.session_state["mv_nominal_voltage_kv"] = 33.0
    app.run()

    payload = app.session_state["phase1_mv_rmu.result"]
    assert payload["equipment_ratings"]["rmu"]["rated_kv"] == pytest.approx(33.0)
    assert all(widget.label != "Manual override RMU equipment class" for widget in app.checkbox)

    app.session_state["mv_nominal_voltage_kv"] = 22.0
    app.run()
    payload = app.session_state["phase1_mv_rmu.result"]
    assert payload["equipment_ratings"]["rmu"]["rated_kv"] == pytest.approx(22.0)

    rmu_voltage_input = _find_number_input(app, "RMU rated voltage (kV)")
    assert rmu_voltage_input.value == pytest.approx(22.0)
