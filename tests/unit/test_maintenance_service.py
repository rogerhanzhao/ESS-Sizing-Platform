"""Bounded growth (owner requirement 2026-08-04: 日志和数据库不能无限制的变大).

The defect these lock in place: deploy/docker/calb-maintenance.sh deleted output
FILES older than 30 days and nothing else, so artifact_registry rows survived
pointing at files that were gone. load_artifact_bytes_from_db swallows every
error, so an old run's report lost its figures silently. Pruning is now always
row-and-file together.
"""
from __future__ import annotations

import datetime

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import ArtifactRegistry
from calb_sizing_tool.infra.db.models.audit_log import AuditLog
from calb_sizing_tool.infra.db.models.run_output_snapshot import RunOutputSnapshot
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services import maintenance_service as ms


def _seed_run(url: str, run_id: str = "r1") -> str:
    """artifact_registry has a real FK to sizing_run — seed the parents."""
    from calb_sizing_tool.infra.db.models.project import Project
    from calb_sizing_tool.infra.db.models.sizing_run import SizingRun

    with session_scope(url) as session:
        project = Project(project_id="p1", project_code="P1", project_name="P1")
        session.add(project)
        session.flush()
        session.add(SizingRun(
            sizing_run_id=run_id, project_id=project.project_id,
            sizing_case_id=None, run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))
    return run_id


@pytest.fixture()
def db_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'maint.sqlite').as_posix()}"
    with session_scope(url) as session:
        Base.metadata.create_all(bind=session.get_bind())
    _seed_run(url)
    return url


def _ago(days: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)


def _artifact(session, run_id, kind, stored_path, *, age_days=0):
    row = ArtifactRegistry(
        sizing_run_id=run_id, artifact_kind=kind,
        file_name=stored_path.split("/")[-1], file_path=stored_path,
        media_type="image/svg+xml", content_hash="h", metadata_json={},
    )
    session.add(row)
    session.flush()
    if age_days:
        row.created_at = _ago(age_days)
    return row


def test_a_row_whose_file_is_gone_is_removed(db_url, tmp_path, monkeypatch):
    """The exact wreckage the file-only retention sweep used to leave behind."""
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    live = tmp_path / "artifacts" / "r1" / "keep.svg"
    live.parent.mkdir(parents=True)
    live.write_text("<svg/>")

    with session_scope(db_url) as session:
        _artifact(session, "r1", "sld_svg", "artifacts/r1/keep.svg")
        _artifact(session, "r1", "layout_svg", "artifacts/r1/deleted-by-the-timer.svg")

    report = ms.prune_orphaned_artifacts(db_url=db_url)
    assert report.orphaned_rows == 1

    with session_scope(db_url) as session:
        remaining = [row.artifact_kind for row in session.query(ArtifactRegistry).all()]
    assert remaining == ["sld_svg"]


def test_age_pruning_removes_the_row_and_the_file_together(db_url, tmp_path, monkeypatch):
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    old = tmp_path / "artifacts" / "r1" / "old.svg"
    new = tmp_path / "artifacts" / "r1" / "new.svg"
    old.parent.mkdir(parents=True)
    old.write_text("<svg>old</svg>")
    new.write_text("<svg>new</svg>")

    with session_scope(db_url) as session:
        _artifact(session, "r1", "sld_svg", "artifacts/r1/old.svg", age_days=90)
        _artifact(session, "r1", "layout_svg", "artifacts/r1/new.svg")

    report = ms.prune_artifacts_older_than(31, db_url=db_url)
    assert report.artifact_rows == 1
    assert report.artifact_files == 1
    assert report.bytes_freed > 0
    assert not old.exists()
    assert new.exists()

    with session_scope(db_url) as session:
        assert session.query(ArtifactRegistry).count() == 1


def test_retention_can_be_switched_off(db_url, tmp_path, monkeypatch):
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    with session_scope(db_url) as session:
        _artifact(session, "r1", "sld_svg", "artifacts/r1/x.svg", age_days=999)
    report = ms.prune_artifacts_older_than(0, db_url=db_url)
    assert report.artifact_rows == 0
    assert "disabled" in " ".join(report.notes)
    with session_scope(db_url) as session:
        assert session.query(ArtifactRegistry).count() == 1


def test_only_the_newest_snapshot_generations_are_kept(db_url):
    """AC re-runs append a full output document while only the newest is read."""
    with session_scope(db_url) as session:
        for i in range(6):
            row = RunOutputSnapshot(
                sizing_run_id="r1", snapshot_kind="ac_runtime_snapshot_v1",
                content_hash=f"h{i}", snapshot_json={"i": i},
            )
            session.add(row)
            session.flush()
            row.created_at = _ago(6 - i)
        # A different kind is a separate lineage and must be untouched.
        session.add(RunOutputSnapshot(
            sizing_run_id="r1", snapshot_kind="dc_pipeline_output",
            content_hash="d", snapshot_json={},
        ))

    report = ms.prune_snapshot_generations(2, db_url=db_url)
    assert report.snapshot_rows == 4

    with session_scope(db_url) as session:
        kinds = [row.snapshot_kind for row in session.query(RunOutputSnapshot).all()]
    assert sorted(kinds) == ["ac_runtime_snapshot_v1", "ac_runtime_snapshot_v1",
                             "dc_pipeline_output"]


