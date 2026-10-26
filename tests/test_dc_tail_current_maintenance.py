"""Current catalogue incompatibilities must not bypass the tail comparison.

All products and database writes here are isolated synthetic test fixtures.
"""
from copy import deepcopy

import pytest

from calb_sizing_tool.services import dc_reduced_string_tail_service as tails
from tests.test_dc_product_maintenance import _catalogue, _tail
from tests.test_dc_reduced_string_tail import example


@pytest.fixture
def current_catalogue(tmp_path, example):
    service, cell_id, parent_id = _catalogue(tmp_path / 'current-tail.sqlite')
    tail_id = service.create_dc_block(_tail(
        gross_energy_mwh=4.179968, nominal_power_kw=2089.984, max_c_rate=0.5,
        dc_output_count=1, max_connected_pcs=1, dc_topology_source_ref='Synthetic owner basis',
        metadata_json=dict(reduced_string_basis_authority=tails.BASIS_AUTHORITY,
                           standard_excel_code=tails.STANDARD_EXCEL_CODE)))
    return service, cell_id, parent_id, tail_id


def _available(service, example):
    return tails.available_products(service.dc_block_maintenance_rows(), example.basis,
                                    tails.STANDARD_EXCEL_CODE)


@pytest.mark.parametrize('changes', [
    {'nominal_voltage_v': 1200}, {'voltage_min_v': 1100}, {'dimension_depth_mm': 6500},
])
def test_parent_structural_edit_removes_current_tail_option(current_catalogue, example, changes):
    service, _, parent_id, _ = current_catalogue
    assert set(_available(service, example)) == {10}
    service.update_record('dc_block', parent_id, changes)
    rows = service.dc_block_maintenance_rows()
    tail = next(row for row in rows if row['block_code'] == 'TEST-TAIL-10')
    assert tail['maintenance_conflicts']
    # Eligibility uses machine fields, never the English display wording.
    tail['parameter_status'] = 'Basic fields present; review pending'
    assert tails.available_products(rows, example.basis, tails.STANDARD_EXCEL_CODE) == {}


@pytest.mark.parametrize('changes', [
    {'nominal_capacity_ah': 500}, {'nominal_voltage_v': 3.7},
    {'is_active': False}, {'is_published': False},
])
def test_same_linked_cell_identity_with_changed_parameters_is_not_eligible(
        current_catalogue, example, changes):
    service, cell_id, _, _ = current_catalogue
    assert set(_available(service, example)) == {10}
    service.update_record('cell', cell_id, changes)
    assert _available(service, example) == {}


def test_unknown_engineering_ratings_do_not_disable_owner_comparison(current_catalogue, example):
    service, _, _, tail_id = current_catalogue
    service.update_record('dc_block', tail_id, dict(max_current_a=None, voltage_min_v=None,
        voltage_max_v=None, dimension_width_mm=None, dimension_depth_mm=None, dimension_height_mm=None))
    product = _available(service, example)[10]
    assert product['parameter_status'] == 'Incomplete'
    assert product['maintenance_conflicts'] == []
    assert product['max_current_a'] is None


def test_unknown_cell_nominal_voltage_retains_explicit_owner_chain_assumption(current_catalogue, example):
    service, cell_id, _, _ = current_catalogue
    service.update_record('cell', cell_id, {'nominal_voltage_v': None})
    product = _available(service, example)[10]
    assert product['linked_cell_snapshot']['nominal_voltage_v'] is None


def test_current_cell_snapshot_rechecks_structure_even_without_reported_conflict(
        current_catalogue, example):
    service, _, _, _ = current_catalogue
    rows = service.dc_block_maintenance_rows()
    tail = next(row for row in rows if row['block_code'] == 'TEST-TAIL-10')
    tail['nominal_voltage_v'] = 1200
    assert tail['maintenance_conflicts'] == []
    assert tails.available_products(rows, example.basis, tails.STANDARD_EXCEL_CODE) == {}


def test_saved_legal_comparison_remains_historical_after_current_catalogue_edit(
        current_catalogue, example):
    service, _, parent_id, _ = current_catalogue
    product = _available(service, example)[10]
    result = tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, product, example.basis)
    saved = deepcopy(example.snapshot)
    saved.summary[tails.SUMMARY_KEY] = deepcopy(result)
    before = saved.model_dump(mode='json')
    service.update_record('dc_block', parent_id, {'nominal_voltage_v': 1200})
    assert _available(service, example) == {}
    assert tails.restored_comparison(saved) == result
    assert saved.model_dump(mode='json') == before


def test_legacy_legal_comparison_without_new_maintenance_fields_still_restores(example):
    product = tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)[10]
    assert 'linked_cell_snapshot' not in product and 'maintenance_conflicts' not in product
    result = tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, product, example.basis)
    saved = deepcopy(example.snapshot)
    saved.summary[tails.SUMMARY_KEY] = result
    assert tails.restored_comparison(saved) == result
