from __future__ import annotations

import pytest
from pydantic import ValidationError

from calb_sizing_tool.schemas.sld_render_input import SldCanonicalInput, legacy_sld_override_preset


def _base_payload() -> dict:
    preset = legacy_sld_override_preset()
    return {
        "run_id": "dc-test",
        "project_name": "Validation Test",
        "scenario_id": "container_only",
        "group_index": 1,
        "ac_blocks_total": 1,
        "mv_voltage_kv": 33.0,
        "lv_voltage_v_ll": 690.0,
        "transformer_rating_mva": 6.0,
        "transformer_vector_group": preset["transformer_vector_group"],
        "transformer_uk_percent": preset["transformer_uk_percent"],
        "pcs_count": 4,
        "pcs_rating_kw_list": [1250.0, 1250.0, 1250.0, 1250.0],
        "dc_block_energy_mwh": 5.0,
        "dc_blocks_total_in_group": 4,
        "dc_blocks_per_feeder": [1, 1, 1, 1],
        "dc_block_voltage_v": 1500.0,
        "equipment_ratings": preset["equipment_ratings"],
        "labels": preset["labels"],
        "validation_mode": "strict",
    }


def test_pcs_count_must_match_rating_list_length():
    payload = _base_payload()
    payload["pcs_rating_kw_list"] = [1250.0, 1250.0]

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "pcs_count must match pcs_rating_kw_list length" in str(exc_info.value)


def test_dc_blocks_per_feeder_length_must_match_pcs_count():
    payload = _base_payload()
    payload["dc_blocks_per_feeder"] = [2, 2]

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "dc_blocks_per_feeder length must match pcs_count" in str(exc_info.value)


def test_dc_block_total_must_match_feeder_sum():
    payload = _base_payload()
    payload["dc_blocks_total_in_group"] = 5

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "dc_blocks_total_in_group must equal sum(dc_blocks_per_feeder)" in str(exc_info.value)


def test_transformer_mv_lv_values_must_be_positive():
    payload = _base_payload()
    payload["transformer_rating_mva"] = 0.0

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "value must be > 0" in str(exc_info.value)
