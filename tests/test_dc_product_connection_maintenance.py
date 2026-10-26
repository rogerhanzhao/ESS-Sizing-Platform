"""Synthetic product-interface maintenance, never released equipment ratings."""
from copy import deepcopy
import io

import pandas as pd
import pytest

from tests.test_dc_product_maintenance import catalogue, _catalogue, _record, _tail


SOURCE = 'Synthetic owner design input; not a supplier rating or drawing'


@pytest.mark.parametrize('strings,outputs,pcs', [(10, 1, 1), (8, 2, 2)])
def test_confirmed_tail_interfaces_are_metadata_not_sizing_activation(catalogue, strings, outputs, pcs):
    service, _, _ = catalogue
    product = service.create_dc_block(_tail(strings_in_parallel=strings,
        dc_output_count=outputs, max_connected_pcs=pcs, dc_topology_source_ref=SOURCE))
    saved = _record(service, product)
    assert saved['metadata_json']['dc_output_count'] == outputs
    assert saved['metadata_json']['max_connected_pcs'] == pcs
    assert saved['metadata_json']['dc_topology_source_ref'] == SOURCE
    assert (saved['nominal_power_kw'], saved['max_current_a'], saved['gross_energy_mwh']) == (1700, 1500, 4.1234)
    row = next(row for row in service.dc_block_maintenance_rows() if row['product_dc_block_id'] == product)
    assert row['max_connected_pcs'] == pcs
    assert row['parameter_status'] == 'Incomplete'  # Curve still missing; topology is not approval.
    assert service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code').loc['TEST-TAIL-10', 'Is_Active'] == 0


@pytest.mark.parametrize('field', ['dc_output_count', 'max_connected_pcs'])
@pytest.mark.parametrize('value', [True, False, 0, -1, 1.5, '1.5', 'NaN', 'inf', float('nan'),
                                  float('inf'), [], {}, 2**53, '9007199254740993'])
@pytest.mark.parametrize('channel', ['flat', 'metadata'])
def test_invalid_interface_integers_never_write(catalogue, field, value, channel):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    extra = {field: value} if channel == 'flat' else {'metadata_json': {field: value}}
    with pytest.raises(ValueError, match='positive whole number'):
        service.create_dc_block(_tail(**extra))
    assert service.snapshot() == before


@pytest.mark.parametrize('strings,outputs,pcs', [(10, 2, 1), (10, 1, 2), (8, 1, 2), (8, 2, 1), (8, 3, 2)])
def test_known_tail_interface_conflicts_rejected_in_form_and_import(catalogue, strings, outputs, pcs):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    values = _tail(strings_in_parallel=strings, dc_output_count=outputs, max_connected_pcs=pcs)
    with pytest.raises(ValueError, match=f'{strings}-string special tail requires'):
        service.create_dc_block(values)
    preview = service.preview_import_from_df(pd.DataFrame([values]), entity='dc_block')
    assert len(preview['errors']) == 1 and preview['errors'][0].startswith('Row 2:')
    assert preview['rows'] == []
    assert service.snapshot() == before


@pytest.mark.parametrize('field,other', [('dc_output_count', 2), ('max_connected_pcs', 2),
                                       ('dc_topology_source_ref', 'Other source')])
def test_flat_and_metadata_connection_aliases_must_agree(catalogue, field, other):
    service, _, _ = catalogue
    before = deepcopy(service.snapshot())
    values = dict(dc_output_count=1, max_connected_pcs=1, dc_topology_source_ref=SOURCE)
    values['metadata_json'] = {field: other}
    with pytest.raises(ValueError, match='conflicts with the supplied metadata'):
        service.create_dc_block(_tail(**values))
    assert service.snapshot() == before


def test_connection_partial_edit_clear_and_metadata_alias_roundtrip(catalogue):
    service, _, _ = catalogue
    product = service.create_dc_block(_tail(dc_output_count='1.0', max_connected_pcs=1,
        dc_topology_source_ref='  ' + SOURCE + '  ', metadata_json={'unrelated': {'preserve': True},
        'dc_output_count': 1}))
    service.update_record('dc_block', product, {'block_name': 'Updated name'})
    assert _record(service, product)['metadata_json']['max_connected_pcs'] == 1
    service.update_record('dc_block', product, dict(metadata_json={'dc_topology_source_ref': 'Revised source'}))
    assert _record(service, product)['metadata_json']['dc_topology_source_ref'] == 'Revised source'
    service.update_record('dc_block', product, dict(dc_output_count=None, max_connected_pcs='',
                                                  dc_topology_source_ref=None))
    saved = _record(service, product)['metadata_json']
    assert not {'dc_output_count', 'max_connected_pcs', 'dc_topology_source_ref'} & saved.keys()
    assert saved['unrelated'] == {'preserve': True}
    row = next(row for row in service.dc_block_maintenance_rows() if row['product_dc_block_id'] == product)
    assert 'DC output circuits required' in row['parameter_details']
    assert 'Maximum connected PCS required' in row['parameter_details']
    assert 'DC connection source required' in row['parameter_details']
    assert row['parameter_status'] == 'Incomplete'


