from __future__ import annotations

import pytest

from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.services.sld_authoritative_builder import build_sld_authoritative_result
from calb_sizing_tool.services.sld_input_builder import SldInputValidationError
from tests.unit.test_sld_input_contract import _build_run_bundle, _make_ac_snapshot


def _project_settings() -> dict:
    return {
        "labels": {
            "to_switchgear": "To Switchgear",
            "to_other_rmu": "To Other RMU",
        },
        "transformer": {
            "vector_group": "Dyn11",
            "uk_percent": 7.0,
        },
        "dc_block_voltage_v": 1500.0,
        "equipment_ratings": {
            "rmu": {
                "rated_kv": 24.0,
                "rated_a": 630.0,
                "short_circuit_ka_3s": 25.0,
                "ct_ratio": "200/1",
                "ct_class": "5P20",
                "ct_va": 10.0,
            },
            "lv_busbar": {
                "rated_a": 6300.0,
                "short_circuit_ka": 25.0,
            },
            "cables": {
                "mv_cable_spec": "TBD",
                "lv_cable_spec": "TBD",
                "dc_cable_spec": "TBD",
            },
            "dc_fuse": {
                "fuse_spec": "DC isolator/fuse",
            },
            "transformer_tap_range": "+/-2x2.5%",
            "transformer_cooling": "ONAN",
        },
    }


def test_sld_authoritative_builder_outputs_single_formal_path(sample_excel_path):
    result = build_sld_authoritative_result(
        run_bundle=_build_run_bundle(sample_excel_path),
        ac_snapshot=_make_ac_snapshot(),
        options=SldRenderOptions(group_index=1, theme="dark", compact_mode=False, draw_summary=False),
        project_settings=_project_settings(),
        validation_mode="strict",
    )

    canonical = result.canonical_input
    topology = result.topology

    assert canonical.validation_mode == "strict"
    assert canonical.override_mode is False
    assert canonical.pcs_count == 4
    assert canonical.dc_blocks_per_feeder == [1, 1, 1, 1]
    assert topology.summary.group_index == canonical.group_index
    assert topology.summary.feeder_count == canonical.pcs_count
    assert topology.summary.dc_blocks_per_feeder == canonical.dc_blocks_per_feeder
    assert topology.labels.to_switchgear == canonical.labels.to_switchgear
    assert topology.equipment_ratings.rmu.rated_kv == canonical.equipment_ratings.rmu.rated_kv


def test_sld_authoritative_builder_rejects_missing_project_engineering_inputs(sample_excel_path):
    with pytest.raises(SldInputValidationError) as exc_info:
        build_sld_authoritative_result(
            run_bundle=_build_run_bundle(sample_excel_path),
            ac_snapshot=_make_ac_snapshot(),
            options=SldRenderOptions(group_index=1),
            project_settings={},
            validation_mode="strict",
        )

    message = str(exc_info.value)
    assert "transformer_vector_group" in message
    assert "transformer_uk_percent" in message
    assert "dc_block_voltage_v" in message
    assert "equipment_ratings" in message


def test_sld_authoritative_builder_rejects_missing_authoritative_ac_allocation(sample_excel_path):
    ac_snapshot = _make_ac_snapshot(
        output_overrides={
            "dc_allocation_plan": None,
            "dc_blocks_total_by_block": [4],
            "dc_blocks_per_feeder_by_block": [[1, 1, 1, 1]],
        }
    )

    with pytest.raises(SldInputValidationError) as exc_info:
        build_sld_authoritative_result(
            run_bundle=_build_run_bundle(sample_excel_path),
            ac_snapshot=ac_snapshot,
            options=SldRenderOptions(group_index=1),
            project_settings=_project_settings(),
            validation_mode="strict",
        )

    assert "dc_allocation_plan is required" in str(exc_info.value)
