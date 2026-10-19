"""Saved source boundary for cabinet arrangement and technical documents."""
from __future__ import annotations

import hashlib
import json


def cabinet_drawing_input(output):
    # This token identifies a UI execution, not the saved AC alternative.
    return {key: value for key, value in output.items() if key != 'source_ac_run_id'}


def document_signature(output, parent_run_id, ac_run_id, *, plugin_id, version, installation_basis=None):
    value = dict(output=cabinet_drawing_input(output), parent_run_id=parent_run_id,
                 ac_run_id=ac_run_id, plugin_id=plugin_id, version=version,
                 installation_basis=installation_basis)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def verify_cabinet_ac_source(output, parent_run_id, ac_run_id, *, db_url=None):
    """Never substitute a parent, sibling, session output, or latest flat file."""
    from calb_sizing_tool.infra.db.session import session_scope
    from calb_sizing_tool.infra.db.models.sizing_run import SizingRun
    from calb_sizing_tool.repositories.run_repository import RunRepository
    from calb_sizing_tool.services.ac_run_service import AC_OUTPUT_SNAPSHOT_KIND
    if not ac_run_id:
        raise ValueError('Save and select an AC alternative before creating cabinet documents')
    with session_scope(db_url) as session:
        child = session.get(SizingRun, ac_run_id)
        if child is None or child.run_type != 'ac_sizing' or child.parent_run_id != parent_run_id:
            raise ValueError('The selected AC alternative does not belong to this DC result')
        snapshot = RunRepository(session).get_latest_output_snapshot_by_kind(ac_run_id, AC_OUTPUT_SNAPSHOT_KIND)
        if (snapshot is None or not isinstance(snapshot.snapshot_json, dict)
                or cabinet_drawing_input(snapshot.snapshot_json) != cabinet_drawing_input(output)
                or output.get('source_run_id') != parent_run_id):
            raise ValueError('Cabinet documents must use the exact saved output of the selected AC alternative')
