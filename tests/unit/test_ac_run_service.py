"""AC alternatives under a fixed DC result (owner ruling B, 2026-08-04).

Two things have to hold at once:

- a DC result may carry MORE THAN ONE AC alternative — that is the point;
- it must not carry one per click — "不能过度的细分".

The identity hash is what reconciles them, so most of these tests are about what
does and does not count as a different alternative.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models.project import Project
from calb_sizing_tool.infra.db.models.sizing_run import SizingRun
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services import ac_run_service as acr

_AC_8x8 = {
    "num_blocks": 13, "pcs_per_block": 8, "pcs_kw": 1250.0, "block_size_mw": 10.0,
    "transformer_mva": 11.111, "total_ac_mw": 130.0, "dc_blocks_total": 104,
    "transformer_topology": "three_winding", "lv_winding_count": 2,
}
_AC_4x4 = {**_AC_8x8, "pcs_per_block": 4, "block_size_mw": 5.0,
           "transformer_topology": "two_winding", "lv_winding_count": 1}


@pytest.fixture()
def dc_run(tmp_path):
    url = f"sqlite:///{(tmp_path / 'acrun.sqlite').as_posix()}"
    with session_scope(url) as session:
        Base.metadata.create_all(bind=session.get_bind())
    with session_scope(url) as session:
        project = Project(project_id="p1", project_code="P1", project_name="P1")
        session.add(project)
        session.flush()
        session.add(SizingRun(
            sizing_run_id="dc-1", project_id="p1", sizing_case_id=None,
            run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))
    return url, "dc-1"


# ---------------------------------------------------------------------------
# It is a branch of the DC run, not a second Case
# ---------------------------------------------------------------------------


def test_an_ac_run_hangs_off_its_dc_run_and_inherits_its_case(dc_run):
    url, parent = dc_run
    result = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_8x8, db_url=url)
    assert result is not None and result.reused is False

    with session_scope(url) as session:
        row = session.query(SizingRun).filter_by(sizing_run_id=result.run_id).one()
        parent_row = session.query(SizingRun).filter_by(sizing_run_id=parent).one()
        assert row.parent_run_id == parent
        assert row.run_type == acr.AC_RUN_TYPE
        # Same project and same Case as its DC run: an AC alternative never
        # invents a Case of its own, which is what would duplicate the Case.
        assert row.project_id == parent_row.project_id
        assert row.sizing_case_id == parent_row.sizing_case_id


def test_the_case_input_schema_still_carries_no_ac_field():
    """The reason an AC run cannot duplicate a Case — checked, not assumed."""
    from calb_sizing_tool.schemas.case import SizingCaseInput

    fields = set(SizingCaseInput.model_fields)
    for ac_only in ("pcs_per_block", "pcs_kw", "transformer_mva",
                    "transformer_topology", "num_blocks", "lv_winding_count"):
        assert ac_only not in fields, ac_only


# ---------------------------------------------------------------------------
# 不能过度的细分
# ---------------------------------------------------------------------------


def test_recomputing_the_same_configuration_reuses_its_run(dc_run):
    url, parent = dc_run
    first = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_8x8, db_url=url)
    for _ in range(5):
        again = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_8x8, db_url=url)
        assert again is not None
        assert again.reused is True
        assert again.run_id == first.run_id

    assert len(acr.list_ac_alternatives(parent, db_url=url)) == 1


def test_a_genuinely_different_configuration_is_a_second_alternative(dc_run):
    url, parent = dc_run
    a = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_8x8, db_url=url)
    b = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_4x4, db_url=url)
    assert a.run_id != b.run_id
    assert b.reused is False
    assert b.alternatives == 2

    alternatives = acr.list_ac_alternatives(parent, db_url=url)
    assert {item["summary"]["pcs_per_block"] for item in alternatives} == {8, 4}


def test_bookkeeping_noise_does_not_mint_an_alternative(dc_run):
    """A timestamp or a UI flag is not a different AC scheme."""
    url, parent = dc_run
    first = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_8x8, db_url=url)
    noisy = {**_AC_8x8, "generated_at": "2026-08-04T00:00:00", "ui_expanded": True}
    again = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=noisy, db_url=url)
    assert again.run_id == first.run_id
    assert again.reused is True


@pytest.mark.parametrize("field,value", [
    ("pcs_per_block", 4),
    ("num_blocks", 12),
    ("transformer_topology", "two_winding"),
    ("dc_blocks_total", 100),
    ("configuration_code", "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"),
])
def test_each_decision_that_changes_the_design_changes_the_identity(field, value):
    base = acr.ac_configuration_hash(_AC_8x8)
    assert acr.ac_configuration_hash({**_AC_8x8, field: value}) != base


def test_the_dc_allocation_plan_is_part_of_the_identity():
    """Matching DC Blocks differently IS a different AC scheme (owner: 可以匹配 DC block)."""
    plan_a = [{"ac_block_index": i, "dc_blocks_total": 8} for i in range(1, 14)]
    plan_b = [{"ac_block_index": i, "dc_blocks_total": 8 if i < 13 else 4} for i in range(1, 14)]
    assert (acr.ac_configuration_hash({**_AC_8x8, "dc_allocation_plan": plan_a})
            != acr.ac_configuration_hash({**_AC_8x8, "dc_allocation_plan": plan_b}))


# ---------------------------------------------------------------------------
# Fail-closed and clean-up
# ---------------------------------------------------------------------------


def test_nothing_is_recorded_without_a_dc_run_or_a_result(dc_run):
    url, parent = dc_run
    assert acr.persist_ac_run(dc_run_id="", ac_inputs={}, ac_output=_AC_8x8, db_url=url) is None
    assert acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output={}, db_url=url) is None
    assert acr.persist_ac_run(dc_run_id="missing", ac_inputs={}, ac_output=_AC_8x8, db_url=url) is None
    assert acr.list_ac_alternatives(parent, db_url=url) == []


def test_deleting_the_dc_run_takes_its_ac_branches_with_it(dc_run):
    url, parent = dc_run
    acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_8x8, db_url=url)
    acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_4x4, db_url=url)
    assert len(acr.list_ac_alternatives(parent, db_url=url)) == 2

    with session_scope(url) as session:
        session.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys=ON"))
        session.delete(session.query(SizingRun).filter_by(sizing_run_id=parent).one())

    with session_scope(url) as session:
        assert session.query(SizingRun).count() == 0, "AC branches must not outlive their DC run"


def test_both_snapshots_are_written_so_the_alternative_is_reproducible(dc_run):
    url, parent = dc_run
    result = acr.persist_ac_run(
        dc_run_id=parent, ac_inputs={"grid_kv": 33.0}, ac_output=_AC_8x8, db_url=url)

    from calb_sizing_tool.infra.db.models.run_input_snapshot import RunInputSnapshot
    from calb_sizing_tool.infra.db.models.run_output_snapshot import RunOutputSnapshot

    with session_scope(url) as session:
        inputs = session.query(RunInputSnapshot).filter_by(sizing_run_id=result.run_id).all()
        outputs = session.query(RunOutputSnapshot).filter_by(sizing_run_id=result.run_id).all()
        assert [row.snapshot_kind for row in inputs] == [acr.AC_INPUT_SNAPSHOT_KIND]
        assert [row.snapshot_kind for row in outputs] == [acr.AC_OUTPUT_SNAPSHOT_KIND]
        # The INPUT snapshot carries the identity hash — that is what dedup matches.
        assert inputs[0].content_hash == result.content_hash
        assert outputs[0].snapshot_json["pcs_per_block"] == 8


def test_alternatives_of_one_dc_run_do_not_leak_into_another(dc_run):
    url, parent = dc_run
    with session_scope(url) as session:
        session.add(SizingRun(
            sizing_run_id="dc-2", project_id="p1", sizing_case_id=None,
            run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))

    acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_AC_8x8, db_url=url)
    # The SAME configuration under a different DC run is a different alternative:
    # the DC result it sits on is part of what makes it what it is.
    other = acr.persist_ac_run(dc_run_id="dc-2", ac_inputs={}, ac_output=_AC_8x8, db_url=url)
    assert other.reused is False
    assert len(acr.list_ac_alternatives(parent, db_url=url)) == 1
    assert len(acr.list_ac_alternatives("dc-2", db_url=url)) == 1


def test_the_ac_page_records_the_alternative_but_never_at_the_cost_of_the_save():
    """Bookkeeping must not be able to lose a user's configuration.

    persist_ac_runtime_snapshot is what SLD and the report read; persist_ac_run is
    the alternative history. If the history write fails, the save must still
    stand — so the call is wrapped and the page carries on.
    """
    import inspect

    from calb_sizing_tool.ui import ac_view

    src = inspect.getsource(ac_view)
    assert "persist_ac_run(" in src, "the AC page must record the alternative"
    # The record call sits inside a try/except so a bookkeeping failure is not a
    # user-facing failure.
    call = src.index("_ac_run = persist_ac_run(")
    preceding = src[:call]
    assert preceding.rstrip().endswith("try:"), (
        "persist_ac_run must be guarded; a failed history write must not lose the save"
    )
