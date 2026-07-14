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


def test_lv_busbar_current_must_cover_transformer_lv_current():
    payload = _base_payload()
    payload["equipment_ratings"]["lv_busbar"]["rated_a"] = 2500.0

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "lv_busbar.rated_a is below the required per-winding LV current" in str(exc_info.value)


def test_lv_winding_count_defaults_to_one():
    obj = SldCanonicalInput.model_validate(_base_payload())
    assert obj.lv_winding_count == 1


def test_split_winding_halves_required_lv_current():
    # base required single-busbar current is ~5020 A (6 MVA / 690 V).
    payload = _base_payload()
    payload["equipment_ratings"]["lv_busbar"]["rated_a"] = 2600.0

    # single LV winding: 2600 A busbar is inadequate (needs ~5020 A).
    payload["lv_winding_count"] = 1
    with pytest.raises(ValidationError):
        SldCanonicalInput.model_validate(payload)

    # split (dual) LV winding: current halves to ~2510 A/section -> 2600 A passes.
    payload["lv_winding_count"] = 2
    obj = SldCanonicalInput.model_validate(payload)
    assert obj.lv_winding_count == 2


def test_lv_winding_count_must_be_positive():
    payload = _base_payload()
    payload["lv_winding_count"] = 0
    with pytest.raises(ValidationError):
        SldCanonicalInput.model_validate(payload)


def test_strict_rejects_transformer_below_pcs_total():
    # 4 x 1250 kW = 5.0 MVA floor; a 4.0 MVA transformer is undersized.
    payload = _base_payload()
    payload["transformer_rating_mva"] = 4.0

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "below the PCS total" in str(exc_info.value)


def test_strict_rejects_rmu_below_transformer_mv_current():
    # 6 MVA at 33 kV -> ~105 A; a 100 A RMU cannot carry it.
    payload = _base_payload()
    payload["equipment_ratings"]["rmu"]["rated_a"] = 100.0

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "below the transformer MV current" in str(exc_info.value)


def test_draft_mode_downgrades_electrical_gates_to_warnings():
    payload = _base_payload()
    payload["validation_mode"] = "draft"
    payload["transformer_rating_mva"] = 4.0
    # 4 MVA at 33 kV -> ~70 A MV current; 50 A RMU still undersized.
    payload["equipment_ratings"]["rmu"]["rated_a"] = 50.0
    obj = SldCanonicalInput.model_validate(payload)

    assert any("below the PCS total" in w for w in obj.draft_warnings)
    assert any("below the transformer MV current" in w for w in obj.draft_warnings)


def test_strict_mode_rejects_tbd_dc_fuse_spec():
    payload = _base_payload()
    payload["equipment_ratings"]["dc_fuse"]["fuse_spec"] = "TBD"

    with pytest.raises(ValidationError) as exc_info:
        SldCanonicalInput.model_validate(payload)

    assert "dc_fuse.fuse_spec must be explicit in strict SLD mode" in str(exc_info.value)
