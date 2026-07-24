"""Phase B — governed mixed 8/4/2/1 tail decomposition.

A site total that is not a multiple of 8 is placed into a whole number of
smaller governed AC Blocks (8 -> 4 -> 2 -> 1), never a generic ceil/average
split. Each governed AC Block stays internally uniform (SLD V1 safe); the mix
lives in the list of groups.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.ac_to_sld_adapter import normalize_ac_output_for_sld
from calb_sizing_tool.schemas.governed_ac_block_config import (
    decompose_governed_site,
    governed_configuration_for_dc_count,
    get_governed_configuration,
)
from calb_sizing_tool.services.governed_ac_block_service import (
    build_governed_site_ac_output,
    build_governed_site_plan,
)


def test_tail_configs_are_registered_and_consistent():
    for dc_count, code, mw, topo, lv in [
        (8, "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL", 10.0, "three_winding", 2),
        (4, "ACBLK-5MW-4PCS-4DC-40FT-LINEAR", 5.0, "two_winding", 1),
        (2, "ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR", 2.5, "two_winding", 1),
        (1, "ACBLK-1P25MW-1PCS-1DC-20FT-LINEAR", 1.25, "two_winding", 1),
    ]:
        cfg = get_governed_configuration(code)
        assert cfg.dc_block_count == dc_count
        assert cfg.pcs_count == dc_count
        assert cfg.pcs_rating_kw == 1250
        assert cfg.block_size_mw == mw
        assert cfg.transformer_topology == topo
        assert cfg.lv_winding_count == lv
        assert governed_configuration_for_dc_count(dc_count) is cfg


@pytest.mark.parametrize(
    "total, expected",
    [
        (8, [(8, 1)]),
        (16, [(8, 2)]),
        (188, [(8, 23), (4, 1)]),
        (14, [(8, 1), (4, 1), (2, 1)]),
        (7, [(4, 1), (2, 1), (1, 1)]),
        (1, [(1, 1)]),
        (13, [(8, 1), (4, 1), (1, 1)]),
    ],
)
def test_decomposition_is_greedy_and_exact(total, expected):
    result = [(cfg.dc_block_count, count) for cfg, count in decompose_governed_site(total)]
    assert result == expected
    # DC blocks are conserved exactly.
    assert sum(dc * n for dc, n in result) == total


def test_decomposition_rejects_non_positive():
    with pytest.raises(ValueError):
        decompose_governed_site(0)


def test_site_plan_conserves_dc_and_power():
    plan = build_governed_site_plan(188)
    assert plan.dc_blocks_total == 188
    assert sum(g.dc_blocks_total for g in plan.groups) == 188
    assert plan.ac_blocks_total == 23 + 1
    # 23 x 10 MW + 1 x 5 MW = 235 MW
    assert plan.ac_power_mw_total == 235.0
    codes = [g.configuration_code for g in plan.groups]
    assert codes == ["ACBLK-10MW-8PCS-8DC-40FT-BILATERAL", "ACBLK-5MW-4PCS-4DC-40FT-LINEAR"]


def test_multiple_of_eight_is_single_bilateral_group():
    plan = build_governed_site_plan(24)
    assert len(plan.groups) == 1
    assert plan.groups[0].configuration_code == "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"
    assert plan.groups[0].ac_block_count == 3
    assert plan.groups[0].layout_variant == "central_40ft_bilateral_4plus4"


def test_each_group_ac_output_is_sld_valid():
    # A tail group (4-DC, two-winding) must still satisfy the AC->SLD contract.
    out = build_governed_site_ac_output(
        "ACBLK-5MW-4PCS-4DC-40FT-LINEAR",
        {"transformer_rating_mva": 5.5},
        dc_blocks_total=8,  # 2 x 4-DC blocks
    )
    assert out["num_blocks"] == 2
    assert out["pcs_per_block"] == 4
    assert out["transformer_topology"] == "two_winding"
    assert out["lv_winding_count"] == 1
    norm = normalize_ac_output_for_sld(out)
    assert norm.num_blocks == 2
    assert norm.lv_winding_count == 1
    assert norm.transformer_topology == "two_winding"
