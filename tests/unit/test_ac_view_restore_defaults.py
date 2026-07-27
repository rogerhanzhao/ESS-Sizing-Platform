from __future__ import annotations

from calb_sizing_tool.services.ac_sizing_service import (
    build_simplified_ac_block_models,
    generate_ac_sizing_options,
)
from calb_sizing_tool.ui.ac_view import (
    _resolve_authoritative_poi_requirements,
    _saved_confirmed_transformer_topology,
    _saved_ac_block_model_choice_index,
    _saved_pcs_choice_index,
)


def test_poi_requirements_prefer_stage13_over_legacy_dc_summary_mwh():
    power, energy = _resolve_authoritative_poi_requirements(
        {
            "poi_power_req_mw": 200.0,
            "poi_energy_req_mwh": 800.0,
        },
        {
            "target_mw": 200.0,
            # A legacy record may carry BOL DC energy here; it must not override
            # the Stage 1/3 POI energy requirement used by AC sizing.
            "mwh": 1013.232,
        },
    )

    assert power == 200.0
    assert energy == 800.0


def test_saved_pcs_choice_index_restores_persisted_pcs_configuration():
    options = generate_ac_sizing_options(
        dc_blocks_total=188,
        target_mw=400,
        target_mwh=800,
        dc_block_mwh=800 / 188,
    )
    ratio_12 = next(option for option in options if option.ratio == "1:2")

    index = _saved_pcs_choice_index(
        {"pcs_per_block": 2, "pcs_kw": 2500},
        ratio_12.pcs_recommendations,
    )

    restored = ratio_12.pcs_recommendations[index]
    assert restored.pcs_count == 2
    assert restored.pcs_kw == 2500


def test_saved_pcs_choice_index_falls_back_to_first_option_when_unmatched():
    options = generate_ac_sizing_options(
        dc_blocks_total=4,
        target_mw=10,
        target_mwh=40,
        dc_block_mwh=5,
    )
    ratio_12 = next(option for option in options if option.ratio == "1:2")

    assert _saved_pcs_choice_index({"pcs_per_block": 3, "pcs_kw": 3333}, ratio_12.pcs_recommendations) == 0


def test_legacy_topology_is_not_restored_without_explicit_confirmation():
    # A previous UI version silently selected three windings for PCS > 2.  The
    # stored value alone is not evidence of an actual transformer design.
    assert _saved_confirmed_transformer_topology({"transformer_topology": "three_winding"}) is None

    assert _saved_confirmed_transformer_topology(
        {
            "transformer_topology": "three_winding",
            "transformer_topology_confirmation": "confirmed_by_user",
        }
    ) == "three_winding"


def test_saved_ac_block_model_choice_index_prefers_persisted_model_code():
    options = generate_ac_sizing_options(
        dc_blocks_total=188,
        target_mw=400,
        target_mwh=800,
        dc_block_mwh=800 / 188,
    )
    ratio_12 = next(option for option in options if option.ratio == "1:2")
    models = build_simplified_ac_block_models(ratio_12.pcs_recommendations)
    target = next(model for model in models if model.model_code == "ACBLK-4X1250KW-20FT")

    index = _saved_ac_block_model_choice_index(
        {
            "ac_block_model_code": target.model_code,
            "pcs_per_block": 2,
            "pcs_kw": 2500,
        },
        models,
        custom_index=len(models),
    )

    assert models[index].model_code == "ACBLK-4X1250KW-20FT"


def test_saved_ac_block_model_choice_index_migrates_legacy_wrong_container_code():
    options = generate_ac_sizing_options(
        dc_blocks_total=188,
        target_mw=400,
        target_mwh=800,
        dc_block_mwh=800 / 188,
    )
    ratio_12 = next(option for option in options if option.ratio == "1:2")
    models = build_simplified_ac_block_models(ratio_12.pcs_recommendations)

    index = _saved_ac_block_model_choice_index(
        {
            "ac_block_model_code": "ACBLK-4X1250KW-40FT",
            "pcs_per_block": 4,
            "pcs_kw": 1250,
        },
        models,
        custom_index=len(models),
    )

    assert models[index].model_code == "ACBLK-4X1250KW-20FT"


def test_saved_ac_block_model_choice_index_restores_legacy_pcs_signature():
    options = generate_ac_sizing_options(
        dc_blocks_total=188,
        target_mw=400,
        target_mwh=800,
        dc_block_mwh=800 / 188,
    )
    ratio_12 = next(option for option in options if option.ratio == "1:2")
    models = build_simplified_ac_block_models(ratio_12.pcs_recommendations)

    index = _saved_ac_block_model_choice_index(
        {"pcs_per_block": 2, "pcs_kw": 2500},
        models,
        custom_index=len(models),
    )

    restored = models[index]
    assert restored.model_code == "ACBLK-2X2500KW-20FT"
    assert restored.block_size_mw == 5.0


def test_saved_ac_block_model_choice_index_uses_custom_index_for_unmatched_saved_values():
    options = generate_ac_sizing_options(
        dc_blocks_total=4,
        target_mw=10,
        target_mwh=40,
        dc_block_mwh=5,
    )
    ratio_12 = next(option for option in options if option.ratio == "1:2")
    models = build_simplified_ac_block_models(ratio_12.pcs_recommendations)

    assert (
        _saved_ac_block_model_choice_index(
            {"pcs_per_block": 3, "pcs_kw": 3333},
            models,
            custom_index=len(models),
        )
        == len(models)
    )
