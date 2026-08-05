from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy.exc import OperationalError

from calb_sizing_tool.infra.db.models.artifact_registry import ArtifactRegistry
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.runtime_paths import ensure_outputs_dir, get_outputs_dir
from calb_sizing_tool.plugins.base import ArtifactPayload
from calb_sizing_tool.utils.files import safe_child_path, safe_storage_filename


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# How many generations of each (run, artifact_kind) to keep. Readers always take
# the NEWEST row, so older generations are already unreachable through the app —
# keeping them only grows the database and the disk. Raise it via
# CALB_ARTIFACT_GENERATIONS if you want regeneration history for diffing.
_DEFAULT_ARTIFACT_GENERATIONS = 1


def artifact_generations_to_keep() -> int:
    raw = os.environ.get("CALB_ARTIFACT_GENERATIONS", "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_ARTIFACT_GENERATIONS
    except ValueError:
        value = _DEFAULT_ARTIFACT_GENERATIONS
    return max(1, value)


def _supersede_older_generations(
    repo: RunRepository, run_id: str, artifact_kind: str, artifact_mode: str, keep: int
) -> int:
    """Drop generations beyond ``keep`` for one lineage, rows AND files.

    Regenerating an SLD or a layout used to leave the previous row and its file
    behind forever. Nothing reads them — load_artifact_bytes_from_db takes the
    newest of each kind — so they were pure growth.

    A lineage is (run, kind, artifact_mode). The mode matters: one SLD run
    legitimately holds a "concept" AND a "draft_override" artifact of the same
    kind, and rendering one must not delete the other.
    """
    rows = repo.list_artifacts(run_id, artifact_kind=artifact_kind, artifact_mode=artifact_mode)
    doomed, survivors = rows[keep:], rows[:keep]
    # A regeneration writes the SAME file name, so the superseded row and the row
    # that replaced it point at the SAME path. Deleting by row alone would erase
    # the file that was just produced. Only remove a file no surviving row claims.
    still_referenced = {str(row.file_path or "") for row in survivors}
    removed = 0
    for row in doomed:
        stored_path = str(row.file_path or "")
        repo.delete_artifact(row.artifact_registry_id)
        removed += 1
        if not stored_path or stored_path in still_referenced:
            continue
        try:
            path = resolve_artifact_path(stored_path)
            if path.is_file():
                path.unlink()
        except OSError:
            # The row is the record of truth; a file we cannot remove is a
            # leftover for the maintenance sweep, not a reason to fail a render.
            pass
    return removed


def relative_to_outputs(file_path: Path, outputs_dir: Path | None = None) -> str:
    """Path as stored in artifact_registry.

    Relative to the outputs directory when the artifact lives inside it, absolute
    otherwise. The base is always the GLOBAL outputs directory, never a caller's
    override: a relative path is only portable if the reader can resolve it, and
    the reader only knows the global one. A caller that redirects its outputs
    (tests, embedding) therefore keeps the old absolute behaviour, which still
    works — it is just not portable, exactly as before.
    """
    base = (outputs_dir or get_outputs_dir())
    try:
        return file_path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(file_path.resolve())


def resolve_artifact_path(stored: str) -> Path:
    """Turn a stored artifact path back into a real one.

    Rows written before 2026-08-04 hold an ABSOLUTE path; rows written since hold
    one relative to the outputs directory. Both must keep working, so an absolute
    stored path is used as-is and a relative one is resolved against the current
    outputs directory.
    """
    candidate = Path(stored)
    if candidate.is_absolute():
        return candidate
    return get_outputs_dir() / candidate


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
            # Record the path RELATIVE to the outputs directory. An absolute path
            # ties the database to one host: restore it elsewhere, or move
            # outputs/, and every stored figure becomes unreachable while the row
            # still claims to have one.
            stored_path = relative_to_outputs(file_path, get_outputs_dir())
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
                file_path=stored_path,
                media_type=artifact.media_type,
                content_hash=content_hash,
                metadata_json=metadata,
                version_tag=plugin_version,
                source_ref=source_ref or plugin_id,
            )
            session.flush()
            artifact_ids.append(row.artifact_registry_id)
            _supersede_older_generations(
                repo, run_id, artifact.artifact_kind,
                str(metadata.get("artifact_mode") or ""),
                artifact_generations_to_keep(),
            )
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
                session.query(ArtifactRegistry.artifact_kind, ArtifactRegistry.file_path)
                .filter(
                    ArtifactRegistry.sizing_run_id == run_id,
                    ArtifactRegistry.artifact_kind.in_(kinds_set),
                )
                .order_by(ArtifactRegistry.created_at.desc())
                .all()
            )
            artifact_paths = [(str(row.artifact_kind), str(row.file_path)) for row in rows]
        seen: set[str] = set()
        for kind, file_path_value in artifact_paths:
            if kind in seen:
                continue
            seen.add(kind)
            try:
                file_path = resolve_artifact_path(file_path_value)
                if file_path.exists():
                    result[kind] = file_path.read_bytes()
            except Exception:
                pass
    except OperationalError:
        pass
    except Exception:
        pass
    return result
