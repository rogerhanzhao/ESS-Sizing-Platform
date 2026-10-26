"""Exercise maintenance through the existing DC product form, on synthetic data."""
from __future__ import annotations

import csv
from copy import deepcopy
import io
import json
import re

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models.product_dc_block import ProductDCBlock
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.services.product_admin_service import ProductAdminService
from tests.test_dc_catalogue_readiness_ui import _catalogue_page
from tests.test_dc_page_run_smoke import signed_in_workspace


def test_original_admin_navigation_preserves_auth_and_returns_to_sizing(signed_in_workspace):
    app = signed_in_workspace()
    auth = dict(app.session_state['auth_context'])
    case_id = app.session_state['active_case_id']
    next(button for button in app.button if button.label == '⚙ Product & Database').click().run()
    assert not app.exception
    assert app.session_state['auth_context'] == auth
    assert app.session_state['__admin_portal__'] is True
    next(radio for radio in app.radio if radio.label == 'Section').set_value('DC Blocks').run()
    assert not app.exception
    assert any(button.label == 'Save DC Block Template' for button in app.button)
    assert app.session_state['auth_context'] == auth
    next(button for button in app.button if button.label == '← Back to Sizing').click().run()
    assert not app.exception
    assert app.session_state['auth_context'] == auth
    assert app.session_state['active_case_id'] == case_id
    assert app.session_state['main_nav'] == 'DC Sizing'


@pytest.fixture
def catalogue(tmp_path):
    url = f"sqlite:///{(tmp_path / 'original-product-maintenance.sqlite').as_posix()}"
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    service = ProductAdminService(url)
    cell = service.create_cell(dict(cell_code='SYN-314', model_name='Synthetic cell',
        chemistry='LFP', nominal_capacity_ah=314, is_active=True, is_published=True))
    parent = service.create_dc_block(dict(block_code='SYN-12', block_name='Synthetic parent',
        product_cell_id=cell, block_form='container', container_type='20ft ISO container',
        cells_in_series=416, strings_in_parallel=12, gross_energy_mwh=5.0,
        nominal_voltage_v=1331.2, voltage_min_v=1164.8, voltage_max_v=1497.6,
        nominal_power_kw=2500, max_current_a=2500,
        dimension_width_mm=2438, dimension_depth_mm=6058, dimension_height_mm=2896,
        source_ref='Synthetic fixture only', is_active=True, is_published=True))
    return url, service, cell, parent


def _page(url):
    page = AppTest.from_function(_catalogue_page, args=(url,), default_timeout=30).run()
    assert not page.exception
    return page


def _add_widget(page, kind, label):
    """The original edit form precedes add; target the add control by its label."""
    return [item for item in getattr(page, kind) if item.label == label][-1]


def _populate_tail(page, *, strings=10):
    _add_widget(page, 'text_input', 'Block Code *').input('SYN-10')
    _add_widget(page, 'text_input', 'Block Name *').input('Synthetic incomplete tail')
    page.selectbox(key='add_dc_role').select('special_tail')
    page.selectbox(key='add_dc_parent').select('SYN-12 - Synthetic parent')
    _add_widget(page, 'selectbox', 'Linked Cell').select('SYN-314 - Synthetic cell')
    _add_widget(page, 'number_input', 'Cells in Series').set_value(416)
    _add_widget(page, 'number_input', 'Strings in Parallel').set_value(strings)
    _add_widget(page, 'text_input', 'Container / Cabinet Type').input('20ft ISO container')
    page.text_input(key='add_dc_source').input('Synthetic tail source')
    page.text_input(key='add_dc_version').input('SYNTHETIC-V1')
    page.text_area(key='add_dc_restrictions').input('Synthetic test only; no engineering approval')


def _submit_add(page):
    _add_widget(page, 'button', 'Save DC Block Template').click().run()
    assert not page.exception


