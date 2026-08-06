"""Bounded growth (owner requirement 2026-08-04: 日志和数据库不能无限制的变大).

The defect these lock in place: deploy/docker/calb-maintenance.sh deleted output
FILES older than 30 days and nothing else, so artifact_registry rows survived
pointing at files that were gone. load_artifact_bytes_from_db swallows every
error, so an old run's report lost its figures silently. Pruning is now always
row-and-file together.
"""
from __future__ import annotations

import datetime
import os

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


# ---------------------------------------------------------------------------
# Files whose ROW is gone — the direction prune_orphaned_artifacts never covered
# ---------------------------------------------------------------------------
#
# prune_orphaned_artifacts removes a row whose file vanished. Nothing in Python
# removed a FILE whose row vanished; only the shell sweep did, and only on the
# deployed host under CALB_RUNTIME_ROOT. A developer checkout therefore grew
# without limit — measured at 479 run directories / ~159 MB, referenced by no
# database still in existence.


def _outputs(tmp_path, monkeypatch):
    out = tmp_path / "out"
    (out / "artifacts" / "r1" / "plug").mkdir(parents=True)
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(out))
    return out


def _old_file(path, days: int):
    path.write_bytes(b"x" * 100)
    stamp = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()
    os.utime(path, (stamp, stamp))


def test_a_file_no_row_points_at_is_found(db_url, tmp_path, monkeypatch):
    out = _outputs(tmp_path, monkeypatch)
    kept = out / "artifacts" / "r1" / "plug" / "kept.svg"
    junk = out / "artifacts" / "r1" / "plug" / "junk.svg"
    _old_file(kept, 40)
    _old_file(junk, 40)
    with session_scope(db_url) as session:
        _artifact(session, "r1", "sld_svg", "artifacts/r1/plug/kept.svg")

    found = ms.find_unreferenced_artifact_files(db_url=db_url)
    assert found == [junk]


def test_a_recent_file_is_never_a_candidate(db_url, tmp_path, monkeypatch):
    """Its row may simply not have committed yet."""
    out = _outputs(tmp_path, monkeypatch)
    fresh = out / "artifacts" / "r1" / "plug" / "fresh.svg"
    fresh.write_bytes(b"new")
    assert ms.find_unreferenced_artifact_files(db_url=db_url) == []


def test_only_the_artifacts_subtree_is_swept(db_url, tmp_path, monkeypatch):
    """logs/ has its own retention and external_ai/ is user-facing output."""
    out = _outputs(tmp_path, monkeypatch)
    for name in ("logs", "external_ai"):
        (out / name).mkdir(parents=True, exist_ok=True)
        _old_file(out / name / "keep.json", 90)
    assert ms.find_unreferenced_artifact_files(db_url=db_url) == []
    assert (out / "logs" / "keep.json").exists()


def test_the_sweep_counts_before_it_deletes(db_url, tmp_path, monkeypatch):
    """Default is dry run: an operator on the wrong database sees a number."""
    out = _outputs(tmp_path, monkeypatch)
    junk = out / "artifacts" / "r1" / "plug" / "junk.svg"
    _old_file(junk, 40)

    report = ms.prune_unreferenced_artifact_files(db_url=db_url)
    assert report.unreferenced_files == 1
    assert junk.exists(), "dry run must not delete"
    assert any("CALB_PRUNE_UNREFERENCED_FILES" in n for n in report.notes)

    report = ms.prune_unreferenced_artifact_files(db_url=db_url, dry_run=False)
    assert report.unreferenced_files == 1 and not junk.exists()
    assert report.bytes_freed == 100


def test_an_unreadable_registry_deletes_nothing(tmp_path, monkeypatch):
    """The worst failure mode: concluding 'no rows' means 'all files are junk'."""
    out = _outputs(tmp_path, monkeypatch)
    junk = out / "artifacts" / "r1" / "plug" / "junk.svg"
    _old_file(junk, 40)
    empty_db = f"sqlite:///{(tmp_path / 'no-tables.sqlite').as_posix()}"

    report = ms.prune_unreferenced_artifact_files(db_url=empty_db, dry_run=False)
    assert junk.exists(), "a missing registry must never authorise deletion"
    assert report.unreferenced_files == 0
    assert any("registry unreadable" in n for n in report.notes)


def test_the_full_sweep_only_counts_unless_enabled(db_url, tmp_path, monkeypatch):
    out = _outputs(tmp_path, monkeypatch)
    junk = out / "artifacts" / "r1" / "plug" / "junk.svg"
    _old_file(junk, 40)

    assert ms.run_maintenance(db_url=db_url).unreferenced_files == 1
    assert junk.exists()

    monkeypatch.setenv("CALB_PRUNE_UNREFERENCED_FILES", "1")
    assert ms.run_maintenance(db_url=db_url).unreferenced_files == 1
    assert not junk.exists()


def test_emptied_directories_are_removed(db_url, tmp_path, monkeypatch):
    out = _outputs(tmp_path, monkeypatch)
    _old_file(out / "artifacts" / "r1" / "plug" / "junk.svg", 40)
    ms.prune_unreferenced_artifact_files(db_url=db_url, dry_run=False)
    assert not (out / "artifacts" / "r1").exists()
    assert (out / "artifacts").exists(), "the root itself stays"


