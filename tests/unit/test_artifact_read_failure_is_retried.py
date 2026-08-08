"""A read that fails is retried, and never reported as "never generated".

Owner ruling 2026-08-08: 读取失败重新读取.

Two different things used to produce the same sentence in the report — "SLD not
generated. Please generate in the Single Line Diagram page.":

  1. the run genuinely has no SLD;
  2. the run HAS one, and this build could not read it — a locked WAL database
     shared by several sessions, or a transient error on the outputs share.

Case 2 was swallowed by `except OperationalError: pass` and by a per-file
`except Exception: pass`, and the advice was actively wrong: regenerating does
not fix a locked database, and the reader is told a drawing is missing when it
is sitting in the registry.

Now the reader retries first, and what survives the retries is reported as a
read failure rather than an absence.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models.project import Project
from calb_sizing_tool.infra.db.models.sizing_run import SizingRun
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.services import artifact_service
from calb_sizing_tool.services.artifact_service import (
    load_artifact_bytes_with_failures,
    retry_read,
)


# --------------------------------------------------------------------------
# the retry itself
# --------------------------------------------------------------------------

def test_a_transient_failure_is_retried_until_it_succeeds(monkeypatch):
    monkeypatch.setattr(artifact_service, "_READ_BACKOFF_S", 0)
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OperationalError("SELECT 1", {}, Exception("database is locked"))
        return b"payload"

    value, error = retry_read(flaky)

    assert value == b"payload"
    assert error is None
    assert attempts["n"] == 3, "the read was not retried"


def test_a_persistent_failure_is_reported_not_swallowed(monkeypatch):
    monkeypatch.setattr(artifact_service, "_READ_BACKOFF_S", 0)
    attempts = {"n": 0}

    def always_locked():
        attempts["n"] += 1
        raise OSError("Input/output error")

    value, error = retry_read(always_locked)

    assert value is None
    assert isinstance(error, OSError)
    assert attempts["n"] == artifact_service._READ_ATTEMPTS


def test_a_bug_is_not_retried_three_times(monkeypatch):
    """A TypeError will fail the same way every time; retrying it just costs."""
    monkeypatch.setattr(artifact_service, "_READ_BACKOFF_S", 0)
    attempts = {"n": 0}

    def broken():
        attempts["n"] += 1
        raise TypeError("not a path")

    value, error = retry_read(broken)

    assert value is None
    assert isinstance(error, TypeError)
    assert attempts["n"] == 1


# --------------------------------------------------------------------------
# the reader
# --------------------------------------------------------------------------

@pytest.fixture()
def run_with_sld(tmp_path, monkeypatch):
    """A run whose SLD really is in the registry, on disk."""
    monkeypatch.setattr(artifact_service, "_READ_BACKOFF_S", 0)
    outputs = tmp_path / "outputs"
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(outputs))
    db_url = f"sqlite:///{(tmp_path / 'artifacts.sqlite').as_posix()}"
    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())
    with session_scope(db_url) as session:
        session.add(Project(project_id="p1", project_code="P1", project_name="P1"))
        session.flush()
        session.add(SizingRun(
            sizing_run_id="run-1", project_id="p1", sizing_case_id=None,
            run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))
    artifact_service.persist_artifacts(
        run_id="run-1",
        artifacts=[
            ArtifactPayload(
                artifact_kind="sld_svg",
                file_name="sld.svg",
                media_type="image/svg+xml",
                content=b"<svg>real</svg>",
                metadata={},
            )
        ],
        plugin_id="test_plugin",
        plugin_version="1.0.0",
        db_url=db_url,
    )
    return db_url


def test_a_present_artifact_reads_with_no_failures(run_with_sld):
    found, failures = load_artifact_bytes_with_failures(
        "run-1", ["sld_svg"], db_url=run_with_sld
    )
    assert found["sld_svg"] == b"<svg>real</svg>"
    assert failures == []


def test_an_unreadable_artifact_is_a_failure_not_an_absence(run_with_sld, monkeypatch):
    """The whole point: the row exists, so this is not "never generated"."""
    real_read_bytes = Path.read_bytes

    def exploding_read_bytes(self):
        if self.name == "sld.svg":
            raise OSError("Input/output error")
        return real_read_bytes(self)

    monkeypatch.setattr("pathlib.Path.read_bytes", exploding_read_bytes)

    found, failures = load_artifact_bytes_with_failures(
        "run-1", ["sld_svg"], db_url=run_with_sld
    )

    assert "sld_svg" not in found
    assert len(failures) == 1
    assert "sld_svg" in failures[0] and "could not be read" in failures[0]


def test_a_row_whose_file_is_gone_is_not_a_read_failure(run_with_sld):
    """That is the maintenance sweep's business, and retrying cannot help it."""
    from calb_sizing_tool.infra.db.models.artifact_registry import ArtifactRegistry

    with session_scope(run_with_sld) as session:
        row = session.query(ArtifactRegistry).one()
        artifact_service.resolve_artifact_path(str(row.file_path)).unlink()

    found, failures = load_artifact_bytes_with_failures(
        "run-1", ["sld_svg"], db_url=run_with_sld
    )
    assert found == {}
    assert failures == []