def test_existing_dc_product_form_keeps_original_controls_and_english_fields(catalogue):
    url, service, _, parent = catalogue
    before = service.snapshot()
    page = _page(url)
    assert {'Edit Selected DC Block Template', 'Add DC Block Template',
            'Import DC Block Templates from CSV / Excel'} <= {item.label for item in page.expander}
    assert {'Save Changes', 'Save DC Block Template'} <= {item.label for item in page.button}
    assert {'Configuration role', 'Parent product (special tail only)', 'Linked Cell'} <= {
        item.label for item in page.selectbox}
    assert {'Technical source reference', 'Source version', 'DC connection source'} <= {
        item.label for item in page.text_input}
    assert {'DC output circuits', 'Maximum connected PCS'} <= {
        item.label for item in page.number_input}
    assert 'Usage restrictions' in {item.label for item in page.text_area}
    assert page.selectbox(key='add_dc_role').options == ['Standard', 'Special tail']
    labels = ' '.join(item.label for kind in ('selectbox', 'text_input', 'text_area',
                        'number_input', 'button', 'expander') for item in getattr(page, kind))
    assert not re.search(r'[\u3400-\u9fff]', labels)
    visible_text = ' '.join(item.value for kind in ('markdown', 'caption') for item in getattr(page, kind))
    assert parent not in visible_text
    assert service.snapshot() == before


def test_original_add_form_saves_incomplete_tail_without_sizing_activation(catalogue):
    url, service, cell, parent = catalogue
    page = _page(url)
    _populate_tail(page)
    _submit_add(page)
    blocks = {row['block_code']: row for row in service.snapshot()['dc_blocks']}
    tail = blocks['SYN-10']
    assert tail['product_cell_id'] == cell
    assert tail['metadata_json']['configuration_role'] == 'engineering_variant'
    assert tail['metadata_json']['parent_product_id'] == parent
    assert tail['source_ref'] == 'Synthetic tail source'
    assert tail['version_tag'] == 'SYNTHETIC-V1'
    assert tail['nominal_power_kw'] is None
    assert tail['gross_energy_mwh'] is None  # no 12-to-10 proportional inference
    status = {row['block_code']: row for row in service.dc_block_maintenance_rows()}
    assert status['SYN-10']['parameter_status'] == 'Incomplete'
    assert 'Excluded from standard sizing' in status['SYN-10']['parameter_details']
    sizing = service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code')
    assert sizing.loc['SYN-12', 'Is_Active'] == 1
    assert sizing.loc['SYN-10', 'Is_Active'] == 0
    fresh = _page(url)
    assert 'SYN-10' in ' '.join(item.value for item in fresh.markdown)


