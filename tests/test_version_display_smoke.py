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

"""The version has to be on the SCREEN, not merely computable.

Every other test around versioning asserts on functions and files. None of them
runs the page, so none would have caught an exception in the sidebar caption or
the login footer — and a crash there takes the whole app with it, which is a
worse outcome than the stale "v2.1" this feature replaced.

AppTest executes app.py for real, so an unsupported keyword (`st.caption(help=)`
on an older Streamlit), a missing import, or an escaping error surfaces here
instead of in front of a user.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.app_version import release_version, version_label


@pytest.fixture()
def app(tmp_path, monkeypatch) -> AppTest:
    monkeypatch.setenv("CALB_DATABASE_URL", f"sqlite:///{(tmp_path / 'v.sqlite').as_posix()}")
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path / "out"))

    # Migrate explicitly, as tests/test_sld_page_state_smoke.py does. app.py runs
    # migrations under @st.cache_resource, so they fire ONCE PER PROCESS: the
    # second app-level test in a session gets a fresh database that was never
    # migrated, and the page then dies on "no such table". Every test here would
    # pass alone and fail in the suite.
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    alembic_command.upgrade(AlembicConfig(str(alembic_ini)), "head")

    return AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)


def _all_text(rendered: AppTest) -> str:
    """Every Markdown/Caption in the tree, including inside columns and blocks.

    ``rendered.markdown`` is top-level only; the login footer lives inside a
    column, so a helper that ignored the tree would report it missing.
    """
    parts: list[str] = []
    for name in ("markdown", "caption"):
        parts.extend(str(e.value) for e in getattr(rendered, name))
        parts.extend(str(e.value) for e in getattr(rendered.sidebar, name))
    for column in rendered.columns:
        for name in ("markdown", "caption"):
            parts.extend(str(e.value) for e in getattr(column, name))
    return "\n".join(parts)


def test_the_app_renders_without_exception_when_signed_out(app):
    rendered = app.run()
    assert not rendered.exception, [str(e) for e in rendered.exception]


def test_the_login_page_shows_the_version(app):
    """Checking whether an upgrade landed must not require credentials."""
    rendered = app.run()
    assert not rendered.exception, [str(e) for e in rendered.exception]
    assert version_label() in _all_text(rendered)


def test_the_sidebar_shows_the_version_after_signing_in(app):
    app.session_state["auth_context"] = {
        "user_id": "test-admin",
        "username": "admin",
        "display_name": "Admin",
        "roles": ["admin"],
    }
    rendered = app.run()
    assert not rendered.exception, [str(e) for e in rendered.exception]

    sidebar_text = "\n".join(str(e.value) for e in rendered.sidebar.caption)
    assert version_label() in sidebar_text, (
        f"the version must be in the sidebar; saw: {sidebar_text!r}"
    )
    assert "CALB ESS Sizing Platform" in sidebar_text
    assert "db:" in sidebar_text, "the schema revision belongs on the same line"


def test_the_version_on_screen_carries_a_capital_v(app):
    """Owner: "版本的 V 请大写"."""
    rendered = app.run()
    assert not rendered.exception, [str(e) for e in rendered.exception]
    text = _all_text(rendered)
    assert release_version() in text
    # And never the lower-cased form the sidebar used to hard-code.
    assert release_version().lower() not in text
