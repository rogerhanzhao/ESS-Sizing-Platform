"""Reduced-string nominal review stays inside the original signed-in AC flow.

All writes use a migrated temporary workspace and synthetic product records.
The optional review never becomes the active DC/AC/drawing configuration.
"""
from copy import deepcopy

import pytest

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.services.ac_run_service import ac_configuration_hash, list_ac_alternatives
from calb_sizing_tool.services.dc_tail_ac_review_service import REVIEW_KEY
from tests.test_dc_page_run_smoke import _app, _dc_run_id, _run_sizing, _state, signed_in_workspace
from tests.test_dc_tail_runtime_ui import (
    authorized_tail_workspace, _select_library, _stored_output, _restore_page,
)


def _dc_run(app, strings):
    app = _select_library(app, 'Admin product library')
    app.session_state['dc_inputs.poi_power_req_mw'] = 2.0
    app.session_state['dc_inputs.poi_energy_req_mwh'] = 16.0
    if strings is not None:
        app.radio(key='dc_tail_option_preview').set_value(f'Compare one {strings}-string tail')
    result = _run_sizing(app)
    assert not result.exception
    return result


def _forbid_stage3(monkeypatch):
    from calb_sizing_tool.services import dc_reduced_string_tail_service, stage3_service
    from calb_sizing_tool.ui import dc_view

    def forbidden(*args, **kwargs):
        raise AssertionError('AC and historical display must not rerun DC sizing or Stage3')

    monkeypatch.setattr(dc_reduced_string_tail_service, 'run_stage3', forbidden)
    monkeypatch.setattr(stage3_service, 'run_stage3', forbidden)
    monkeypatch.setattr(dc_view, 'service_size_with_guarantee', forbidden)


def _open_ac(sized, monkeypatch, ratio='1:2'):
    from calb_sizing_tool.ui import ac_view
    # AppTest currently serializes segmented single-choice controls as a list.
    # Fix only that widget, as the original signed-in AC save smoke test does.
    monkeypatch.setattr(ac_view.st, 'segmented_control', lambda *args, **kwargs: ratio)
    # The original DC smoke documents stale AppTest widget IDs immediately
    # after its Run. Restore its real saved page before following visible Next.
    historical = _restore_page(sized)
    assert not historical.exception
    next(button for button in historical.button if button.label == 'AC Sizing →').click()
    app = historical.run()
    assert not app.exception
    assert _state(app, 'main_nav') == 'AC Sizing'
    model = next(item for item in app.selectbox if item.label == 'Select AC Block Model')
    model.select(len(model.options) - 1)  # Existing Custom AC Block Model.
    app = app.run()
    next(item for item in app.selectbox if item.label == 'PCS Count per AC Block').select(2)
    app.number_input(key='custom_pcs_kw').set_value(1000)
    app = app.run()
    next(item for item in app.selectbox if item.label == 'Transformer LV Topology').select('two_winding')
    return app.run()


def _run_ac(app):
    next(button for button in app.button if button.label == 'Run AC Sizing').click()
    app = app.run()
    assert not app.exception
    assert any('AC Configuration Complete' in str(item.value) for item in app.success)
    assert any('Single Line Diagram' in button.label for button in app.button)
    return app


def _saved_ac(app):
    run_id = _state(app, 'active_ac_run_id')
    assert run_id
    with session_scope() as session:
        row = RunRepository(session).get_latest_output_snapshot_by_kind(run_id, 'ac_sizing_output')
        return run_id, deepcopy(row.snapshot_json)


def _fresh_ac(app, dc_run_id, ac_run_id, *, complete_metadata=True):
    restored = _app()
    keys = ['auth_context', 'active_project_id', 'active_project_name',
            'active_case_id', 'active_case_name']
    if complete_metadata:
        keys += ['active_project_code', 'active_case_code']
    for key in keys:
        restored.session_state[key] = app.session_state[key]
    restored.session_state['active_run_id'] = dc_run_id
    restored.session_state['active_ac_run_id'] = ac_run_id
    restored.session_state['main_nav'] = 'AC Sizing'
    return restored.run()


