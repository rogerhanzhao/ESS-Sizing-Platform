"""Mixed AC Block station — a manual-adjustment layer over the uniform trunk.

These tests protect the business rules of the mixed station (head/tail
composition, feeder capacity, sum-to-total) without touching the frozen sizing
canon. Uniform must remain the single-entry case so UI and report stay on one
code path.
"""
from __future__ import annotations

from calb_sizing_tool.services.ac_mixed_station import (
    build_mixed_dc_allocation_plan,
    default_uniform_rows,
    is_mixed_station,
    summarize_ac_block_rows,
    validate_ac_block_rows,
)


def test_uniform_rows_summarise_to_one_head_entry():
    rows = default_uniform_rows([8, 8, 8], pcs_count=8, pcs_kw=1250)
    assert not is_mixed_station(rows)
    entries = summarize_ac_block_rows(rows)
    assert len(entries) == 1
    head = entries[0]
    assert head["role"] == "Head"
    assert (head["count"], head["pcs_count"], head["pcs_kw"], head["dc_blocks_each"]) == (
        3,
        8,
        1250,
        8,
    )
    assert head["block_mw"] == 10.0


def test_mixed_rows_head_is_largest_power_rest_are_tails():
    # Two 10 MW head blocks (8x1250, 8 DC) + one 5 MW tail (4x1250, 4 DC).
    rows = [
        {"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8},
        {"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8},
        {"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4},
    ]
    assert is_mixed_station(rows)
    entries = summarize_ac_block_rows(rows)
    assert len(entries) == 2
    head = next(e for e in entries if e["role"] == "Head")
    tail = next(e for e in entries if e["role"] == "Tail")
    assert (head["count"], head["block_mw"]) == (2, 10.0)
    assert (tail["count"], tail["block_mw"], tail["dc_blocks_each"]) == (1, 5.0, 4)


def test_uneven_dc_of_one_model_is_not_a_mixed_station():
    # The uniform trunk fills DC unevenly (20x8 + 6x7) across ONE PCS model.
    rows = default_uniform_rows([8] * 20 + [7] * 6, pcs_count=8, pcs_kw=1250)
    assert not is_mixed_station(rows)
    entries = summarize_ac_block_rows(rows)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["count"] == 26
    assert entry["dc_blocks_total"] == 20 * 8 + 6 * 7
    assert (entry["dc_blocks_min"], entry["dc_blocks_max"]) == (7, 8)
    assert entry["dc_blocks_each"] is None  # varies -> reported as a range


def test_validation_ok_when_dc_sums_and_feeders_fit():
    rows = [
        {"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8},
        {"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8},
        {"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4},
    ]
    result = validate_ac_block_rows(rows, dc_blocks_total=20)
    assert result.ok
    assert result.total_dc_assigned == 20
    assert result.total_ac_mw == 25.0
    assert result.total_pcs == 20
    assert result.infeasible_rows == ()
    assert result.messages == ()


def test_validation_flags_dc_sum_mismatch():
    rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8}]
    result = validate_ac_block_rows(rows, dc_blocks_total=20)
    assert not result.ok
    assert result.total_dc_assigned == 8
    assert any("sum to exactly 20" in m for m in result.messages)


def test_validation_flags_feeder_shortfall():
    # 8 PCS with default 2 output circuits need >= 4 DC Blocks; 3 is infeasible.
    rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 3}]
    result = validate_ac_block_rows(rows, dc_blocks_total=3)
    assert not result.ok
    assert 1 in result.infeasible_rows
    assert any("at least 4 DC Blocks" in m for m in result.messages)


def test_validation_rejects_nonpositive_row():
    rows = [{"pcs_count": 0, "pcs_kw": 1250, "dc_blocks": 8}]
    result = validate_ac_block_rows(rows, dc_blocks_total=8)
    assert not result.ok
    assert 1 in result.infeasible_rows


def test_mixed_dc_allocation_plan_indexes_every_block():
    rows = [
        {"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8},
        {"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4},
    ]
    plan = build_mixed_dc_allocation_plan(rows)
    assert [p["ac_block_index"] for p in plan] == [1, 2]
    assert [p["dc_blocks_total"] for p in plan] == [8, 4]
    # Every PCS feeder in each block is fed (no dangling PCS).
    for entry, row in zip(plan, rows):
        assert len(entry["feeder_allocations"]) == row["pcs_count"]
        assert all(count >= 1 for count in entry["feeder_allocations"])
