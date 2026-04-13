from __future__ import annotations

from typing import Any

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride
from calb_sizing_tool.sld.voltage_contract import resolve_mv_rmu_voltage_contract


def build_persisted_sld_project_settings(
    override: SldInputOverride,
    *,
    mv_nominal_voltage_kv: float | None = None,
) -> dict[str, Any]:
    if override.labels is None:
        raise ValueError("labels are required before saving formal SLD engineering settings.")
    if override.equipment_ratings is None:
        raise ValueError("equipment_ratings are required before saving formal SLD engineering settings.")
    if not str(override.transformer_vector_group or "").strip():
        raise ValueError("transformer_vector_group is required before saving formal SLD engineering settings.")
    if override.transformer_uk_percent is None or float(override.transformer_uk_percent) <= 0:
        raise ValueError("transformer_uk_percent must be > 0 before saving formal SLD engineering settings.")
    if override.dc_block_voltage_v is None or float(override.dc_block_voltage_v) <= 0:
        raise ValueError("dc_block_voltage_v must be > 0 before saving formal SLD engineering settings.")

    equipment_payload = override.equipment_ratings.model_dump(mode="python")
    mv_value = float(mv_nominal_voltage_kv) if mv_nominal_voltage_kv is not None else None
    if mv_value is not None and mv_value > 0:
        contract = resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=mv_value)
        rmu_payload = dict(equipment_payload.get("rmu") or {})
        rmu_payload["rated_kv"] = float(contract.rmu_rated_voltage_kv)
        equipment_payload["rmu"] = rmu_payload

    return {
        "transformer": {
            "vector_group": str(override.transformer_vector_group).strip(),
            "uk_percent": float(override.transformer_uk_percent),
        },
        "dc_block_voltage_v": float(override.dc_block_voltage_v),
        "labels": override.labels.model_dump(mode="python"),
        "equipment_ratings": equipment_payload,
    }


def load_case_sld_project_settings(sizing_case_id: str | None, *, db_url: str | None = None) -> dict[str, Any]:
    case_id = str(sizing_case_id or "").strip()
    if not case_id:
        return {}
    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        return repo.get_case_project_settings(case_id)


def load_run_sld_project_settings(run_id: str | None, *, db_url: str | None = None) -> dict[str, Any]:
    resolved_run_id = str(run_id or "").strip()
    if not resolved_run_id:
        return {}
    with session_scope(db_url) as session:
        run_repo = RunRepository(session)
        bundle = run_repo.get_run_bundle(resolved_run_id)
        if bundle is None:
            return {}
        case_row = bundle.get("case")
        sizing_case_id = getattr(case_row, "sizing_case_id", None)
        if not sizing_case_id:
            return {}
        repo = CaseRepository(session)
        return repo.get_case_project_settings(sizing_case_id)


def save_case_sld_project_settings(
    sizing_case_id: str,
    project_settings: dict[str, Any],
    *,
    actor: str | None = None,
    db_url: str | None = None,
    source_ref: str = "sld_engineering_settings_service",
) -> dict[str, Any]:
    case_id = str(sizing_case_id or "").strip()
    if not case_id:
        raise ValueError("sizing_case_id is required to save formal SLD engineering settings.")

    with session_scope(db_url) as session:
        case_repo = CaseRepository(session)
        run_repo = RunRepository(session)
        case_row = case_repo.save_case_project_settings(case_id, project_settings)
        if case_row is None:
            raise ValueError(f"Sizing case not found: {case_id}")
        run_repo.add_audit_log(
            entity_type="sizing_case",
            entity_id=case_id,
            action="save_sld_project_settings",
            actor=actor,
            payload_json={"project_settings": project_settings},
            source_ref=source_ref,
        )
        session.flush()
        return {
            "sizing_case_id": case_row.sizing_case_id,
            "project_settings": dict(project_settings or {}),
        }