def test_the_server_can_actually_tune_the_sweep():
    """calb-maintenance.sh runs the sweep INSIDE the container.

    A retention variable that compose does not pass cannot reach it, so an
    operator setting it in deploy/docker/.env would change nothing and the sweep
    would silently keep its built-in defaults. This was the state before
    2026-08-06 for every database-side knob.
    """
    # This is a narrow deployment-file contract, not a YAML-parser test.  Keep it
    # standard-library-only so the project test suite has no undeclared PyYAML
    # dependency in either a local checkout or GitHub Actions.
    compose = open("deploy/docker/docker-compose.ubuntu.yml", encoding="utf-8").read()
    expected_mappings = {
        "CALB_ARTIFACT_GENERATIONS": "${CALB_ARTIFACT_GENERATIONS:-1}",
        "CALB_ARTIFACT_RETENTION_DAYS": "${CALB_ARTIFACT_RETENTION_DAYS:-30}",
        "CALB_SNAPSHOT_GENERATIONS": "${CALB_SNAPSHOT_GENERATIONS:-3}",
        "CALB_AUDIT_RETENTION_DAYS": "${CALB_AUDIT_RETENTION_DAYS:-180}",
        "CALB_OPLOG_RETENTION_DAYS": "${CALB_OPLOG_RETENTION_DAYS:-30}",
        "CALB_UNREFERENCED_GRACE_DAYS": "${CALB_UNREFERENCED_GRACE_DAYS:-7}",
        # Empty keeps the destructive file sweep explicitly opt-in.
        "CALB_PRUNE_UNREFERENCED_FILES": "${CALB_PRUNE_UNREFERENCED_FILES:-}",
    }
    for name, value in expected_mappings.items():
        assert f"      {name}: {value}" in compose, (
            f"{name} never reaches the container with its safe default"
        )


def test_a_full_sweep_dry_run_never_changes_rows_or_files(db_url, tmp_path, monkeypatch):
    """The local cleanup script promises measurement only until -Delete."""
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("CALB_OPLOG_DIR", str(log_dir))

    old_artifact = tmp_path / "artifacts" / "r1" / "old.svg"
    old_artifact.parent.mkdir(parents=True)
    old_artifact.write_text("<svg>old</svg>")
    old_log = log_dir / "oplog-20200101.jsonl"
    old_log.write_text('{"kind":"page_view"}\n')
    os.utime(old_log, (_ago(90).timestamp(), _ago(90).timestamp()))

    with session_scope(db_url) as session:
        _artifact(session, "r1", "sld_svg", "artifacts/r1/old.svg", age_days=90)
        _artifact(session, "r1", "layout_svg", "artifacts/r1/missing.svg")
        for i in range(4):
            row = RunOutputSnapshot(
                sizing_run_id="r1", snapshot_kind="ac_runtime_snapshot_v1",
                content_hash=f"h{i}", snapshot_json={"i": i},
            )
            session.add(row)
            session.flush()
            row.created_at = _ago(4 - i)
        audit = AuditLog(entity_type="sizing_run", entity_id="r1",
                         action="persist", actor="tester", payload_json={})
        session.add(audit)
        session.flush()
        audit.created_at = _ago(400)

    report = ms.run_maintenance(db_url=db_url, dry_run=True)
    assert report.artifact_rows == 1
    assert report.orphaned_rows == 1
    assert report.snapshot_rows == 1
    assert report.audit_rows == 1
    assert report.oplog_files == 1
    assert any("dry run" in note for note in report.notes)
    assert old_artifact.exists() and old_log.exists()

    with session_scope(db_url) as session:
        assert session.query(ArtifactRegistry).count() == 2
        assert session.query(RunOutputSnapshot).count() == 4
        assert session.query(AuditLog).count() == 1


def test_the_server_sweep_runs_rows_before_files():
    """File-only pruning is what left rows pointing at nothing in the first place."""
    script = open("deploy/docker/calb-maintenance.sh", encoding="utf-8").read()
    assert script.index("cleanup_database_retention\n") < script.index("  cleanup_outputs\n")


def test_the_cleanup_script_contract_holds(tmp_path, monkeypatch):
    """scripts/clean_outputs.ps1 parses this JSON by key.

    A renamed key would not fail anything — the script would quietly print blank
    numbers and an operator would delete against a report that said nothing.
    """
    import contextlib
    import io
    import json
    import re

    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("CALB_DATABASE_URL", f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}")
    with session_scope() as session:
        Base.metadata.create_all(bind=session.get_bind())

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        ms.main(["--dry-run"])
    payload = json.loads(buffer.getvalue())

    for path in (("before", "output_files"), ("before", "output_mb"),
                 ("before", "row_counts", "artifact_registry"),
                 ("pruned", "unreferenced_files"), ("pruned", "bytes_freed"),
                 ("after", "output_files"), ("after", "output_mb")):
        cursor = payload
        for key in path:
            assert key in cursor, f"clean_outputs.ps1 reads {'.'.join(path)}"
            cursor = cursor[key]

    script = open("scripts/clean_outputs.ps1", encoding="utf-8").read()
    # The safe order is the shape of the script, not a habit: without -Delete it
    # must not be able to set the deletion flag.
    assert 'if (-not $Delete)' in script
    assert 'maintenance_service --dry-run' in script
    assert re.search(r'CALB_PRUNE_UNREFERENCED_FILES\s*=\s*""', script), (
        "the measuring pass must explicitly blank the deletion flag"
    )
