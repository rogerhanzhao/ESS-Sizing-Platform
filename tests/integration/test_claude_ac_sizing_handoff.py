"""Cross-module acceptance contract for the 2026-07-28 Claude cloud handoff.

This test deliberately protects business boundaries rather than a particular
vendor catalogue row.  A future refactor may move UI/SLD plumbing, but it must
not turn 1:8 into a locked product or infer an unsafe transformer topology.
"""
from pathlib import Path

import pytest

from calb_sizing_tool.services.ac_block_product_match import preferred_catalogue_architecture
from calb_sizing_tool.services.ac_sizing_service import (
    build_simplified_ac_block_models,
    dc_grouping_has_feeder_capacity,
    generate_ac_sizing_options,
    minimum_dc_blocks_for_pcs_feeders,
    standard_pcs_recommendations,
)
from calb_sizing_tool.sld.transformer_vector_group import (
    TransformerVectorGroupError,
    parse_transformer_vector_group,
)


def test_cloud_handoff_keeps_one_to_eight_generic_and_physically_feasible():
    one_to_eight = next(
        option
        for option in generate_ac_sizing_options(
            dc_blocks_total=202,
            target_mw=200.0,
            target_mwh=800.0,
            dc_block_mwh=5.0,
        )
        if option.ratio == "1:8"
    )

    # 202 must remain an even generic allocation, not a fixed 8/4/2/1
    # catalogue decomposition.
    assert one_to_eight.ac_block_count == 26
    assert one_to_eight.dc_blocks_per_ac.count(8) == 20
    assert one_to_eight.dc_blocks_per_ac.count(7) == 6

    models = build_simplified_ac_block_models(
        standard_pcs_recommendations(),
        grouping_ratio="1:8",
    )
    assert (models[0].pcs_count, models[0].pcs_kw) == (8, 1250)
    assert models[0].source == "one_to_eight_small_pcs_candidate"
    # The normal 5 MW comparison remains selectable; 1:8 must not force 10 MW.
    assert any((model.pcs_count, model.pcs_kw) == (2, 2500) for model in models)

    assert minimum_dc_blocks_for_pcs_feeders(8) == 4
    assert dc_grouping_has_feeder_capacity(one_to_eight.dc_blocks_per_ac, 8)
    assert not dc_grouping_has_feeder_capacity([3], 8)


def test_cloud_handoff_treats_catalogue_preference_as_preference_only():
    normal = preferred_catalogue_architecture("1:2")
    one_to_eight = preferred_catalogue_architecture("1:8")

    assert (normal["pcs_count"], normal["pcs_kw"]) == (2, 2500)
    assert (one_to_eight["pcs_count"], one_to_eight["pcs_kw"]) == (8, 1250)
    assert "does not lock a product" in one_to_eight["reason"]
    assert "does not alter AC grouping or PCS sizing" in normal["reason"]


def test_cloud_handoff_requires_truthful_three_winding_vector_data():
    assert parse_transformer_vector_group(
        "Dy11-y11",
        lv_winding_count=2,
    ).lv_tokens == ("y11", "y11")

    with pytest.raises(TransformerVectorGroupError, match="declares 1 LV winding"):
        parse_transformer_vector_group("Dyn11", lv_winding_count=2)


def test_cloud_handoff_has_no_legacy_product_preset_sizing_branch():
    source = (
        Path(__file__).parents[2] / "calb_sizing_tool" / "ui" / "ac_view.py"
    ).read_text(encoding="utf-8")

    assert "use_product_preset" not in source
    assert "Run AC Sizing (Governed)" not in source
    assert "standard product AC Block preset" not in source
    assert "dc_grouping_has_feeder_capacity" in source