def test_tail_metadata_only_conflict_edit_is_not_a_bypass(catalogue):
    service, _, _ = catalogue
    product = service.create_dc_block(_tail(dc_output_count=1, max_connected_pcs=1))
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError, match='10-string special tail requires'):
        service.update_record('dc_block', product, {'metadata_json': {'max_connected_pcs': 2}})
    assert service.snapshot() == before


@pytest.mark.parametrize('metadata', [None, [], '', 0, False])
def test_non_mapping_metadata_cannot_erase_tail_role_or_connections(catalogue, metadata):
    service, _, _ = catalogue
    product = service.create_dc_block(_tail(dc_output_count=1, max_connected_pcs=1))
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError, match='metadata must be a mapping'):
        service.update_record('dc_block', product, {'metadata_json': metadata})
    assert service.snapshot() == before
    frame = service.df_blocks_as_sizing_dataframe().set_index('Dc_Block_Code')
    assert frame.loc['TEST-TAIL-10', 'Is_Active'] == 0


@pytest.mark.parametrize('old,new,count', [(8, 10, 2), (10, 8, 1)])
def test_partial_string_change_cannot_reuse_incompatible_connection_counts(catalogue, old, new, count):
    service, _, _ = catalogue
    product = service.create_dc_block(_tail(strings_in_parallel=old, dc_output_count=count,
        max_connected_pcs=count, dc_topology_source_ref=SOURCE))
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError, match=f'{new}-string special tail requires'):
        service.update_record('dc_block', product, {'strings_in_parallel': new})
    assert service.snapshot() == before


@pytest.mark.parametrize('strings', [8, 10])
def test_standard_records_do_not_infer_or_inherit_tail_connection_rules(catalogue, strings):
    service, _, _ = catalogue
    product = service.create_dc_block(dict(block_code='OTHER-STANDARD', block_name='Another family',
        block_form='container', strings_in_parallel=strings, cells_in_series=400,
        dc_output_count=1, max_connected_pcs=3, dc_topology_source_ref=SOURCE))
    saved = _record(service, product)['metadata_json']
    assert saved['dc_output_count'] == 1 and saved['max_connected_pcs'] == 3
    parent = next(row for row in service.dc_block_maintenance_rows() if row['block_code'] == 'TEST-PARENT-12')
    assert parent['dc_output_count'] is None and parent['max_connected_pcs'] is None
    assert 'DC output circuits required' not in parent['parameter_details']


@pytest.mark.parametrize('changes', [{'strings_in_parallel': 9}, {'cells_in_series': 500},
                                    {'block_form': 'cabinet'}, {'container_type': '40ft'}])
def test_declared_tail_interface_raw_edits_cannot_escape_product_family(catalogue, changes):
    service, _, _ = catalogue
    product = service.create_dc_block(_tail(dc_output_count=1, max_connected_pcs=1))
    before = deepcopy(service.snapshot())
    with pytest.raises(ValueError):
        service.update_record('dc_block', product, changes)
    assert service.snapshot() == before


def test_connection_export_import_and_old_header_are_consistent(catalogue, tmp_path):
    service, _, _ = catalogue
    product = service.create_dc_block(_tail(dc_output_count=1, max_connected_pcs=1,
        dc_topology_source_ref=SOURCE))
    original = _record(service, product)
    exported = service.export_dc_blocks_dataframe()
    fields = ['dc_output_count', 'max_connected_pcs', 'dc_topology_source_ref']
    assert set(fields) <= set(exported)
    csv = pd.read_csv(io.StringIO(exported.loc[exported.block_code == 'TEST-TAIL-10'].to_csv(index=False)), dtype=str)
    target, _, _ = _catalogue(tmp_path / 'new-template.sqlite')
    assert target.import_records_from_df('dc_block', csv) == {'imported': 1, 'skipped': 0, 'errors': []}
    saved = next(row for row in target.snapshot()['dc_blocks'] if row['block_code'] == 'TEST-TAIL-10')
    assert all(saved['metadata_json'][field] == original['metadata_json'][field] for field in fields)
    display = target.dc_block_import_preview_dataframe(target.preview_import_from_df(csv, entity='dc_block')['rows'])
    assert display.iloc[0]['DC outputs'] == 1
    assert display.iloc[0]['Maximum connected PCS'] == 1
    assert display.iloc[0]['DC connection source'] == SOURCE
    legacy, _, _ = _catalogue(tmp_path / 'old-template.sqlite')
    assert legacy.import_records_from_df('dc_block', csv.drop(columns=fields)) == {'imported': 1, 'skipped': 0, 'errors': []}
    old = next(row for row in legacy.dc_block_maintenance_rows() if row['block_code'] == 'TEST-TAIL-10')
    assert old['dc_output_count'] is None and old['max_connected_pcs'] is None
    assert old['parameter_status'] == 'Incomplete'


@pytest.mark.parametrize('value', [[], {}, 42, True])
def test_connection_source_requires_text(catalogue, value):
    service, _, _ = catalogue
    with pytest.raises(ValueError, match='source must be text'):
        service.create_dc_block(_tail(dc_topology_source_ref=value))
