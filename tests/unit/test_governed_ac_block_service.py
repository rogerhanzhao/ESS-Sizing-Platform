"""Bind the governed configuration to persisted Engineering Settings.

Verifies that owner-confirmed provisional values (transformer nameplate MVA,
vector group, Uk%, cooling) flow from ``project_settings`` into the governed
AC->SLD output, that unset values stay unresolved (never inferred), and that
the AC->SLD contract accepts the result once MVA is present.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.ac_to_sld_adapter import (
    AcToSldAdapterError,
    normalize_ac_output_for_sld,
)
from calb_sizing_tool.services.governed_ac_block_service import (
    build_governed_ac_output_from_settings,
    build_governed_site_ac_output,
    map_engineering_settings_to_overrides,
    unresolved_provisional_fields,
)
from calb_sizing_tool.schemas.governed_ac_block_config import (
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as CFG,
)

CODE = "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"


def _settings(**overrides):
    base = {
        "transformer": {"vector_group": "Dyn11", "uk_percent": 8.0},
        "equipment_ratings": {"transformer_cooling": "ONAN"},
        "dc_block_voltage_v": 1500.0,
    }
    base.update(overrides)
    return base


def test_maps_confirmed_settings_to_overrides():
    settings = _settings(transformer_rating_mva=11.5)
    overrides = map_engineering_settings_to_overrides(settings, CFG)
    assert overrides["transformer_mva"] == 11.5
    assert overrides["transformer_vector_group"] == "Dyn11"
    assert overrides["transformer_uk_percent"] == 8.0
    assert overrides["transformer_cooling"] == "ONAN"


def test_unset_mva_stays_unresolved_and_is_not_inferred():
    settings = _settings()  # no transformer_rating_mva
    payload = build_governed_ac_output_from_settings(CODE, settings)
    assert "transformer_mva" not in payload
    assert "transformer_mva" in payload["provisional_unresolved"]
    # The strict AC->SLD contract must still refuse to render without MVA.
    with pytest.raises(AcToSldAdapterError):
        normalize_ac_output_for_sld(payload)


def test_confirmed_mva_makes_output_valid():
    settings = _settings(transformer_rating_mva=11.5)
    payload = build_governed_ac_output_from_settings(CODE, settings)
    assert payload["transformer_mva"] == 11.5
    assert "transformer_mva" not in payload["provisional_unresolved"]
    norm = normalize_ac_output_for_sld(payload)
    assert norm.transformer_mva == 11.5
    assert norm.lv_winding_count == 2
    assert norm.pcs_per_block == 8


def test_unresolved_list_shrinks_as_owner_confirms_values():
    empty = unresolved_provisional_fields(CODE, {})
    assert "transformer_mva" in empty
    assert "transformer_vector_group" in empty

    partial = unresolved_provisional_fields(
        CODE, _settings(transformer_rating_mva=11.5)
    )
    assert "transformer_mva" not in partial
    assert "transformer_vector_group" not in partial
    # layout-only dims are not in SLD settings, so they remain unresolved
    assert "ac_station_length_m" in partial


def test_phase_a_gate_enforced_when_dc_total_supplied():
    with pytest.raises(ValueError):
        build_governed_ac_output_from_settings(
            CODE, _settings(transformer_rating_mva=11.5), dc_blocks_total=12
        )
    # divisible by 8 is fine
    payload = build_governed_ac_output_from_settings(
        CODE, _settings(transformer_rating_mva=11.5), dc_blocks_total=16
    )
    assert payload["configuration_code"] == CODE


def test_site_output_single_unit():
    site = build_governed_site_ac_output(
        CODE, _settings(transformer_rating_mva=11.5), dc_blocks_total=8
    )
    assert site["num_blocks"] == 1
    assert site["dc_blocks_total"] == 8
    assert site["total_ac_mw"] == 10.0
    norm = normalize_ac_output_for_sld(site)
    assert norm.num_blocks == 1
    assert norm.pcs_count_total == 8


def test_site_output_multi_unit_is_uniform_and_valid():
    site = build_governed_site_ac_output(
        CODE, _settings(transformer_rating_mva=11.5), dc_blocks_total=16
    )
    assert site["num_blocks"] == 2
    assert site["dc_blocks_total"] == 16
    assert site["total_ac_mw"] == 20.0
    assert site["pcs_count_total"] == 16
    assert site["transformer_count"] == 2
    assert len(site["dc_allocation_plan"]) == 2
    assert [p["ac_block_index"] for p in site["dc_allocation_plan"]] == [1, 2]
    # Each block keeps its own contiguous DC-1..8 -> PCS-1..8 mapping.
    for plan in site["dc_allocation_plan"]:
        assert plan["dc_blocks_total"] == 8
        assert plan["feeder_allocations"] == [1] * 8

    norm = normalize_ac_output_for_sld(site)
    assert norm.num_blocks == 2
    assert norm.dc_blocks_total == 16
    assert norm.lv_winding_count == 2
    assert norm.transformer_topology == "three_winding"


def test_site_output_rejects_non_phase_a_total():
    with pytest.raises(ValueError):
        build_governed_site_ac_output(
            CODE, _settings(transformer_rating_mva=11.5), dc_blocks_total=20
        )


def test_site_output_carries_source_fields_and_stays_gated_without_mva():
    site = build_governed_site_ac_output(
        CODE,
        _settings(),  # no MVA
        dc_blocks_total=8,
        source_fields={"mv_voltage_kv": 33.0, "source_case_code": "case-1"},
    )
    assert site["mv_voltage_kv"] == 33.0
    assert site["source_case_code"] == "case-1"
    assert "transformer_mva" in site["provisional_unresolved"]
    with pytest.raises(AcToSldAdapterError):
        normalize_ac_output_for_sld(site)


def test_extra_overrides_filtered_to_provisional_fields():
    payload = build_governed_ac_output_from_settings(
        CODE,
        _settings(transformer_rating_mva=11.5),
        extra_overrides={"ac_station_length_m": 12.0, "pcs_count": 4},
    )
    # provisional layout dim accepted; non-provisional field ignored
    assert "ac_station_length_m" not in payload["provisional_unresolved"]
    assert payload["pcs_per_block"] == 8
