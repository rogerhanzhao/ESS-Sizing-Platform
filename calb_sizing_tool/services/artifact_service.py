from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from sqlalchemy.exc import OperationalError

from calb_sizing_tool.infra.db.models.artifact_registry import ArtifactRegistry
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.runtime_paths import ensure_outputs_dir
from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.utils.files import safe_child_path, safe_storage_filename


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def persist_artifacts(
    *,
    run_id: str,
    artifacts: Iterable[ArtifactPayload],
    plugin_id: str,
    plugin_version: str,
    actor: str | None = None,
    db_url: str | None = None,
    outputs_dir: Path | None = None,
    source_ref: str | None = None,
) -> list[str]:
    outputs_dir = outputs_dir or ensure_outputs_dir()
    base_dir = outputs_dir / "artifacts" / run_id / plugin_id
    base_dir.mkdir(parents=True, exist_ok=True)
    artifact_ids: list[str] = []

    with session_scope(db_url) as session:
        repo = RunRepository(session)
        for artifact in artifacts:
            file_name = safe_storage_filename(artifact.file_name, fallback=f"{artifact.artifact_kind}.bin")
            file_path = safe_child_path(base_dir, file_name, fallback=f"{artifact.artifact_kind}.bin")
            file_path.write_bytes(artifact.content)
            content_hash = _hash_bytes(artifact.content)
            metadata = dict(artifact.metadata or {})
            metadata.update(
                {
                    "plugin_id": plugin_id,
                    "plugin_version": plugin_version,
                    "actor": actor,
                }
            )
            row = repo.register_artifact(
                sizing_run_id=run_id,
                artifact_kind=artifact.artifact_kind,
                file_name=file_name,
                file_path=str(file_path),
                media_type=artifact.media_type,
                content_hash=content_hash,
                metadata_json=metadata,
                version_tag=plugin_version,
                source_ref=source_ref or plugin_id,
            )
            session.flush()
            artifact_ids.append(row.artifact_registry_id)
            repo.add_audit_log(
                entity_type="artifact_registry",
                entity_id=row.artifact_registry_id,
                action="register_artifact",
                actor=actor,
                payload_json={
                    "run_id": run_id,
                    "artifact_kind": artifact.artifact_kind,
                    "plugin_id": plugin_id,
                    "plugin_version": plugin_version,
                },
                version_tag=plugin_version,
                source_ref=source_ref or plugin_id,
            )
    return artifact_ids


def load_artifact_bytes_from_db(
    run_id: str,
    artifact_kinds: list[str],
    *,
    db_url: str | None = None,
) -> dict[str, bytes]:
    """Load artifact file bytes from disk using paths recorded in artifact_registry.

    Returns a dict mapping artifact_kind → file bytes for each kind found.
    Missing or unreadable artifacts are silently omitted.
    """
    result: dict[str, bytes] = {}
    if not run_id or not artifact_kinds:
        return result
    kinds_set = set(artifact_kinds)
    try:
        with session_scope(db_url) as session:
            rows = (
                session.query(ArtifactRegistry)
                .filter(
                    ArtifactRegistry.sizing_run_id == run_id,
                    ArtifactRegistry.artifact_kind.in_(kinds_set),
                )
                .order_by(ArtifactRegistry.created_at.desc())
                .all()
            )
        seen: set[str] = set()
        for row in rows:
            kind = row.artifact_kind
            if kind in seen:
                continue
            seen.add(kind)
            try:
                file_path = Path(row.file_path)
                if file_path.exists():
                    result[kind] = file_path.read_bytes()
            except Exception:
                pass
    except OperationalError:
        pass
    except Exception:
        pass
    return result
