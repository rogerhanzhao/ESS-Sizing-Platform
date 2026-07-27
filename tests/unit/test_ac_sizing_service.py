from __future__ import annotations

from calb_sizing_tool.common.ac_block import derive_ac_template_fields
from calb_sizing_tool.services.ac_sizing_service import (
    STANDARD_PCS_COUNTS,
    STANDARD_PCS_RATINGS_KW,
    SUPPORTED_AC_DC_RATIOS,
    build_simplified_ac_block_models,
    build_dc_block_connection_plan,
    build_dc_allocation_plan,
    calculate_optimal_pcs_rating,
    evaluate_ac_sizing_feasibility,
    generate_ac_sizing_options,
    select_ac_block_container_type,
    standard_pcs_recommendations,
)


def test_ac_sizing_service_freezes_supported_ratios_and_recommendations():
    options = generate_ac_sizing_options(
        dc_blocks_total=9,
        target_mw=100.0,
        target_mwh=400.0,
        dc_block_mwh=5.0,
    )

    assert tuple(option.ratio for option in options) == SUPPORTED_AC_DC_RATIOS
    assert [option.ac_block_count for option in options] == [9, 5, 3, 2]
    assert options[0].dc_blocks_per_ac == [1] * 9
    assert options[1].dc_blocks_per_ac == [2, 2, 2, 2, 1]
    assert options[2].dc_blocks_per_ac == [3, 3, 3]
    assert options[3].dc_blocks_per_ac == [5, 4]
    assert options[0].is_recommended is False
    assert options[1].is_recommended is True
    assert options[2].is_recommended is True
    assert options[3].is_recommended is False


def test_ac_sizing_service_freezes_standard_pcs_library():
    recommendations = standard_pcs_recommendations()
    expected_pairs = [
        (pcs_count, pcs_kw)
        for pcs_count in STANDARD_PCS_COUNTS
        for pcs_kw in STANDARD_PCS_RATINGS_KW
    ]

    assert [(item.pcs_count, item.pcs_kw) for item in recommendations] == expected_pairs


def test_ac_sizing_service_builds_simplified_ac_block_models_from_pcs_library():
    models = build_simplified_ac_block_models(standard_pcs_recommendations())
    by_pair = {(model.pcs_count, model.pcs_kw): model for model in models}

    two_pcs_5mw = by_pair[(2, 2500)]
    assert two_pcs_5mw.model_code == "ACBLK-2X2500KW-20FT"
    assert two_pcs_5mw.block_size_mw == 5.0
    assert two_pcs_5mw.container_type == "20ft"
    assert two_pcs_5mw.source == "simplified_dropdown"

    four_pcs_5mw = by_pair[(4, 1250)]
    assert four_pcs_5mw.model_code == "ACBLK-4X1250KW-20FT"
    assert four_pcs_5mw.block_size_mw == 5.0
    assert four_pcs_5mw.container_type == "20ft"
    assert "4 x 1250 kW PCS" in four_pcs_5mw.readable


def test_one_to_eight_adds_optional_small_pcs_candidate_without_locking_product():
    models = build_simplified_ac_block_models(
        standard_pcs_recommendations(),
        grouping_ratio="1:8",
    )
    small_pcs = next(model for model in models if (model.pcs_count, model.pcs_kw) == (8, 1250))

    assert (models[0].pcs_count, models[0].pcs_kw) == (8, 1250)
    assert small_pcs.block_size_mw == 10.0
    assert small_pcs.container_type == "40ft"
    assert small_pcs.source == "one_to_eight_small_pcs_candidate"
    assert "small-PCS combination" in small_pcs.display_name


