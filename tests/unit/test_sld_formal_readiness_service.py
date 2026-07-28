from __future__ import annotations

from pathlib import Path

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.services.sld_formal_readiness_service import assess_sld_formal_readiness
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from tests.integration.sld_regression_support import build_case_inputs, load_case_definition
from tests.unit.test_sld_input_contract import _build_run_bundle


def _professional_project_settings() -> dict:
    return {
        "labels": {
            "to_switchgear": "To Switchgear",
            "to_other_rmu": "To Other RMU",
        },
        "transformer": {
            "vector_group": "Dyn11yn11",
            "uk_percent": 7.0,
        },
        "dc_block_voltage_v": 1500.0,
        "equipment_ratings": {
            "rmu": {
                "rated_kv": 33.0,
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
                "mv_cable_spec": "MV-3x1C-240mm2",
                "lv_cable_spec": "LV-3P+PE-630mm2",
                "dc_cable_spec": "DC-1x240mm2",
            },
            "dc_fuse": {
                "fuse_spec": "DC isolator/fuse",
            },
            "transformer_tap_range": "+/-2x2.5%",
            "transformer_cooling": "ONAN",
            "battery_cell_spec": "LFP 3.2V/314Ah",
        },
    }


def test_formal_readiness_flags_renderer_fixture_as_not_formal(sample_excel_path):
    case_dir = Path(__file__).resolve().parents[1] / "fixtures" / "sld_cases" / "case01_container_only_group1"
    run_bundle, ac_snapshot, options, project_settings = build_case_inputs(load_case_definition(case_dir))
    project_settings = dict(project_settings)
    project_settings["transformer"] = {
        **dict(project_settings.get("transformer") or {}),
        "vector_group": "Dyn11yn11",
    }
    options = options.model_copy(update={"renderer_mode": "engineering_v2"})
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        validation_mode="strict",
    )

    report = assess_sld_formal_readiness(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        canonical_input=canonical,
        options=options,
        project_settings=project_settings,
    )

    issue_ids = {issue.issue_id for issue in report.issues}
    assert report.ready is False
    assert "missing_ac_snapshot_provenance" in issue_ids
    assert "dc_ac_block_total_mismatch" in issue_ids
    assert "sld_dc_energy_representation_mismatch" in issue_ids
    assert "missing_professional_field:mv_cable_spec" in issue_ids
    assert "missing_professional_field:battery_cell_spec" in issue_ids


def test_formal_readiness_passes_consistent_authoritative_inputs(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    project_settings = _professional_project_settings()
    dc_total_blocks = int(run_bundle.snapshot.stage2.container_count + run_bundle.snapshot.stage2.cabinet_count)
    base = dc_total_blocks // 4
    remainder = dc_total_blocks % 4
    feeder_allocations = [base + (1 if index < remainder else 0) for index in range(4)]
    assert sum(feeder_allocations) == dc_total_blocks
    ac_snapshot = AcSnapshot(
        inputs={"grid_kv": 33.0, "lv_voltage_v": 690.0},
        output={
            "source_run_id": run_bundle.run_id,
            "num_blocks": 1,
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
            "block_size_mw": 5.0,
            "transformer_mva": 6.0,
            "dc_allocation_plan": [
                {
                    "ac_block_index": 1,
                    "dc_blocks_total": dc_total_blocks,
                    "feeder_allocations": feeder_allocations,
                }
            ],
            "dc_blocks_total": dc_total_blocks,
            "dc_total_mwh": run_bundle.snapshot.stage2.dc_nameplate_bol_mwh,
            "mv_voltage_kv": 33.0,
            "lv_voltage_v": 690.0,
        },
        results={},
    )
    options = SldRenderOptions(group_index=1, renderer_mode="engineering_v2")
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        validation_mode="strict",
    )

    report = assess_sld_formal_readiness(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        canonical_input=canonical,
        options=options,
        project_settings=project_settings,
    )

    assert report.ready is True
    assert report.error_count == 0


def _consistent_ac_snapshot(run_bundle, *, dc_total: int, feeder_allocations, extra=None):
    output = {
        "source_run_id": run_bundle.run_id,
        "num_blocks": 1,
        "pcs_per_block": 4,
        "pcs_kw": 1250.0,
        "block_size_mw": 5.0,
        "transformer_mva": 6.0,
        "dc_allocation_plan": [
            {
                "ac_block_index": 1,
                "dc_blocks_total": dc_total,
                "feeder_allocations": feeder_allocations,
            }
        ],
        "dc_blocks_total": dc_total,
        "dc_total_mwh": run_bundle.snapshot.stage2.dc_nameplate_bol_mwh,
        "mv_voltage_kv": 33.0,
        "lv_voltage_v": 690.0,
    }
    output.update(extra or {})
    return AcSnapshot(inputs={"grid_kv": 33.0, "lv_voltage_v": 690.0}, output=output, results={})


