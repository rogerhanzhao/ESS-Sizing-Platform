from __future__ import annotations

from types import SimpleNamespace

import calb_sizing_tool.state.workspace_state as workspace_state
from tests.unit.test_sld_input_contract import _build_run_bundle


def _seed_session_state() -> dict:
    return {
        "active_run_id": "run-stale",
        "dc_last_run_id": "run-stale",
        "ac_output": {"source_run_id": "run-stale", "mv_voltage_kv": 11.0},
        "selected_ac_ratio": "1:2",
        "sld_artifacts": {"artifacts": ["stale"]},
        "sld_pipeline_meta": {"run_id": "run-stale"},
        "ac_inputs": {"grid_kv": 11.0, "mv_kv": 11.0, "grid_frequency_hz": 50.0},
        "ac_results": {"mv_voltage_kv": 11.0},
        "dc_results": {},
        "diagram_outputs": SimpleNamespace(
            sld_svg=b"svg",
            sld_png=b"png",
            sld_svg_path="old.svg",
            sld_png_path="old.png",
        ),
        "artifacts": {
            "sld_png_bytes": b"png",
            "sld_svg_bytes": b"svg",
            "sld_meta": {"run_id": "run-stale"},
        },
        "project_state": {
            "ac_inputs": {"grid_kv": 11.0},
            "ac_results": {"mv_voltage_kv": 11.0},
            "ac": {"run_id": "ac-stale", "results": {"foo": "bar"}},
            "dc": {},
            "inputs": {},
        },
    }


def test_clear_active_run_clears_downstream_runtime_state(monkeypatch):
    session_state = _seed_session_state()
    monkeypatch.setattr(workspace_state, "st", SimpleNamespace(session_state=session_state))

    workspace_state.clear_active_run()

    assert "active_run_id" not in session_state
    assert "dc_last_run_id" not in session_state
    assert "ac_output" not in session_state
    assert "sld_artifacts" not in session_state
    assert session_state["ac_inputs"] == {}
    assert session_state["ac_results"] == {}
    assert session_state["project_state"]["ac"]["run_id"] is None
    assert session_state["diagram_outputs"].sld_svg is None
    assert session_state["artifacts"]["sld_meta"] == {}


def test_restore_run_bundle_to_session_clears_stale_ac_state_and_seeds_case_voltage(monkeypatch, sample_excel_path):
    session_state = _seed_session_state()
    monkeypatch.setattr(workspace_state, "st", SimpleNamespace(session_state=session_state))

    bundle = _build_run_bundle(sample_excel_path)
    bundle.input_snapshot.payload["case_input"]["poi_nominal_voltage_kv"] = 34.5
    bundle.input_snapshot.payload["case_input"]["poi_frequency_hz"] = 60.0

    workspace_state.restore_run_bundle_to_session(bundle, bundle.run_id)

    assert "ac_output" not in session_state
    assert "sld_artifacts" not in session_state
    assert session_state["active_run_id"] == bundle.run_id
    assert session_state["dc_last_run_id"] == bundle.run_id
    assert session_state["poi_nominal_voltage_kv"] == 34.5
    assert session_state["grid_kv"] == 34.5
    assert session_state["poi_frequency_hz"] == 60.0
    assert session_state["ac_inputs"]["grid_kv"] == 34.5
    assert session_state["ac_inputs"]["mv_kv"] == 34.5
    assert session_state["ac_inputs"]["grid_frequency_hz"] == 60.0
    assert session_state["project_state"]["ac"]["run_id"] is None
    assert session_state["project_state"]["inputs"]["mv_kv"] == 34.5
    assert session_state["project_state"]["inputs"]["poi_freq_hz"] == 60.0