def test_one_to_eight_distribution_and_feeder_capacity_are_physical_not_product_locked():
    from calb_sizing_tool.services.ac_sizing_service import (
        dc_grouping_has_feeder_capacity,
        minimum_dc_blocks_for_pcs_feeders,
    )

    options = generate_ac_sizing_options(202, 200.0, 800.0, 5.0)
    one_to_eight = next(option for option in options if option.ratio == "1:8")
    assert one_to_eight.ac_block_count == 26
    # Generic grouping remains balanced, rather than manufacturing a fixed
    # 8-DC head plus a small product tail: 202 = 20 x 8 DC + 6 x 7 DC.
    assert one_to_eight.dc_blocks_per_ac.count(8) == 20
    assert one_to_eight.dc_blocks_per_ac.count(7) == 6

    # Both architectures are valid for a balanced 202-DC 1:8 selection. A
    # small project with only three DC Blocks is correctly rejected for 8 PCS.
    assert minimum_dc_blocks_for_pcs_feeders(2) == 1
    assert minimum_dc_blocks_for_pcs_feeders(8) == 4
    assert dc_grouping_has_feeder_capacity(one_to_eight.dc_blocks_per_ac, 2)
    assert dc_grouping_has_feeder_capacity(one_to_eight.dc_blocks_per_ac, 8)
    small_one_to_eight = next(
        option for option in generate_ac_sizing_options(3, 10.0, 40.0, 5.0) if option.ratio == "1:8"
    )
    assert not dc_grouping_has_feeder_capacity(small_one_to_eight.dc_blocks_per_ac, 8)


def test_ac_sizing_service_builds_authoritative_dc_allocation_plan():
    allocation_plan = build_dc_allocation_plan(dc_blocks_total=12, ac_block_count=3, pcs_per_block=4)

    assert [
        (item["ac_block_index"], item["dc_blocks_total"], item["feeder_allocations"])
        for item in allocation_plan
    ] == [(1, 4, [1, 1, 1, 1]), (2, 4, [1, 1, 1, 1]), (3, 4, [1, 1, 1, 1])]
    assert allocation_plan[0]["dc_block_connections"] == [
        {"dc_block_index": 1, "feeder_indices": [1], "output_circuit_count": 2, "internal_dc_busbar_mode": "common"},
        {"dc_block_index": 2, "feeder_indices": [2], "output_circuit_count": 2, "internal_dc_busbar_mode": "common"},
        {"dc_block_index": 3, "feeder_indices": [3], "output_circuit_count": 2, "internal_dc_busbar_mode": "common"},
        {"dc_block_index": 4, "feeder_indices": [4], "output_circuit_count": 2, "internal_dc_busbar_mode": "common"},
    ]


def test_dc_block_connection_plan_models_two_protected_outputs_from_one_common_bus():
    assert build_dc_block_connection_plan(2, 4) == [
        {"dc_block_index": 1, "feeder_indices": [1, 2], "output_circuit_count": 2, "internal_dc_busbar_mode": "common"},
        {"dc_block_index": 2, "feeder_indices": [3, 4], "output_circuit_count": 2, "internal_dc_busbar_mode": "common"},
    ]


def test_ac_sizing_service_freezes_container_selection_threshold():
    assert select_ac_block_container_type(5.0, 2) == "20ft"
    assert select_ac_block_container_type(5.0, 4) == "20ft"
    assert select_ac_block_container_type(5.01, 2) == "40ft"
    assert select_ac_block_container_type(4.0, 4) == "20ft"


def test_ac_sizing_service_freezes_power_and_energy_thresholds():
    errors, warnings = evaluate_ac_sizing_feasibility(
        total_energy_mwh=380.0,
        target_energy_mwh=400.0,
        total_ac_mw=120.0,
        target_power_mw=100.0,
    )

    assert errors == []
    assert warnings == []

    errors, warnings = evaluate_ac_sizing_feasibility(
        total_energy_mwh=379.0,
        target_energy_mwh=400.0,
        total_ac_mw=94.0,
        target_power_mw=100.0,
    )

    assert "Insufficient energy: 379 MWh < 400 MWh" in errors
    assert "Insufficient power: 94.0 MW < 100.0 MW" in errors
    assert warnings == []

    errors, warnings = evaluate_ac_sizing_feasibility(
        total_energy_mwh=430.0,
        target_energy_mwh=400.0,
        total_ac_mw=131.0,
        target_power_mw=100.0,
    )

    assert errors == []
    assert warnings == [
        "Excess energy: 430 MWh > 400 MWh (+7.5%)",
        "Power overhead: 31.0 MW (31% of POI requirement)",
    ]


