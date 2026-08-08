from __future__ import annotations

import hashlib
import os
import time
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


def _artifact_run_chain(session, run_id: str, depth: int = 4) -> list[str]:
    """``run_id`` and its ancestors, nearest first.

    An AC alternative is a child run (ac_run_service). Its drawings belong to it,
    but anything produced before the alternative existed — and everything in a
    database written before AC runs did — still hangs off the DC run. Reading the
    chain is what lets both be true at once without a data migration.
    """
    from calb_sizing_tool.infra.db.models.sizing_run import SizingRun

    chain: list[str] = []
    current: str | None = run_id
    seen: set[str] = set()
    while current and current not in seen and len(chain) < depth:
        chain.append(current)
        seen.add(current)
        row = (
            session.query(SizingRun.parent_run_id)
            .filter(SizingRun.sizing_run_id == current)
            .one_or_none()
        )
        current = str(row[0]) if row and row[0] else None
    return chain


#: Owner ruling 2026-08-08 — 读取失败重新读取. A failed read is not the same as
#: nothing to read: the outputs directory sits on a network share on the server
#: and the registry lives in a WAL-mode SQLite file several sessions share, so
#: "database is locked" and a transient OSError are both things that succeed on
#: a second look. Only a genuinely absent row or file means "not generated".
_READ_ATTEMPTS = 3
_READ_BACKOFF_S = 0.1


def retry_read(read, *, attempts: int = _READ_ATTEMPTS):
    """Call ``read`` again on a transient failure. Returns (value, error).

    ``error`` is the last exception when every attempt failed, else None. Only
    the failure modes that a retry can actually clear are retried — a lock, a
    busy database, an I/O error. Anything else is a bug that will fail the same
    way three times, so it is reported after one attempt.
    """
    transient = (OperationalError, OSError)
    last: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return read(), None
        except transient as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(_READ_BACKOFF_S * (2 ** attempt))
        except Exception as exc:
            return None, exc
    return None, last


def load_artifact_bytes_with_failures(
    run_id: str,
    artifact_kinds: list[str],
    *,
    db_url: str | None = None,
    include_ancestors: bool = True,
) -> tuple[dict[str, bytes], list[str]]:
    """``load_artifact_bytes_from_db``, plus what could not be read and why.

    The second element is empty when every recorded artifact was read. A
    non-empty list means a figure EXISTS but this process could not get at it —
    which a caller must not report as "not generated". Kinds with no registry
    row at all are absent from both: nothing was recorded, nothing failed.
    """
    result: dict[str, bytes] = {}
    failures: list[str] = []
    if not run_id or not artifact_kinds:
        return result, failures
    kinds_set = set(artifact_kinds)

    def _query_registry():
        with session_scope(db_url) as session:
            chain = _artifact_run_chain(session, run_id) if include_ancestors else [run_id]
            rows = (
                session.query(
                    ArtifactRegistry.sizing_run_id,
                    ArtifactRegistry.artifact_kind,
                    ArtifactRegistry.file_path,
                )
                .filter(
                    ArtifactRegistry.sizing_run_id.in_(chain),
                    ArtifactRegistry.artifact_kind.in_(kinds_set),
                )
                .order_by(ArtifactRegistry.created_at.desc())
                .all()
            )
            rank = {value: index for index, value in enumerate(chain)}
            # Nearest run wins; within one run, newest wins. Sorting by rank only
            # is stable, so the created_at order above is preserved inside a run.
            rows = sorted(rows, key=lambda row: rank.get(str(row[0]), len(chain)))
            return [(str(row[1]), str(row[2])) for row in rows]

    artifact_paths, query_error = retry_read(_query_registry)
    if query_error is not None:
        failures.append(f"artifact registry unreadable: {query_error}")
        return result, failures

    seen: set[str] = set()
    for kind, file_path_value in artifact_paths or []:
        if kind in seen:
            continue
        seen.add(kind)
        try:
            file_path = resolve_artifact_path(file_path_value)
        except Exception as exc:
            failures.append(f"{kind}: unusable stored path {file_path_value!r} ({exc})")
            continue
        if not file_path.exists():
            # Nothing to retry — the row outlived its file. The maintenance
            # sweep owns that case; it is not a read failure.
            continue
        data, read_error = retry_read(file_path.read_bytes)
        if read_error is not None:
            failures.append(f"{kind}: {file_path} could not be read ({read_error})")
            continue
        result[kind] = data
    return result, failures


def load_artifact_bytes_from_db(
    run_id: str,
    artifact_kinds: list[str],
    *,
    db_url: str | None = None,
    include_ancestors: bool = True,
) -> dict[str, bytes]:
    """Load artifact file bytes from disk using paths recorded in artifact_registry.

    Returns a dict mapping artifact_kind → file bytes for each kind found. A
    transient failure is retried before the kind is dropped; use
    ``load_artifact_bytes_with_failures`` when the caller has to tell "could not
    read it" apart from "it was never made".

    ``include_ancestors`` walks up ``parent_run_id`` for kinds this run does not
    have of its own, NEAREST FIRST — so an AC alternative's own drawing always
    wins, and one it never produced falls back to the DC run's. Pass False to
    read strictly this run.
    """
    result, _failures = load_artifact_bytes_with_failures(
        run_id, artifact_kinds, db_url=db_url, include_ancestors=include_ancestors
    )
    return result
