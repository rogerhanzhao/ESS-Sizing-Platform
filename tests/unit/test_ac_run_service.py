"""AC alternatives under a fixed DC result (owner ruling B, 2026-08-04).

Two things have to hold at once:

- a DC result may carry MORE THAN ONE AC alternative — that is the point;
- it must not carry one per click — "不能过度的细分".

The identity hash is what reconciles them, so most of these tests are about what
does and does not count as a different alternative.
"""
from __future__ import annotations

from copy import deepcopy

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


def _mixed_output(tail_kw=1000):
    from calb_sizing_tool.services.ac_mixed_station import build_mixed_dc_allocation_plan

    rows = [
        {"pcs_count": 2, "pcs_kw": 2500, "dc_blocks": 4},
        {"pcs_count": 2, "pcs_kw": tail_kw, "dc_blocks": 2},
    ]
    return {
        "num_blocks": 2, "pcs_per_block": 2, "pcs_kw": 2500,
        "block_size_mw": 5.0, "transformer_mva": 5.0 / .9,
        "dc_blocks_total": 6, "ac_block_mixed": True,
        "ac_block_rows": rows,
        "dc_allocation_plan": build_mixed_dc_allocation_plan(rows),
        "total_ac_mw": 5.0 + 2 * tail_kw / 1000,
    }


def _seed_legacy_mixed(dc_run, monkeypatch, output):
    url, parent = dc_run
    with monkeypatch.context() as legacy:
        legacy.setattr(acr, "ac_configuration_hash", acr._legacy_configuration_hash)
        return acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=output, db_url=url)


def test_tail_pcs_rating_changes_the_ac_alternative_without_overwriting(dc_run):
    url, parent = dc_run
    first_output = _mixed_output(1000)
    second_output = _mixed_output(1250)
    assert first_output["dc_allocation_plan"] == second_output["dc_allocation_plan"]
    first = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=first_output, db_url=url)
    second = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=second_output, db_url=url)
    assert first.run_id != second.run_id
    assert not second.reused and second.alternatives == 2

    again = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=second_output, db_url=url)
    assert again.reused and again.run_id == second.run_id and again.alternatives == 2
    from calb_sizing_tool.repositories.run_repository import RunRepository
    with session_scope(url) as session:
        saved = RunRepository(session).get_latest_output_snapshot_by_kind(first.run_id, acr.AC_OUTPUT_SNAPSHOT_KIND)
        assert saved.snapshot_json == first_output


def test_legacy_mixed_exact_match_upgrades_identity_without_adding_alternative(dc_run, monkeypatch):
    url, parent = dc_run
    output = _mixed_output()
    legacy = _seed_legacy_mixed(dc_run, monkeypatch, output)
    expected_hash = acr.ac_configuration_hash(output)
    assert legacy.content_hash != expected_hash
    upgraded = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=output, db_url=url)
    assert upgraded.reused and upgraded.run_id == legacy.run_id and upgraded.alternatives == 1
    assert upgraded.content_hash == expected_hash
    from calb_sizing_tool.repositories.run_repository import RunRepository
    with session_scope(url) as session:
        repo = RunRepository(session)
        assert repo.get_latest_input_snapshot_by_kind(legacy.run_id, acr.AC_INPUT_SNAPSHOT_KIND).content_hash == expected_hash
        assert repo.find_child_run_by_hash(parent, acr.AC_RUN_TYPE, expected_hash).sizing_run_id == legacy.run_id
    again = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=output, db_url=url)
    assert again.reused and again.run_id == legacy.run_id and again.alternatives == 1


def test_legacy_hash_match_cannot_reuse_or_overwrite_a_different_tail(dc_run, monkeypatch):
    url, parent = dc_run
    original = _mixed_output(1000)
    legacy = _seed_legacy_mixed(dc_run, monkeypatch, original)
    changed = _mixed_output(1250)
    assert acr._legacy_configuration_hash(changed) == legacy.content_hash
    result = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=changed, db_url=url)
    assert not result.reused and result.run_id != legacy.run_id and result.alternatives == 2
    from calb_sizing_tool.repositories.run_repository import RunRepository
    with session_scope(url) as session:
        repo = RunRepository(session)
        assert repo.get_latest_output_snapshot_by_kind(legacy.run_id, acr.AC_OUTPUT_SNAPSHOT_KIND).snapshot_json == original
        assert repo.get_latest_input_snapshot_by_kind(legacy.run_id, acr.AC_INPUT_SNAPSHOT_KIND).content_hash == legacy.content_hash


def test_upgraded_legacy_historical_hash_cannot_overwrite_the_first_mixed_variant(dc_run, monkeypatch):
    url, parent = dc_run
    original = _mixed_output(1000)
    legacy = _seed_legacy_mixed(dc_run, monkeypatch, original)
    upgraded = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=original, db_url=url)
    changed = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_mixed_output(1250), db_url=url)
    assert upgraded.run_id == legacy.run_id
    assert changed.run_id != upgraded.run_id and changed.alternatives == 2
    restored = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=original, db_url=url)
    assert restored.run_id == upgraded.run_id and restored.alternatives == 2


def test_uniform_and_rowless_historical_hashes_remain_byte_identical():
    expected_legacy_hash = "8bbe0c956008456270fc92a1d9a00dc5f67ac10b456dac0cee7b7c3af78c8bd7"
    assert acr.ac_configuration_hash(_AC_8x8) == expected_legacy_hash
    uniform = {**_AC_8x8, "ac_block_rows": [
        {"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": dc} for dc in (8, 7)
    ]}
    assert acr.ac_configuration_hash(uniform) == expected_legacy_hash


def test_mixed_rows_normalize_integral_numbers_and_ignore_presentation_noise():
    output = _mixed_output()
    normalized = deepcopy(output)
    normalized["ac_block_rows"] = [
        {**{key: float(value) for key, value in row.items()}, "label": "Display only"}
        for row in output["ac_block_rows"]
    ]
    assert acr.ac_configuration_hash(normalized) == acr.ac_configuration_hash(output)
    assert acr.ac_configuration_hash({**output, "ac_block_rows": list(reversed(output["ac_block_rows"]))}) != acr.ac_configuration_hash(output)


@pytest.mark.parametrize("field", ["pcs_count", "pcs_kw", "dc_blocks"])
@pytest.mark.parametrize("invalid", [True, False, 1.5, float("nan"), float("inf"), "1250"])
def test_invalid_row_numbers_do_not_silently_normalize_to_valid_identity(dc_run, field, invalid):
    url, parent = dc_run
    malformed = _mixed_output()
    malformed["ac_block_rows"][1][field] = invalid
    with pytest.raises(ValueError, match="positive integer"):
        acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=malformed, db_url=url)
    assert acr.list_ac_alternatives(parent, db_url=url) == []


def test_legacy_invalid_rows_are_never_adopted_via_compatibility_lookup(dc_run, monkeypatch):
    url, parent = dc_run
    malformed = _mixed_output()
    malformed["ac_block_rows"][1]["pcs_kw"] = True
    legacy = _seed_legacy_mixed(dc_run, monkeypatch, malformed)
    result = acr.persist_ac_run(dc_run_id=parent, ac_inputs={}, ac_output=_mixed_output(), db_url=url)
    assert not result.reused and result.run_id != legacy.run_id and result.alternatives == 2


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
