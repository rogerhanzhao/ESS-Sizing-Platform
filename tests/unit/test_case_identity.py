"""A Case is 方案 x scenario WITHIN one project (owner ruling 2026-08-04).

Its identity is therefore (project_id, case_code). Before this was fixed the DB
enforced a GLOBAL unique on case_code while CaseRepository looked it up per
project — two disagreeing rules, and both reachable failure modes raised a raw
IntegrityError instead of resolving:

- a second project reusing a case code;
- the same code created under a different scenario (the lookup included
  scenario_mode, missed the existing row, then collided on insert).
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository


@pytest.fixture()
def db_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'cases.sqlite').as_posix()}"
    with session_scope(url) as session:
        Base.metadata.create_all(bind=session.get_bind())
    return url


def _case(db_url, project_code, case_code, scenario, *, name="C"):
    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        project = repo.get_or_create_project(
            project_code=project_code, project_name=project_code)
        session.flush()
        row = repo.create_case_if_needed(
            project_id=project.project_id, case_code=case_code, case_name=name,
            stage_scope="DC", scenario_mode=scenario, input_json={},
        )
        session.flush()
        return row.sizing_case_id, row.project_id, row.scenario_mode


def test_two_projects_may_reuse_the_same_case_code(db_url):
    a = _case(db_url, "P-A", "base", "container_only")
    b = _case(db_url, "P-B", "base", "container_only")
    assert a[0] != b[0]
    assert a[1] != b[1]


def test_the_same_case_in_the_same_project_is_reused_not_duplicated(db_url):
    a = _case(db_url, "P", "P-base-container-only", "container_only")
    b = _case(db_url, "P", "P-base-container-only", "container_only")
    assert a[0] == b[0]


def test_reusing_a_code_under_another_scenario_is_refused_in_plain_words(db_url):
    """Not an IntegrityError: a Case is one scenario, so this is a naming clash."""
    _case(db_url, "P", "P-base-container-only", "container_only")
    with pytest.raises(ValueError) as excinfo:
        _case(db_url, "P", "P-base-container-only", "hybrid")
    message = str(excinfo.value)
    assert "already exists in this project" in message
    assert "container_only" in message and "hybrid" in message


def test_one_scenario_per_code_lets_both_scenarios_coexist(db_url):
    """The scenario belongs IN the code, which is what the workbench now does."""
    a = _case(db_url, "P", "P-base-container-only", "container_only")
    b = _case(db_url, "P", "P-base-hybrid", "hybrid")
    assert a[0] != b[0]
    assert {a[2], b[2]} == {"container_only", "hybrid"}


def test_lookup_by_code_is_scoped_to_a_project(db_url):
    _case(db_url, "P-A", "base", "container_only")
    _case(db_url, "P-B", "base", "container_only")
    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        project_a = repo.get_or_create_project(project_code="P-A", project_name="P-A")
        project_b = repo.get_or_create_project(project_code="P-B", project_name="P-B")
        found_a = repo.get_case_by_code("base", project_id=project_a.project_id)
        found_b = repo.get_case_by_code("base", project_id=project_b.project_id)
        assert found_a is not None and found_b is not None
        assert found_a.sizing_case_id != found_b.sizing_case_id
        # Unscoped still resolves to a single row rather than raising on the
        # two matches that are now legal.
        assert repo.get_case_by_code("base") is not None


def test_the_model_declares_the_composite_constraint(db_url):
    from calb_sizing_tool.infra.db.models.sizing_case import SizingCase

    uniques = {
        tuple(sorted(col.name for col in constraint.columns))
        for constraint in SizingCase.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("case_code", "project_id") in uniques
    # And case_code alone must NOT be unique any more.
    assert ("case_code",) not in uniques
    assert SizingCase.__table__.c.case_code.unique is not True


def test_a_persisted_run_creates_its_case_under_the_right_project(db_url):
    """The persistence path uses the same identity rule as the workbench."""
    from calb_sizing_tool.repositories.run_repository import RunRepository

    case_id, project_id, _ = _case(db_url, "P", "P-base-container-only", "container_only")
    with session_scope(db_url) as session:
        run = RunRepository(session).create_run(
            project_id=project_id, sizing_case_id=case_id,
            run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        )
        session.flush()
        assert run.sizing_case_id == case_id
        assert run.project_id == project_id
