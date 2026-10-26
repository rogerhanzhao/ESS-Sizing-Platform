"""Actual BOM handoff, including original source-rounding and mixed quantities."""
from copy import deepcopy

import pytest

from calb_sizing_tool.adapters.session_state_adapter import build_dc_bom_handoff
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from calb_sizing_tool.services.stage2_service import _build_items, build_config_container_only
from calb_sizing_tool.services.stage3_service import run_stage3
from calb_sizing_tool.services import dc_reduced_string_tail_service as tails
from tests.test_dc_reduced_string_tail import example


def _mixed_stage2(lines=None):
    # The producer remains the existing frozen Stage 2 item builder. These
    # multiple quantities exercise transport only, never a new sizing policy.
    lines = lines or [("12R", 5.0159616, 2), ("10R", 4.179968, 3), ("8R", 3.3439744, 4)]
    rows = [dict(zip(("Block Code", "Unit Capacity (MWh)", "Count"), line),
                 **{"Block Name": f"Synthetic {line[0]}", "Form": "container"})
            for line in lines]
    items = _build_items(rows)
    total = items[0].total_dc_nameplate_bol_mwh
    return Stage2Result(mode="synthetic_transport_only", dc_nameplate_bol_mwh=total,
        oversize_mwh=0, config_adjustment_frac=0, block_config_items=items,
        container_count=sum(line[2] for line in lines), cabinet_count=0, busbars_needed=0)


def test_retains_both_reduced_skus_multiple_quantities_and_original_order():
    source = _mixed_stage2([("10R", 4.179968, 3), ("12R", 5.0159616, 2), ("8R", 3.3439744, 4)])
    before = deepcopy(source.model_dump(mode="json"))

    result = build_dc_bom_handoff(source)

    assert [item["count"] for item in result["items"]] == [3, 2, 4]
    assert [unit["block_code"] for unit in result["units"]] == ["10R"] * 3 + ["12R"] * 2 + ["8R"] * 4
    assert [unit["bom_ordinal"] for unit in result["units"]] == list(range(1, 10))
    assert result["units"][3]["item_ordinal"] == 2
    assert result["totals"]["unit_count"] == 9
    assert result["totals"]["dc_nameplate_bol_mwh"] == source.dc_nameplate_bol_mwh
    assert result["unit_ordinals_are_inventory_only"] is True
    assert result["electrical_mapping_provided"] is False
    assert result["adoption_asserted"] is False
    assert source.model_dump(mode="json") == before
    assert result["source_stage2_sha256"] == _hash_payload(before)


def test_preserves_admin_source_subtotal_without_inventing_an_average():
    source = build_config_container_only(450, 5.0159616, "MAIN", "Synthetic main")

    result = build_dc_bom_handoff(source)

    assert source.container_count == 90
    assert result["items"][0]["unit_capacity_mwh"] == 5.016
    assert result["items"][0]["subtotal_mwh"] == 451.437
    assert result["totals"]["dc_nameplate_bol_mwh"] == 451.437
    assert sum(unit["unit_capacity_mwh"] for unit in result["units"]) != pytest.approx(451.437, abs=0.0001)
    assert {unit["unit_capacity_mwh"] for unit in result["units"]} == {5.016}


def test_accepts_original_aggregate_vs_item_rounding_difference():
    source = _mixed_stage2([("A", 5.0154, 1), ("B", 4.1794, 1)])
    assert sum(item.subtotal_mwh for item in source.block_config_items) != source.dc_nameplate_bol_mwh

    result = build_dc_bom_handoff(source)

    assert result["totals"]["dc_nameplate_bol_mwh"] == 9.195
    assert [item["subtotal_mwh"] for item in result["items"]] == [5.015, 4.179]


def test_valid_zero_configuration_remains_empty_inventory():
    source = build_config_container_only(0, 5.016, "MAIN", "Synthetic main")
    result = build_dc_bom_handoff(source)
    assert result["units"] == []
    assert result["totals"] == dict(container_count=0, cabinet_count=0, unit_count=0,
                                    dc_nameplate_bol_mwh=0.0)


@pytest.mark.parametrize("strings", [10, 8])
@pytest.mark.parametrize("main_code,unit", [(tails.STANDARD_EXCEL_CODE, 5.016), ("CATALOGUE-12", 5.01596)])
def test_real_tail_producer_preserves_excel_and_admin_bom(example, strings, main_code, unit):
    example.snapshot.stage2 = build_config_container_only(95.5 * unit, unit, main_code, "Main container")
    example.snapshot.stage3 = run_stage3(example.snapshot.stage1, example.snapshot.stage2, example.bundle)
    product = tails.available_products(example.rows, example.basis, main_code)[strings]
    comparison = tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, product, example.basis)
    stage2 = Stage2Result.model_validate(comparison["snapshot"]["stage2"])

    result = build_dc_bom_handoff(stage2)

    assert result["source_mode"] == tails.COMPARISON_MODE
    assert result["adoption_asserted"] is False
    assert result["totals"]["unit_count"] == 96
    assert result["items"][0]["subtotal_mwh"] == round(95 * unit, 3)
    assert result["units"][-1]["block_code"] == f"CATALOGUE-{strings}R"
    assert result["units"][-1]["unit_capacity_mwh"] == example.basis["tails"][strings]["energy_mwh"]
    assert result["totals"]["dc_nameplate_bol_mwh"] == stage2.dc_nameplate_bol_mwh


@pytest.mark.parametrize("mutation", ["container_count", "cabinet_count", "repeated_total", "subtotal",
    "zero_subtotal", "empty_code", "empty_name", "nan_capacity", "nan_source", "negative_count", "bool_count"])
def test_rejects_inconsistent_or_nonfinite_source(mutation):
    source = _mixed_stage2()
    first = source.block_config_items[0]
    if mutation == "container_count":
        source.container_count += 1
    elif mutation == "cabinet_count":
        source.cabinet_count = 1
    elif mutation == "repeated_total":
        first.total_dc_nameplate_bol_mwh += 1
    elif mutation == "subtotal":
        first.subtotal_mwh += 0.1
    elif mutation == "zero_subtotal":
        first.count = 0
    elif mutation == "empty_code":
        first.block_code = " "
    elif mutation == "empty_name":
        first.block_name = " "
    elif mutation == "nan_capacity":
        first.unit_capacity_mwh = float("nan")
    elif mutation == "nan_source":
        source.oversize_mwh = float("nan")
    elif mutation == "negative_count":
        first.count = -1
    else:
        first.count = True
    with pytest.raises(ValueError):
        build_dc_bom_handoff(source)


def test_rejects_total_inconsistency_even_when_repeated_totals_are_changed():
    source = _mixed_stage2()
    source.dc_nameplate_bol_mwh += 1
    for item in source.block_config_items:
        item.total_dc_nameplate_bol_mwh = source.dc_nameplate_bol_mwh
    with pytest.raises(ValueError, match="subtotals differ"):
        build_dc_bom_handoff(source)


def test_full_source_identity_changes_without_rewriting_original_payload():
    source = _mixed_stage2()
    initial = build_dc_bom_handoff(source)
    changed = deepcopy(source)
    changed.oversize_mwh += 0.1
    revised = build_dc_bom_handoff(changed)
    assert revised["items"] == initial["items"]
    assert revised["source_stage2_sha256"] != initial["source_stage2_sha256"]


def test_handoff_copies_nested_inventory_values():
    source = _mixed_stage2()
    initial = deepcopy(source)
    result = build_dc_bom_handoff(source)
    result["items"][0]["count"] = 999
    result["units"][0]["block_code"] = "CHANGED"
    assert source == initial
