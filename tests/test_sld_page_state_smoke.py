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


def test_sld_first_visit_no_crash():
    app = _app()
    _login(app)
    app.run()
    _go_to(app, "Single Line Diagram")
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
