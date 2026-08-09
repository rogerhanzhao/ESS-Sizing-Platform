"""A confirmed drawing that cannot be retrieved stops the export.

Owner ruling 2026-08-08:

    读取失败重读，要确认是没有生成还是读不到？如果走到了报告生成这一步，就是
    网页上是已经确认了生成才往下的！所以要确认清楚，获取成功再生成报告！

Reaching the Report Export page means the SLD and the arrangement were produced
and confirmed on their own pages. So a figure the artifact registry HAS but this
process cannot read is a RETRIEVAL problem, not a missing drawing — and a
proposal that silently omits a confirmed drawing is worse than no proposal.

The reads are retried first (artifact_service.retry_read). What survives the
retries now stops the export, fail-closed, with a retry control. A figure that
was genuinely never generated still does not block anything: that is the
ordinary "not generated" note in sections 7/8.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.services import artifact_service
from calb_sizing_tool.services.ac_run_service import persist_ac_run
from calb_sizing_tool.services.auth_service import AuthService

pytest.importorskip("docx")

_DOWNLOAD_LABEL_FRAGMENT = "Download Combined Report"


def _app() -> AppTest:
    return AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=180)


def _ac_output(run_id: str) -> dict:
    """A complete AC result tied to the DC parent run."""
    return {
        "source_run_id": run_id,
        "project_name": "Gate", "num_blocks": 20, "block_size_mw": 5.0,
        "pcs_per_block": 2, "pcs_kw": 2500, "pcs_count_total": 40,
        "grid_kv": 33.0, "mv_kv": 33.0, "lv_voltage_v": 800.0,
        "transformer_kva": 5555.0, "dc_blocks_per_ac": 4,
    }


@pytest.fixture
def session_with_a_finished_run(tmp_path, monkeypatch):
    """A signed-in session that has completed DC sizing — ready to export."""
    monkeypatch.setattr(artifact_service, "_READ_BACKOFF_S", 0)
    db_url = f"sqlite:///{(tmp_path / 'export_gate.sqlite').as_posix()}"
    monkeypatch.setenv("CALB_DATABASE_URL", db_url)
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path / "outputs"))

    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    alembic_command.upgrade(AlembicConfig(str(alembic_ini)), "head")

    auth = AuthService(db_url)
    auth.ensure_system_roles()
    user = auth.create_user(username="admin", password="secret-admin-pw", role_codes=["admin"])

    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        project = repo.get_or_create_project(project_code="gate", project_name="Gate")
        session.flush()
        case = repo.create_case(
            project_id=project.project_id, case_code="gate-case", case_name="Gate Case",
            stage_scope="proposal", scenario_mode="container_only", input_json={},
            source_ref="test_report_export_requires_the_figures",
        )
        session.flush()
        ids = (project.project_id, case.sizing_case_id)

    # One session performs the sizing; a SECOND opens the export page. AppTest
    # cannot navigate away from a page in the same run that submitted its form,
    # so the two are split — which also matches how the export is really reached.
    sizing = _app()
    auth_context = {
        "user_id": str(user.user_id), "username": "admin",
        "display_name": "Admin", "roles": ["admin"],
    }
    sizing.session_state["auth_context"] = auth_context
    sizing.session_state["active_project_id"] = ids[0]
    sizing.session_state["active_case_id"] = ids[1]
    sizing.session_state["main_nav"] = "DC Sizing"
    sizing.run()
    next(button for button in sizing.button if button.label == "Run Sizing").click()
    sizing.run()

    run_id = sizing.session_state["dc_last_run_id"]
    stage13_output = sizing.session_state["stage13_output"]

    def open_export(active_ac_run_id: str | None = None) -> AppTest:
        app = _app()
        app.session_state["auth_context"] = auth_context
        app.session_state["active_project_id"] = ids[0]
        app.session_state["active_case_id"] = ids[1]
        app.session_state["dc_last_run_id"] = run_id
        app.session_state["active_run_id"] = run_id
        app.session_state["stage13_output"] = stage13_output
        # An AC result is required before the page offers an export at all.
        # `ac_results` is what the compatibility resolver reads (the page does
        # not take session `ac_output` directly).
        ac = _ac_output(run_id)
        app.session_state["ac_results"] = ac
        app.session_state["ac_inputs"] = {"grid_kv": 33.0, "mv_kv": 33.0, "lv_voltage_v": 800.0}
        if active_ac_run_id:
            app.session_state["active_ac_run_id"] = active_ac_run_id
        app.session_state["main_nav"] = "Report Export"
        app.run()
        return app

    return open_export, run_id


def _record_an_sld(run_id: str) -> Path:
    """Register a real SLD artifact — the run HAS one, confirmed."""
    artifact_service.persist_artifacts(
        run_id=run_id,
        artifacts=[ArtifactPayload(
            artifact_kind="sld_svg", file_name="sld.svg", media_type="image/svg+xml",
            content=b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>",
            metadata={},
        )],
        plugin_id="test_plugin", plugin_version="1.0.0",
    )
    from calb_sizing_tool.infra.db.models.artifact_registry import ArtifactRegistry

    with session_scope() as session:
        row = session.query(ArtifactRegistry).filter(
            ArtifactRegistry.sizing_run_id == run_id
        ).one()
        return artifact_service.resolve_artifact_path(str(row.file_path))


def _download_offered(app: AppTest) -> bool:
    return any(_DOWNLOAD_LABEL_FRAGMENT in b.label for b in app.get("download_button"))


def _errors(app: AppTest) -> str:
    return "\n".join(e.value for e in app.error)


def test_a_run_with_no_figures_still_exports(session_with_a_finished_run):
    """"Never generated" must not be treated as a retrieval failure."""
    open_export, _run_id = session_with_a_finished_run
    app = open_export()

    assert not app.exception
    assert "could not be retrieved" not in _errors(app)
    assert _download_offered(app), "a run without drawings must still produce a report"


def test_a_recorded_figure_that_cannot_be_read_blocks_the_export(
    session_with_a_finished_run, monkeypatch
):
    """The ruling: confirm retrieval succeeded before generating."""
    open_export, run_id = session_with_a_finished_run
    artifact_path = _record_an_sld(run_id)

    real_read_bytes = Path.read_bytes

    def unreadable(self):
        if self.name == artifact_path.name:
            raise OSError("Input/output error")
        return real_read_bytes(self)

    monkeypatch.setattr("pathlib.Path.read_bytes", unreadable)

    app = open_export()

    assert not app.exception
    assert not _download_offered(app), (
        "the export produced a report while a confirmed drawing was unreadable"
    )
    errors = _errors(app)
    assert "could not be retrieved" in errors
    assert "not a missing drawing" in errors
    assert any("Retry" in b.label for b in app.button), "no way to retry the fetch"


def test_the_export_recovers_once_the_figure_can_be_read(session_with_a_finished_run):
    """The retry has to actually lead somewhere."""
    open_export, run_id = session_with_a_finished_run
    _record_an_sld(run_id)

    app = open_export()

    assert not app.exception
    assert "could not be retrieved" not in _errors(app)
    assert _download_offered(app), "a readable figure must let the export through"


def test_a_selected_ac_alternative_resolves_from_its_dc_parent(session_with_a_finished_run):
    """Selecting an AC child must not make Report Export call it the DC run.

    The alternative's ``source_run_id`` is its DC parent.  Artifacts attach to
    the child, but ``resolve_preferred_ac_snapshot`` must receive the parent so
    its cross-run guard accepts the selected configuration.
    """
    open_export, run_id = session_with_a_finished_run
    alternative = persist_ac_run(
        dc_run_id=run_id,
        ac_inputs={"grid_kv": 33.0, "mv_kv": 33.0, "lv_voltage_v": 800.0},
        ac_output=_ac_output(run_id),
    )
    assert alternative is not None

    app = open_export(active_ac_run_id=alternative.run_id)

    assert not app.exception
    assert "AC sizing is missing" not in "\n".join(message.value for message in app.info)
    assert _download_offered(app), "the selected AC alternative must enable export"