def test_original_edit_and_refresh_retain_tail_declaration_and_clear_optionals(catalogue):
    url, service, cell, _ = catalogue
    tail_id = service.create_dc_block(dict(block_code='SYN-10', block_name='Synthetic incomplete tail',
        block_form='container', product_cell_id=cell, cells_in_series=416,
        strings_in_parallel=10, container_type='20ft ISO container', configuration_role='Special tail',
        parent_block_code='SYN-12', source_ref='Synthetic old source', version_tag='V0',
        usage_restrictions='Synthetic old restrictions', nominal_power_kw=1000,
        is_active=True, is_published=True))
    page = _page(url)
    record = next(value for value in page.selectbox(key='edit_dc_block_record').options
                  if value.startswith('SYN-10'))
    page.selectbox(key='edit_dc_block_record').select(record).run()
    assert page.selectbox(key=f'edit_dc_{tail_id}_role').value == 'special_tail'
    assert page.selectbox(key=f'edit_dc_{tail_id}_role').disabled
    assert page.selectbox(key=f'edit_dc_{tail_id}_role').options == ['Special tail']
    assert page.selectbox(key=f'edit_dc_{tail_id}_parent').value == 'SYN-12 - Synthetic parent'
    page.text_input(key=f'edit_dc_{tail_id}_source').input('Synthetic corrected source')
    page.text_input(key=f'edit_dc_{tail_id}_version').input('')
    page.text_area(key=f'edit_dc_{tail_id}_restrictions').input('Synthetic corrected restriction')
    page.checkbox(key=f'clear_dc_block_{tail_id}_nominal_power_kw').check()
    [button for button in page.button if button.label == 'Save Changes'][0].click().run()
    assert not page.exception
    tail = next(row for row in service.snapshot()['dc_blocks'] if row['block_code'] == 'SYN-10')
    assert tail['source_ref'] == 'Synthetic corrected source'
    assert tail['version_tag'] is None
    assert tail['nominal_power_kw'] is None
    assert tail['metadata_json']['usage_restrictions'] == 'Synthetic corrected restriction'
    fresh = _page(url)
    fresh.selectbox(key='edit_dc_block_record').select(record).run()
    assert fresh.text_input(key=f'edit_dc_{tail_id}_source').value == 'Synthetic corrected source'
    assert fresh.text_input(key=f'edit_dc_{tail_id}_version').value == ''
    assert fresh.number_input(key=f'edit_dc_block_{tail_id}_nominal_power_kw').value is None
    assert fresh.selectbox(key=f'edit_dc_{tail_id}_role').value == 'special_tail'
    assert fresh.selectbox(key=f'edit_dc_{tail_id}_parent').value == 'SYN-12 - Synthetic parent'
    assert service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code').loc['SYN-10', 'Is_Active'] == 0


def test_incompatible_tail_is_a_friendly_form_error_without_catalogue_write(catalogue):
    url, service, _, _ = catalogue
    before = service.snapshot()
    page = _page(url)
    _populate_tail(page, strings=9)
    _submit_add(page)
    assert any('Child string count' in message.value for message in page.error)
    assert not page.success
    assert service.snapshot() == before


def test_original_import_template_and_parameter_export_share_human_identifiers(catalogue):
    from calb_sizing_tool.ui.admin_portal_view import _DC_BLOCK_CSV_COLUMNS, _template_csv

    url, service, cell, parent = catalogue
    service.create_dc_block(dict(block_code='SYN-10', block_name='Synthetic tail', block_form='container',
        product_cell_id=cell, configuration_role='Special tail', parent_block_code='SYN-12',
        source_ref='Synthetic source', version_tag='V1', usage_restrictions='Synthetic only'))
    page = _page(url)
    labels = {item.label for item in page.get('download_button')}
    assert {'Export DC Product Parameters (CSV)', 'Download DC Block Templates CSV Template'} <= labels
    exported = service.export_dc_blocks_dataframe()
    header = next(csv.reader(io.StringIO(_template_csv(_DC_BLOCK_CSV_COLUMNS).decode())))
    assert list(exported.columns) == header
    assert {'configuration_role', 'parent_block_code', 'cell_code', 'source_ref',
            'version_tag', 'usage_restrictions', 'dc_output_count', 'max_connected_pcs',
            'dc_topology_source_ref'} <= set(header)
    assert not any(name.endswith('_id') or name == 'metadata_json' for name in header)
    text = exported.to_csv(index=False)
    assert parent not in text and cell not in text
    tail = exported.set_index('block_code').loc['SYN-10']
    assert tail['parent_block_code'] == 'SYN-12'
    assert tail['cell_code'] == 'SYN-314'
    preview = service.preview_import_from_df(exported, entity='dc_block')
    assert not preview['errors']
    assert len(preview['rows']) == 2


