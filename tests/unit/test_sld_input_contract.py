from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.run_snapshot import RunInputSnapshotSchema
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.sld_input_builder import SldInputValidationError, build_sld_canonical_input
from calb_sizing_tool.services.stage1_service import run_stage1 as service_run_stage1


def _to_float(value, fallback):
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except Exception:
        return float(fallback)


def _build_run_bundle(sample_excel_path) -> DcRunBundle:
    bundle = load_dc_excel_bundle_from_path(sample_excel_path)
    defaults = dict(bundle.defaults)
    stage1_inputs = {
        "project_name": "SLD Canonical Contract",
        "poi_power_req_mw": 50.0,
        "poi_energy_req_mwh": 200.0,
        "project_life_years": 20,
        "cycles_per_year": 365,
        "poi_guarantee_year": 0,
        "sc_time_months": 3,
        "dod_pct": _to_float(defaults.get("dod_pct", 95.0), 95.0),
        "dc_round_trip_efficiency_pct": _to_float(defaults.get("dc_round_trip_efficiency_pct", 94.0), 94.0),
        "eff_dc_cables": _to_float(defaults.get("eff_dc_cables", 99.5), 99.5),
        "eff_pcs": _to_float(defaults.get("eff_pcs", 98.5), 98.5),
        "eff_mvt": _to_float(defaults.get("eff_mvt", 99.5), 99.5),
        "eff_ac_cables_sw_rmu": _to_float(defaults.get("eff_ac_cables_sw_rmu", 99.2), 99.2),
        "eff_hvt_others": _to_float(defaults.get("eff_hvt_others", 100.0), 100.0),
        "rte_curve_adjust_pp": _to_float(defaults.get("rte_curve_adjust_pp", 0.0), 0.0),
        "rte_monotonic_enforce": defaults.get("rte_monotonic_enforce", True),
    }
    stage1 = service_run_stage1(stage1_inputs, defaults)
    snapshot = size_with_guarantee(stage1, "container_only", bundle)
    case_input = {
        "project_name": stage1_inputs["project_name"],
        "scenario_id": "container_only",
        "poi_power_req_mw": stage1_inputs["poi_power_req_mw"],
        "poi_energy_req_mwh": stage1_inputs["poi_energy_req_mwh"],
        "poi_nominal_voltage_kv": 33.0,
        "poi_frequency_hz": 50.0,
    }
    return DcRunBundle(
        run_id="dc-test-contract",
        project_name=stage1_inputs["project_name"],
        scenario_mode="container_only",
        input_snapshot=RunInputSnapshotSchema(
            snapshot_kind="dc_case_input",
            payload={"case_input": case_input, "defaults": defaults},
        ),
        snapshot=snapshot,
    )


def _make_ac_snapshot() -> AcSnapshot:
    return AcSnapshot(
        inputs={"grid_kv": 33.0, "lv_voltage_v": 690.0},
        output={
            "num_blocks": 1,
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
            "transformer_mva": 6.0,
            "dc_allocation_plan": [
                {"ac_block_index": 1, "dc_blocks_total": 4, "feeder_allocations": [1, 1, 1, 1]}
            ],
        },
        results={},
    )


def test_builder_outputs_valid_canonical_input(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["dc_block_voltage_v"] = 1500.0

    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=_make_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )

    assert canonical.run_id == run_bundle.run_id
    assert canonical.project_name == "SLD Canonical Contract"
    assert canonical.group_index == 1
    assert canonical.pcs_count == 4
    assert canonical.pcs_rating_kw_list == [1250.0, 1250.0, 1250.0, 1250.0]
    assert canonical.dc_blocks_per_feeder == [1, 1, 1, 1]
    assert canonical.validation_mode == "strict"
    assert canonical.override_mode is True


def test_builder_strict_mode_rejects_missing_critical_fields(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)

    with pytest.raises(SldInputValidationError) as exc_info:
        build_sld_canonical_input(
            run_bundle=run_bundle,
            ac_snapshot=_make_ac_snapshot(),
            options=SldRenderOptions(group_index=1),
            validation_mode="strict",
        )

    message = str(exc_info.value)
    assert "transformer_vector_group" in message
    assert "transformer_uk_percent" in message
    assert "dc_block_voltage_v" in message
    assert "equipment_ratings" in message


def test_builder_requires_explicit_override_mode(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["dc_block_voltage_v"] = 1500.0

    with pytest.raises(SldInputValidationError) as exc_info:
        build_sld_canonical_input(
            run_bundle=run_bundle,
            ac_snapshot=_make_ac_snapshot(),
            options=SldRenderOptions(
                group_index=1,
                override_mode=False,
                overrides=SldInputOverride.model_validate(override_payload),
            ),
            validation_mode="strict",
        )

    assert "override_mode is disabled" in str(exc_info.value)
