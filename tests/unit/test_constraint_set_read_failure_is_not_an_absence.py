"""A Site Constraint Set that cannot be retrieved is not a run without one.

Owner ruling 2026-08-08 (读取失败重新读取), applied to the second place that
reads a stored artifact. `site_layout_view` caches this read for the whole
session, so a failure that returned None would be frozen in: the page would
report "no constraint set" on every rerun until the run changed, and the
suggested remedy — register a new one — would be wrong, because the run has one.

The loader now raises instead, and the page declines to cache a failure.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models.project import Project
from calb_sizing_tool.infra.db.models.sizing_run import SizingRun
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services import artifact_service
from calb_sizing_tool.services.site_constraint_set_service import (
    SITE_CONSTRAINT_SCHEMA_VERSION,
    SiteConstraintSetReadError,
    load_persisted_site_constraint_set,
    register_site_constraint_set,
)


@pytest.fixture()
def run_with_a_constraint_set(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(artifact_service, "_READ_BACKOFF_S", 0)
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path / "outputs"))
    db_url = f"sqlite:///{(tmp_path / 'constraints.sqlite').as_posix()}"
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
    register_site_constraint_set(
        run_id="run-1",
        constraint_set={
            "schema_version": SITE_CONSTRAINT_SCHEMA_VERSION,
            "site_boundary": {"area_m2": 1000},
        },
        actor="test",
        db_url=db_url,
    )
    return db_url


def test_a_run_without_one_reads_as_none(tmp_path, monkeypatch):
    monkeypatch.setenv("CALB_OUTPUTS_DIR", str(tmp_path / "outputs"))
    db_url = f"sqlite:///{(tmp_path / 'empty.sqlite').as_posix()}"
    with session_scope(db_url) as session:
        Base.metadata.create_all(bind=session.get_bind())

    assert load_persisted_site_constraint_set("run-1", db_url=db_url) is None


def test_a_registered_set_reads_back(run_with_a_constraint_set):
    loaded = load_persisted_site_constraint_set("run-1", db_url=run_with_a_constraint_set)
    assert isinstance(loaded, dict)
    assert loaded["site_boundary"]["area_m2"] == 1000


def test_a_set_that_cannot_be_retrieved_raises_instead_of_reading_as_absent(
    run_with_a_constraint_set, monkeypatch
):
    """The distinction the session cache depends on."""
    real_read_bytes = Path.read_bytes

    def unreadable(self):
        if self.suffix == ".json":
            raise OSError("Input/output error")
        return real_read_bytes(self)

    monkeypatch.setattr("pathlib.Path.read_bytes", unreadable)

    with pytest.raises(SiteConstraintSetReadError) as caught:
        load_persisted_site_constraint_set("run-1", db_url=run_with_a_constraint_set)

    assert "could not be read" in str(caught.value)


def test_the_page_does_not_cache_a_failed_read():
    """Caching None would freeze the failure for the whole session."""
    import inspect

    from calb_sizing_tool.ui import site_layout_view

    source = inspect.getsource(site_layout_view._load_persisted_constraint_set_cached)
    handler = source.split("except SiteConstraintSetReadError", 1)
    assert len(handler) == 2, "the page no longer distinguishes a failed read"
    assert "_PERSISTED_CONSTRAINT_CACHE_KEY" not in handler[1].split("return None", 1)[0], (
        "the failure branch writes to the cache; the next rerun would not retry"
    )