@pytest.mark.parametrize('strings', [10, 8])
def test_original_run_saves_and_restores_tail_review_without_adoption_or_dc_recalculation(
        authorized_tail_workspace, monkeypatch, strings):
    app, _ = authorized_tail_workspace
    sized = _dc_run(app, strings)
    standard = _stored_output(sized)['stage2']
    dc_id = _dc_run_id(sized)
    _forbid_stage3(monkeypatch)
    page = _open_ac(sized, monkeypatch)
    assert not page.exception
    assert any(item.label == 'Advanced: Reduced-string tail' for item in page.expander)
    page = _run_ac(page)
    ac_id, output = _saved_ac(page)
    assert output['dc_total_mwh'] == standard['dc_nameplate_bol_mwh']
    assert output['dc_blocks_total'] == standard['container_count']
    assert output['pcs_kw'] == 1000
    assert all(row['pcs_kw'] == 1000 and row['pcs_count'] == 2 for row in output['ac_block_rows'])
    review = output[REVIEW_KEY]
    assert review['comparison_only'] is True and review['downstream_ready'] is False
    assert review['selected_tail_strings'] == strings
    assert review['total_dc_energy_mwh'] < output['dc_total_mwh']
    assert review['main_count'] == standard['container_count'] - 1 and review['tail_count'] == 1
    assert sum(group['tail_count'] for group in review['groups'][:-1]) == 0
    assert review['groups'][-1]['tail_count'] == 1
    assert len(list_ac_alternatives(dc_id)) == 1
    from calb_sizing_tool.adapters.ac_to_sld_adapter import normalize_ac_output_for_sld
    without_review = deepcopy(output)
    without_review.pop(REVIEW_KEY)
    assert normalize_ac_output_for_sld(output).model_dump() == normalize_ac_output_for_sld(without_review).model_dump()
    restored = _fresh_ac(page, dc_id, ac_id)
    assert not restored.exception
    assert _saved_ac(restored) == (ac_id, output)
    assert restored.number_input(key='custom_pcs_kw').value == 1000
    assert restored.selectbox(key='custom_pcs_count').value == 2
    assert any('Reduced-string Tail — AC Comparison' in str(item.value) for item in restored.markdown)
    assert any('Single Line Diagram' in button.label for button in restored.button)
    assert _state(restored, 'dc_result_summary')['dc_nameplate_bol_mwh'] == standard['dc_nameplate_bol_mwh']


def test_tail_only_pcs_edit_reuses_formal_alternative_and_refreshes_saved_comparison(
        authorized_tail_workspace, monkeypatch):
    app, _ = authorized_tail_workspace
    sized = _dc_run(app, 10)
    dc_id = _dc_run_id(sized)
    _forbid_stage3(monkeypatch)
    page = _run_ac(_open_ac(sized, monkeypatch))
    first_id, before = _saved_ac(page)
    rating = next(item for item in page.number_input if item.label.startswith('Tail-comparison PCS '))
    rating.set_value(1250.0)
    page = _run_ac(page.run())
    second_id, after = _saved_ac(page)
    assert second_id == first_id
    assert len(list_ac_alternatives(dc_id)) == 1
    assert ac_configuration_hash(before) == ac_configuration_hash(after)
    assert before['ac_block_rows'] == after['ac_block_rows']
    assert before['dc_allocation_plan'] == after['dc_allocation_plan']
    assert before['pcs_kw'] == after['pcs_kw'] == 1000
    assert before['dc_total_mwh'] == after['dc_total_mwh']
    assert before[REVIEW_KEY]['review_sha256'] != after[REVIEW_KEY]['review_sha256']
    assert after[REVIEW_KEY]['tail_pcs_rating_overrides_kw'][0]['rating_kw'] == 1250.0
    restored = _fresh_ac(page, dc_id, second_id)
    assert not restored.exception
    assert next(item for item in restored.number_input
                if item.label.startswith('Tail-comparison PCS ')).value == 1250.0
    assert _saved_ac(restored) == (second_id, after)


@pytest.mark.parametrize('strings', [10, 8])
def test_one_dc_two_pcs_topology_keeps_standard_save_and_honest_tail_result(
        authorized_tail_workspace, monkeypatch, strings):
    app, _ = authorized_tail_workspace
    sized = _dc_run(app, strings)
    standard = _stored_output(sized)['stage2']
    _forbid_stage3(monkeypatch)
    page = _run_ac(_open_ac(sized, monkeypatch, ratio='1:1'))
    _, output = _saved_ac(page)
    assert output['dc_total_mwh'] == standard['dc_nameplate_bol_mwh']
    assert all(row == dict(pcs_count=2, pcs_kw=1000, dc_blocks=1) for row in output['ac_block_rows'])
    review = output[REVIEW_KEY]
    assert review['tail_feeder_indices'] == [1, 2]
    assert review['topology_valid'] is (strings == 8)
    tail = review['groups'][-1]['connections'][-1]
    assert [item['required_dc_duty_kw'] for item in tail['per_feeder_duties']] == [None, None]
    assert all(item['meets_pcs_nameplate'] is None for item in review['groups'][-1]['pcs_items'])
    if strings == 10:
        assert any('cannot feed 2 PCS' in message for message in review['errors'])
        assert any('cannot feed 2 PCS' in str(item.value) for item in page.warning)
    else:
        assert any('no 4+4 or equal split' in message for message in review['pending_evidence'])
        assert all(item['nominal_power_check'] == 'unknown_output_duty'
                   for item in review['groups'][-1]['pcs_items'])


def test_standard_dc_has_no_new_tail_area_or_saved_attachment(authorized_tail_workspace, monkeypatch):
    app, _ = authorized_tail_workspace
    sized = _dc_run(app, None)
    _forbid_stage3(monkeypatch)
    page = _open_ac(sized, monkeypatch)
    assert not any(item.label == 'Advanced: Reduced-string tail' for item in page.expander)
    assert not any(item.label.startswith('Tail-comparison PCS ') for item in page.number_input)
    page = _run_ac(page)
    _, output = _saved_ac(page)
    assert REVIEW_KEY not in output


