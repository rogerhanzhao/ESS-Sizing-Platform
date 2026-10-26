"""Exact selected snapshot and authorization checks, on temporary data only."""
from copy import deepcopy
from types import SimpleNamespace
import sqlite3

import pytest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.repositories.case_repository import CaseRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.run_snapshot import RunInputSnapshotSchema, RunOutputSnapshotSchema
from calb_sizing_tool.services.ac_run_service import persist_ac_run
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.dc_tail_ac_review_service import REVIEW_KEY, evaluate_tail_ac_review
from calb_sizing_tool.services.dc_tail_preview_source_service import load_saved_tail_sld_preview
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from tests.test_dc_tail_ac_review import example, parent, ac


@pytest.fixture
def saved_tail_source(example, tmp_path):
    path = tmp_path / 'tail-preview.sqlite'
    url = f'sqlite:///{path.as_posix()}'
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    snapshot = parent(example)
    with session_scope(url) as session:
        cases = CaseRepository(session)
        project = cases.get_or_create_project(project_code='preview', project_name='Preview')
        session.flush()
        case = cases.create_case(project_id=project.project_id, case_code='case', case_name='Case',
                                 stage_scope='proposal', scenario_mode='container_only', input_json={})
        session.flush()
        runs = RunRepository(session)
        dc = runs.create_run(project_id=project.project_id, sizing_case_id=case.sizing_case_id,
                             run_type='dc_pipeline', status='succeeded')
        session.flush()
        dc_id, project_id, case_id = dc.sizing_run_id, project.project_id, case.sizing_case_id
        runs.add_input_snapshot(dc_id, RunInputSnapshotSchema(
            snapshot_kind='dc_case_input', payload={}, content_hash=_hash_payload({})))
        payload = snapshot.model_dump(mode='json')
        runs.add_output_snapshot(dc_id, RunOutputSnapshotSchema(
            snapshot_kind='dc_pipeline_output', payload=payload, content_hash=_hash_payload(payload)))
    output = ac()
    output.update(source_run_id=dc_id, source_project_id=project_id, source_case_id=case_id)
    output[REVIEW_KEY] = evaluate_tail_ac_review(snapshot, output)
    result = persist_ac_run(dc_run_id=dc_id, ac_inputs={}, ac_output=output, db_url=url)
    args = dict(dc_run_id=dc_id, ac_run_id=result.run_id, project_id=project_id, case_id=case_id,
                auth_user=AuthUser('test-admin', 'admin', 'Admin', ['admin']),
                expected_ac_output=deepcopy(output), db_url=url)
    return SimpleNamespace(path=path, url=url, args=args, output=output, snapshot=snapshot)


def _database_rows(path):
    with sqlite3.connect(path) as connection:
        names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                for name in names}


def test_selected_preview_is_scoped_and_read_only(saved_tail_source):
    before = _database_rows(saved_tail_source.path)
    result = load_saved_tail_sld_preview(**saved_tail_source.args)
    assert result['preview_available'] is True
    assert result['last_group']['connections'][-1]['unit_id'] == 'DC-004'
    assert result['source']['ac_payload_sha256'] == _hash_payload(saved_tail_source.output)
    assert _database_rows(saved_tail_source.path) == before


@pytest.mark.parametrize('field', ['dc_run_id', 'ac_run_id', 'project_id', 'case_id', 'auth_user'])
def test_missing_selection_never_uses_runtime_or_session_fallback(saved_tail_source, field):
    args = dict(saved_tail_source.args, **{field: None})
    assert load_saved_tail_sld_preview(**args) is None


def test_project_nonmember_cannot_read_preview(saved_tail_source):
    args = dict(saved_tail_source.args, auth_user=AuthUser('nonmember', 'other', None, ['user']))
    with pytest.raises(PermissionError, match='access denied'):
        load_saved_tail_sld_preview(**args)


@pytest.mark.parametrize('field', ['project_id', 'case_id', 'dc_run_id', 'ac_run_id'])
def test_foreign_workspace_selection_is_rejected_even_for_admin(saved_tail_source, field):
    args = dict(saved_tail_source.args, **{field: 'another-record'})
    with pytest.raises(ValueError):
        load_saved_tail_sld_preview(**args)


