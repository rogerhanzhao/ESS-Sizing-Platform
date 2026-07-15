# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
# -----------------------------------------------------------------------------

from pathlib import Path

from streamlit.testing.v1 import AppTest


def _app() -> AppTest:
    return AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=60)


def _enter_guest(app: AppTest) -> AppTest:
    app.run()
    guest_button = next(button for button in app.button if button.label.startswith("Continue as Guest"))
    guest_button.click()
    return app.run()


def test_guest_entry_defaults_to_dc_sizing_and_hides_restricted_navigation():
    app = _enter_guest(_app())

    assert app.session_state["auth_context"]["roles"] == ["guest"]
    assert app.session_state["main_nav"] == "DC Sizing"

    visible_buttons = {button.label for button in app.button}
    assert {"AC Sizing", "Single Line Diagram", "Typical AC Block Arrangement"} <= visible_buttons
    assert not {
        "Workbench",
        "Report Export",
        "Engineering Settings",
        "Project Directory",
        "Case Directory",
        "Run Registry",
    } & visible_buttons
    assert not app.exception


def test_guest_stale_restricted_navigation_is_clamped_to_dc_sizing():
    app = _enter_guest(_app())

    app.session_state["main_nav"] = "Workbench"
    app.run()
    assert app.session_state["main_nav"] == "DC Sizing"

    assert not app.exception


def test_guest_cannot_access_report_export_or_its_sign_in_cta():
    app = _enter_guest(_app())

    app.session_state["main_nav"] = "Report Export"
    app.run()

    assert app.session_state["main_nav"] == "DC Sizing"
    assert not any(button.label == "Sign In to Enable Export" for button in app.button)
    assert not app.exception


def test_guest_dc_sizing_stores_result_in_session():
    app = _enter_guest(_app())

    next(button for button in app.button if button.label == "Run Sizing").click()
    app.run(timeout=60)

    assert not app.exception
    assert not app.error
    assert app.success
    assert "guest_dc_run_snapshot" in app.session_state
    assert "dc_last_run_id" in app.session_state
