from __future__ import annotations

from copy import deepcopy
import pytest

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.run_persistence_service import _hash_payload, persist_dc_run
from calb_sizing_tool.services.run_restore_service import RunRestoreError, load_dc_run_bundle
from calb_sizing_tool.services.stage1_service import run_stage1


@pytest.fixture(scope="module")
def dc_basis(sample_excel_path):
    baseline = load_dc_excel_bundle_from_path(sample_excel_path)
    case = SizingCaseInput(
        project_name="DC integrity regression",
        poi_power_req_mw=20.0,
        poi_energy_req_mwh=80.0,
    )
    stage1 = run_stage1(case.model_dump(mode="python"), baseline.defaults)
    return case, baseline, stage1


def _saved_run(dc_basis, tmp_path, *, mode="container_only"):
    case, baseline, stage1 = dc_basis
    case = SizingCaseInput.model_validate({**case.model_dump(mode="python"), "scenario_id": mode})
    snapshot = size_with_guarantee(stage1, mode, baseline)
    db_url = f"sqlite:///{(tmp_path / 'integrity.sqlite').as_posix()}"
    saved = persist_dc_run(case, snapshot, db_url=db_url, defaults=baseline.defaults)
    return db_url, saved["run_id"], snapshot, saved


@pytest.mark.parametrize("mode", ["container_only", "cabinet_only", "hybrid"])
def test_original_modes_round_trip_with_payload_hashes(dc_basis, tmp_path, mode):
    db_url, run_id, expected, saved = _saved_run(dc_basis, tmp_path, mode=mode)
    restored = load_dc_run_bundle(run_id, db_url=db_url)
    assert restored.snapshot == expected
    assert restored.input_snapshot.content_hash == saved["input_hash"]
    assert restored.output_snapshot.content_hash == saved["output_hash"]
    # Hashing the database JSON agrees with the original pre-JSON payload,
    # including the string-enum case input and all nested Stage 2 BOM fields.
    assert _hash_payload(restored.input_snapshot.payload) == saved["input_hash"]
    assert _hash_payload(restored.output_snapshot.payload) == saved["output_hash"]


@pytest.mark.parametrize("change", ["same_energy_product", "same_energy_count", "input"])
def test_changed_saved_bom_or_input_is_rejected(dc_basis, tmp_path, change):
    db_url, run_id, _, saved = _saved_run(dc_basis, tmp_path)
    with session_scope(db_url) as session:
        repo = RunRepository(session)
        if change == "input":
            row = repo.get_latest_input_snapshot_by_kind(run_id, "dc_case_input")
            payload = deepcopy(row.snapshot_json)
            payload["case_input"]["poi_power_req_mw"] += 1.0
            expected_hash = saved["input_hash"]
        else:
            row = repo.get_latest_output_snapshot_by_kind(run_id, "dc_pipeline_output")
            payload = deepcopy(row.snapshot_json)
            before_energy = payload["stage2"]["dc_nameplate_bol_mwh"]
            item = payload["stage2"]["block_config_items"][0]
            if change == "same_energy_product":
                item["block_code"] += "-OTHER-PRODUCT"
            else:
                item["count"] *= 2
                item["unit_capacity_mwh"] /= 2
            assert payload["stage2"]["dc_nameplate_bol_mwh"] == before_energy
            expected_hash = saved["output_hash"]
        assert _hash_payload(payload) != expected_hash
        row.snapshot_json = payload

    with pytest.raises(RunRestoreError, match="changed since they were saved"):
        load_dc_run_bundle(run_id, db_url=db_url)


@pytest.mark.parametrize("mode", ["container_only", "cabinet_only", "hybrid"])
def test_legacy_missing_hashes_remain_restorable(dc_basis, tmp_path, mode):
    db_url, run_id, expected, _ = _saved_run(dc_basis, tmp_path, mode=mode)
    with session_scope(db_url) as session:
        repo = RunRepository(session)
        repo.get_latest_input_snapshot_by_kind(run_id, "dc_case_input").content_hash = None
        repo.get_latest_output_snapshot_by_kind(run_id, "dc_pipeline_output").content_hash = None
    assert load_dc_run_bundle(run_id, db_url=db_url).snapshot == expected


@pytest.mark.parametrize("mode", ["composition_comparison_only", "unrecognized_planning_mode"])
def test_comparison_or_unknown_mode_is_rejected_before_any_database_write(dc_basis, tmp_path, mode):
    case, baseline, stage1 = dc_basis
    snapshot = size_with_guarantee(stage1, "container_only", baseline)
    comparison = snapshot.model_copy(
        update={"stage2": snapshot.stage2.model_copy(update={"mode": mode})}
    )
    database = tmp_path / "must-not-be-created.sqlite"
    with pytest.raises(ValueError, match="Comparison-only results cannot be adopted"):
        persist_dc_run(case, comparison, db_url=f"sqlite:///{database.as_posix()}")
    assert not database.exists()


@pytest.mark.parametrize("with_hash", [True, False])
def test_comparison_mode_cannot_be_restored_even_with_valid_or_missing_hash(dc_basis, tmp_path, with_hash):
    db_url, run_id, _, _ = _saved_run(dc_basis, tmp_path)
    with session_scope(db_url) as session:
        row = RunRepository(session).get_latest_output_snapshot_by_kind(run_id, "dc_pipeline_output")
        payload = deepcopy(row.snapshot_json)
        payload["stage2"]["mode"] = "composition_comparison_only"
        row.snapshot_json = payload
        row.content_hash = _hash_payload(payload) if with_hash else None
    with pytest.raises(RunRestoreError, match="Comparison-only results cannot be adopted"):
        load_dc_run_bundle(run_id, db_url=db_url)


def test_non_dc_input_identity_hash_is_not_reinterpreted_as_payload_hash(dc_basis, tmp_path):
    db_url, run_id, expected, _ = _saved_run(dc_basis, tmp_path)
    with session_scope(db_url) as session:
        row = RunRepository(session).get_latest_input_snapshot_by_kind(run_id, "dc_case_input")
        row.snapshot_kind = "ac_case_input"
        row.snapshot_json = {"grid_kv": 33.0}
        row.content_hash = "alternative-identity-not-a-payload-hash"
    restored = load_dc_run_bundle(run_id, db_url=db_url)
    assert restored.snapshot == expected
    assert restored.input_snapshot.snapshot_kind == "ac_case_input"


def test_later_ac_runtime_snapshot_does_not_replace_dc_hash_source(dc_basis, tmp_path):
    from calb_sizing_tool.services.sld_data_source_service import persist_ac_runtime_snapshot

    db_url, run_id, expected, _ = _saved_run(dc_basis, tmp_path)
    persist_ac_runtime_snapshot(
        run_id=run_id,
        db_url=db_url,
        ac_inputs={"grid_kv": 33.0},
        ac_output={"source_run_id": run_id, "num_blocks": 2, "pcs_per_block": 4, "pcs_kw": 1250.0},
    )
    restored = load_dc_run_bundle(run_id, db_url=db_url)
    assert restored.snapshot == expected
    assert restored.input_snapshot.snapshot_kind == "dc_case_input"
    assert restored.output_snapshot.snapshot_kind == "dc_pipeline_output"