def test_calculate_optimal_pcs_rating_uses_real_discharge_duration():
    # 4-hour system: 2 DC blocks × 5 MWh = 10 MWh total
    # total_kw = 10000 / 4.0 / (0.97 * 0.9) = 2865 kW; per 2 PCS = 1432 kW → ceil to 1500
    assert calculate_optimal_pcs_rating(2, 5.0, 2, 4.0) == 1500
    # per 4 PCS = 716 kW → ceil to 1000
    assert calculate_optimal_pcs_rating(2, 5.0, 4, 4.0) == 1000

    # 2-hour system: same 10 MWh but discharge in 2h → double the power requirement
    # total_kw = 10000 / 2.0 / 0.873 = 5729 kW; per 2 PCS = 2865 kW → ceil to 3000
    assert calculate_optimal_pcs_rating(2, 5.0, 2, 2.0) == 3000
    # per 4 PCS = 1432 kW → ceil to 1500
    assert calculate_optimal_pcs_rating(2, 5.0, 4, 2.0) == 1500

    # 6-hour system: same 10 MWh, discharge in 6h → less power needed
    # total_kw = 10000 / 6.0 / 0.873 = 1910 kW; per 2 PCS = 955 kW → ceil to 1000
    assert calculate_optimal_pcs_rating(2, 5.0, 2, 6.0) == 1000


def test_generate_ac_sizing_options_marks_is_optimal_from_ep_ratio():
    # 4h system (400 MWh / 100 MW), 4 DC blocks, dc_block_mwh=5.0
    # 1:2 ratio → max 2 DC blocks per AC block
    # For 2 PCS: total=10000/4/0.873=2865kW, per unit=1432kW → optimal=1500 (in standard) → marked
    # For 4 PCS: per unit=716kW → optimal=1000 (NOT in standard) → not marked
    options = generate_ac_sizing_options(4, 100.0, 400.0, 5.0)
    ratio_12 = next(o for o in options if o.ratio == "1:2")
    assert any(r.is_optimal and r.pcs_count == 2 and r.pcs_kw == 1500
               for r in ratio_12.pcs_recommendations)
    assert not any(r.is_optimal and r.pcs_count == 4
                   for r in ratio_12.pcs_recommendations)

    # 2h system (200 MWh / 100 MW), same 4 blocks — discharge duration halved → power doubles
    # For 2 PCS: per unit=2865kW → optimal=3000 (NOT in standard) → not marked
    # For 4 PCS: per unit=1432kW → optimal=1500 (in standard) → marked
    options_2h = generate_ac_sizing_options(4, 100.0, 200.0, 5.0)
    ratio_12_2h = next(o for o in options_2h if o.ratio == "1:2")
    assert any(r.is_optimal and r.pcs_count == 4 and r.pcs_kw == 1500
               for r in ratio_12_2h.pcs_recommendations)
    assert not any(r.is_optimal and r.pcs_count == 2
                   for r in ratio_12_2h.pcs_recommendations)


def test_generate_ac_sizing_options_is_optimal_independent_of_is_recommended():
    # structure tests: is_recommended and is_optimal are orthogonal flags
    options = generate_ac_sizing_options(4, 100.0, 400.0, 5.0)
    for opt in options:
        for rec in opt.pcs_recommendations:
            assert isinstance(rec.is_optimal, bool)
            assert isinstance(rec.is_recommended, bool) if hasattr(rec, "is_recommended") else True


def test_derive_ac_template_fields_freezes_template_and_pf_resolution():
    template_fields = derive_ac_template_fields(
        {
            "block_size_mw": 5.0,
            "pcs_per_block": 4,
            "pcs_kw": 1250,
            "transformer_kva": 5555.555555555556,
        }
    )

    assert template_fields["ac_block_template_id"] == "4x1250kw"
    assert template_fields["pcs_per_block"] == 4
    assert template_fields["feeders_per_block"] == 4
    assert round(template_fields["grid_power_factor"], 3) == 0.9
