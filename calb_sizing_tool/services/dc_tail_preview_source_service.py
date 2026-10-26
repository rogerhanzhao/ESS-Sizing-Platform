"""Read the exact selected, authorized AC child for a tail comparison preview.

This reader intentionally has no parent-runtime, session or artifact fallback.
It does not change the standard SLD data-source rules or publish any drawing.
"""
from __future__ import annotations

from copy import deepcopy

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.services.access_control_service import AccessControlService
from calb_sizing_tool.services.ac_run_service import AC_OUTPUT_SNAPSHOT_KIND
from calb_sizing_tool.services.dc_tail_preview_service import build_tail_sld_preview
from calb_sizing_tool.services.run_persistence_service import _hash_payload


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def load_saved_tail_sld_preview(*, dc_run_id, ac_run_id, project_id, case_id,
                                auth_user, expected_ac_output=None, db_url=None):
    """Return a read-only preview of one exact selected saved AC alternative.

    Missing selection has no preview. Supplied foreign, changed or incomplete
    sources fail closed without searching for another alternative. IDs and
    hashes remain private; the renderer consumes only the manifest's group.
    """
    if not all((dc_run_id, ac_run_id, project_id, case_id, auth_user)):
        return None
    with session_scope(db_url) as session:
        repo = RunRepository(session)
        access = AccessControlService(session, auth_user)
        access.ensure_project_access(project_id)
        parent = repo.get_run(dc_run_id)
        _require(parent is not None and parent.run_type == 'dc_pipeline'
                 and parent.project_id == project_id and parent.sizing_case_id == case_id,
                 'The selected DC result does not match the current project and case.')
        child = repo.get_run(ac_run_id)
        _require(child is not None and child.run_type == 'ac_sizing'
                 and child.parent_run_id == dc_run_id and child.project_id == project_id
                 and child.sizing_case_id == case_id,
                 'Select the saved AC alternative belonging to this DC result.')
        row = repo.get_latest_output_snapshot_by_kind(ac_run_id, AC_OUTPUT_SNAPSHOT_KIND)
        _require(row is not None and isinstance(row.snapshot_json, dict) and row.content_hash,
                 'The selected AC alternative has no complete saved output.')
        output = deepcopy(row.snapshot_json)
        _require(_hash_payload(output) == row.content_hash,
                 'The saved AC output has changed. Restore or save AC Sizing again.')
        _require(output.get('source_run_id') == dc_run_id
                 and output.get('source_project_id') == project_id
                 and output.get('source_case_id') == case_id,
                 'The saved AC output does not match its source DC result and workspace.')
        if expected_ac_output is not None:
            _require(isinstance(expected_ac_output, dict)
                     and _hash_payload(expected_ac_output) == row.content_hash,
                     'The displayed AC configuration has changed. Restore the selected AC alternative.')
        bundle = access.load_dc_run_bundle(dc_run_id)
        _require(bundle is not None and bundle.project_id == project_id
                 and bundle.sizing_case_id == case_id,
                 'The source DC result is unavailable for this workspace.')
        # Tail comparisons were introduced with complete hashed DC snapshots.
        # Legacy hashless runs keep their original SLD path, not this preview.
        for snapshot in (bundle.input_snapshot, bundle.output_snapshot):
            _require(snapshot is not None and snapshot.content_hash
                     and _hash_payload(snapshot.payload) == snapshot.content_hash,
                     'The source DC result needs complete saved input and output snapshots.')
        return build_tail_sld_preview(bundle.snapshot, output)
