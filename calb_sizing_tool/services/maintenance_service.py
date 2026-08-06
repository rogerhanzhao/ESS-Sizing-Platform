# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

"""Bounded growth for the runtime store (owner requirement 2026-08-04).

    "运行的日志和数据库不能无限制的变大"

WHAT WAS GROWING WITHOUT BOUND, measured on a working checkout:

| store                | growth                                   | pruned before? |
|----------------------|------------------------------------------|----------------|
| outputs/ files       | a file per regeneration                  | 30 d by mtime  |
| artifact_registry    | a row per regeneration                   | NO             |
| run_output_snapshot  | a row per AC re-run                      | NO             |
| audit_log            | a row per persist and per artifact       | NO             |
| oplog jsonl          | a line per page view                     | 30 d by mtime  |
| the test suite       | wrote into the REAL outputs directory    | NO             |

Two of those are now handled at the source: the suite writes to a temporary
directory (tests/conftest.py), and each artifact lineage keeps only the newest
generation (artifact_service). This module handles the rest, and — importantly —
keeps FILES AND ROWS IN STEP.

THE DEFECT THIS EXISTS TO FIX: deploy/docker/calb-maintenance.sh deleted files
older than 30 days and nothing else. The artifact_registry rows survived,
pointing at files that no longer existed, and load_artifact_bytes_from_db
swallows every error — so an old run's report lost its figures SILENTLY. Pruning
must always be row-and-file together, which is what prune_orphaned_artifacts and
prune_artifacts_older_than do.

THE OTHER HALF, found 2026-08-06: the reverse direction had no owner at all.
prune_orphaned_artifacts drops a row whose file is gone; NOTHING in Python
removed a file whose row is gone. Only that shell sweep did, and only on the
deployed host under CALB_RUNTIME_ROOT — so a developer checkout accumulated
without limit (measured: 479 run directories, 5267 files, ~159 MB, referenced
by no database still in existence). prune_unreferenced_artifact_files closes it,
and COUNTS rather than deletes unless explicitly enabled, because an operator
pointed at the wrong database would otherwise reclassify every artifact on disk
as garbage.

Nothing here runs automatically. Call it from the maintenance timer or
``python -m calb_sizing_tool.services.maintenance_service``, so that deleting
data is always something a human or an operator scheduled.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.exc import OperationalError

from calb_sizing_tool.infra.db.models import ArtifactRegistry
from calb_sizing_tool.infra.db.models.audit_log import AuditLog
from calb_sizing_tool.infra.db.models.run_input_snapshot import RunInputSnapshot
from calb_sizing_tool.infra.db.models.run_output_snapshot import RunOutputSnapshot
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.runtime_paths import get_outputs_dir
from calb_sizing_tool.services.artifact_service import resolve_artifact_path

# Defaults chosen to match the file retention the deploy timer already applies,
# so files and rows expire together instead of drifting apart.
DEFAULT_ARTIFACT_RETENTION_DAYS = 30
DEFAULT_AUDIT_RETENTION_DAYS = 180
DEFAULT_OPLOG_RETENTION_DAYS = 30
# Snapshots are the run's evidence; keep the newest few of each kind per run so a
# re-run does not erase what the previous one recorded.
DEFAULT_SNAPSHOT_GENERATIONS = 3
# An artifact file younger than this is never treated as unreferenced: its row
# may simply not have committed yet. A week is far longer than any write window
# and still short enough to reclaim a developer checkout.
DEFAULT_UNREFERENCED_GRACE_DAYS = 7


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(0, value)


@dataclass
class PruneReport:
    """What a sweep removed, or would remove in an explicit dry run."""

    artifact_rows: int = 0
    artifact_files: int = 0
    orphaned_rows: int = 0
    unreferenced_files: int = 0
    snapshot_rows: int = 0
    audit_rows: int = 0
    oplog_files: int = 0
    bytes_freed: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_rows": self.artifact_rows,
            "artifact_files": self.artifact_files,
            "orphaned_rows": self.orphaned_rows,
            "unreferenced_files": self.unreferenced_files,
            "snapshot_rows": self.snapshot_rows,
            "audit_rows": self.audit_rows,
            "oplog_files": self.oplog_files,
            "bytes_freed": self.bytes_freed,
            "notes": list(self.notes),
        }


def _cutoff(days: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)


def _delete_file(stored_path: str) -> int:
    """Remove an artifact file; return the bytes freed."""
    if not stored_path:
        return 0
    try:
        path = resolve_artifact_path(stored_path)
        if path.is_file():
            size = path.stat().st_size
            path.unlink()
            return size
    except OSError:
        pass
    return 0


def prune_orphaned_artifacts(*, db_url: str | None = None,
                             dry_run: bool = False,
                             report: PruneReport | None = None) -> PruneReport:
    """Drop registry rows whose file is gone.

    These are what the file-only retention sweep left behind. A row that cannot
    produce its file is worse than no row: the reader silently returns nothing and
    the report loses a figure without saying so.
    """
    report = report or PruneReport()
    try:
        with session_scope(db_url) as session:
            rows = session.query(ArtifactRegistry).all()
            for row in rows:
                stored = str(row.file_path or "")
                try:
                    exists = bool(stored) and resolve_artifact_path(stored).is_file()
                except OSError:
                    exists = False
                if not exists:
                    report.orphaned_rows += 1
                    if not dry_run:
                        session.delete(row)
    except OperationalError as exc:
        report.notes.append(f"artifact_registry unavailable: {exc}")
    return report


def prune_artifacts_older_than(days: int | None = None, *, db_url: str | None = None,
                               dry_run: bool = False,
                               report: PruneReport | None = None) -> PruneReport:
    """Delete artifact rows AND their files older than ``days``.

    Row and file go together — that is the whole point. ``days=0`` disables it.
    """
    report = report or PruneReport()
    days = _env_int("CALB_ARTIFACT_RETENTION_DAYS", DEFAULT_ARTIFACT_RETENTION_DAYS) if days is None else days
    if days <= 0:
        report.notes.append("artifact retention disabled")
        return report
    cutoff = _cutoff(days)
    try:
        with session_scope(db_url) as session:
            rows = (
                session.query(ArtifactRegistry)
                .filter(ArtifactRegistry.created_at < cutoff)
                .all()
            )
            for row in rows:
                report.artifact_rows += 1
                if dry_run:
                    continue
                freed = _delete_file(str(row.file_path or ""))
                if freed:
                    report.artifact_files += 1
                    report.bytes_freed += freed
                session.delete(row)
    except OperationalError as exc:
        report.notes.append(f"artifact_registry unavailable: {exc}")
    return report


def prune_snapshot_generations(keep: int | None = None, *, db_url: str | None = None,
                               dry_run: bool = False,
                               report: PruneReport | None = None) -> PruneReport:
    """Keep the newest ``keep`` snapshots of each (run, kind), inputs and outputs.

    Re-running AC appends a full AC output document every time while only the
    newest is ever read, so the tail is unreachable weight. ``keep=0`` disables it.

    Input snapshots are pruned on the same rule because a reused AC alternative
    re-records its inputs whenever their content drifts under an unchanged
    identity (see ``ac_run_service._refresh_alternative_snapshots``). That is
    safe for the dedup lookup: every input row of one AC run carries the SAME
    identity hash, so ``find_child_run_by_hash`` still matches the newest.
    """
    report = report or PruneReport()
    keep = _env_int("CALB_SNAPSHOT_GENERATIONS", DEFAULT_SNAPSHOT_GENERATIONS) if keep is None else keep
    if keep <= 0:
        report.notes.append("snapshot retention disabled")
        return report
    for model, label in ((RunOutputSnapshot, "run_output_snapshot"),
                         (RunInputSnapshot, "run_input_snapshot")):
        try:
            with session_scope(db_url) as session:
                rows = session.query(model).order_by(model.created_at.desc()).all()
                seen: dict[tuple[str, str], int] = {}
                for row in rows:
                    key = (str(row.sizing_run_id), str(row.snapshot_kind))
                    seen[key] = seen.get(key, 0) + 1
                    if seen[key] > keep:
                        report.snapshot_rows += 1
                        if not dry_run:
                            session.delete(row)
        except OperationalError as exc:
            report.notes.append(f"{label} unavailable: {exc}")
    return report


def prune_audit_log(days: int | None = None, *, db_url: str | None = None,
                    dry_run: bool = False,
                    report: PruneReport | None = None) -> PruneReport:
    """Trim the audit trail. ``days=0`` disables it — set that to keep everything.

    The default is deliberately longer than the artifact retention: the trail is
    small per row and is the only record of who did what.
    """
    report = report or PruneReport()
    days = _env_int("CALB_AUDIT_RETENTION_DAYS", DEFAULT_AUDIT_RETENTION_DAYS) if days is None else days
    if days <= 0:
        report.notes.append("audit retention disabled")
        return report
    cutoff = _cutoff(days)
    try:
        with session_scope(db_url) as session:
            query = session.query(AuditLog).filter(AuditLog.created_at < cutoff)
            if dry_run:
                report.audit_rows += query.count()
            else:
                report.audit_rows += query.delete(synchronize_session=False)
    except OperationalError as exc:
        report.notes.append(f"audit_log unavailable: {exc}")
    return report


def prune_oplog(days: int | None = None, *, dry_run: bool = False,
                report: PruneReport | None = None) -> PruneReport:
    """Delete op-log day files older than ``days``. ``days=0`` disables it."""
    report = report or PruneReport()
    days = _env_int("CALB_OPLOG_RETENTION_DAYS", DEFAULT_OPLOG_RETENTION_DAYS) if days is None else days
    if days <= 0:
        report.notes.append("oplog retention disabled")
        return report
    cutoff = _cutoff(days).timestamp()
    log_dir = Path(os.environ.get("CALB_OPLOG_DIR", "").strip() or (get_outputs_dir() / "logs"))
    if not log_dir.is_dir():
        return report
    for path in sorted(log_dir.glob("oplog-*.jsonl")):
        try:
            if path.stat().st_mtime < cutoff:
                report.oplog_files += 1
                if not dry_run:
                    report.bytes_freed += path.stat().st_size
                    path.unlink()
        except OSError:
            pass
    return report


def find_unreferenced_artifact_files(*, db_url: str | None = None,
                                     grace_days: int | None = None) -> list[Path]:
    """Artifact FILES that no registry row points at.

    This is the direction ``prune_orphaned_artifacts`` does not cover. That one
    removes a row whose file is gone; this one finds a file whose row is gone —
    and nothing in Python reclaimed those. Only the shell sweep in
    ``deploy/docker/calb-maintenance.sh`` did, and only on the deployed host
    under ``CALB_RUNTIME_ROOT``. A developer checkout therefore accumulates
    forever: a working tree measured 479 run directories / 172 MB, none of it
    referenced by any database still in existence.

    Two things bound the blast radius, because this returns deletion candidates:

    - only ``outputs/artifacts`` is walked, never the whole outputs tree
      (``logs/`` has its own retention, ``external_ai/`` is user-facing output);
    - a file younger than ``grace_days`` is never a candidate, so an artifact
      written moments ago whose row has not committed yet is safe.
    """
    grace = _env_int("CALB_UNREFERENCED_GRACE_DAYS",
                     DEFAULT_UNREFERENCED_GRACE_DAYS) if grace_days is None else max(0, grace_days)
    root = get_outputs_dir() / "artifacts"
    if not root.is_dir():
        return []

    referenced: set[Path] = set()
    with session_scope(db_url) as session:
        # Deliberately NOT guarded against OperationalError: if the registry
        # cannot be read we must not conclude "nothing is referenced" and hand
        # back every file on disk. Let it raise.
        for row in session.query(ArtifactRegistry).all():
            stored = str(row.file_path or "")
            if not stored:
                continue
            try:
                referenced.add(resolve_artifact_path(stored).resolve())
            except OSError:
                pass

    cutoff = _cutoff(grace).timestamp()
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            if path.resolve() not in referenced:
                candidates.append(path)
        except OSError:
            pass
    return sorted(candidates)


def prune_unreferenced_artifact_files(*, db_url: str | None = None,
                                      grace_days: int | None = None,
                                      dry_run: bool = True,
                                      report: PruneReport | None = None) -> PruneReport:
    """Delete artifact files no registry row references. **Counts by default.**

    ``dry_run=True`` is the default and ``run_maintenance`` keeps it that way
    unless ``CALB_PRUNE_UNREFERENCED_FILES`` is set. Reason: an operator pointed
    at the wrong database would see an empty registry and this sweep would
    reclassify every artifact on disk as garbage. Counting first makes that
    mistake visible instead of expensive — the number belongs in front of a
    human before the deletion does.
    """
    report = report or PruneReport()
    try:
        candidates = find_unreferenced_artifact_files(db_url=db_url, grace_days=grace_days)
    except OperationalError as exc:
        report.notes.append(f"unreferenced sweep skipped, registry unreadable: {exc}")
        return report

    report.unreferenced_files = len(candidates)
    if dry_run:
        if candidates:
            total = sum(p.stat().st_size for p in candidates if p.exists())
            report.notes.append(
                f"{len(candidates)} unreferenced artifact files ({total / 1048576:.1f} MB) "
                f"— set CALB_PRUNE_UNREFERENCED_FILES=1 to delete"
            )
        return report

    for path in candidates:
        try:
            size = path.stat().st_size
            path.unlink()
            report.bytes_freed += size
        except OSError:
            report.unreferenced_files -= 1
    _remove_empty_dirs(get_outputs_dir() / "artifacts")
    return report


def _remove_empty_dirs(root: Path) -> None:
    """Deepest first, so a directory emptied by its children is removed too."""
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def storage_report(*, db_url: str | None = None) -> dict[str, Any]:
    """Measure the stores, so growth is a number rather than a worry."""
    outputs = get_outputs_dir()
    files = 0
    total_bytes = 0
    if outputs.is_dir():
        for path in outputs.rglob("*"):
            if path.is_file():
                files += 1
                try:
                    total_bytes += path.stat().st_size
                except OSError:
                    pass
    counts: dict[str, int] = {}
    try:
        with session_scope(db_url) as session:
            for label, model in (
                ("artifact_registry", ArtifactRegistry),
                ("run_output_snapshot", RunOutputSnapshot),
                ("run_input_snapshot", RunInputSnapshot),
                ("audit_log", AuditLog),
            ):
                counts[label] = session.query(model).count()
    except OperationalError as exc:
        counts["error"] = str(exc)[:120]
    return {
        "outputs_dir": str(outputs),
        "output_files": files,
        "output_bytes": total_bytes,
        "output_mb": round(total_bytes / (1024 * 1024), 1),
        "row_counts": counts,
    }


def run_maintenance(*, db_url: str | None = None, dry_run: bool = False) -> PruneReport:
    """One sweep: orphans first, then age, then generations, then logs.

    ``dry_run`` measures every policy without changing rows or files. Orphans go
    first during a real run so the age pass is not slowed by rows it would delete.
    """
    report = PruneReport()
    if dry_run:
        report.notes.append("dry run — no rows or files were deleted")
    prune_orphaned_artifacts(db_url=db_url, dry_run=dry_run, report=report)
    prune_artifacts_older_than(db_url=db_url, dry_run=dry_run, report=report)
    prune_snapshot_generations(db_url=db_url, dry_run=dry_run, report=report)
    prune_audit_log(db_url=db_url, dry_run=dry_run, report=report)
    prune_oplog(dry_run=dry_run, report=report)
    # Files whose rows are gone. COUNTED, not deleted, unless explicitly enabled
    # — see prune_unreferenced_artifact_files for why that default is not timidity.
    prune_unreferenced_artifact_files(
        db_url=db_url,
        dry_run=dry_run or not _env_flag("CALB_PRUNE_UNREFERENCED_FILES"),
        report=report,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run CALB runtime retention.")
    parser.add_argument("--dry-run", action="store_true",
                        help="measure every retention policy without deleting data")
    args = parser.parse_args([] if argv is None else argv)

    before = storage_report()
    report = run_maintenance(dry_run=args.dry_run)
    after = storage_report()
    print(json.dumps({"before": before, "pruned": report.as_dict(), "after": after},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    import sys

    raise SystemExit(main(sys.argv[1:]))
