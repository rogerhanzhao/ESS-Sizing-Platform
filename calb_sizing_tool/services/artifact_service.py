from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.runtime_paths import ensure_outputs_dir
from calb_sizing_tool.plugins.base import ArtifactPayload


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
            file_path = base_dir / artifact.file_name
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
                file_name=artifact.file_name,
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