def test_parent_control_excludes_known_incompatible_products_but_keeps_incomplete_drafts(catalogue):
    url, service, cell, _ = catalogue
    other_cell = service.create_cell(dict(cell_code='SYN-OTHER-314', model_name='Other exact cell',
        chemistry='LFP', nominal_capacity_ah=314))
    base = dict(block_form='container', product_cell_id=cell, cells_in_series=416,
                strings_in_parallel=12, container_type='20ft ISO container')
    incompatible = {
        'BAD-CABINET': dict(block_form='cabinet'),
        'BAD-40FT': dict(container_type='40ft ISO container'),
        'BAD-STRINGS': dict(strings_in_parallel=10),
        'BAD-SERIES': dict(cells_in_series=400),
        'BAD-CELL': dict(product_cell_id=other_cell),
    }
    for code, changes in incompatible.items():
        service.create_dc_block(dict(base, block_code=code, block_name=code, **changes))
    service.create_dc_block(dict(block_code='DRAFT-PARENT', block_name='Draft parent awaiting data'))
    tail_id = service.create_dc_block(dict(base, block_code='SYN-10', block_name='Synthetic tail',
        strings_in_parallel=10, configuration_role='Special tail', parent_block_code='SYN-12'))
    page = _page(url)
    record = next(value for value in page.selectbox(key='edit_dc_block_record').options
                  if value.startswith('SYN-10'))
    page.selectbox(key='edit_dc_block_record').select(record).run()
    assert not page.exception
    choices = page.selectbox(key=f'edit_dc_{tail_id}_parent').options
    assert 'SYN-12 - Synthetic parent' in choices
    assert 'DRAFT-PARENT - Draft parent awaiting data' in choices
    assert not any(code in choice for code in incompatible for choice in choices)
    assert not any(choice.startswith('SYN-10') for choice in choices)
    assert 'No parent product' in choices


def test_incomplete_parameter_status_uses_readable_form_terms(catalogue):
    url, service, cell, _ = catalogue
    service.create_dc_block(dict(block_code='SYN-MISSING', block_name='Synthetic missing fields',
        block_form='container', product_cell_id=cell, configuration_role='Special tail',
        parent_block_code='SYN-12'))
    before = service.snapshot()
    row = next(row for row in service.dc_block_maintenance_rows() if row['block_code'] == 'SYN-MISSING')
    assert row['parameter_status'] == 'Incomplete'
    details = row['parameter_details']
    for internal in ('nominal_voltage_v', 'dimension_width_mm', 'dimension_depth_mm',
                     'dimension_height_mm', 'cells_in_series', 'strings_in_parallel',
                     'container_type', 'block_form'):
        assert internal not in details
    for readable in ('Nominal voltage (V)', 'Width (mm)', 'Depth / Length (mm)',
                     'Height (mm)', 'Cells in series', 'Strings in parallel', 'Container type'):
        assert readable in details
    page = _page(url)
    label = next(value for value in page.selectbox(key='edit_dc_block_record').options
                 if value.startswith('SYN-MISSING'))
    page.selectbox(key='edit_dc_block_record').select(label).run()
    assert not page.exception
    assert any(details in item.value for item in page.caption)
    assert service.snapshot() == before


