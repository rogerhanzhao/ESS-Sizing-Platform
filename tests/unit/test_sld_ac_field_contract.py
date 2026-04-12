from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.ac_to_sld_adapter import (
    AC_TO_SLD_AUTHORITATIVE_FIELDS_V1,
    AC_TO_SLD_LEGACY_ALIASES_V1,
    AcToSldAdapterError,
    normalize_ac_output_for_sld,
)


def test_ac_to_sld_authoritative_field_map_keeps_single_contract():
    normalized = normalize_ac_output_for_sld(
        {
            "num_blocks": 2,
            "pcs_per_block": 2,
            "pcs_kw": 1725.0,
            "block_size_mw": 3.45,
            "transformer_mva": 4.0,
            "dc_allocation_plan": [
                {"ac_block_index": 1, "dc_blocks_total": 3, "feeder_allocations": [2, 1]},
                {"ac_block_index": 2, "dc_blocks_total": 3, "feeder_allocations": [1, 2]},
            ],
            "dc_blocks_total": 6,
            "dc_total_mwh": 30.0,
            "transformer_count": 2,
            "pcs_count_total": 4,
            "mv_voltage_kv": 33.0,
            "lv_voltage_v": 690.0,
        }
    )

    assert "dc_allocation_plan" in AC_TO_SLD_AUTHORITATIVE_FIELDS_V1
    assert AC_TO_SLD_LEGACY_ALIASES_V1["pcs_kw"] == ("pcs_power_kw", "pcs_rating_kw_each")
    assert normalized.num_blocks == 2
    assert normalized.pcs_count_by_block == [2, 2]
    assert normalized.pcs_rating_kw_list_by_block == [[1725.0, 1725.0], [1725.0, 1725.0]]
    assert normalized.dc_blocks_total_by_block == [3, 3]
    assert normalized.dc_blocks_per_feeder_by_block == [[2, 1], [1, 2]]
    assert normalized.legacy_aliases_used == []


def test_ac_to_sld_authoritative_field_map_converts_legacy_aliases_once():
    normalized = normalize_ac_output_for_sld(
        {
            "ac_blocks_total": 1,
            "pcs_count_per_ac_block": 4,
            "pcs_power_kw": 1250.0,
            "block_size_mw": 5.0,
            "transformer_kva": 6000.0,
            "total_pcs": 4,
            "mv_kv": 33.0,
            "lv_v": 690.0,
            "dc_block_allocation": {
                "per_ac_block": [
                    {
                        "dc_blocks_total": 4,
                        "per_feeder": {"F1": 1, "F2": 1, "F3": 1, "F4": 1},
                    }
                ]
            },
        }
    )

    assert normalized.num_blocks == 1
    assert normalized.pcs_per_block == 4
    assert normalized.pcs_kw == 1250.0
    assert normalized.transformer_mva == 6.0
    assert normalized.dc_allocation_plan[0].feeder_allocations == [1, 1, 1, 1]
    assert normalized.legacy_aliases_used == [
        "ac_blocks_total",
        "dc_block_allocation",
        "lv_v",
        "mv_kv",
        "pcs_count_per_ac_block",
        "pcs_power_kw",
        "total_pcs",
        "transformer_kva",
    ]
    assert normalized.field_sources["dc_allocation_plan"] == "dc_block_allocation"


def test_ac_to_sld_authoritative_field_map_rejects_missing_allocation():
    with pytest.raises(AcToSldAdapterError) as exc_info:
        normalize_ac_output_for_sld(
            {
                "num_blocks": 1,
                "pcs_per_block": 4,
                "pcs_kw": 1250.0,
                "block_size_mw": 5.0,
                "transformer_mva": 6.0,
            }
        )

    assert "dc_allocation_plan is required" in str(exc_info.value)


def test_ac_to_sld_authoritative_field_map_rejects_conflicting_mirror_fields():
    with pytest.raises(AcToSldAdapterError) as exc_info:
        normalize_ac_output_for_sld(
            {
                "num_blocks": 1,
                "pcs_per_block": 4,
                "pcs_kw": 1250.0,
                "block_size_mw": 5.0,
                "transformer_mva": 6.0,
                "dc_allocation_plan": [
                    {"ac_block_index": 1, "dc_blocks_total": 4, "feeder_allocations": [1, 1, 1, 1]}
                ],
                "dc_blocks_total_by_block": [5],
            }
        )

    assert "dc_blocks_total_by_block conflicts" in str(exc_info.value)