def test_representative_head_fleet_is_never_formal(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    project_settings = _professional_project_settings()
    dc_total = int(run_bundle.snapshot.stage2.container_count + run_bundle.snapshot.stage2.cabinet_count)
    base, remainder = dc_total // 4, dc_total % 4
    feeders = [base + (1 if i < remainder else 0) for i in range(4)]
    # Otherwise fully consistent + professional inputs (would be READY) — the
    # representative-of-mixed marker alone must keep it non-official.
    ac_snapshot = _consistent_ac_snapshot(
        run_bundle, dc_total=dc_total, feeder_allocations=feeders,
        extra={"sld_representative_of_mixed": True},
    )
    options = SldRenderOptions(group_index=1, renderer_mode="engineering_v2")
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle, ac_snapshot=ac_snapshot, options=options,
        project_settings=project_settings, validation_mode="strict",
    )
    report = assess_sld_formal_readiness(
        run_bundle=run_bundle, ac_snapshot=ac_snapshot, canonical_input=canonical,
        options=options, project_settings=project_settings,
    )
    issue_ids = {issue.issue_id for issue in report.issues}
    assert report.ready is False
    assert "representative_head_fleet_only" in issue_ids


def test_representative_head_fleet_suppresses_incidental_total_mismatch(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    project_settings = _professional_project_settings()
    dc_total = int(run_bundle.snapshot.stage2.container_count + run_bundle.snapshot.stage2.cabinet_count)
    # Head-only fleet carries fewer DC Blocks than the whole DC run (a tail was
    # dropped). That mismatch is expected-by-design and must NOT surface as an
    # error; only the explicit representative blocker should.
    head_total = max(4, dc_total - 4)
    base, remainder = head_total // 4, head_total % 4
    feeders = [base + (1 if i < remainder else 0) for i in range(4)]
    ac_snapshot = _consistent_ac_snapshot(
        run_bundle, dc_total=head_total, feeder_allocations=feeders,
        extra={"sld_representative_of_mixed": True},
    )
    options = SldRenderOptions(group_index=1, renderer_mode="engineering_v2")
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle, ac_snapshot=ac_snapshot, options=options,
        project_settings=project_settings, validation_mode="strict",
    )
    report = assess_sld_formal_readiness(
        run_bundle=run_bundle, ac_snapshot=ac_snapshot, canonical_input=canonical,
        options=options, project_settings=project_settings,
    )
    issue_ids = {issue.issue_id for issue in report.issues}
    assert report.ready is False
    assert "representative_head_fleet_only" in issue_ids
    assert "dc_ac_block_total_mismatch" not in issue_ids
    assert "sld_dc_energy_representation_mismatch" not in issue_ids


def test_missing_transformer_vector_group_is_never_formal(sample_excel_path):
    # Strict mode already *requires* a vector group at build time, so the only
    # way to reach a drawing without one is draft mode, where the canonical input
    # resolves it to "TBD". That TBD winding symbol must keep the SLD non-formal
    # with an explicit vector-group reason (not only the generic draft reason).
    run_bundle = _build_run_bundle(sample_excel_path)
    project_settings = _professional_project_settings()
    project_settings["transformer"] = {"uk_percent": 7.0}  # drop the vector_group
    dc_total = int(run_bundle.snapshot.stage2.container_count + run_bundle.snapshot.stage2.cabinet_count)
    base, remainder = dc_total // 4, dc_total % 4
    feeders = [base + (1 if i < remainder else 0) for i in range(4)]
    ac_snapshot = _consistent_ac_snapshot(run_bundle, dc_total=dc_total, feeder_allocations=feeders)
    options = SldRenderOptions(group_index=1, renderer_mode="engineering_v2", override_mode=True)
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle, ac_snapshot=ac_snapshot, options=options,
        project_settings=project_settings, validation_mode="draft",
    )
    assert canonical.transformer_vector_group == "TBD"
    report = assess_sld_formal_readiness(
        run_bundle=run_bundle, ac_snapshot=ac_snapshot, canonical_input=canonical,
        options=options, project_settings=project_settings,
    )
    issue_ids = {issue.issue_id for issue in report.issues}
    assert report.ready is False
    assert "transformer_vector_group_unconfirmed" in issue_ids