def test_existing_mix_editor_remains_authoritative_and_review_only_replaces_final_dc(
        authorized_tail_workspace, monkeypatch):
    app, _ = authorized_tail_workspace
    sized = _dc_run(app, 10)
    standard = _stored_output(sized)['stage2']
    _forbid_stage3(monkeypatch)
    page = _open_ac(sized, monkeypatch)
    page.number_input(key='custom_pcs_kw').set_value(2000)
    page = page.run()
    next(item for item in page.checkbox if item.label.startswith('Enable mixed AC Block station')).check()
    page = page.run()
    ratings = [item for item in page.number_input if item.label.startswith('PCS rating for AC Block ')]
    assert len(ratings) >= 2
    ratings[-1].set_value(1000)
    page = _run_ac(page.run())
    _, output = _saved_ac(page)
    assert output['ac_block_mixed'] is True
    assert output['pcs_kw'] == 2000
    assert output['ac_block_rows'][-1]['pcs_kw'] == 1000
    assert all(row['pcs_kw'] == 2000 for row in output['ac_block_rows'][:-1])
    assert output['dc_total_mwh'] == standard['dc_nameplate_bol_mwh']
    review = output[REVIEW_KEY]
    assert len(review['groups']) == len(output['ac_block_rows'])
    assert review['groups'][-1]['tail_count'] == 1
    assert sum(group['tail_count'] for group in review['groups'][:-1]) == 0
    assert all(item['rating_kw'] == 2000 for group in review['groups'][:-1]
               for item in group['pcs_items'])
    assert all(item['rating_kw'] == 1000 for item in review['groups'][-1]['pcs_items'])


def test_lightweight_restore_keeps_selected_older_ac_alternative_and_its_review(
        authorized_tail_workspace, monkeypatch):
    app, _ = authorized_tail_workspace
    sized = _dc_run(app, 10)
    dc_id = _dc_run_id(sized)
    _forbid_stage3(monkeypatch)
    page = _run_ac(_open_ac(sized, monkeypatch))
    first_id, first_output = _saved_ac(page)
    page.number_input(key='custom_pcs_kw').set_value(1200)
    page = _run_ac(page.run())
    latest_id, latest_output = _saved_ac(page)
    assert first_id != latest_id and len(list_ac_alternatives(dc_id)) == 2
    assert latest_output['pcs_kw'] == 1200 and first_output['pcs_kw'] == 1000
    # The parent's last-runtime record is the newer alternative. IDs/names alone
    # must still recover the deliberately selected older sibling, not that one.
    restored = _fresh_ac(page, dc_id, first_id, complete_metadata=False)
    assert not restored.exception
    assert _state(restored, 'active_ac_run_id') == first_id
    assert _state(restored, 'ac_output')['pcs_kw'] == 1000
    assert _saved_ac(restored) == (first_id, first_output)
    assert restored.number_input(key='custom_pcs_kw').value == 1000
    assert _state(restored, 'active_project_code')
    assert _state(restored, 'active_case_code')
    assert any('Single Line Diagram' in button.label for button in restored.button)


@pytest.mark.parametrize('foreign', [False, True])
def test_lightweight_restore_does_not_keep_a_missing_or_foreign_ac_selection(
        authorized_tail_workspace, monkeypatch, foreign):
    from calb_sizing_tool.services.ac_run_service import persist_ac_run

    app, _ = authorized_tail_workspace
    sized = _dc_run(app, 10)
    dc_id = _dc_run_id(sized)
    _forbid_stage3(monkeypatch)
    page = _run_ac(_open_ac(sized, monkeypatch))
    valid_id, valid_output = _saved_ac(page)
    rejected_id = 'missing-ac-alternative'
    if foreign:
        # A real persisted alternative under a different DC parent, deliberately
        # in the same project/case: parent identity must be checked as well.
        with session_scope() as session:
            repo = RunRepository(session)
            parent = repo.get_run(dc_id)
            other = repo.create_run(
                project_id=parent.project_id, sizing_case_id=parent.sizing_case_id,
                run_type='dc_pipeline', status='succeeded',
                input_summary_json={}, output_summary_json={}, source_ref='synthetic_ui_test',
            )
            session.flush()
            foreign_dc_id = other.sizing_run_id
        foreign_output = deepcopy(valid_output)
        foreign_output['source_run_id'] = foreign_dc_id
        rejected_id = persist_ac_run(dc_run_id=foreign_dc_id, ac_inputs={},
                                     ac_output=foreign_output).run_id
    restored = _fresh_ac(page, dc_id, rejected_id, complete_metadata=False)
    assert not restored.exception
    assert _state(restored, 'active_ac_run_id') != rejected_id
    assert _state(restored, 'active_run_id') == dc_id
    assert _state(restored, 'ac_output')['source_run_id'] == dc_id
    assert _state(restored, 'ac_output')['pcs_kw'] == valid_output['pcs_kw']
    with session_scope() as session:
        saved = RunRepository(session).get_latest_output_snapshot_by_kind(valid_id, 'ac_sizing_output')
        assert saved.snapshot_json == valid_output
