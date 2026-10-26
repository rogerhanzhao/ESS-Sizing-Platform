"""One optional reduced-string comparison through the original signed-in page.

Catalogue rows are synthetic fixtures in the temporary workspace database.
Neither this fixture nor these UI checks create or activate real equipment.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.services.product_admin_service import ProductAdminService
from tests.test_dc_page_run_smoke import (
    _app, _dc_run_id, _run_sizing, _state, signed_in_workspace,
)


SUMMARY_KEY = 'reduced_string_tail_comparison'
MAIN_CODE = 'UI-MAIN-12'
EXCEL_MAIN_CODE = 'CALB_5MWh_20FT_12R'
AUTHORITY = 'owner_reduced_string_basis_2026_10_22'


def _tail_values(strings, *, code=None):
    energy = {10: 4.179968, 8: 3.3439744}[strings]
    count = 1 if strings == 10 else 2
    return dict(
        block_code=code or f'UI-TAIL-{strings}',
        block_name=f'Synthetic {strings}-string tail',
        configuration_role='special_tail', parent_block_code=MAIN_CODE,
        cell_code='CALB-314AH-A', cells_in_series=416,
        strings_in_parallel=strings, racks_per_block=strings,
        packs_per_rack=4, pack_count=strings * 4,
        block_form='container', container_type='20ft ISO container',
        gross_energy_mwh=energy, nominal_power_kw=energy * 500,
        nominal_voltage_v=1331.2, max_c_rate=0.5,
        source_ref='Synthetic test only',
        usage_restrictions='Synthetic comparison only; never released equipment.',
        is_active=True, is_published=True,
        metadata_json=dict(
            reduced_string_basis_authority=AUTHORITY,
            standard_excel_code=EXCEL_MAIN_CODE,
            dc_output_count=count, max_connected_pcs=count,
            dc_topology_source_ref='Synthetic test only',
        ),
    )


@pytest.fixture
def authorized_tail_workspace(signed_in_workspace):
    # The imported fixture creates its own migrated temporary database first.
    # Do not write to the source database or to the running local web copy.
    app = signed_in_workspace()
    service = ProductAdminService()
    cell_id = service.create_cell(dict(
        cell_code='CALB-314AH-A', model_name='Synthetic 314Ah cell', manufacturer='CALB',
        chemistry='LFP', nominal_capacity_ah=314, nominal_voltage_v=3.2,
        is_active=True, is_published=True,
    ))
    service.create_dc_block(dict(
        block_code=MAIN_CODE, block_name='Synthetic standard 12-string main',
        product_cell_id=cell_id, cells_in_series=416,
        strings_in_parallel=12, racks_per_block=12, packs_per_rack=4,
        pack_count=48, block_form='container',
        container_type='20ft ISO container', gross_energy_mwh=5.01596,
        nominal_voltage_v=1331.2, max_c_rate=0.5,
        source_ref='Synthetic test only', is_active=True, is_published=True,
    ))
    for strings in (10, 8):
        service.create_dc_block(_tail_values(strings))
    return app.run(), service


def _select_library(app, source):
    app.radio(key='dc_block_source').set_value(source)
    app = app.run()
    app.session_state['dc_inputs.enable_hybrid'] = False
    app.session_state['dc_inputs.enable_cabinet_only'] = False
    return app.run()


def _stored_output(app):
    with session_scope() as session:
        run_id = _dc_run_id(app) or _state(app, 'active_run_id')
        outputs = RunRepository(session).get_output_snapshots(run_id)
        return deepcopy(outputs[-1].snapshot_json)


def _restore_page(sized, page='DC Sizing'):
    app = _app()
    for key in ('auth_context', 'active_project_id', 'active_project_name',
                'active_case_id', 'active_case_name'):
        app.session_state[key] = sized.session_state[key]
    app.session_state['active_run_id'] = _dc_run_id(sized)
    app.session_state['main_nav'] = page
    return app.run()


def _assert_standard_handoff(app, standard):
    summary = _state(app, 'dc_result_summary')
    assert summary['mode'] == 'container_only'
    assert summary['container_count'] == standard['container_count']
    # The original immediate-run summary uses mwh for installed energy; the
    # canonical restored summary also exposes dc_nameplate_bol_mwh explicitly.
    assert summary.get('dc_nameplate_bol_mwh', summary['mwh']) == standard['dc_nameplate_bol_mwh']
    assert summary['dc_product_codes'] == [standard['block_config_items'][0]['block_code']]
    stage13 = _state(app, 'stage13_output')
    assert stage13['selected_scenario'] == 'container_only'
    assert stage13['container_count'] == standard['container_count']
    assert stage13['dc_nameplate_bol_mwh'] == standard['dc_nameplate_bol_mwh']
    assert len(stage13['block_config_table_records']) == 1
    assert stage13['block_config_table_records'][0]['Block Code'] == summary['dc_product_codes'][0]


def test_authorized_products_enable_three_choices_with_one_original_run(authorized_tail_workspace):
    app, service = authorized_tail_workspace
    assert not app.exception
    choice = app.radio(key='dc_tail_option_preview')
    assert choice.options == ['Standard 12-string only', 'Compare one 10-string tail',
                              'Compare one 8-string tail']
    assert choice.label == 'Tail comparison (not adopted)'
    assert choice.value == 'Standard 12-string only'
    assert not choice.disabled
    assert len([button for button in app.button if button.label == 'Run Sizing']) == 1
    frame = service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code')
    assert frame.loc[MAIN_CODE, 'Is_Active'] == 1
    assert frame.loc['UI-TAIL-10', 'Is_Active'] == frame.loc['UI-TAIL-8', 'Is_Active'] == 0


@pytest.mark.parametrize('source,main_code', [
    ('Excel reference library', EXCEL_MAIN_CODE), ('Admin product library', MAIN_CODE),
])
@pytest.mark.parametrize('strings', [10, 8])
def test_one_run_saves_tail_comparison_and_restores_without_recalculation(
        authorized_tail_workspace, monkeypatch, source, main_code, strings):
    app, service = authorized_tail_workspace
    app = _select_library(app, source)
    if source == 'Admin product library' and strings == 10:
        # A nonzero checkpoint must remain visible after a saved-result restore.
        app.session_state['dc_inputs.poi_guarantee_year'] = 3
        app = app.run()
    before_products = deepcopy(service.snapshot())
    app.radio(key='dc_tail_option_preview').set_value(f'Compare one {strings}-string tail')
    sized = _run_sizing(app)
    assert not sized.exception
    assert 'Reduced-string tail — Comparison only' in [tab.label for tab in sized.tabs]
    assert any(button.label == 'AC Sizing →' for button in sized.button)

    saved = _stored_output(sized)
    main = saved['stage2']
    assert main['mode'] == 'container_only'
    assert len(main['block_config_items']) == 1
    assert main['block_config_items'][0]['block_code'] == main_code
    comparison = saved['summary'][SUMMARY_KEY]
    year = saved['stage1']['poi_guarantee_year']
    target = saved['stage1']['poi_energy_req_mwh']
    energy = comparison['poi_energy_at_guarantee_year_mwh']
    metrics = {item.label: item.value for item in sized.metric}
    assert metrics[f'POI Target at Y{year}'] == f'{target:.3f} MWh'
    assert metrics[f'POI Usable Energy at Y{year}'] == f'{energy:.3f} MWh'
    assert metrics[f'Energy Margin at Y{year}'] == f'{energy - target:+.3f} MWh'
    assert any(f'Energy guarantee checkpoint: Y{year} from COD.' in item.value
               and 'does not establish' in item.value for item in sized.caption)
    assert comparison['selected_tail_strings'] == strings
    assert comparison['comparison_only'] is True
    assert comparison['downstream_ready'] is False
    assert comparison['output_partition_pending'] is (strings == 8)
    tail_stage2 = comparison['snapshot']['stage2']
    assert [(row['block_code'], row['count']) for row in tail_stage2['block_config_items']] == [
        (main_code, main['container_count'] - 1), (f'UI-TAIL-{strings}', 1),
    ]
    assert tail_stage2['container_count'] == main['container_count']
    assert tail_stage2['dc_nameplate_bol_mwh'] < main['dc_nameplate_bol_mwh']
    _assert_standard_handoff(sized, main)
    assert service.snapshot() == before_products

    from calb_sizing_tool.ui import dc_view
    from calb_sizing_tool.services import dc_reduced_string_tail_service

    def forbidden(*args, **kwargs):
        raise AssertionError('Saved comparison display must not calculate or persist.')

    monkeypatch.setattr(dc_view, 'service_size_with_guarantee', forbidden)
    monkeypatch.setattr(dc_view, 'persist_dc_run', forbidden)
    monkeypatch.setattr(dc_reduced_string_tail_service, 'run_stage3', forbidden)
    monkeypatch.setattr(dc_reduced_string_tail_service, 'evaluate_reduced_string_tail', forbidden)
    restored = _restore_page(sized)
    assert not restored.exception
    assert any('Showing the selected saved result' in str(item.value) for item in restored.info)
    assert any('Saved result' in str(item.value) for item in restored.markdown)
    assert any(f'One {strings}-string tail replaces' in str(item.value) for item in restored.info)
    assert _stored_output(restored) == saved
    restored_metrics = {item.label: item.value for item in restored.metric}
    assert restored_metrics[f'POI Usable Energy at Y{year}'] == metrics[f'POI Usable Energy at Y{year}']
    assert any(button.label == 'AC Sizing →' for button in restored.button)
    assert any(button.label == 'Single Line Diagram →' for button in restored.button)
    # Follow the original visible workflow from a fresh historical DC page;
    # AC must restore the standard active run, never adopt its comparison.
    next(button for button in restored.button if button.label == 'AC Sizing →').click()
    ac = restored.run()
    assert not ac.exception
    assert _state(ac, 'main_nav') == 'AC Sizing'
    _assert_standard_handoff(ac, main)
    assert service.snapshot() == before_products


def test_standard_choice_retains_original_result_and_next_steps(authorized_tail_workspace):
    app, _ = authorized_tail_workspace
    app = _select_library(app, 'Admin product library')
    assert app.radio(key='dc_tail_option_preview').value == 'Standard 12-string only'
    sized = _run_sizing(app)
    assert not sized.exception
    saved = _stored_output(sized)
    assert SUMMARY_KEY not in saved['summary']
    assert 'Reduced-string tail — Comparison only' not in [tab.label for tab in sized.tabs]
    assert any(button.label == 'AC Sizing →' for button in sized.button)
    assert any(button.label == 'Single Line Diagram →' for button in sized.button)
    _assert_standard_handoff(sized, saved['stage2'])


def test_previous_comparison_choice_keeps_selection_with_clearer_label(authorized_tail_workspace):
    opened, _ = authorized_tail_workspace
    app = _app()
    for key in ('auth_context', 'active_project_id', 'active_project_name',
                'active_case_id', 'active_case_name'):
        app.session_state[key] = opened.session_state[key]
    app.session_state['main_nav'] = 'DC Sizing'
    app.session_state['dc_tail_option_preview'] = 'Allow one 10-string tail'
    app = app.run()
    assert not app.exception
    assert app.radio(key='dc_tail_option_preview').value == 'Compare one 10-string tail'
    assert any('not define the permitted scope of future manual combinations' in item.value
               for item in app.caption)


def test_wrong_main_or_duplicate_tail_is_not_offered(authorized_tail_workspace):
    app, service = authorized_tail_workspace
    service.create_dc_block(_tail_values(10, code='UI-TAIL-10-DUPLICATE'))
    app = app.run()
    assert app.radio(key='dc_tail_option_preview').options == [
        'Standard 12-string only', 'Compare one 8-string tail',
    ]
    cell_id = next(row['product_cell_id'] for row in service.snapshot()['cells']
                   if row['cell_code'] == 'CALB-314AH-A')
    service.create_dc_block(dict(
        block_code='UI-UNRELATED-MAIN', block_name='Synthetic unrelated larger container',
        product_cell_id=cell_id, cells_in_series=416, strings_in_parallel=12,
        block_form='container', container_type='20ft ISO container',
        gross_energy_mwh=6.0, source_ref='Synthetic test only',
        is_active=True, is_published=True,
    ))
    app = _select_library(app.run(), 'Admin product library')
    assert not app.exception
    choice = app.radio(key='dc_tail_option_preview')
    assert choice.options == ['Standard 12-string only']
    assert choice.disabled
    assert len([button for button in app.button if button.label == 'Run Sizing']) == 1


def test_saved_curve_details_distinguish_changed_effective_rate_from_changed_profiles():
    from calb_sizing_tool.ui.dc_view import _tail_curve_comparison_details
    baseline = SimpleNamespace(effective_c_rate=0.2499, chosen_soh_c_rate=0.25,
        chosen_soh_cycles_per_year=365, soh_profile_id=1, chosen_rte_c_rate=0.25,
        rte_profile_id=1)
    tail = deepcopy(baseline)
    tail.effective_c_rate = 0.2501
    rows, changed = _tail_curve_comparison_details(baseline, tail)
    assert changed == []
    assert rows[0]['Effective DC rate'] == '0.2499C'
    assert rows[1]['Effective DC rate'] == '0.2501C'
    assert rows[0]['Selected SOH cycles/year'] == rows[1]['Selected SOH cycles/year'] == 365
    tail.soh_profile_id, tail.chosen_soh_c_rate = 2, 0.5
    tail.chosen_soh_cycles_per_year = 730
    tail.rte_profile_id, tail.chosen_rte_c_rate = 2, 0.5
    rows, changed = _tail_curve_comparison_details(baseline, tail)
    assert changed == ['SOH', 'RTE']
    assert rows[1]['Selected SOH rate'] == '0.5C'
    assert rows[1]['Selected SOH cycles/year'] == 730
    assert rows[1]['Selected RTE rate'] == '0.5C'
    assert baseline.effective_c_rate == 0.2499
    assert baseline.chosen_soh_c_rate == baseline.chosen_rte_c_rate == 0.25