def test_a_kind_that_was_never_recorded_is_not_a_read_failure(run_with_sld):
    found, failures = load_artifact_bytes_with_failures(
        "run-1", ["layout_png"], db_url=run_with_sld
    )
    assert found == {}
    assert failures == []


# --------------------------------------------------------------------------
# what the report says
# --------------------------------------------------------------------------

def _ctx(**overrides):
    from calb_sizing_tool.reporting.report_context import build_report_context

    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": {
                "project_name": "Read Failure",
                "poi_power_req_mw": 100.0,
                "poi_energy_req_mwh": 400.0,
                "project_life_years": 20,
                "poi_guarantee_year": 10,
                "cycles_per_year": 365,
            },
            "stage2": {"container_count": 80},
            "ac_output": {"num_blocks": 20, "block_size_mw": 5.0, "pcs_per_block": 2},
        },
        project_inputs={},
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def test_the_report_says_not_generated_when_nothing_was_generated():
    from calb_sizing_tool.reporting.report_v2 import _missing_figure_note

    note = _missing_figure_note(_ctx(), "SLD", "Please generate in the SLD page.")
    assert note == "SLD not generated. Please generate in the SLD page."


def test_the_report_does_not_say_not_generated_when_the_read_failed():
    from calb_sizing_tool.reporting.report_v2 import _missing_figure_note

    note = _missing_figure_note(
        _ctx(artifact_read_failures=["sld_png: /outputs/sld.png could not be read (locked)"]),
        "SLD",
        "Please generate in the SLD page.",
    )

    assert "not generated" not in note, (
        "a figure that exists but could not be read must not be reported as absent"
    )
    assert "could not be read" in note
    assert "NOT missing from the run" in note
    assert "locked" in note, "the reader needs the actual reason"


def test_the_context_carries_read_failures_from_the_reader(tmp_path, monkeypatch):
    """End to end: an unreadable stored figure reaches ReportContext as a failure."""
    monkeypatch.setattr(artifact_service, "_READ_BACKOFF_S", 0)

    from calb_sizing_tool.reporting import report_context as rc

    def failing_reader(run_id, kinds, **kwargs):
        return {}, [f"{kinds[0]}: could not be read (database is locked)"]

    monkeypatch.setattr(
        "calb_sizing_tool.services.artifact_service.load_artifact_bytes_with_failures",
        failing_reader,
    )

    ctx = rc.build_report_context(
        session_state={"active_run_id": "run-1", "dc_last_run_id": "run-1"},
        stage_outputs={
            "stage13_output": {
                "project_name": "Read Failure",
                "poi_power_req_mw": 100.0,
                "poi_energy_req_mwh": 400.0,
                "project_life_years": 20,
                "poi_guarantee_year": 10,
                "cycles_per_year": 365,
            },
            "stage2": {"container_count": 80},
            "ac_output": {"num_blocks": 20, "block_size_mw": 5.0, "pcs_per_block": 2},
        },
        project_inputs={},
    )

    assert ctx.artifact_read_failures, "the failure did not reach the report context"
    assert "database is locked" in ctx.artifact_read_failures[0]
