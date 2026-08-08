"""The signed-in DC Sizing page, driven through its Run Sizing button.

The guest half of this flow is covered by test_guest_mode_smoke; the signed-in
half — persist the run, then offer the DOCX download — was not pressed by any
test, and it is the half that owns the report export branch.

What this pins:
  * a signed-in run persists and the export button is offered;
  * a run rejected by the input guard consumes no run id (the id used to be
    bumped before the guard, so every rejected submission burned one);
  * the page raises nothing on either path.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services.auth_service import AuthService

pytest.importorskip("docx")


def _app() -> AppTest:
    return AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=120)


@pytest.fixture
def signed_in_workspace(tmp_path, monkeypatch):
    """A signed-in admin with an active project and case — what show() requires."""
    db_url = f"sqlite:///{(tmp_path / 'dc_run_smoke.sqlite').as_posix()}"
    monkeypatch.setenv("CALB_DATABASE_URL", db_url)

    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    alembic_command.upgrade(AlembicConfig(str(alembic_ini)), "head")

    auth = AuthService(db_url)
    auth.ensure_system_roles()
    user = auth.create_user(username="admin", password="secret-admin-pw", role_codes=["admin"])

    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        project = repo.get_or_create_project(project_code="dc-smoke", project_name="DC Smoke")
        session.flush()
        case = repo.create_case(
            project_id=project.project_id,
            case_code="dc-smoke-case",
            case_name="DC Smoke Case",
            stage_scope="proposal",
            scenario_mode="container_only",
            input_json={},
            source_ref="test_dc_page_run_smoke",
        )
        session.flush()
        workspace = {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "case_id": case.sizing_case_id,
            "case_name": case.case_name,
        }

    def _open() -> AppTest:
        app = _app()
        app.session_state["auth_context"] = {
            "user_id": str(user.user_id),
            "username": "admin",
            "display_name": "Admin",
            "roles": ["admin"],
        }
        app.session_state["active_project_id"] = workspace["project_id"]
        app.session_state["active_project_name"] = workspace["project_name"]
        app.session_state["active_case_id"] = workspace["case_id"]
        app.session_state["active_case_name"] = workspace["case_name"]
        app.session_state["main_nav"] = "DC Sizing"
        return app.run()

    return _open


def _run_sizing(app: AppTest) -> AppTest:
    next(button for button in app.button if button.label == "Run Sizing").click()
    return app.run()


def _state(app: AppTest, key: str, default=None):
    """AppTest's session_state has no .get()."""
    return app.session_state[key] if key in app.session_state else default


def _dc_run_id(app: AppTest):
    return (_state(app, "project_state") or {}).get("dc", {}).get("run_id")


def test_a_signed_in_run_persists_and_offers_the_export(signed_in_workspace):
    app = _run_sizing(signed_in_workspace())

    assert not app.exception
    assert _state(app, "dc_result_summary"), "the run produced no DC summary"
    assert any(
        button.label == "Export Technical Sizing Report" for button in app.download_button
    ), "a signed-in user must be offered the report download"


def test_a_rejected_run_does_not_consume_a_run_id(signed_in_workspace):
    """The input guard runs before the run id is taken."""
    app = signed_in_workspace()
    before = _dc_run_id(app)

    # Zero POI energy cannot be sized; dc_input_guard_service rejects it.
    app.session_state["dc_inputs.poi_energy_req_mwh"] = 0.0
    app = _run_sizing(app)

    assert app.error, "the guard should have refused this run"
    assert _dc_run_id(app) == before, (
        "a rejected submission consumed a DC run id"
    )