def test_legacy_id_and_new_alias_import_previews_show_same_human_fields_without_writes(catalogue):
    _, service, cell, parent = catalogue
    before = service.snapshot()
    inputs = pd.DataFrame([
        dict(block_code='LEGACY-10', block_name='Legacy tail', block_form='container',
             product_cell_id=cell, metadata_json=dict(configuration_role='engineering_variant',
                 parent_product_id=parent, usage_restrictions='Synthetic only'),
             gross_energy_mwh='4.1', nominal_power_kw='2000', max_current_a='1500'),
        dict(block_code='ALIAS-10', block_name='Alias tail', block_form='container',
             cell_code='SYN-314', configuration_role='Special tail', parent_block_code='SYN-12',
             usage_restrictions='Synthetic only', gross_energy_mwh='4.1',
             nominal_power_kw='2000', max_current_a='1500'),
    ])
    normalized = service.preview_import_from_df(inputs, entity='dc_block')
    assert not normalized['errors']
    unchanged_rows = deepcopy(normalized['rows'])
    frame = service.dc_block_import_preview_dataframe(normalized['rows'])
    assert list(frame.columns) == ['Row', 'Code', 'Name', 'Use', 'Parent', 'Cell',
                                   'Gross MWh', 'Nominal power (kW)', 'Current limit (A)',
                                   'DC outputs', 'Maximum connected PCS', 'DC connection source']
    assert frame['Row'].tolist() == [2, 3]
    assert frame['Code'].tolist() == ['LEGACY-10', 'ALIAS-10']
    assert frame['Name'].tolist() == ['Legacy tail', 'Alias tail']
    for _, row in frame.iterrows():
        assert (row['Use'], row['Parent'], row['Cell']) == ('Special tail', 'SYN-12', 'SYN-314')
        assert (row['Gross MWh'], row['Nominal power (kW)'], row['Current limit (A)']) == (4.1, 2000, 1500)
    visible = frame.to_csv(index=False)
    for hidden in (cell, parent, 'engineering_variant', 'metadata_json', 'parent_product_id', 'product_cell_id'):
        assert hidden not in visible
    assert normalized['rows'] == unchanged_rows  # projection must not change import payloads
    assert service.snapshot() == before


def test_dc_connection_fields_save_reopen_and_clear_in_original_forms(catalogue):
    url, service, _, _ = catalogue
    page = _page(url)
    _populate_tail(page)
    page.number_input(key='add_dc_dc_output_count').set_value(1)
    page.number_input(key='add_dc_max_connected_pcs').set_value(1)
    page.text_input(key='add_dc_dc_topology_source_ref').input('User design confirmation: 10-string single output')
    _submit_add(page)

    tail = next(row for row in service.dc_block_maintenance_rows() if row['block_code'] == 'SYN-10')
    tail_id = tail['product_dc_block_id']
    assert tail['dc_output_count'] == tail['max_connected_pcs'] == 1
    assert tail['dc_topology_source_ref'] == 'User design confirmation: 10-string single output'
    assert tail['parameter_status'] == 'Incomplete'
    saved = next(row for row in service.snapshot()['dc_blocks'] if row['block_code'] == 'SYN-10')
    assert saved['metadata_json']['dc_output_count'] == 1
    assert saved['metadata_json']['max_connected_pcs'] == 1

    fresh = _page(url)
    record = next(value for value in fresh.selectbox(key='edit_dc_block_record').options
                  if value.startswith('SYN-10'))
    fresh.selectbox(key='edit_dc_block_record').select(record).run()
    assert fresh.number_input(key=f'edit_dc_{tail_id}_dc_output_count').value == 1
    assert fresh.number_input(key=f'edit_dc_{tail_id}_max_connected_pcs').value == 1
    assert fresh.text_input(key=f'edit_dc_{tail_id}_dc_topology_source_ref').value == tail['dc_topology_source_ref']
    assert any('1 DC output / max 1 PCS' in item.value for item in fresh.markdown)
    fresh.checkbox(key=f'clear_dc_block_{tail_id}_dc_output_count').check()
    fresh.checkbox(key=f'clear_dc_block_{tail_id}_max_connected_pcs').check()
    fresh.text_input(key=f'edit_dc_{tail_id}_dc_topology_source_ref').input('')
    next(button for button in fresh.button if button.label == 'Save Changes').click().run()
    assert not fresh.exception

    reopened = _page(url)
    reopened.selectbox(key='edit_dc_block_record').select(record).run()
    assert reopened.number_input(key=f'edit_dc_{tail_id}_dc_output_count').value is None
    assert reopened.number_input(key=f'edit_dc_{tail_id}_max_connected_pcs').value is None
    assert reopened.text_input(key=f'edit_dc_{tail_id}_dc_topology_source_ref').value == ''
    cleared = next(row for row in service.dc_block_maintenance_rows() if row['block_code'] == 'SYN-10')
    assert cleared['dc_output_count'] is None and cleared['max_connected_pcs'] is None
    assert not cleared['dc_topology_source_ref']
    assert service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code').loc['SYN-10', 'Is_Active'] == 0


