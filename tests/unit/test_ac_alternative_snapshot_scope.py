"""Step 5: REGENERATING on an alternative uses that alternative's configuration.

Steps 2-4 made the drawings and the report follow the selected AC alternative,
but the AC RUNTIME snapshot was still read as "the last AC saved on this DC run".
So opening alternative A and regenerating the SLD could feed it B's parameters —
the figures would then say A while being drawn from B.

The fix adds no storage. `persist_ac_run` already writes each alternative's
inputs and outputs as its own run snapshots, from the same dicts the runtime
snapshot is built from; the reader simply prefers them.

Two directions are load-bearing and both are locked here:
- an alternative with nothing of its own falls back to the DC run's snapshot,
  which is what EVERY database written before AC runs existed contains;
- a selection pointing at another DC run's branch must NOT be used.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models.project import Project
from calb_sizing_tool.infra.db.models.sizing_run import SizingRun
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.ac_run_service import persist_ac_run
from calb_sizing_tool.services.sld_data_source_service import (
    load_persisted_ac_snapshot,
    persist_ac_runtime_snapshot,
    resolve_preferred_ac_snapshot,
)


def _ac_output(run_id: str, pcs_per_block: int) -> dict:
    return {
        "source_run_id": run_id,
        "num_blocks": 4,
        "block_size_mw": 10.0,
        "pcs_per_block": pcs_per_block,
        "pcs_kw": 1250 if pcs_per_block == 8 else 2500,
        "dc_blocks_total": 32,
    }


@pytest.fixture()
def db(tmp_path):
    url = f"sqlite:///{(tmp_path / 'snap.sqlite').as_posix()}"
    with session_scope(url) as session:
        Base.metadata.create_all(bind=session.get_bind())
    with session_scope(url) as session:
        session.add(Project(project_id="p1", project_code="P1", project_name="P1"))
        session.flush()
        session.add(SizingRun(
            sizing_run_id="dc-1", project_id="p1", sizing_case_id=None,
            run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))
    return url


@pytest.fixture()
def two_alternatives(db):
    """Alternative A (8 PCS) then B (4 PCS); B was saved last."""
    a = persist_ac_run(dc_run_id="dc-1", ac_inputs={"ratio": "1:8"},
                       ac_output=_ac_output("dc-1", 8), db_url=db)
    persist_ac_runtime_snapshot(run_id="dc-1", ac_inputs={"ratio": "1:8"},
                                ac_output=_ac_output("dc-1", 8), db_url=db)
    b = persist_ac_run(dc_run_id="dc-1", ac_inputs={"ratio": "1:4"},
                       ac_output=_ac_output("dc-1", 4), db_url=db)
    persist_ac_runtime_snapshot(run_id="dc-1", ac_inputs={"ratio": "1:4"},
                                ac_output=_ac_output("dc-1", 4), db_url=db)
    assert a is not None and b is not None and a.run_id != b.run_id
    return db, a.run_id, b.run_id


def test_the_dc_run_alone_still_yields_the_last_saved_ac(two_alternatives):
    """Unchanged behaviour: no alternative asked for, no alternative applied."""
    url, _a, _b = two_alternatives
    snapshot = load_persisted_ac_snapshot("dc-1", db_url=url)
    assert snapshot is not None
    assert snapshot.output["pcs_per_block"] == 4


def test_an_alternative_yields_its_own_configuration(two_alternatives):
    """The whole point: A stays A even though B was saved after it."""
    url, a, b = two_alternatives
    assert load_persisted_ac_snapshot("dc-1", ac_run_id=a, db_url=url).output["pcs_per_block"] == 8
    assert load_persisted_ac_snapshot("dc-1", ac_run_id=b, db_url=url).output["pcs_per_block"] == 4


def test_the_alternatives_inputs_come_back_too(two_alternatives):
    url, a, _b = two_alternatives
    assert load_persisted_ac_snapshot("dc-1", ac_run_id=a, db_url=url).inputs == {"ratio": "1:8"}


def test_an_alternative_without_its_own_record_falls_back(db):
    """A pre-AC-run database: everything on the DC run, no alternative rows."""
    with session_scope(db) as session:
        session.add(SizingRun(
            sizing_run_id="ac-empty", project_id="p1", sizing_case_id=None,
            parent_run_id="dc-1", run_type="ac_sizing", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))
    persist_ac_runtime_snapshot(run_id="dc-1", ac_inputs={"ratio": "1:8"},
                                ac_output=_ac_output("dc-1", 8), db_url=db)
    snapshot = load_persisted_ac_snapshot("dc-1", ac_run_id="ac-empty", db_url=db)
    assert snapshot is not None and snapshot.output["pcs_per_block"] == 8


def test_the_resolver_prefers_the_selected_alternative(two_alternatives):
    url, a, _b = two_alternatives
    resolution = resolve_preferred_ac_snapshot(
        "dc-1", project_state=None, shared_state=None,
        session_state={"active_ac_run_id": a}, db_url=url,
    )
    assert resolution.source == "persisted_ac_alternative"
    assert resolution.snapshot.output["pcs_per_block"] == 8


def test_the_resolver_is_unchanged_without_a_selection(two_alternatives):
    url, _a, _b = two_alternatives
    resolution = resolve_preferred_ac_snapshot(
        "dc-1", project_state=None, shared_state=None,
        session_state={}, db_url=url,
    )
    assert resolution.source == "persisted_run_snapshot"
    assert resolution.snapshot.output["pcs_per_block"] == 4


def test_a_selection_from_another_dc_run_is_ignored(db):
    """A stale selection must never smuggle in a foreign run's configuration."""
    with session_scope(db) as session:
        session.add(SizingRun(
            sizing_run_id="dc-2", project_id="p1", sizing_case_id=None,
            run_type="dc_pipeline", status="succeeded",
            input_summary_json={}, output_summary_json={},
        ))
    foreign = persist_ac_run(dc_run_id="dc-2", ac_inputs={},
                             ac_output=_ac_output("dc-2", 8), db_url=db)
    persist_ac_runtime_snapshot(run_id="dc-1", ac_inputs={},
                                ac_output=_ac_output("dc-1", 4), db_url=db)

    resolution = resolve_preferred_ac_snapshot(
        "dc-1", project_state=None, shared_state=None,
        session_state={"active_ac_run_id": foreign.run_id}, db_url=db,
    )
    assert resolution.source == "persisted_run_snapshot"
    assert resolution.snapshot.output["source_run_id"] == "dc-1"


