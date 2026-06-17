from __future__ import annotations

import hashlib
from pathlib import Path

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.repositories.artifact_repository import ArtifactRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.runtime_paths import ensure_outputs_dir
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderOptions
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.artifact_service import persist_artifacts
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.sld_data_source_service import load_persisted_ac_snapshot
from calb_sizing_tool.utils.files import safe_child_path, safe_storage_filename


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_auth_user(auth_user: AuthUser | None) -> AuthUser:
    if auth_user is None:
        raise PermissionError("Login required.")
    return auth_user


def generate_layout_prompt(
    *,
    run_id: str,
    auth_user: AuthUser | None,
    options: LayoutRenderOptions | None = None,
    db_url: str | None = None,
) -> dict:
    auth_user = _require_auth_user(auth_user)
    with session_scope(db_url) as session:
        access = AccessControlService(session, auth_user)
        bundle = access.load_dc_run_bundle(run_id)
        if bundle is None:
            raise ValueError("Run not found.")

    registry = get_plugin_registry()
    plugin = registry.get("layout_prompt_v1")
    if plugin is None:
        raise ValueError("Prompt plugin not registered.")

    ac_snapshot = load_persisted_ac_snapshot(run_id, db_url=db_url) or AcSnapshot()

    render_input = plugin.build_input_from_run(
        run_bundle=bundle,
        ac_snapshot=ac_snapshot,
        options=options or LayoutRenderOptions(),
        topology_snapshot=None,
        layout_rules=None,
    )
    errors = plugin.validate_input(render_input)
    if errors:
        raise ValueError("; ".join(errors))

    render_output = plugin.render(render_input)
    artifacts = plugin.emit_artifact(render_output)

    persist_artifacts(
        run_id=run_id,
        artifacts=artifacts,
        plugin_id=plugin.metadata.plugin_id,
        plugin_version=plugin.metadata.plugin_version,
        actor=auth_user.username if auth_user else None,
        db_url=db_url,
        source_ref="layout_prompt",
    )

    return {
        "payload": render_output["payload"],
        "prompt_text": render_output["prompt_text"],
        "artifacts": [artifact.__dict__ for artifact in artifacts],
    }


def submit_external_layout_artifact(
    *,
    run_id: str,
    auth_user: AuthUser | None,
    file_bytes: bytes,
    file_name: str,
    media_type: str,
    notes: str | None = None,
    db_url: str | None = None,
) -> dict:
    auth_user = _require_auth_user(auth_user)
    with session_scope(db_url) as session:
        access = AccessControlService(session, auth_user)
        bundle = access.load_dc_run_bundle(run_id)
        if bundle is None:
            raise ValueError("Run not found.")

    outputs_dir = ensure_outputs_dir() / "external_ai" / run_id
    outputs_dir.mkdir(parents=True, exist_ok=True)

    stored_file_name = safe_storage_filename(file_name, fallback="layout_ai_upload")
    file_path = safe_child_path(outputs_dir, stored_file_name, fallback="layout_ai_upload")
    file_path.write_bytes(file_bytes)
    content_hash = _hash_bytes(file_bytes)

    with session_scope(db_url) as session:
        repo = ArtifactRepository(session)
        submission = repo.create_external_submission(
            sizing_run_id=run_id,
            plugin_id="layout_prompt_v1",
            plugin_version="1.0.0",
            artifact_kind="layout_ai_preview",
            file_name=stored_file_name,
            file_path=str(file_path),
            media_type=media_type,
            content_hash=content_hash,
            status="pending_review",
            ai_label="ai_generated_preview",
            actor=auth_user.username if auth_user else None,
            notes=notes,
            metadata_json={"source": "external_ai_upload"},
            source_ref="external_ai",
        )
        session.flush()
        RunRepository(session).add_audit_log(
            entity_type="external_artifact_submission",
            entity_id=submission.submission_id,
            action="submit_external_ai",
            actor=auth_user.username if auth_user else None,
            payload_json={"run_id": run_id, "file_name": stored_file_name},
            source_ref="external_ai",
        )
        session.flush()
        return {
            "submission_id": submission.submission_id,
            "status": submission.status,
            "ai_label": submission.ai_label,
        }


def review_external_layout(
    *,
    submission_id: str,
    decision: str,
    reviewer: AuthUser | None,
    comments: str | None = None,
    db_url: str | None = None,
) -> dict:
    if decision not in {"approve", "reject", "request_revision"}:
        raise ValueError("Invalid decision.")
    if reviewer is None or not reviewer.is_admin:
        raise PermissionError("Only admin can review external layouts.")

    with session_scope(db_url) as session:
        repo = ArtifactRepository(session)
        submission = repo.get_submission(submission_id)
        if submission is None:
            raise ValueError("Submission not found.")

        repo.add_review(
            submission_id=submission_id,
            decision=decision,
            reviewer=reviewer.username if reviewer else None,
            comments=comments,
        )

        if decision == "approve":
            approved_index = _next_approved_revision_index(session, submission.sizing_run_id)
            ai_label = f"approved_revision_{approved_index}"
            submission.status = ai_label
            submission.ai_label = ai_label
            submission.metadata_json = {
                **(submission.metadata_json or {}),
                "approved_revision": approved_index,
            }

            # Promote to artifact registry
            content = Path(submission.file_path).read_bytes()
            persist_artifacts(
                run_id=submission.sizing_run_id,
                artifacts=[
                    __import__("calb_sizing_tool.plugins.base", fromlist=["ArtifactPayload"]).ArtifactPayload(
                        artifact_kind="layout_ai_approved",
                        file_name=submission.file_name,
                        media_type=submission.media_type or "image/png",
                        content=content,
                        metadata={
                            "ai_label": ai_label,
                            "submission_id": submission.submission_id,
                            "reviewer": reviewer.username if reviewer else None,
                        },
                    )
                ],
                plugin_id=submission.plugin_id,
                plugin_version=submission.plugin_version,
                actor=reviewer.username if reviewer else None,
                db_url=db_url,
                source_ref="layout_review",
            )
        elif decision == "reject":
            submission.status = "rejected"
        else:
            submission.status = "request_revision"

        RunRepository(session).add_audit_log(
            entity_type="external_artifact_submission",
            entity_id=submission.submission_id,
            action=f"review_{decision}",
            actor=reviewer.username if reviewer else None,
            payload_json={"submission_id": submission.submission_id, "decision": decision},
            source_ref="layout_review",
        )
        return {
            "submission_id": submission.submission_id,
            "status": submission.status,
        }


def list_external_submissions(run_id: str, *, db_url: str | None = None) -> list[dict]:
    with session_scope(db_url) as session:
        repo = ArtifactRepository(session)
        rows = repo.list_submissions_by_run(run_id)
        return [
            {
                "submission_id": row.submission_id,
                "file_name": row.file_name,
                "status": row.status,
                "ai_label": row.ai_label,
                "actor": row.actor,
                "created_at": row.created_at,
            }
            for row in rows
        ]


def _next_approved_revision_index(session, run_id: str) -> int:
    repo = ArtifactRepository(session)
    rows = repo.list_submissions_by_run(run_id)
    approved = [row for row in rows if row.ai_label.startswith("approved_revision_")]
    if not approved:
        return 1
    max_idx = 0
    for row in approved:
        try:
            max_idx = max(max_idx, int(row.ai_label.split("_")[-1]))
        except Exception:
            continue
    return max_idx + 1