def test_original_form_rejects_two_pcs_on_ten_string_single_output(catalogue):
    url, service, _, _ = catalogue
    before = service.snapshot()
    page = _page(url)
    _populate_tail(page)
    page.number_input(key='add_dc_dc_output_count').set_value(1)
    page.number_input(key='add_dc_max_connected_pcs').set_value(2)
    page.text_input(key='add_dc_dc_topology_source_ref').input('Synthetic invalid 10-string connection')
    _submit_add(page)
    assert page.error
    assert any('10' in item.value and 'PCS' in item.value for item in page.error)
    assert not page.success
    assert service.snapshot() == before


def test_eight_string_two_outputs_allow_up_to_two_pcs_without_becoming_ready(catalogue):
    url, service, _, _ = catalogue
    page = _page(url)
    _populate_tail(page, strings=8)
    _add_widget(page, 'text_input', 'Block Code *').input('SYN-8')
    page.number_input(key='add_dc_dc_output_count').set_value(2)
    page.number_input(key='add_dc_max_connected_pcs').set_value(2)
    page.text_input(key='add_dc_dc_topology_source_ref').input('User design confirmation: 8-string two outputs')
    _submit_add(page)
    tail = next(row for row in service.dc_block_maintenance_rows() if row['block_code'] == 'SYN-8')
    assert (tail['dc_output_count'], tail['max_connected_pcs']) == (2, 2)
    assert tail['parameter_status'] == 'Incomplete'
    assert 'Excluded from standard sizing' in tail['parameter_details']
    assert tail['nominal_power_kw'] is None
    assert tail['max_current_a'] is None
    assert tail['gross_energy_mwh'] is None
    assert service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code').loc['SYN-8', 'Is_Active'] == 0
    assert any('2 DC outputs / max 2 PCS' in item.value for item in page.markdown)


def test_standard_product_dc_connections_remain_unspecified_until_maintained(catalogue):
    url, service, _, parent = catalogue
    before = service.snapshot()
    page = _page(url)
    for key in ('dc_output_count', 'max_connected_pcs'):
        assert page.number_input(key=f'edit_dc_{parent}_{key}').value is None
        assert page.number_input(key=f'add_dc_{key}').value is None
    assert page.text_input(key=f'edit_dc_{parent}_dc_topology_source_ref').value == ''
    assert page.text_input(key='add_dc_dc_topology_source_ref').value == ''
    assert any('DC connection' in item.value and 'Not specified' in item.value for item in page.markdown)
    assert service.snapshot() == before


def _legacy_connection_tail(catalogue, *, outputs, maximum, source):
    """Bypass the maintenance writer to represent already-stored legacy JSON."""
    url, service, cell, _ = catalogue
    tail_id = service.create_dc_block(dict(block_code='LEGACY-10', block_name='Legacy connection tail',
        block_form='container', product_cell_id=cell, cells_in_series=416,
        strings_in_parallel=10, container_type='20ft ISO container',
        configuration_role='Special tail', parent_block_code='SYN-12'))
    with session_scope(url) as session:
        tail = session.get(ProductDCBlock, tail_id)
        tail.metadata_json = dict(tail.metadata_json or {}, dc_output_count=outputs,
                                  max_connected_pcs=maximum, dc_topology_source_ref=source)
    return tail_id


def _edit_connection_tail(page, prefix='LEGACY-10'):
    record = next(value for value in page.selectbox(key='edit_dc_block_record').options
                  if value.startswith(prefix))
    page.selectbox(key='edit_dc_block_record').select(record).run()
    assert not page.exception