@pytest.mark.parametrize('field,value', [
    ('parent_run_id', None), ('project_id', 'foreign-project'),
    ('sizing_case_id', None), ('run_type', 'dc_pipeline'),
])
def test_actual_child_relation_is_checked_not_only_payload(saved_tail_source, field, value):
    # Foreign project needs a valid FK target; other fields exercise existing ones.
    with session_scope(saved_tail_source.url) as session:
        if field == 'project_id':
            project = CaseRepository(session).get_or_create_project(
                project_code='foreign', project_name='Foreign')
            session.flush()
            value = project.project_id
        child = RunRepository(session).get_run(saved_tail_source.args['ac_run_id'])
        setattr(child, field, value)
    with pytest.raises(ValueError, match='belonging'):
        load_saved_tail_sld_preview(**saved_tail_source.args)


@pytest.mark.parametrize('corruption', ['hash', 'payload', 'provenance', 'display', 'dc_hash'])
def test_changed_or_incomplete_sources_have_no_preview(saved_tail_source, corruption):
    args = dict(saved_tail_source.args)
    if corruption == 'display':
        changed = deepcopy(saved_tail_source.output)
        changed['display_only_changed'] = True
        args['expected_ac_output'] = changed
    else:
        with session_scope(saved_tail_source.url) as session:
            repo = RunRepository(session)
            run_id = args['dc_run_id'] if corruption == 'dc_hash' else args['ac_run_id']
            kind = 'dc_pipeline_output' if corruption == 'dc_hash' else 'ac_sizing_output'
            row = repo.get_latest_output_snapshot_by_kind(run_id, kind)
            if corruption in ('hash', 'dc_hash'):
                row.content_hash = None
            else:
                changed = deepcopy(row.snapshot_json)
                changed['source_case_id'] = 'forged-case'
                row.snapshot_json = changed
                if corruption == 'provenance':
                    row.content_hash = _hash_payload(changed)
                    args['expected_ac_output'] = changed
    with pytest.raises(ValueError):
        load_saved_tail_sld_preview(**args)


def test_new_output_under_same_ac_identity_cannot_reuse_stale_preview(saved_tail_source):
    before = load_saved_tail_sld_preview(**saved_tail_source.args)
    output = deepcopy(saved_tail_source.output)
    output[REVIEW_KEY] = evaluate_tail_ac_review(saved_tail_source.snapshot, output, {2: 1500})
    result = persist_ac_run(dc_run_id=saved_tail_source.args['dc_run_id'], ac_inputs={},
                            ac_output=output, db_url=saved_tail_source.url)
    assert result.reused is True and result.run_id == saved_tail_source.args['ac_run_id']
    with pytest.raises(ValueError, match='displayed AC configuration has changed'):
        load_saved_tail_sld_preview(**saved_tail_source.args)
    fresh = load_saved_tail_sld_preview(**dict(saved_tail_source.args, expected_ac_output=output))
    assert fresh['preview_sha256'] != before['preview_sha256']
    assert fresh['last_group']['pcs_items'][-1]['rating_kw'] == 1500


def test_sibling_alternatives_of_same_dc_cannot_exchange_displayed_preview(saved_tail_source):
    first_args = dict(saved_tail_source.args)
    first = load_saved_tail_sld_preview(**first_args)
    second_output = deepcopy(saved_tail_source.output)
    # Same project, case, DC parent and container count, but a genuinely
    # different last-group PCS alternative. Parent IDs alone cannot bind a figure.
    second_output['ac_block_rows'][-1]['pcs_kw'] = 1500
    second_output[REVIEW_KEY] = evaluate_tail_ac_review(
        saved_tail_source.snapshot, second_output)
    second_run = persist_ac_run(dc_run_id=first_args['dc_run_id'], ac_inputs={},
        ac_output=second_output, db_url=saved_tail_source.url)
    assert second_run.run_id != first_args['ac_run_id']
    second_args = dict(first_args, ac_run_id=second_run.run_id,
                       expected_ac_output=second_output)
    before = _database_rows(saved_tail_source.path)
    for mismatched in (
        dict(second_args, expected_ac_output=saved_tail_source.output),
        dict(first_args, expected_ac_output=second_output),
    ):
        with pytest.raises(ValueError, match='displayed AC configuration has changed'):
            load_saved_tail_sld_preview(**mismatched)
    second = load_saved_tail_sld_preview(**second_args)
    assert second['preview_sha256'] != first['preview_sha256']
    assert second['last_group']['pcs_items'][-1]['rating_kw'] == 1500
    assert first['last_group']['pcs_items'][-1]['rating_kw'] == 1250
    assert _database_rows(saved_tail_source.path) == before
