from __future__ import annotations

import json
from typing import Any

from calb_sizing_tool.plugins.base import ArtifactPayload, json_bytes
from calb_sizing_tool.services.artifact_service import (
    load_artifact_bytes_with_failures,
    persist_artifacts,
)
from calb_sizing_tool.services.site_constraint_readiness_service import (
    SITE_CONSTRAINT_SCHEMA_VERSION,
    assess_site_constraint_readiness,
)


_PLUGIN_ID = "site_constraint_set_v1"
_PLUGIN_VERSION = "1.0.0"
_ARTIFACT_KIND = "site_constraint_set_json"


def register_site_constraint_set(
    *,
    run_id: str,
    constraint_set: dict[str, Any],
    actor: str | None,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Persist a user-provided Site Constraint Set as a versioned run artifact.

    Incomplete sets are deliberately accepted as `draft_incomplete` so the
    project can retain and audit the engineering intake without enabling a
    master-layout output prematurely.
    """
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        raise ValueError("A valid run_id is required to register a Site Constraint Set.")
    if not isinstance(constraint_set, dict):
        raise ValueError("Site Constraint Set must be a JSON object.")
    schema_version = str(constraint_set.get("schema_version") or "").strip()
    if schema_version != SITE_CONSTRAINT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported Site Constraint Set schema_version. Expected {SITE_CONSTRAINT_SCHEMA_VERSION}."
        )
    source_run = constraint_set.get("source_run")
    declared_run_id = str((source_run or {}).get("run_id") or "").strip() if isinstance(source_run, dict) else ""
    if declared_run_id and declared_run_id != normalized_run_id:
        raise ValueError(
            "Site Constraint Set declares source_run.run_id "
            f"'{declared_run_id}' but is being registered to run '{normalized_run_id}'. "
            "Site constraints are run-specific; regenerate the template from the target run."
        )

    readiness = assess_site_constraint_readiness(constraint_set)
    constraint_status = "ready_for_constraint_validation" if readiness["ready"] else "draft_incomplete"
    file_name = (
        "site_constraint_set.ready.json"
        if readiness["ready"]
        else "site_constraint_set.draft.json"
    )
    artifact = ArtifactPayload(
        artifact_kind=_ARTIFACT_KIND,
        file_name=file_name,
        media_type="application/json",
        content=json_bytes(constraint_set),
        metadata={
            "schema_version": schema_version,
            "constraint_set_status": constraint_status,
            "master_layout_readiness": readiness,
            "not_for_construction": True,
        },
    )
    artifact_ids = persist_artifacts(
        run_id=normalized_run_id,
        artifacts=[artifact],
        plugin_id=_PLUGIN_ID,
        plugin_version=_PLUGIN_VERSION,
        actor=actor,
        db_url=db_url,
        source_ref="site_constraint_set_service",
    )
    return {
        "artifact_registry_ids": artifact_ids,
        "constraint_set_status": constraint_status,
        "master_layout_readiness": readiness,
        "file_name": file_name,
    }


class SiteConstraintSetReadError(RuntimeError):
    """A Site Constraint Set the run HAS could not be retrieved.

    Distinct from "there is none": the read was already retried
    (artifact_service.retry_read), so this is a retrieval problem the caller
    must surface and retry rather than cache as an absence.
    """


def load_persisted_site_constraint_set(
    run_id: str,
    *,
    db_url: str | None = None,
) -> dict[str, Any] | None:
    """Load the most recently registered Site Constraint Set for a run.

    Returns None when the run has none. Raises ``SiteConstraintSetReadError``
    when it HAS one that could not be retrieved — the two must not look alike to
    the caller, which caches its result for the session (owner ruling
    2026-08-08, 读取失败重新读取: a cached failure would never be retried).
    """
    artifacts, failures = load_artifact_bytes_with_failures(
        run_id, [_ARTIFACT_KIND], db_url=db_url
    )
    if failures:
        raise SiteConstraintSetReadError("; ".join(failures))
    payload = artifacts.get(_ARTIFACT_KIND)
    if not payload:
        return None
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    if decoded.get("schema_version") != SITE_CONSTRAINT_SCHEMA_VERSION:
        return None
    return decoded
