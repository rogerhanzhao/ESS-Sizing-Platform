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


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(0, value)


@dataclass
class PruneReport:
    """What a sweep actually removed. Returned so it can be logged, not guessed."""

    artifact_rows: int = 0
    artifact_files: int = 0
    orphaned_rows: int = 0
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
                    session.delete(row)
                    report.orphaned_rows += 1
    except OperationalError as exc:
        report.notes.append(f"artifact_registry unavailable: {exc}")
    return report


def prune_artifacts_older_than(days: int | None = None, *, db_url: str | None = None,
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
                freed = _delete_file(str(row.file_path or ""))
                if freed:
                    report.artifact_files += 1
                    report.bytes_freed += freed
                session.delete(row)
                report.artifact_rows += 1
    except OperationalError as exc:
        report.notes.append(f"artifact_registry unavailable: {exc}")
    return report


def prune_snapshot_generations(keep: int | None = None, *, db_url: str | None = None,
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
                        session.delete(row)
                        report.snapshot_rows += 1
        except OperationalError as exc:
            report.notes.append(f"{label} unavailable: {exc}")
    return report


def prune_audit_log(days: int | None = None, *, db_url: str | None = None,
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
            report.audit_rows += (
                session.query(AuditLog)
                .filter(AuditLog.created_at < cutoff)
                .delete(synchronize_session=False)
            )
    except OperationalError as exc:
        report.notes.append(f"audit_log unavailable: {exc}")
    return report


def prune_oplog(days: int | None = None, *, report: PruneReport | None = None) -> PruneReport:
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
                report.bytes_freed += path.stat().st_size
                path.unlink()
                report.oplog_files += 1
        except OSError:
            pass
    return report


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


def run_maintenance(*, db_url: str | None = None) -> PruneReport:
    """One sweep: orphans first, then age, then generations, then logs.

    Orphans go first so the age pass is not slowed by rows it would delete anyway.
    """
    report = PruneReport()
    prune_orphaned_artifacts(db_url=db_url, report=report)
    prune_artifacts_older_than(db_url=db_url, report=report)
    prune_snapshot_generations(db_url=db_url, report=report)
    prune_audit_log(db_url=db_url, report=report)
    prune_oplog(report=report)
    return report


def main() -> int:
    import json

    before = storage_report()
    report = run_maintenance()
    after = storage_report()
    print(json.dumps({"before": before, "pruned": report.as_dict(), "after": after},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
