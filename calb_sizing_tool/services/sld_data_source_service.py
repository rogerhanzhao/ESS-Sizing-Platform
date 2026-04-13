from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.exc import OperationalError

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.schemas.run_snapshot import RunOutputSnapshotSchema


AC_RUNTIME_SNAPSHOT_KIND = "ac_runtime_snapshot_v1"


@dataclass(frozen=True)
class AcSnapshotResolution:
    snapshot: AcSnapshot | None
    source: str


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_ac_snapshot(candidate: Any) -> AcSnapshot | None:
    if not isinstance(candidate, dict) or not candidate:
        return None
    try:
        snapshot = AcSnapshot.model_validate(candidate)
    except Exception:
        return None
    if not isinstance(snapshot.output, dict) or not snapshot.output:
        return None
    return snapshot


def _snapshot_matches_run(snapshot: AcSnapshot | None, run_id: str | None) -> bool:
    if snapshot is None:
        return False
    expected_run_id = str(run_id or "").strip()
    if not expected_run_id:
        return True
    source_run_id = str(snapshot.output.get("source_run_id") or "").strip()
    return bool(source_run_id and source_run_id == expected_run_id)


def _build_compatibility_snapshot(project_state: Mapping[str, Any] | None, shared_state: Any) -> AcSnapshot | None:
    ac_output = None
    ac_inputs = None

    if isinstance(project_state, Mapping):
        ac_output = project_state.get("ac_results")
        ac_inputs = project_state.get("ac_inputs")

    if not isinstance(ac_output, dict) or not ac_output:
        ac_output = getattr(shared_state, "ac_results", None)
    if not isinstance(ac_inputs, dict):
        ac_inputs = getattr(shared_state, "ac_inputs", None)

    return _build_ac_snapshot(
        {
            "inputs": ac_inputs or {},
            "output": ac_output or {},
            "results": {},
        }
    )


def _build_session_cached_snapshot(session_state: Mapping[str, Any] | None) -> AcSnapshot | None:
    if not isinstance(session_state, Mapping):
        return None
    return _build_ac_snapshot(
        {
            "inputs": session_state.get("ac_inputs") or {},
            "output": session_state.get("ac_output") or {},
            "results": {},
        }
    )


def load_persisted_ac_snapshot(run_id: str | None, *, db_url: str | None = None) -> AcSnapshot | None:
    resolved_run_id = str(run_id or "").strip()
    if not resolved_run_id:
        return None
    try:
        with session_scope(db_url) as session:
            repo = RunRepository(session)
            row = repo.get_latest_output_snapshot_by_kind(resolved_run_id, AC_RUNTIME_SNAPSHOT_KIND)
            if row is None:
                return None
            payload = row.snapshot_json if isinstance(row.snapshot_json, dict) else {}
            candidate = payload.get("ac_snapshot") if isinstance(payload.get("ac_snapshot"), dict) else payload
            return _build_ac_snapshot(candidate)
    except OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise
        return None


def resolve_preferred_ac_snapshot(
    run_id: str | None,
    *,
    project_state: Mapping[str, Any] | None,
    shared_state: Any,
    session_state: Mapping[str, Any] | None,
    db_url: str | None = None,
) -> AcSnapshotResolution:
    persisted = load_persisted_ac_snapshot(run_id, db_url=db_url)
    if _snapshot_matches_run(persisted, run_id):
        return AcSnapshotResolution(snapshot=persisted, source="persisted_run_snapshot")

    compatibility = _build_compatibility_snapshot(project_state, shared_state)
    if _snapshot_matches_run(compatibility, run_id) or (compatibility is not None and not str(run_id or "").strip()):
        return AcSnapshotResolution(snapshot=compatibility, source="compatibility_adapter")

    session_cached = _build_session_cached_snapshot(session_state)
    if _snapshot_matches_run(session_cached, run_id) or (session_cached is not None and not str(run_id or "").strip()):
        return AcSnapshotResolution(snapshot=session_cached, source="session_cache")

    return AcSnapshotResolution(snapshot=None, source="none")


def _persist_ac_runtime_snapshot_with_session(
    session,
    *,
    run_id: str,
    ac_snapshot: AcSnapshot,
    source_ref: str | None,
    version_tag: str | None,
    actor: str | None,
) -> dict[str, str]:
    repo = RunRepository(session)
    payload = {"ac_snapshot": ac_snapshot.model_dump(mode="python")}
    content_hash = _hash_payload(payload)
    row = repo.add_output_snapshot(
        run_id,
        RunOutputSnapshotSchema(
            snapshot_kind=AC_RUNTIME_SNAPSHOT_KIND,
            payload=payload,
            content_hash=content_hash,
        ),
        version_tag=version_tag,
        source_ref=source_ref,
    )
    session.flush()
    repo.add_audit_log(
        entity_type="sizing_run",
        entity_id=run_id,
        action="persist_ac_runtime_snapshot",
        actor=actor,
        payload_json={
            "run_id": run_id,
            "snapshot_kind": AC_RUNTIME_SNAPSHOT_KIND,
            "content_hash": content_hash,
        },
        version_tag=version_tag,
        source_ref=source_ref,
    )
    return {
        "run_output_snapshot_id": row.run_output_snapshot_id,
        "snapshot_kind": AC_RUNTIME_SNAPSHOT_KIND,
        "content_hash": content_hash,
    }


def persist_ac_runtime_snapshot(
    *,
    run_id: str | None,
    ac_inputs: Mapping[str, Any] | None,
    ac_output: Mapping[str, Any] | None,
    results: Mapping[str, Any] | None = None,
    db_url: str | None = None,
    source_ref: str | None = "ac_view",
    version_tag: str | None = None,
    actor: str | None = None,
) -> dict[str, str] | None:
    resolved_run_id = str(run_id or "").strip()
    if not resolved_run_id:
        return None
    snapshot = _build_ac_snapshot(
        {
            "inputs": dict(ac_inputs or {}),
            "output": dict(ac_output or {}),
            "results": dict(results or {}),
        }
    )
    if snapshot is None:
        return None
    try:
        with session_scope(db_url) as session:
            return _persist_ac_runtime_snapshot_with_session(
                session,
                run_id=resolved_run_id,
                ac_snapshot=snapshot,
                source_ref=source_ref,
                version_tag=version_tag,
                actor=actor,
            )
    except OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise
        with session_scope(db_url) as session:
            Base.metadata.create_all(bind=session.get_bind())
        with session_scope(db_url) as session:
            return _persist_ac_runtime_snapshot_with_session(
                session,
                run_id=resolved_run_id,
                ac_snapshot=snapshot,
                source_ref=source_ref,
                version_tag=version_tag,
                actor=actor,
            )
