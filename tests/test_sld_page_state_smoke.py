# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.schemas.diagram_inputs import DiagramArtifactBundle


def _app() -> AppTest:
    return AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10)


def _login(app: AppTest) -> None:
    app.session_state["auth_context"] = {
        "user_id": "test-admin",
        "username": "admin",
        "display_name": "Admin",
        "roles": ["admin"],
    }


def _go_to(app: AppTest, page: str) -> AppTest:
    app.session_state["main_nav"] = page
    return app.run()


def _sld_settings_navigation_app() -> None:
    """Render the two pages involved in the SLD settings handoff only."""
    import streamlit as st

    st.session_state.setdefault(
        "auth_context",
        {
            "user_id": "test-admin",
            "username": "admin",
            "display_name": "Admin",
            "roles": ["admin"],
        },
    )
    st.session_state.setdefault("active_case_id", "case-test")
    st.session_state.setdefault("active_case_name", "Case Test")

    if st.session_state.get("main_nav") == "Engineering Settings":
        from calb_sizing_tool.ui.engineering_settings_view import show
    else:
        from calb_sizing_tool.ui.single_line_diagram_view import show
    show()


def test_sld_first_visit_no_crash():
    app = _app()
    _login(app)
    app.run()
    _go_to(app, "Single Line Diagram")
    assert len(app.exception) == 0


def test_sld_keeps_pipeline_next_steps_visible_and_navigable():
    app = _app()
    _login(app)
    app.run()
    _go_to(app, "Single Line Diagram")

    buttons = {button.label: button for button in app.button}
    assert "Typical AC Block Arrangement →" in buttons
    assert "Report Export →" in buttons

    buttons["Typical AC Block Arrangement →"].click()
    app.run()
    assert app.session_state["main_nav"] == "Typical AC Block Arrangement"
    assert len(app.exception) == 0


def test_sld_page_keeps_ac_lv_value_across_pages():
    app = _app()
    _login(app)
    app.session_state["ac_inputs"] = {"lv_voltage_v": 690.0, "pcs_lv_v": 690.0, "grid_kv": 33.0}
    app.run()

    _go_to(app, "Single Line Diagram")
    assert app.session_state["ac_inputs"]["lv_voltage_v"] == pytest.approx(690.0)

    _go_to(app, "Site Layout")
    _go_to(app, "Single Line Diagram")
    assert app.session_state["ac_inputs"]["lv_voltage_v"] == pytest.approx(690.0)


def test_sld_clear_preview_removes_runtime_artifacts():
    app = _app()
    _login(app)
    _go_to(app, "Single Line Diagram")

    app.session_state["sld_artifacts"] = DiagramArtifactBundle(
        plugin_id="sld_engineering_v1",
        plugin_version="1.3.0",
        run_id="run-test",
        metadata={},
        artifacts=[],
    )
    app.session_state["sld_pipeline_meta"] = {"run_id": "run-test", "artifact_mode": "concept"}
    app.run()

    clear_button = next(button for button in app.button if button.label == "Clear Preview")
    assert not clear_button.disabled

    clear_button.click()
    app.run()
    assert "sld_artifacts" not in app.session_state
    assert "sld_pipeline_meta" not in app.session_state
    assert not app.exception

def test_sld_open_engineering_settings_navigates_to_settings_page():
    app = AppTest.from_function(_sld_settings_navigation_app, default_timeout=10)
    app.run()

    settings_button = next(button for button in app.button if button.label == "Open Engineering Settings")
    settings_button.click()
    app.run()

    assert app.session_state["main_nav"] == "Engineering Settings"
    assert not app.exception


def test_sld_override_mode_reveals_and_hides_draft_controls():
    app = _app()
    _login(app)
    _go_to(app, "Single Line Diagram")

    override = next(item for item in app.checkbox if item.label == "Enable Engineering Override Mode")
    base_number_inputs = len(app.number_input)
    base_text_inputs = len(app.text_input)

    override.set_value(True)
    app.run()

    assert next(item for item in app.checkbox if item.label == "Enable Engineering Override Mode").value is True
    assert any("non-official draft" in str(item.value) for item in app.warning)
    assert len(app.number_input) > base_number_inputs or len(app.text_input) > base_text_inputs

    next(item for item in app.checkbox if item.label == "Enable Engineering Override Mode").set_value(False)
    app.run()

    assert next(item for item in app.checkbox if item.label == "Enable Engineering Override Mode").value is False
    assert not any("non-official draft" in str(item.value) for item in app.warning)
    assert not app.exception
