"""Inline Load Run switches the original DC page atomically without resizing."""
from calb_sizing_tool.adapters.session_state_adapter import build_dc_result_summary
from calb_sizing_tool.infra.db.models import SizingRun, RunOutputSnapshot
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from tests.test_dc_page_run_smoke import (
    _dc_run_id, _run_sizing, _state, signed_in_workspace,
)


def _saved_state(page):
    inputs = _state(page, 'dc_inputs')
    run_id = _dc_run_id(page)
    bundle = load_dc_run_bundle(run_id)
    assert bundle is not None
    return dict(
        run_id=run_id,
        summary=build_dc_result_summary(bundle.snapshot),
        nameplate=next(item.value for item in page.metric if item.label == 'Installed DC Nameplate'),
        power=inputs['poi_power_req_mw'],
        energy=inputs['poi_energy_req_mwh'],
        dod=inputs['dod_pct'],
        sc_time=inputs['sc_time_months'],
    )


def _counts():
    with session_scope() as session:
        return tuple(session.query(model).count() for model in (SizingRun, RunOutputSnapshot))


def _workbench_round_trip(page):
    page.button(key='nav_btn_Workbench').click()
    page = page.run()
    assert not page.exception
    assert _state(page, 'main_nav') == 'Workbench'
    page.button(key='nav_btn_DC Sizing').click()
    page = page.run()
    assert not page.exception
    assert _state(page, 'main_nav') == 'DC Sizing'
    return page


def test_inline_load_a_then_b_updates_inputs_result_and_workspace_on_same_click(
        signed_in_workspace, monkeypatch):
    page = signed_in_workspace()
    page.number_input(key='dc_inputs.dod_pct').set_value(98.0)
    page.number_input(key='dc_inputs.sc_time_months').set_value(6)
    page = _run_sizing(page)
    first = _saved_state(page)
    # A fresh driver avoids AppTest's known stale widget IDs immediately after
    # a form submission; both actual saved runs remain in this temporary case.
    page = signed_in_workspace()
    page.number_input(key='dc_inputs.poi_power_req_mw').set_value(50.0)
    page.number_input(key='dc_inputs.poi_energy_req_mwh').set_value(200.0)
    page.number_input(key='dc_inputs.dod_pct').set_value(92.0)
    page.number_input(key='dc_inputs.sc_time_months').set_value(6)
    page = _run_sizing(page)
    second = _saved_state(page)
    assert first['run_id'] != second['run_id']
    assert first['nameplate'] != second['nameplate']
    before = _counts()
    page = signed_in_workspace()

    from calb_sizing_tool.ui import dc_view

    def forbidden(*args, **kwargs):
        raise AssertionError('Inline history restore must not calculate or persist a run')

    monkeypatch.setattr(dc_view, 'service_size_with_guarantee', forbidden)
    monkeypatch.setattr(dc_view, 'service_run_stage3', forbidden)
    monkeypatch.setattr(dc_view, 'persist_dc_run', forbidden)

    for expected in (first, second):
        page.text_input(key='dc_load_run_id').set_value(expected['run_id'])
        page.button(key='dc_load_run_btn').click()
        page = page.run()
        assert not page.exception and not page.error
        assert _state(page, 'active_run_id') == expected['run_id']
        assert _state(page, 'dc_last_run_id') == expected['run_id']
        assert _state(page, 'dc_result_summary') == expected['summary']
        assert _saved_state(page) == expected
        for field, expected_value in (('poi_power_req_mw', expected['power']),
                                      ('poi_energy_req_mwh', expected['energy']),
                                      ('dod_pct', expected['dod']),
                                      ('sc_time_months', expected['sc_time'])):
            assert page.number_input(key=f'dc_inputs.{field}').value == expected_value
        assert not _state(page, '_pending_dc_input_restore')
        assert any('Showing the selected saved result' in str(item.value) for item in page.info)
        assert not any('created with a default value' in str(item.value) for item in page.warning)
        assert _counts() == before
        page = _workbench_round_trip(page)
        assert _saved_state(page) == expected
        assert page.number_input(key='dc_inputs.dod_pct').value == expected['dod']
        assert page.number_input(key='dc_inputs.sc_time_months').value == expected['sc_time']
        assert _counts() == before


def test_session_form_edits_survive_navigation_and_fresh_defaults_stay_unchanged(
        signed_in_workspace, monkeypatch):
    page = signed_in_workspace()
    assert page.number_input(key='dc_inputs.dod_pct').value == 95.0
    assert page.number_input(key='dc_inputs.sc_time_months').value == 3
    before = _counts()

    from calb_sizing_tool.ui import dc_view

    def forbidden(*args, **kwargs):
        raise AssertionError('Navigating an edited form must not calculate or save')

    monkeypatch.setattr(dc_view, 'service_size_with_guarantee', forbidden)
    monkeypatch.setattr(dc_view, 'persist_dc_run', forbidden)
    page.number_input(key='dc_inputs.dod_pct').set_value(96.0)
    page.number_input(key='dc_inputs.sc_time_months').set_value(5)
    page = page.run()
    assert _state(page, 'dc_inputs')['dod_pct'] == 96.0
    assert _state(page, 'dc_inputs')['sc_time_months'] == 5
    page = _workbench_round_trip(page)
    assert page.number_input(key='dc_inputs.dod_pct').value == 96.0
    assert page.number_input(key='dc_inputs.sc_time_months').value == 5
    assert _state(page, 'dc_inputs')['dod_pct'] == 96.0
    assert _state(page, 'dc_inputs')['sc_time_months'] == 5
    assert _counts() == before
