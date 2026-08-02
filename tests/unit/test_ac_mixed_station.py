"""Mixed AC Block station — a manual-adjustment layer over the uniform trunk.

These tests protect the business rules of the mixed station (head/tail
composition, feeder capacity, sum-to-total) without touching the frozen sizing
canon. Uniform must remain the single-entry case so UI and report stay on one
code path.
"""
from __future__ import annotations

from calb_sizing_tool.adapters.ac_to_sld_adapter import normalize_ac_output_for_sld
from calb_sizing_tool.services.ac_mixed_station import (
    build_mixed_dc_allocation_plan,
    default_uniform_rows,
    head_fleet_ac_output_for_sld,
    is_mixed_station,
    summarize_ac_block_rows,
    validate_ac_block_rows,
)


def _mixed_ac_output() -> dict:
    """A 5-AC-Block station: 4 × (8 PCS, 8 DC) head + 1 × (4 PCS, 4 DC) tail."""
    rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8} for _ in range(4)]
    rows.append({"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4})
    plan = build_mixed_dc_allocation_plan(rows, dc_block_output_circuits=2)
    return {
        "num_blocks": 5,
        "pcs_per_block": 8,
        "pcs_kw": 1250,
        "block_size_mw": 10.0,
        "transformer_mva": 10.0 / 0.9,
        "pcs_count_by_block": [r["pcs_count"] for r in rows],
        "dc_blocks_per_ac": [r["dc_blocks"] for r in rows],
        "dc_blocks_total_by_block": [p["dc_blocks_total"] for p in plan],
        "dc_blocks_per_feeder_by_block": [list(p.get("feeder_allocations", [])) for p in plan],
        "dc_block_connections_by_block": [list(p.get("dc_block_connections", [])) for p in plan],
        "dc_allocation_plan": plan,
        "dc_blocks_total": 36,
        "transformer_count": 5,
        "pcs_count_total": 36,
        "transformer_topology": "three_winding",
        "lv_winding_count": 2,
        "mv_voltage_kv": 33.0,
        "lv_voltage_v": 690.0,
        "dc_block_output_circuits": 2,
        "ac_block_mixed": True,
        "ac_block_rows": rows,
    }


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


def test_head_fleet_projection_yields_uniform_head_only_station():
    rep = head_fleet_ac_output_for_sld(_mixed_ac_output())
    assert rep is not None
    # Only the 4 head AC Blocks survive; the 5 MW tail is dropped.
    assert rep["num_blocks"] == 4
    assert rep["pcs_count_by_block"] == [8, 8, 8, 8]
    assert rep["pcs_per_block"] == 8
    assert rep["dc_blocks_total"] == 32
    assert rep["dc_blocks_total_by_block"] == [8, 8, 8, 8]
    assert rep["transformer_count"] == 4
    assert rep["pcs_count_total"] == 32
    # The projection is a uniform station in its own right, with a trail marker.
    assert rep["ac_block_mixed"] is False
    assert rep["sld_representative_of_mixed"] is True
    assert rep["sld_head_fleet_block_count"] == 4


def test_head_fleet_projection_passes_ac_to_sld_adapter():
    rep = head_fleet_ac_output_for_sld(_mixed_ac_output())
    out = normalize_ac_output_for_sld(rep)
    assert out.num_blocks == 4
    assert out.pcs_count_by_block == [8, 8, 8, 8]
    assert out.dc_blocks_total_by_block == [8, 8, 8, 8]


def test_head_fleet_projection_is_identity_for_uniform_station():
    rows = default_uniform_rows([8, 8, 7], pcs_count=8, pcs_kw=1250)
    plan = build_mixed_dc_allocation_plan(rows, dc_block_output_circuits=2)
    uniform = {
        "num_blocks": 3,
        "pcs_per_block": 8,
        "pcs_kw": 1250,
        "pcs_count_by_block": [8, 8, 8],
        "dc_blocks_per_ac": [8, 8, 7],
        "dc_block_output_circuits": 2,
        "ac_block_mixed": False,
        "ac_block_rows": rows,
    }
    rep = head_fleet_ac_output_for_sld(uniform)
    assert rep is not None
    # A single-model station (uneven DC filling) keeps all its AC Blocks.
    assert rep["num_blocks"] == 3
    assert rep["pcs_count_by_block"] == [8, 8, 8]
    assert rep["dc_blocks_per_ac"] == [8, 8, 7]
    assert rep["sld_representative_of_mixed"] is False


def test_head_fleet_projection_returns_none_without_rows():
    assert head_fleet_ac_output_for_sld({}) is None
    assert head_fleet_ac_output_for_sld({"pcs_count_by_block": []}) is None


def test_head_fleet_flags_representative_even_without_the_mixed_marker():
    """The head-fleet SLD must be marked representative-only from the ROWS.

    ``ac_block_mixed`` is written by the AC Sizing page, but rows are also
    RECONSTRUCTED for runs persisted before the mixed table existed — those carry
    no marker. Trusting the marker alone let a genuinely mixed station's
    head-fleet-only drawing pass the formal-readiness gate as a full-site SLD,
    even though the tail AC Blocks are not on it.
    """
    mixed_rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8} for _ in range(11)]
    mixed_rows.append({"pcs_count": 4, "pcs_kw": 1250, "dc_blocks": 4})
    uniform_rows = [{"pcs_count": 8, "pcs_kw": 1250, "dc_blocks": 8} for _ in range(3)]

    # Mixed rows, marker absent (legacy run) -> still representative-only.
    assert head_fleet_ac_output_for_sld(
        {"ac_block_rows": mixed_rows}
    )["sld_representative_of_mixed"] is True
    # Same via the legacy reconstruction path (no ac_block_rows at all).
    assert head_fleet_ac_output_for_sld(
        {"pcs_count_by_block": [8] * 11 + [4], "dc_blocks_per_ac": [8] * 11 + [4], "pcs_kw": 1250}
    )["sld_representative_of_mixed"] is True
    # A genuinely uniform station is NOT representative-only.
    assert head_fleet_ac_output_for_sld(
        {"ac_block_rows": uniform_rows}
    )["sld_representative_of_mixed"] is False