def test_saving_on_the_ac_page_points_the_selection_at_what_was_saved():
    """Otherwise the next page regenerates from the alternative just replaced."""
    src = open("calb_sizing_tool/ui/ac_view.py", encoding="utf-8-sig").read()
    assert "set_active_ac_run(_ac_run.run_id, clear_downstream=False)" in src, (
        "AC sizing must select the alternative it just saved, and must NOT clear "
        "downstream state doing so — that state IS this alternative's"
    )


def test_switching_alternatives_still_clears_stale_state():
    """clear_downstream defaults to True: a real switch invalidates the screen."""
    import inspect

    from calb_sizing_tool.state.workspace_state import set_active_ac_run

    params = inspect.signature(set_active_ac_run).parameters
    assert params["clear_downstream"].default is True


# --------------------------------------------------------------------------
# A reused alternative must not serve the FIRST save's content
# --------------------------------------------------------------------------
#
# The identity hash covers 17 fields. Everything else in ac_output — a renamed
# case, an edited input that does not change the scheme — can legitimately move
# while the identity holds, and the run is then REUSED. Before alternatives were
# read from, the DC runtime snapshot was rewritten on every save, so this could
# not arise; now the alternative's own snapshots are what the pages read, and
# they have to keep up.


def test_a_reused_alternative_serves_the_latest_content(db):
    first = dict(_ac_output("dc-1", 8), source_case_name="OLD")
    a = persist_ac_run(dc_run_id="dc-1", ac_inputs={"note": "first"},
                       ac_output=first, db_url=db)
    again = persist_ac_run(dc_run_id="dc-1", ac_inputs={"note": "second"},
                           ac_output=dict(first, source_case_name="NEW"), db_url=db)

    assert again.reused and again.run_id == a.run_id, (
        "a non-identity change must NOT mint a second alternative"
    )
    snapshot = load_persisted_ac_snapshot("dc-1", ac_run_id=a.run_id, db_url=db)
    assert snapshot.output["source_case_name"] == "NEW"
    assert snapshot.inputs == {"note": "second"}


def test_an_unchanged_re_save_writes_nothing(db):
    """The growth gate: re-running an identical configuration adds no rows."""
    from calb_sizing_tool.infra.db.models.run_input_snapshot import RunInputSnapshot
    from calb_sizing_tool.infra.db.models.run_output_snapshot import RunOutputSnapshot

    payload = _ac_output("dc-1", 8)
    persist_ac_run(dc_run_id="dc-1", ac_inputs={"note": "x"}, ac_output=payload, db_url=db)

    def _counts():
        with session_scope(db) as session:
            return (session.query(RunInputSnapshot).count(),
                    session.query(RunOutputSnapshot).count())

    before = _counts()
    for _ in range(3):
        persist_ac_run(dc_run_id="dc-1", ac_inputs={"note": "x"},
                       ac_output=dict(payload), db_url=db)
    assert _counts() == before


def test_refreshing_does_not_break_deduplication(db):
    """The refreshed input row must keep the IDENTITY hash, not its own."""
    payload = dict(_ac_output("dc-1", 8), source_case_name="OLD")
    a = persist_ac_run(dc_run_id="dc-1", ac_inputs={"note": "1"}, ac_output=payload, db_url=db)
    persist_ac_run(dc_run_id="dc-1", ac_inputs={"note": "2"},
                   ac_output=dict(payload, source_case_name="NEW"), db_url=db)
    third = persist_ac_run(dc_run_id="dc-1", ac_inputs={"note": "3"},
                           ac_output=dict(payload, source_case_name="THIRD"), db_url=db)
    assert third.reused and third.run_id == a.run_id
    assert third.alternatives == 1, "still ONE alternative, not three"


def test_snapshot_pruning_keeps_the_dedup_lookup_working(db):
    """Input snapshots are pruned now too; the identity must survive it."""
    from calb_sizing_tool.services.maintenance_service import prune_snapshot_generations

    payload = _ac_output("dc-1", 8)
    a = persist_ac_run(dc_run_id="dc-1", ac_inputs={"n": 0}, ac_output=payload, db_url=db)
    for n in range(1, 8):
        persist_ac_run(dc_run_id="dc-1", ac_inputs={"n": n},
                       ac_output=dict(payload, source_case_name=str(n)), db_url=db)

    prune_snapshot_generations(keep=2, db_url=db)

    after = persist_ac_run(dc_run_id="dc-1", ac_inputs={"n": 99},
                           ac_output=dict(payload, source_case_name="99"), db_url=db)
    assert after.reused and after.run_id == a.run_id, (
        "pruning must not orphan the alternative and mint a duplicate run"
    )
    snapshot = load_persisted_ac_snapshot("dc-1", ac_run_id=a.run_id, db_url=db)
    assert snapshot.output["source_case_name"] == "99"
