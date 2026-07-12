"""Removable production operation/error trail (trial-run instrumentation).

Scope: page-view trail and uncaught page errors only. Business operations
(runs, artifacts, admin edits) are already persisted with actors in the
database and need no instrumentation here.

Removal plan (designed-in):
1. Instant off: set CALB_OPLOG_ENABLED=false in deploy/docker/.env, restart.
2. Full removal: delete this module and the single block marked
   "BEGIN OPLOG" / "END OPLOG" in app.py. Nothing else references it.

Log destination: <CALB_OUTPUTS_DIR>/logs/oplog-YYYYMMDD.jsonl on the
bind-mounted runtime volume, so records survive container rebuilds and are
cleaned by the existing scoped-retention maintenance timer.

Every function is best-effort and never raises: instrumentation must not be
able to break the product.
"""

from __future__ import annotations

import datetime
import json
import os
import traceback
from pathlib import Path
from typing import Any


def _enabled() -> bool:
    return os.environ.get("CALB_OPLOG_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _log_dir() -> Path:
    override = os.environ.get("CALB_OPLOG_DIR", "").strip()
    if override:
        return Path(override)
    outputs = os.environ.get("CALB_OUTPUTS_DIR", "outputs").strip() or "outputs"
    return Path(outputs) / "logs"


def _write(record: dict[str, Any]) -> None:
    if not _enabled():
        return
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        record = {"ts": now.isoformat(timespec="seconds"), **record}
        directory = _log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"oplog-{now:%Y%m%d}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Instrumentation is never allowed to break or slow the app.
        pass


def log_page_view(*, actor: str | None, page: str, is_guest: bool = False) -> None:
    _write({"kind": "page_view", "actor": actor or "anonymous", "page": page, "guest": bool(is_guest)})


def log_error(*, actor: str | None, page: str, error: BaseException) -> None:
    _write(
        {
            "kind": "error",
            "actor": actor or "anonymous",
            "page": page,
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(limit=30),
        }
    )
