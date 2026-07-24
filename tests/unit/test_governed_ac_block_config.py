"""Governed AC Block configuration contract (Phase A).

Verifies the fixed ACBLK-10MW-8PCS-8DC-40FT-BILATERAL identity and its
AC->SLD output payload. The governed configuration must:
- bind 8 DC / 8 PCS / 10 MW / 40 ft / bilateral as one atomic choice;
- gate Phase A to homogeneous totals divisible by 8;
- keep every unconfirmed engineering value provisional (never inferred);
- map DC-i -> PCS-i dedicated links while keeping the DC product's own output
  capability independent of that connection policy.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.ac_to_sld_adapter import (
    AcToSldAdapterError,
    normalize_ac_output_for_sld,
)
from calb_sizing_tool.schemas.governed_ac_block_config import (
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as CFG,
    DC_BLOCK_PRODUCT_OUTPUT_CIRCUITS,
    DEDICATED_LINK_OUTPUT_CIRCUITS,
    get_governed_configuration,
)


def test_confirmed_identity_fields():
    assert CFG.configuration_code == "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"
    assert CFG.ac_power_mw == 10.0
    assert CFG.pcs_count == 8
    assert CFG.pcs_rating_kw == 1250
    assert CFG.dc_block_count == 8
    assert CFG.ac_container_type == "40ft"
    assert CFG.layout_variant == "central_40ft_bilateral_4plus4"
    assert CFG.dc_field_split == (4, 4)
    assert CFG.dc_connection_policy == "dedicated_dc_to_pcs"
    assert CFG.transformer_topology == "three_winding"
    assert CFG.lv_winding_count == 2
    assert CFG.pcs_per_lv_winding == (4, 4)
    # 8 x 1250 kW = 10 MW equal-PCS basis
    assert CFG.block_size_mw == 10.0


def test_registry_lookup():
    assert get_governed_configuration(CFG.configuration_code) is CFG
    with pytest.raises(KeyError):
        get_governed_configuration("ACBLK-DOES-NOT-EXIST")


def test_phase_a_gate_requires_multiple_of_eight():
    assert CFG.phase_a_eligible(8) is True
    assert CFG.phase_a_eligible(16) is True
    assert CFG.phase_a_eligible(80) is True
    assert CFG.phase_a_eligible(4) is False   # deferred Phase B tail
    assert CFG.phase_a_eligible(12) is False
    assert CFG.phase_a_eligible(9) is False
    assert CFG.phase_a_eligible(0) is False


def test_ac_block_count_for():
    assert CFG.ac_block_count_for(8) == 1
    assert CFG.ac_block_count_for(16) == 2
    with pytest.raises(ValueError):
        CFG.ac_block_count_for(12)


def test_dedicated_dc_to_pcs_mapping_is_one_to_one():
    connections = CFG.build_dc_block_connections()
    assert len(connections) == 8
    assert [(c["dc_block_index"], c["feeder_indices"]) for c in connections] == [
        (i, [i]) for i in range(1, 9)
    ]
    # The connection policy uses a single physical output circuit per link ...
    assert all(c["output_circuit_count"] == DEDICATED_LINK_OUTPUT_CIRCUITS for c in connections)
    # ... while the DC Block product still exposes two protected outputs.
    assert CFG.dc_block_output_circuits == DC_BLOCK_PRODUCT_OUTPUT_CIRCUITS == 2


def test_allocation_plan_has_no_dangling_feeders():
    plan = CFG.build_dc_allocation_plan()
    assert len(plan) == 1
    assert plan[0]["dc_blocks_total"] == 8
    assert plan[0]["feeder_allocations"] == [1] * 8
    assert 0 not in plan[0]["feeder_allocations"]


def test_provisional_values_default_to_none_and_are_listed():
    for name in CFG.provisional_fields:
        assert getattr(CFG, name) is None, f"{name} must be provisional (None) until owner-confirmed"
    assert "transformer_mva" in CFG.provisional_fields
    assert "transformer_vector_group" in CFG.provisional_fields
    assert "lv_voltage_v" in CFG.provisional_fields


def test_ac_output_omits_transformer_mva_until_supplied():
    """10 MW / 0.9 must never auto-become an approved 11.11 MVA nameplate."""
    out = CFG.to_ac_sld_output()
    assert "transformer_mva" not in out
    assert "transformer_mva" in out["provisional_unresolved"]
    # The strict AC->SLD contract must fail loudly rather than invent a rating.
    with pytest.raises(AcToSldAdapterError):
        normalize_ac_output_for_sld(out)


def test_ac_output_carries_governed_identity_and_topology():
    out = CFG.to_ac_sld_output(
        engineering_overrides={"transformer_mva": 11.11, "lv_voltage_v": 690.0}
    )
    assert out["configuration_code"] == CFG.configuration_code
    assert out["layout_variant"] == "central_40ft_bilateral_4plus4"
    assert out["dc_field_split"] == [4, 4]
    assert out["dc_connection_policy"] == "dedicated_dc_to_pcs"
    assert out["governed_configuration"] is True

    norm = normalize_ac_output_for_sld(out)
    assert norm.num_blocks == 1
    assert norm.pcs_per_block == 8
    assert norm.pcs_kw == 1250.0
    assert norm.block_size_mw == 10.0
    assert norm.lv_winding_count == 2
    assert norm.transformer_topology == "three_winding"
    assert norm.dc_blocks_per_feeder_by_block == [[1] * 8]
    assert [
        (c.dc_block_index, c.feeder_indices) for c in norm.dc_block_connections_by_block[0]
    ] == [(i, [i]) for i in range(1, 9)]


def test_engineering_overrides_reject_non_provisional_fields():
    with pytest.raises(ValueError):
        CFG.to_ac_sld_output(engineering_overrides={"pcs_count": 4})
