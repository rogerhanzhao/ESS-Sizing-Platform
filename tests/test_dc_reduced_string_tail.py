"""Bounded original-page tail comparisons; synthetic curves are not warranties."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle
from calb_sizing_tool.services import dc_reduced_string_tail_service as tails
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from calb_sizing_tool.services.stage1_service import run_stage1
from calb_sizing_tool.services.stage2_service import build_config_container_only
from calb_sizing_tool.services.stage3_service import run_stage3


@pytest.fixture
def example():
    raw = {
        'battery_cell_type_314_data': pd.DataFrame([dict(Cell_Type_Id=1, Cell_Model='CALB_314Ah_LFP_G1',
            Cell_Capacity_Ah=314, Cell_Nominal_Voltage_V=3.2, Cell_Energy_Wh=1004.8)]),
        'pack_type_314_data': pd.DataFrame([dict(Pack_Type_Id=1, Cell_Type_Id=1,
            Cells_In_Series=104, Cells_In_Parallel=1)]),
        'rack_type_314_data': pd.DataFrame([dict(Rack_Type_Id=1, Pack_Type_Id=1, Packs_Per_Rack=4)]),
        'dc_block_template_314_data': pd.DataFrame([dict(Dc_Block_Code=tails.STANDARD_EXCEL_CODE,
            Dc_Block_Name='Standard main', Block_Form='container', Container_Length_Ft=20,
            Rack_Type_Id=1, Racks_Per_Block=12, Block_Nameplate_Capacity_Mwh=5,
            Is_Active=1, Is_Default_Option=1)])}
    bundle = DcExcelMasterDataBundle(workbook_path=Path('synthetic-original-chain.xlsx'), defaults={},
        raw_sheets=raw, df_blocks=raw['dc_block_template_314_data'].assign(Block_Nameplate_Capacity_Mwh=5.016),
        df_soh_profile=pd.DataFrame([dict(Profile_Id=key, C_Rate=rate, Cycles_Per_Year=365)
                                    for key, rate in ((1, 0.25), (2, 0.5))]),
        df_soh_curve=pd.DataFrame([dict(Profile_Id=key, Life_Year_Index=year, Soh_Dc_Pct=soh)
            for key in (1, 2) for year, soh in enumerate((100, 95, 80))]),
        df_rte_profile=pd.DataFrame([dict(Profile_Id=key, C_Rate=rate) for key, rate in ((1, 0.25), (2, 0.5))]),
        df_rte_curve=pd.DataFrame([dict(Profile_Id=key, Soh_Band_Min_Pct=0, Rte_Dc_Pct=94) for key in (1, 2)]))
    stage1 = run_stage1(dict(project_name='Synthetic local test', poi_power_req_mw=2, poi_energy_req_mwh=6,
        project_life_years=2, poi_guarantee_year=2, cycles_per_year=365, sc_time_months=3,
        dod_pct=95, dc_round_trip_efficiency_pct=94, eff_dc_cables=100, eff_pcs=100,
        eff_mvt=100, eff_ac_cables_sw_rmu=100, eff_hvt_others=100), {})
    snapshot = size_with_guarantee(stage1, 'container_only', bundle)
    basis = tails.derive_reduced_string_basis(bundle)
    parent = dict(block_code='CATALOGUE-12', block_name='Maintained main', product_cell_id='exact-cell-A',
        cells_in_series=416, strings_in_parallel=12, block_form='container', container_type='20ft ISO container',
        gross_energy_mwh=5.01596, is_active=True, is_published=True, metadata_json={})
    rows = [parent]
    for strings in (10, 8):
        info = basis['tails'][strings]
        rows.append(dict(block_code=f'CATALOGUE-{strings}R', block_name=f'{strings}-string tail',
            product_cell_id='exact-cell-A', configuration_role='special_tail', parent_block_code='CATALOGUE-12',
            cells_in_series=416, strings_in_parallel=strings, block_form='container', container_type='20ft ISO container',
            gross_energy_mwh=info['energy_raw_mwh'], nominal_power_kw=info['power_kw'], max_c_rate=0.5,
            max_current_a=None, is_active=True, is_published=True, source_ref='Owner local test basis',
            metadata_json=dict(reduced_string_basis_authority=tails.BASIS_AUTHORITY,
                standard_excel_code=tails.STANDARD_EXCEL_CODE, dc_output_count=info['dc_output_count'],
                max_connected_pcs=info['max_connected_pcs'], dc_topology_source_ref='Owner connection clarification')))
    return SimpleNamespace(bundle=bundle, snapshot=snapshot, basis=basis, rows=rows)


def selected(example, strings=10):
    return tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)[strings]


def evaluate(example, strings=10):
    return tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, selected(example, strings), example.basis)


def saved_parent(example, result):
    parent = deepcopy(example.snapshot)
    parent.summary[tails.SUMMARY_KEY] = deepcopy(result)
    return parent


def resign(result):
    result['comparison_sha256'] = _hash_payload({key: value for key, value in result.items() if key != 'comparison_sha256'})


def test_original_capacity_chain_and_owner_power(example):
    basis = example.basis
    assert basis['main_energy_raw_mwh'] == pytest.approx(5.0159616)
    assert basis['main_energy_mwh'] == 5.016
    assert basis['tails'][10]['energy_raw_mwh'] == pytest.approx(4.179968)
    assert basis['tails'][10]['energy_mwh'] == 4.18
    assert basis['tails'][10]['power_kw'] == pytest.approx(2089.984)
    assert basis['tails'][8]['energy_raw_mwh'] == pytest.approx(3.3439744)
    assert basis['tails'][8]['energy_mwh'] == 3.344
    assert basis['tails'][8]['power_kw'] == pytest.approx(1671.9872)


@pytest.mark.parametrize('change', ['missing_source', 'wrong_cell_energy', 'wrong_series', 'wrong_main'])
def test_capacity_chain_known_conflicts_rejected(example, change):
    bundle = deepcopy(example.bundle)
    if change == 'missing_source':
        del bundle.raw_sheets['pack_type_314_data']
    elif change == 'wrong_cell_energy':
        bundle.raw_sheets['battery_cell_type_314_data'].loc[0, 'Cell_Energy_Wh'] = 999
    elif change == 'wrong_series':
        bundle.raw_sheets['pack_type_314_data'].loc[0, 'Cells_In_Series'] = 100
    else:
        bundle.raw_sheets['dc_block_template_314_data'].loc[0, 'Racks_Per_Block'] = 10
    with pytest.raises(ValueError):
        tails.derive_reduced_string_basis(bundle)


@pytest.mark.parametrize('field,value', [('is_active', False), ('is_published', False),
    ('product_cell_id', 'different-314-Ah-cell'), ('cells_in_series', 400),
    ('gross_energy_mwh', 4.167), ('nominal_power_kw', 2500), ('max_c_rate', 1),
    ('parent_block_code', 'another-parent')])
def test_tail_catalogue_parameters_cannot_be_bypassed(example, field, value):
    example.rows[1][field] = value
    assert 10 not in tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)


def test_parent_cell_identity_comes_from_actual_parent_not_claimed_metadata(example):
    example.rows[0]['product_cell_id'] = 'actual-other-cell'
    example.rows[1]['metadata_json']['parent_product_cell_id'] = 'exact-cell-A'
    assert tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE) == {}


def test_exact_parent_or_explicit_excel_mapping_required(example):
    assert set(tails.available_products(example.rows, example.basis, 'CATALOGUE-12')) == {8, 10}
    assert tails.available_products(example.rows, example.basis, 'similar-main-name') == {}
    del example.rows[1]['metadata_json']['standard_excel_code']
    assert 10 not in tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)
    assert 10 in tails.available_products(example.rows, example.basis, 'CATALOGUE-12')


def test_duplicate_valid_tail_is_ambiguous_and_not_available(example):
    duplicate = deepcopy(example.rows[1])
    duplicate['block_code'] = 'SECOND-10R'
    example.rows.append(duplicate)
    assert set(tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)) == {8}


def test_10_string_two_pcs_is_rejected_but_8_two_pcs_allowed(example):
    example.rows[1]['metadata_json']['max_connected_pcs'] = 2
    assert set(tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)) == {8}


@pytest.mark.parametrize('label,accepted', [('20ft ISO container', True), ('20 feet container', True),
                                         ('20ftXYZ', False), ('40ft container', False)])
def test_runtime_reuses_exact_maintenance_container_terms(example, label, accepted):
    example.rows[1]['container_type'] = label
    assert (10 in tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)) is accepted


@pytest.mark.parametrize('value,accepted', [('1.0', True), (1.0, True), (True, False),
                                         (1.5, False), ('NaN', False)])
def test_runtime_reuses_maintenance_connection_integer_parser(example, value, accepted):
    example.rows[1]['metadata_json']['dc_output_count'] = value
    assert (10 in tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)) is accepted


def test_invalid_connection_source_is_not_converted_to_text(example):
    example.rows[1]['metadata_json']['dc_topology_source_ref'] = {'not': 'a source reference'}
    assert 10 not in tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)


@pytest.mark.parametrize('strings', [10, 8])
def test_one_tail_actual_bom_curve_and_standard_snapshot_unchanged(example, strings):
    original = example.snapshot.model_dump(mode='json')
    result = evaluate(example, strings)
    assert example.snapshot.model_dump(mode='json') == original
    assert result['comparison_only'] is True and result['downstream_ready'] is False
    assert result['snapshot']['stage2']['mode'] == tails.COMPARISON_MODE
    bom = result['snapshot']['stage2']['block_config_items']
    assert [row['count'] for row in bom] == [example.snapshot.stage2.container_count - 1, 1]
    assert bom[1]['block_code'] == f'CATALOGUE-{strings}R'
    assert result['snapshot']['stage2']['dc_nameplate_bol_mwh'] == pytest.approx(
        5.016 * (example.snapshot.stage2.container_count - 1) + example.basis['tails'][strings]['energy_mwh'])
    assert len(result['curve_table_sha256']) == 4
    assert result['output_partition_pending'] is (strings == 8)
    assert tails.restored_comparison(saved_parent(example, result)) == result


@pytest.mark.parametrize('main_code,unit', [(tails.STANDARD_EXCEL_CODE, 5.016), ('CATALOGUE-12', 5.01596)])
def test_excel_and_admin_fleet_totals_retain_original_unit_precision(example, main_code, unit):
    example.snapshot.stage2 = build_config_container_only(95.5 * unit, unit, main_code, 'Main container')
    example.snapshot.stage3 = run_stage3(example.snapshot.stage1, example.snapshot.stage2, example.bundle)
    product = tails.available_products(example.rows, example.basis, main_code)[10]
    result = tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, product, example.basis)
    assert example.snapshot.stage2.container_count == 96
    assert example.snapshot.stage2.dc_nameplate_bol_mwh == round(96 * unit, 3)
    assert result['snapshot']['stage2']['dc_nameplate_bol_mwh'] == round(95 * unit + 4.18, 3)
    assert tails.restored_comparison(saved_parent(example, result)) == result


def test_single_main_cannot_become_tail_only(example):
    example.snapshot.stage2.container_count = 1
    with pytest.raises(ValueError, match='at least two'):
        evaluate(example)


def test_nominal_power_and_lifetime_remaining_capacity_rate_are_separate(example):
    # BOL nominal rate can pass although the same discharge duty exceeds 0.5C
    # against remaining capacity at year 2. This is not a hardware derating model.
    example.snapshot.stage1.poi_power_req_mw = 4.3
    example.snapshot.stage1.dc_power_required_mw = 4.3
    result = evaluate(example)
    assert result['meets_nominal_dc_power']
    assert result['annual_current_capacity_rate_review'][-1]['within_0_5c_current_capacity'] is False
    assert result['lifetime_power_guaranteed'] is False
    assert result['ac_power_matching_pending'] is True
    example.snapshot.stage1.poi_power_req_mw = 5
    example.snapshot.stage1.dc_power_required_mw = 5
    assert evaluate(example)['meets_nominal_dc_power'] is False


def test_energy_failure_retains_diagnostic_comparison_instead_of_adding_boxes(example):
    example.snapshot.stage1.poi_energy_req_mwh = 100
    result = evaluate(example)
    assert result['meets_guarantee_year_energy'] is False
    assert result['snapshot']['stage2']['container_count'] == example.snapshot.stage2.container_count


def test_actual_c_rate_reselects_original_profile(example):
    example.snapshot.stage1.poi_power_req_mw = 3.6
    example.snapshot.stage1.dc_power_required_mw = 3.6
    assert example.snapshot.stage3.meta.soh_profile_id == 1
    result = evaluate(example, 8)
    assert result['snapshot']['stage3']['meta']['soh_profile_id'] == 2


@pytest.mark.parametrize('guarantee_year', [10, 20])
@pytest.mark.parametrize('strings', [10, 8])
def test_tail_bol_pass_cannot_hide_later_guarantee_failure_or_replace_standard(
        example, guarantee_year, strings):
    # A real 20-year table avoids an accidental last-point extrapolation in this
    # fixture. Both standard boxes pass the chosen guarantee year; replacing one
    # by either tail passes at BOL but fails the actual energy checkpoint.
    example.bundle.df_soh_curve = pd.DataFrame([
        dict(Profile_Id=profile, Life_Year_Index=year, Soh_Dc_Pct=100 - 1.75 * year)
        for profile in (1, 2) for year in range(21)])
    fraction = 0.98 * 0.95 * (0.94 ** 0.5) * (1 - 0.0175 * guarantee_year)
    requirement = ((2 * 5.016 + 5.016 + 4.18) / 2) * fraction
    stage1 = run_stage1(dict(project_name='Synthetic later-year guarantee',
        poi_power_req_mw=2, poi_energy_req_mwh=requirement, project_life_years=20,
        poi_guarantee_year=guarantee_year, cycles_per_year=365, sc_time_months=3,
        dod_pct=95, dc_round_trip_efficiency_pct=94, eff_dc_cables=100, eff_pcs=100,
        eff_mvt=100, eff_ac_cables_sw_rmu=100, eff_hvt_others=100), {})
    example.snapshot = size_with_guarantee(stage1, 'container_only', example.bundle)
    original = example.snapshot.model_dump(mode='json')
    assert example.snapshot.converged and example.snapshot.stage2.container_count == 2
    result = evaluate(example, strings)
    rows = result['snapshot']['stage3']['rows']
    checkpoint = next(row for row in rows if row['year_index'] == guarantee_year)
    assert rows[0]['poi_usable_energy_mwh'] > requirement
    assert checkpoint['poi_usable_energy_mwh'] < requirement
    assert checkpoint['is_guarantee_year'] is True
    assert result['guarantee_year'] == guarantee_year
    assert result['poi_energy_at_guarantee_year_mwh'] == checkpoint['poi_usable_energy_mwh']
    assert result['meets_guarantee_year_energy'] is False
    assert result['snapshot']['converged'] is False
    assert result['snapshot']['stage2']['container_count'] == 2
    assert example.snapshot.model_dump(mode='json') == original
    assert tails.restored_comparison(saved_parent(example, result)) == result


def test_curve_reselection_uses_actual_new_soh_and_rte_instead_of_scaling_old_curve(example):
    example.bundle.df_soh_curve.loc[
        (example.bundle.df_soh_curve['Profile_Id'] == 2)
        & (example.bundle.df_soh_curve['Life_Year_Index'] == 2), 'Soh_Dc_Pct'] = 60
    example.bundle.df_rte_curve.loc[
        example.bundle.df_rte_curve['Profile_Id'] == 2, 'Rte_Dc_Pct'] = 88
    example.snapshot.stage1.poi_power_req_mw = 3.6
    example.snapshot.stage1.dc_power_required_mw = 3.6
    example.snapshot.stage3 = run_stage3(
        example.snapshot.stage1, example.snapshot.stage2, example.bundle)
    original = example.snapshot.model_dump(mode='json')
    result = evaluate(example, 8)
    comparison = result['snapshot']['stage3']
    assert example.snapshot.stage3.meta.soh_profile_id == 1
    assert comparison['meta']['soh_profile_id'] == 2
    assert comparison['meta']['rte_profile_id'] == 2
    assert comparison['meta']['effective_c_rate'] > example.snapshot.stage3.meta.effective_c_rate
    assert comparison['rows'][-1]['soh_relative'] == 0.6
    assert comparison['rows'][-1]['dc_rte_frac'] == 0.88
    expected = (5.016 + 3.344) * 0.98 * 0.95 * (0.88 ** 0.5) * 0.6
    actual = comparison['rows'][-1]['poi_usable_energy_mwh']
    naive_scaled_standard = (example.snapshot.stage3.rows[-1].poi_usable_energy_mwh
                             * (5.016 + 3.344) / (2 * 5.016))
    assert actual == pytest.approx(expected)
    assert actual != pytest.approx(naive_scaled_standard)
    assert result['meets_guarantee_year_energy'] is False
    assert example.snapshot.model_dump(mode='json') == original
    assert tails.restored_comparison(saved_parent(example, result)) == result


@pytest.mark.parametrize('invalid_field,invalid_value', [
    ('gross_energy_mwh', 4.167), ('nominal_power_kw', 2500)])
def test_invalid_duplicate_does_not_hide_valid_product_or_mutate_catalogue(
        example, invalid_field, invalid_value):
    invalid = deepcopy(example.rows[1])
    invalid['block_code'] = 'INVALID-10R'
    invalid[invalid_field] = invalid_value
    example.rows.append(invalid)
    original = deepcopy(example.rows)
    available = tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)
    assert set(available) == {8, 10}
    assert available[10]['block_code'] == 'CATALOGUE-10R'
    available[10]['metadata_json']['dc_output_count'] = 99
    available[10]['_tail_parent']['product_cell_id'] = 'changed-by-consumer'
    assert example.rows == original


def test_missing_selected_soh_curve_rejected(example):
    example.bundle.df_soh_curve = example.bundle.df_soh_curve.iloc[:1].copy()
    with pytest.raises(ValueError, match='no degradation curve'):
        evaluate(example)


def test_standard_restore_has_no_comparison_and_no_new_key(example):
    before = example.snapshot.model_dump(mode='json')
    assert tails.restored_comparison(example.snapshot) is None
    assert example.snapshot.model_dump(mode='json') == before


@pytest.mark.parametrize('change', ['digest', 'parent', 'adoption', 'bom', 'summary', 'annual_rate'])
def test_saved_comparison_rejects_changed_content_or_linkage(example, change):
    result = evaluate(example)
    parent = saved_parent(example, result)
    stored = parent.summary[tails.SUMMARY_KEY]
    if change == 'digest':
        stored['nominal_dc_power_mw'] += 1
    elif change == 'parent':
        parent.stage1.poi_power_req_mw += 1
    elif change == 'adoption':
        stored['downstream_ready'] = True
        resign(stored)
    elif change == 'bom':
        stored['snapshot']['stage2']['block_config_items'][1]['count'] = 2
        resign(stored)
    elif change == 'summary':
        stored['meets_guarantee_year_energy'] = not stored['meets_guarantee_year_energy']
        resign(stored)
    else:
        stored['annual_current_capacity_rate_review'][0]['within_0_5c_current_capacity'] = False
        resign(stored)
    with pytest.raises(ValueError):
        tails.restored_comparison(parent)
