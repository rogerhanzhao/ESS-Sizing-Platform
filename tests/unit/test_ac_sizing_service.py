from __future__ import annotations

from calb_sizing_tool.common.ac_block import derive_ac_template_fields
from calb_sizing_tool.services.ac_sizing_service import (
    STANDARD_PCS_COUNTS,
    STANDARD_PCS_RATINGS_KW,
    SUPPORTED_AC_DC_RATIOS,
    build_dc_allocation_plan,
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
    assert [option.ac_block_count for option in options] == [9, 5, 3]
    assert options[0].dc_blocks_per_ac == [1] * 9
    assert options[1].dc_blocks_per_ac == [2, 2, 2, 2, 1]
    assert options[2].dc_blocks_per_ac == [3, 3, 3]
    assert options[0].is_recommended is False
    assert options[1].is_recommended is True
    assert options[2].is_recommended is True


def test_ac_sizing_service_freezes_standard_pcs_library():
    recommendations = standard_pcs_recommendations()
    expected_pairs = [
        (pcs_count, pcs_kw)
        for pcs_count in STANDARD_PCS_COUNTS
        for pcs_kw in STANDARD_PCS_RATINGS_KW
    ]

    assert [(item.pcs_count, item.pcs_kw) for item in recommendations] == expected_pairs


def test_ac_sizing_service_builds_authoritative_dc_allocation_plan():
    allocation_plan = build_dc_allocation_plan(dc_blocks_total=12, ac_block_count=3, pcs_per_block=4)

    assert allocation_plan == [
        {"ac_block_index": 1, "dc_blocks_total": 4, "feeder_allocations": [1, 1, 1, 1]},
        {"ac_block_index": 2, "dc_blocks_total": 4, "feeder_allocations": [1, 1, 1, 1]},
        {"ac_block_index": 3, "dc_blocks_total": 4, "feeder_allocations": [1, 1, 1, 1]},
    ]


def test_ac_sizing_service_freezes_container_selection_threshold():
    assert select_ac_block_container_type(5.0, 2) == "20ft"
    assert select_ac_block_container_type(5.01, 2) == "40ft"
    assert select_ac_block_container_type(4.0, 4) == "40ft"


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
