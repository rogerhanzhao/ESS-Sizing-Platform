from __future__ import annotations

from typing import Any

from calb_sizing_tool.infra.db.models import AuditLog, SldProjectSettings
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
    # Uk% is optional: impedance is not a sizing input and is a grid-filing value
    # the owner often lacks. When absent the SLD falls back to a standard typical
    # by voltage class, so saving must not require it.
    if override.dc_block_voltage_v is None or float(override.dc_block_voltage_v) <= 0:
        raise ValueError("dc_block_voltage_v must be > 0 before saving formal SLD engineering settings.")

    equipment_payload = override.equipment_ratings.model_dump(mode="python")
    mv_value = float(mv_nominal_voltage_kv) if mv_nominal_voltage_kv is not None else None
    if mv_value is not None and mv_value > 0:
        contract = resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=mv_value)
        rmu_payload = dict(equipment_payload.get("rmu") or {})
        rmu_payload["rated_kv"] = float(contract.rmu_rated_voltage_kv)
        equipment_payload["rmu"] = rmu_payload

    transformer_settings: dict[str, Any] = {
        "vector_group": str(override.transformer_vector_group).strip(),
    }
    if override.transformer_uk_percent is not None and float(override.transformer_uk_percent) > 0:
        transformer_settings["uk_percent"] = float(override.transformer_uk_percent)
    project_settings: dict[str, Any] = {
        "transformer": transformer_settings,
        "dc_block_voltage_v": float(override.dc_block_voltage_v),
        "labels": override.labels.model_dump(mode="python"),
        "equipment_ratings": equipment_payload,
    }
    # Owner-confirmed transformer nameplate. Persisted only when explicitly set,
    # so a governed configuration's transformer MVA comes from Engineering
    # Settings and is never inferred (10 MW / 0.9 is not auto-promoted). The SLD
    # builder reads project_settings["transformer_rating_mva"].
    if override.transformer_rating_mva is not None and float(override.transformer_rating_mva) > 0:
        project_settings["transformer_rating_mva"] = float(override.transformer_rating_mva)
    return project_settings


def load_case_sld_project_settings(sizing_case_id: str | None, *, db_url: str | None = None) -> dict[str, Any]:
    case_id = str(sizing_case_id or "").strip()
    if not case_id:
        return {}
    with session_scope(db_url) as session:
        repo = CaseRepository(session)
        return repo.get_case_project_settings(case_id)


def load_case_sld_project_settings_record(
    sizing_case_id: str | None,
    *,
    db_url: str | None = None,
) -> dict[str, Any]:
    case_id = str(sizing_case_id or "").strip()
    if not case_id:
        return {"source": "none", "project_settings": {}}
    with session_scope(db_url) as session:
        case_repo = CaseRepository(session)
        case_row = case_repo.get_case_by_id(case_id)
        if case_row is None:
            return {"source": "none", "project_settings": {}}
        settings_row = (
            session.query(SldProjectSettings)
            .filter_by(sizing_case_id=case_id)
            .one_or_none()
        )
        if settings_row is not None and isinstance(settings_row.settings_json, dict):
            return {
                "source": "dedicated_table",
                "project_settings": dict(settings_row.settings_json),
                "updated_at": settings_row.updated_at,
                "created_at": settings_row.created_at,
                "source_ref": settings_row.source_ref,
                "version_tag": settings_row.version_tag,
            }
        if isinstance(case_row.input_json, dict) and isinstance(case_row.input_json.get("project_settings"), dict):
            return {
                "source": "legacy_case_json",
                "project_settings": dict(case_row.input_json["project_settings"]),
                "updated_at": case_row.updated_at,
                "created_at": case_row.created_at,
                "source_ref": case_row.source_ref,
                "version_tag": case_row.version_tag,
            }
        return {"source": "none", "project_settings": {}}


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


def list_case_sld_project_settings_history(
    sizing_case_id: str | None,
    *,
    db_url: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    case_id = str(sizing_case_id or "").strip()
    if not case_id:
        return []
    with session_scope(db_url) as session:
        rows = (
            session.query(AuditLog)
            .filter_by(
                entity_type="sizing_case",
                entity_id=case_id,
                action="save_sld_project_settings",
            )
            .order_by(AuditLog.created_at.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        return [
            {
                "created_at": row.created_at,
                "actor": row.actor,
                "source_ref": row.source_ref,
                "version_tag": row.version_tag,
            }
            for row in rows
        ]


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
        case_row = case_repo.save_case_project_settings(
            case_id,
            project_settings,
            version_tag=None,
            source_ref=source_ref,
        )
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