def test_audit_log_is_trimmed_but_kept_longer_than_artifacts(db_url):
    with session_scope(db_url) as session:
        for age in (400, 10):
            row = AuditLog(entity_type="sizing_run", entity_id="r1",
                           action="persist", actor="tester", payload_json={})
            session.add(row)
            session.flush()
            row.created_at = _ago(age)

    assert ms.DEFAULT_AUDIT_RETENTION_DAYS > ms.DEFAULT_ARTIFACT_RETENTION_DAYS
    report = ms.prune_audit_log(180, db_url=db_url)
    assert report.audit_rows == 1
    with session_scope(db_url) as session:
        assert session.query(AuditLog).count() == 1


def test_oplog_day_files_expire(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old = log_dir / "oplog-20200101.jsonl"
    new = log_dir / "oplog-20991231.jsonl"
    old.write_text('{"kind":"page_view"}\n')
    new.write_text('{"kind":"page_view"}\n')
    import os

    os.utime(old, (_ago(90).timestamp(), _ago(90).timestamp()))
    monkeypatch.setenv("CALB_OPLOG_DIR", str(log_dir))

    report = ms.prune_oplog(30)
    assert report.oplog_files == 1
    assert not old.exists() and new.exists()


def test_a_full_sweep_reports_what_it_removed(db_url, tmp_path, monkeypatch):
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    monkeypatch.setenv("CALB_OPLOG_DIR", str(tmp_path / "logs"))
    with session_scope(db_url) as session:
        _artifact(session, "r1", "sld_svg", "artifacts/r1/missing.svg")

    report = ms.run_maintenance(db_url=db_url)
    payload = report.as_dict()
    assert payload["orphaned_rows"] == 1
    # Every counter is present, so a sweep can be logged rather than guessed at.
    assert set(payload) >= {
        "artifact_rows", "artifact_files", "orphaned_rows", "snapshot_rows",
        "audit_rows", "oplog_files", "bytes_freed", "notes",
    }


def test_storage_report_measures_both_stores(db_url, tmp_path, monkeypatch):
    # A directory of its own: tmp_path also holds the sqlite file and its WAL.
    outputs = tmp_path / "out"
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(outputs))
    (outputs / "artifacts").mkdir(parents=True)
    (outputs / "artifacts" / "a.svg").write_text("<svg/>")

    payload = ms.storage_report(db_url=db_url)
    assert payload["output_files"] == 1
    assert payload["output_bytes"] > 0
    assert payload["row_counts"]["artifact_registry"] == 0


# ---------------------------------------------------------------------------
# Growth control at the SOURCE, not just after the fact
# ---------------------------------------------------------------------------


def test_regenerating_an_artifact_supersedes_the_previous_generation(tmp_path, monkeypatch):
    """The main growth source: every render used to leave its predecessor behind."""
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    db = f"sqlite:///{(tmp_path / 'gen.sqlite').as_posix()}"
    with session_scope(db) as session:
        Base.metadata.create_all(bind=session.get_bind())
    _seed_run(db)

    from calb_sizing_tool.plugins.base import ArtifactPayload
    from calb_sizing_tool.services.artifact_service import persist_artifacts

    for i in range(4):
        persist_artifacts(
            run_id="r1",
            artifacts=[ArtifactPayload(
                artifact_kind="layout_svg", file_name="layout.svg",
                media_type="image/svg+xml", content=f"<svg>{i}</svg>".encode(),
                metadata={},
            )],
            plugin_id="p", plugin_version="1", db_url=db,
        )

    with session_scope(db) as session:
        rows = session.query(ArtifactRegistry).all()
        assert len(rows) == 1, "four renders must leave one generation"
        stored = rows[0].file_path

    from calb_sizing_tool.services.artifact_service import resolve_artifact_path

    # The live file must SURVIVE: a regeneration reuses the same file name, so a
    # naive "delete the superseded row's file" erases what was just written.
    assert resolve_artifact_path(stored).read_text() == "<svg>3</svg>"
    files = list((tmp_path / "artifacts").rglob("*.svg"))
    assert len(files) == 1, files


def test_two_artifact_modes_of_one_kind_do_not_supersede_each_other(tmp_path, monkeypatch):
    """An SLD run holds a concept AND a draft_override artifact of the same kind."""
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    db = f"sqlite:///{(tmp_path / 'modes.sqlite').as_posix()}"
    with session_scope(db) as session:
        Base.metadata.create_all(bind=session.get_bind())
    _seed_run(db)

    from calb_sizing_tool.plugins.base import ArtifactPayload
    from calb_sizing_tool.services.artifact_service import persist_artifacts

    for mode in ("concept", "draft_override"):
        persist_artifacts(
            run_id="r1",
            artifacts=[ArtifactPayload(
                artifact_kind="sld_svg", file_name=f"sld.{mode}.svg",
                media_type="image/svg+xml", content=f"<svg>{mode}</svg>".encode(),
                metadata={"artifact_mode": mode},
            )],
            plugin_id="p", plugin_version="1", db_url=db,
        )

    with session_scope(db) as session:
        modes = {
            (row.metadata_json or {}).get("artifact_mode")
            for row in session.query(ArtifactRegistry).all()
        }
    assert modes == {"concept", "draft_override"}


def test_the_generation_count_is_configurable(monkeypatch):
    from calb_sizing_tool.services.artifact_service import artifact_generations_to_keep

    monkeypatch.delenv("CALB_ARTIFACT_GENERATIONS", raising=False)
    assert artifact_generations_to_keep() == 1
    monkeypatch.setenv("CALB_ARTIFACT_GENERATIONS", "5")
    assert artifact_generations_to_keep() == 5
    # Nonsense never means "keep nothing".
    monkeypatch.setenv("CALB_ARTIFACT_GENERATIONS", "0")
    assert artifact_generations_to_keep() == 1
    monkeypatch.setenv("CALB_ARTIFACT_GENERATIONS", "abc")
    assert artifact_generations_to_keep() == 1
