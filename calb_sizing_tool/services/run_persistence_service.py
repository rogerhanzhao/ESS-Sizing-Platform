from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from sqlalchemy.exc import OperationalError

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot, RunInputSnapshotSchema, RunOutputSnapshotSchema


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "project"


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _persist_dc_run_with_session(
    session,
    *,
    case_model: SizingCaseInput,
    snapshot: DcPipelineRunSnapshot,
    project_code: str,
    project_name: str,
    scenario_id: str,
    case_code: str,
    case_name: str,
    version_tag: str | None,
    source_ref: str,
    actor: str | None,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    input_hash: str,
    output_hash: str,
) -> dict[str, Any]:
    case_repo = CaseRepository(session)
    run_repo = RunRepository(session)

    project = case_repo.get_or_create_project(
        project_code=project_code,
        project_name=project_name,
        version_tag=version_tag,
        source_ref=source_ref,
    )
    session.flush()
    sizing_case = case_repo.create_case_if_needed(
        project_id=project.project_id,
        case_code=case_code,
        case_name=case_name,
        stage_scope="dc",
        scenario_mode=scenario_id,
        input_json=case_model.model_dump(mode="python"),
        version_tag=version_tag,
        source_ref=source_ref,
    )
    session.flush()
    run = run_repo.create_run(
        project_id=project.project_id,
        sizing_case_id=sizing_case.sizing_case_id,
        run_type="dc_pipeline",
        status="succeeded",
        input_summary_json={
            "project_name": project_name,
            "scenario_id": scenario_id,
            "poi_power_req_mw": snapshot.stage1.poi_power_req_mw,
            "poi_energy_req_mwh": snapshot.stage1.poi_energy_req_mwh,
        },
        output_summary_json={
            "dc_power_required_mw": snapshot.stage1.dc_power_required_mw,
            "dc_energy_capacity_required_mwh": snapshot.stage1.dc_energy_capacity_required_mwh,
            "effective_c_rate": snapshot.stage3.meta.effective_c_rate,
            "guarantee_year_poi_usable_mwh": snapshot.poi_usable_energy_mwh_at_guarantee_year,
            "iterations": snapshot.iteration_count,
            "converged": snapshot.converged,
        },
        version_tag=version_tag,
        source_ref=source_ref,
    )
    session.flush()

    run_repo.add_input_snapshot(
        run.sizing_run_id,
        RunInputSnapshotSchema(
            snapshot_kind="dc_case_input",
            payload=input_payload,
            content_hash=input_hash,
        ),
        version_tag=version_tag,
        source_ref=source_ref,
    )
    run_repo.add_output_snapshot(
        run.sizing_run_id,
        RunOutputSnapshotSchema(
            snapshot_kind="dc_pipeline_output",
            payload=output_payload,
            content_hash=output_hash,
        ),
        version_tag=version_tag,
        source_ref=source_ref,
    )
    run_repo.add_audit_log(
        entity_type="sizing_run",
        entity_id=run.sizing_run_id,
        action="persist_dc_run",
        actor=actor,
        payload_json={"run_id": run.sizing_run_id, "input_hash": input_hash, "output_hash": output_hash},
        version_tag=version_tag,
        source_ref=source_ref,
    )
    session.flush()

    return {
        "run_id": run.sizing_run_id,
        "case_code": case_code,
        "project_code": project_code,
        "input_hash": input_hash,
        "output_hash": output_hash,
    }


def persist_dc_run(
    case_input: SizingCaseInput | dict[str, Any],
    snapshot: DcPipelineRunSnapshot,
    *,
    db_url: str | None = None,
    run_id: str | None = None,
    version_tag: str | None = None,
    source_ref: str = "dc_run",
    actor: str | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(case_input, dict):
        case_model = SizingCaseInput.model_validate(case_input)
    else:
        case_model = case_input

    project_name = case_model.project_name
    scenario_id = str(case_model.scenario_id)
    project_code = _slug(project_name)
    run_id = run_id or f"dc-{uuid.uuid4().hex[:12]}"
    case_code = f"{project_code}-{scenario_id}"
    case_name = f"{project_name} {scenario_id}".strip()

    case_payload = case_model.model_dump(mode="python")
    input_payload = {
        "case_input": case_payload,
        "defaults": defaults or {},
    }
    output_payload = {
        "stage1": snapshot.stage1.model_dump(mode="python"),
        "stage2": snapshot.stage2.model_dump(mode="python"),
        "stage3": snapshot.stage3.model_dump(mode="python"),
        "summary": snapshot.summary,
        "iteration_count": snapshot.iteration_count,
        "converged": snapshot.converged,
        "poi_usable_energy_mwh_at_guarantee_year": snapshot.poi_usable_energy_mwh_at_guarantee_year,
    }
    input_hash = _hash_payload(input_payload)
    output_hash = _hash_payload(output_payload)

    try:
        with session_scope(db_url) as session:
            return _persist_dc_run_with_session(
                session,
                case_model=case_model,
                snapshot=snapshot,
                project_code=project_code,
                project_name=project_name,
                scenario_id=scenario_id,
                case_code=case_code,
                case_name=case_name,
                version_tag=version_tag,
                source_ref=source_ref,
                actor=actor,
                input_payload=input_payload,
                output_payload=output_payload,
                input_hash=input_hash,
                output_hash=output_hash,
            )
    except OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise
        with session_scope(db_url) as session:
            Base.metadata.create_all(bind=session.get_bind())
        with session_scope(db_url) as session:
            return _persist_dc_run_with_session(
                session,
                case_model=case_model,
                snapshot=snapshot,
                project_code=project_code,
                project_name=project_name,
                scenario_id=scenario_id,
                case_code=case_code,
                case_name=case_name,
                version_tag=version_tag,
                source_ref=source_ref,
                actor=actor,
                input_payload=input_payload,
                output_payload=output_payload,
                input_hash=input_hash,
                output_hash=output_hash,
            )


def load_dc_run(sizing_run_id: str, *, db_url: str | None = None) -> dict[str, Any] | None:
    with session_scope(db_url) as session:
        run_repo = RunRepository(session)
        run = run_repo.get_run(sizing_run_id)
        if run is None:
            return None
        inputs = run_repo.get_input_snapshots(sizing_run_id)
        outputs = run_repo.get_output_snapshots(sizing_run_id)
        input_snapshot = inputs[-1] if inputs else None
        output_snapshot = outputs[-1] if outputs else None
        return {
            "run": run,
            "input_snapshot": input_snapshot.snapshot_json if input_snapshot else None,
            "output_snapshot": output_snapshot.snapshot_json if output_snapshot else None,
        }