def test_legacy_whole_number_strings_open_without_read_time_catalogue_write(catalogue):
    url, service, _, _ = catalogue
    tail_id = _legacy_connection_tail(catalogue, outputs='1.0', maximum='1.0', source='Legacy user confirmation')
    before = json.dumps(service.snapshot(), default=str, sort_keys=True)
    page = _page(url)
    _edit_connection_tail(page)
    assert page.number_input(key=f'edit_dc_{tail_id}_dc_output_count').value == 1
    assert page.number_input(key=f'edit_dc_{tail_id}_max_connected_pcs').value == 1
    assert page.text_input(key=f'edit_dc_{tail_id}_dc_topology_source_ref').value == 'Legacy user confirmation'
    assert not any('Stored DC connection value needs correction' in message.value for message in page.warning)
    assert any('1 DC output / max 1 PCS' in item.value for item in page.markdown)
    assert json.dumps(service.snapshot(), default=str, sort_keys=True) == before
    next(button for button in page.button if button.label == 'Save Changes').click().run()
    assert not page.exception
    saved = next(row for row in service.snapshot()['dc_blocks'] if row['product_dc_block_id'] == tail_id)
    assert type(saved['metadata_json']['dc_output_count']) is int
    assert type(saved['metadata_json']['max_connected_pcs']) is int


@pytest.mark.parametrize(('outputs', 'maximum', 'source', 'invalid_field'), [
    ('bad', '1', 'Legacy confirmation', 'dc_output_count'),
    ('0', '1', 'Legacy confirmation', 'dc_output_count'),
    ('NaN', '1', 'Legacy confirmation', 'dc_output_count'),
    (float('nan'), '1', 'Legacy confirmation', 'dc_output_count'),
    ('1', 'bad', 'Legacy confirmation', 'max_connected_pcs'),
    ('1', '1', {'drawing': 'not a text reference'}, 'dc_topology_source_ref'),
])
def test_invalid_legacy_connections_open_with_warning_and_can_be_corrected(
        catalogue, outputs, maximum, source, invalid_field):
    url, service, _, _ = catalogue
    tail_id = _legacy_connection_tail(catalogue, outputs=outputs, maximum=maximum, source=source)
    before = json.dumps(service.snapshot(), default=str, sort_keys=True)
    page = _page(url)
    _edit_connection_tail(page)
    assert any('Stored DC connection value needs correction' in message.value for message in page.warning)
    assert any('Needs correction' in item.value for item in page.markdown)
    if invalid_field == 'dc_topology_source_ref':
        assert page.text_input(key=f'edit_dc_{tail_id}_{invalid_field}').value == ''
    else:
        assert page.number_input(key=f'edit_dc_{tail_id}_{invalid_field}').value is None
    row = next(row for row in service.dc_block_maintenance_rows() if row['product_dc_block_id'] == tail_id)
    assert row['parameter_status'] != 'Ready'
    assert row['parameter_details'] in ' '.join(item.value for item in page.caption)
    assert json.dumps(service.snapshot(), default=str, sort_keys=True) == before

    page.number_input(key=f'edit_dc_{tail_id}_dc_output_count').set_value(1)
    page.number_input(key=f'edit_dc_{tail_id}_max_connected_pcs').set_value(1)
    page.text_input(key=f'edit_dc_{tail_id}_dc_topology_source_ref').input('Corrected user design confirmation')
    next(button for button in page.button if button.label == 'Save Changes').click().run()
    assert not page.exception
    saved = next(row for row in service.snapshot()['dc_blocks'] if row['product_dc_block_id'] == tail_id)
    assert saved['metadata_json']['dc_output_count'] == saved['metadata_json']['max_connected_pcs'] == 1
    assert saved['metadata_json']['dc_topology_source_ref'] == 'Corrected user design confirmation'
    fresh = _page(url)
    _edit_connection_tail(fresh)
    assert not any('Stored DC connection value needs correction' in message.value for message in fresh.warning)
