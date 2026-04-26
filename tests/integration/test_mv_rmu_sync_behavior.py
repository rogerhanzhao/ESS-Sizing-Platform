from __future__ import annotations

from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.ui import single_line_diagram_view


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


def _override_form_with_bess_cell_app() -> None:
    import streamlit as st

    from calb_sizing_tool.schemas.sld_render_input import legacy_sld_override_preset
    from calb_sizing_tool.ui.sld_inputs import render_electrical_inputs

    defaults = legacy_sld_override_preset()
    defaults["equipment_ratings"]["battery_cell_spec"] = "LFP 3.2V/314Ah"
    result = render_electrical_inputs(
        defaults,
        key_prefix="phase1_sld_bess",
        mv_nominal_voltage_kv=st.session_state.get("mv_nominal_voltage_kv"),
    )
    st.session_state["phase1_sld_bess.result"] = result.model_dump(mode="python")


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


def test_sld_form_exposes_bess_cell_spec_for_professional_notes():
    app = AppTest.from_function(_override_form_with_bess_cell_app, default_timeout=10)
    app.session_state["mv_nominal_voltage_kv"] = 33.0
    app.run()

    payload = app.session_state["phase1_sld_bess.result"]
    assert payload["equipment_ratings"]["battery_cell_spec"] == "LFP 3.2V/314Ah"
    assert any(widget.label == "BESS cell spec" for widget in app.text_input)


def test_sld_visible_mv_voltage_prefers_resolved_ac_snapshot_over_stale_session(monkeypatch):
    monkeypatch.setattr(
        single_line_diagram_view,
        "st",
        SimpleNamespace(session_state={"poi_nominal_voltage_kv": 33.0}),
    )
    project_state = {"dc_inputs": {"poi_nominal_voltage_kv": 33.0}}
    shared_state = SimpleNamespace(dc_inputs={"poi_nominal_voltage_kv": 33.0})
    ac_snapshot = AcSnapshot(
        inputs={"grid_kv": 22.0},
        output={"mv_voltage_kv": 22.0},
        results={},
    )

    resolved = single_line_diagram_view._resolve_mv_nominal_voltage_kv(
        shared_state,
        project_state,
        ac_snapshot,
    )

    assert resolved == pytest.approx(22.0)
