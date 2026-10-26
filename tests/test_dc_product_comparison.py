"""Synthetic, isolated C1 comparison contract; no live database or activation.

These examples are test evidence only, never CALB product performance data.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from calb_sizing_tool.domain.enums import ScenarioMode
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.dc_catalogue_revision_service import DcCatalogueRevisionService
from calb_sizing_tool.services import dc_product_comparison_service as comparison
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.product_admin_service import ProductAdminService
from calb_sizing_tool.services.stage1_service import run_stage1


@pytest.fixture
def candidate(tmp_path):
    db_path = tmp_path / 'synthetic-comparison.sqlite'
    url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    admin = ProductAdminService(url)
    cell_id = admin.create_cell(dict(
        cell_code='SYNTHETIC-CELL-A', model_name='Synthetic test cell A', chemistry='LFP',
        is_active=True, is_published=True))
    admin.create_degradation_curve(dict(
        curve_code='SYNTHETIC-CATALOGUE-CURVE', product_cell_id=cell_id,
        condition_label='Synthetic catalogue link, not runtime performance evidence',
        is_active=True, is_published=True))
    product_id = admin.create_dc_block(dict(
        block_code='SYNTHETIC-CONTAINER-5', block_name='Synthetic 5 MWh comparison container',
        product_cell_id=cell_id, block_form='container', gross_energy_mwh=5.0,
        source_ref='Synthetic test data only', voltage_min_v=1000, voltage_max_v=1500,
        nominal_power_kw=2500, max_current_a=2500, cells_in_series=416,
        strings_in_parallel=12, default_degradation_curve_code='SYNTHETIC-CATALOGUE-CURVE',
        is_active=True, is_published=True))
    actor = AuthUser('synthetic-admin', 'synthetic-reviewer', 'Synthetic Reviewer', ['admin'])
    service = DcCatalogueRevisionService(actor, url)
    revision_id = service.create(product_id, 'SYNTHETIC-R1', 'Synthetic source register')
    service.transition(revision_id, 'draft', 'parameter_review', 'Synthetic parameter review')
    service.transition(revision_id, 'parameter_review', 'candidate_only', 'Synthetic candidate approval')
    detail = service.inspect(revision_id)
    assert detail['candidate_review_current']
    package = dict(
        schema_version=1, package_code='SYNTHETIC-CURVE-PACKAGE', version='TEST-1',
        product_revision_sha256=detail['sha256'], product_cell_id=cell_id,
        review_status='comparison_approved', reviewed_by='synthetic-reviewer',
        approval_ref='Synthetic comparison approval; no engineering release', measurement_boundary='DC',
        conditions=dict(dod_min_pct=90, dod_max_pct=100, temperature_min_c=20,
            temperature_max_c=30, standby_soc_min_pct=40, standby_soc_max_pct=60,
            project_life_max_years=2, rte_adjust_pp=0, rte_monotonic_enforce=True),
        soh_applicability=[dict(Profile_Id=1, c_rate_min=0, c_rate_max=1,
            cycles_min=300, cycles_max=400, evidence_ref='Synthetic SOH scope')],
        rte_applicability=[dict(Profile_Id=1, c_rate_min=0, c_rate_max=1,
            cycles_min=300, cycles_max=400, evidence_ref='Synthetic RTE scope')],
        tables=dict(
            soh_profile=[dict(Profile_Id=1, C_Rate=0.2, Cycles_Per_Year=365)],
            soh_curve=[dict(Profile_Id=1, Life_Year_Index=year, Soh_Dc_Pct=soh)
                       for year, soh in enumerate((100, 95, 90))],
            rte_profile=[dict(Profile_Id=1, C_Rate=0.2)],
            rte_curve=[dict(Profile_Id=1, Soh_Band_Min_Pct=100, Soh_Band_Max_Pct=100,
                            Rte_Dc_Pct=94),
                       dict(Profile_Id=1, Soh_Band_Min_Pct=0, Soh_Band_Max_Pct=100,
                            Rte_Dc_Pct=93)]))
    baseline = DcExcelMasterDataBundle(
        workbook_path=Path('SYNTHETIC-BASELINE.xlsx'), defaults={'synthetic_marker': 'unchanged'},
        df_blocks=pd.DataFrame([
            dict(Dc_Block_Code='SYNTHETIC-BASELINE', Dc_Block_Name='Synthetic baseline container',
                 Block_Form='container', Block_Nameplate_Capacity_Mwh=6.26,
                 Is_Active=1, Is_Default_Option=1),
            dict(Dc_Block_Code='SYNTHETIC-BASELINE-CAB', Dc_Block_Name='Synthetic baseline cabinet',
                 Block_Form='cabinet', Block_Nameplate_Capacity_Mwh=0.418,
                 Is_Active=1, Is_Default_Option=1)]),
        df_soh_profile=pd.DataFrame(deepcopy(package['tables']['soh_profile'])),
        df_soh_curve=pd.DataFrame(deepcopy(package['tables']['soh_curve'])),
        df_rte_profile=pd.DataFrame(deepcopy(package['tables']['rte_profile'])),
        df_rte_curve=pd.DataFrame(deepcopy(package['tables']['rte_curve'])),
        raw_sheets={'Synthetic retained source': pd.DataFrame({'source': ['unchanged']})})
    case = SizingCaseInput(
        project_name='SYNTHETIC C1 comparison', scenario_id=ScenarioMode.CONTAINER_ONLY,
        poi_power_req_mw=2, poi_energy_req_mwh=8, project_life_years=2,
        poi_guarantee_year=2, cycles_per_year=365, sc_time_months=3, dod_pct=95,
        dc_round_trip_efficiency_pct=94, eff_dc_cables=100, eff_pcs=100,
        eff_mvt=100, eff_ac_cables_sw_rmu=100, eff_hvt_others=100)
    return SimpleNamespace(db_path=db_path, url=url, admin=admin, service=service,
        product_id=product_id, cell_id=cell_id, revision_id=revision_id,
        package=package, baseline=baseline, case=case)


def run(candidate, package=None, case=None, **kwargs):
    package = candidate.package if package is None else package
    digest = kwargs.pop('expected_package_sha256', comparison.package_sha256(package))
    return comparison.run_product_comparison(
        candidate.service, candidate.revision_id, candidate.case if case is None else case,
        candidate.baseline, package, digest,
        temperature_c=kwargs.pop('temperature_c', 25),
        standby_soc_pct=kwargs.pop('standby_soc_pct', 50),
        max_iter=kwargs.pop('max_iter', 3), **kwargs)


def forbid_core(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid comparison reached the frozen sizing engine')
    monkeypatch.setattr(comparison, 'size_with_guarantee', unexpected)


def database_contents(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


def assert_bundle_equal(left, right):
    assert left.workbook_path == right.workbook_path
    assert left.defaults == right.defaults
    for name in ('df_blocks', 'df_soh_profile', 'df_soh_curve', 'df_rte_profile', 'df_rte_curve'):
        pd.testing.assert_frame_equal(getattr(left, name), getattr(right, name))
    assert left.raw_sheets.keys() == right.raw_sheets.keys()
    for name in left.raw_sheets:
        pd.testing.assert_frame_equal(left.raw_sheets[name], right.raw_sheets[name])


def test_comparison_matches_direct_frozen_pipeline_without_mutation(candidate):
    original_bundle = deepcopy(candidate.baseline)
    original_case = candidate.case.model_dump(mode='python')
    original_package = deepcopy(candidate.package)
    before_db = database_contents(candidate.db_path)
    direct_bundle = deepcopy(candidate.baseline)
    direct_bundle.df_blocks = pd.DataFrame([dict(
        Dc_Block_Code='SYNTHETIC-CONTAINER-5', Dc_Block_Name='Synthetic 5 MWh comparison container',
        Block_Form='container', Block_Nameplate_Capacity_Mwh=5.0, Is_Active=1, Is_Default_Option=1)])
    for name in ('soh_profile', 'soh_curve', 'rte_profile', 'rte_curve'):
        setattr(direct_bundle, f'df_{name}', pd.DataFrame(deepcopy(candidate.package['tables'][name])))
    stage1 = run_stage1(candidate.case.model_dump(mode='python'), direct_bundle.defaults)
    expected = size_with_guarantee(stage1, 'container_only', direct_bundle, max_iter=3)
    result = run(candidate)
    assert result['snapshot'].model_dump(mode='python') == expected.model_dump(mode='python')
    assert result['comparison_only'] is True
    assert result['downstream_ready'] is False
    assert result['provenance']['revision_sha256'] == candidate.package['product_revision_sha256']
    assert result['provenance']['product_cell_id'] == candidate.cell_id
    assert result['provenance']['package_sha256'] == comparison.package_sha256(candidate.package)
    assert result['provenance']['max_iter'] == 3
    assert len(result['preflight']) == 3
    assert [row['container_count'] for row in result['preflight']] == [2, 3, 4]
    assert result['snapshot'].stage2.container_count == 2
    assert_bundle_equal(candidate.baseline, original_bundle)
    assert candidate.package == original_package
    assert candidate.case.model_dump(mode='python') == original_case
    assert database_contents(candidate.db_path) == before_db


@pytest.mark.parametrize('budget', [1, 60])
def test_comparison_accepts_bounded_budget_endpoints(candidate, budget):
    result = run(candidate, max_iter=budget)
    assert len(result['preflight']) == budget
    assert result['snapshot'].converged


@pytest.mark.parametrize('budget', [0, -1, 61, True, 2.0])
def test_comparison_rejects_invalid_budgets_before_core(candidate, monkeypatch, budget):
    forbid_core(monkeypatch)
    with pytest.raises(ValueError):
        run(candidate, max_iter=budget)


@pytest.mark.parametrize('scenario', [ScenarioMode.CABINET_ONLY, ScenarioMode.HYBRID])
def test_c1_does_not_unlock_other_sizing_paths(candidate, monkeypatch, scenario):
    forbid_core(monkeypatch)
    with pytest.raises(ValueError):
        run(candidate, case=candidate.case.model_copy(update={'scenario_id': scenario}))


@pytest.mark.parametrize('field,value', [
    ('schema_version', 2), ('review_status', 'draft'), ('product_revision_sha256', 'wrong-revision'),
    ('product_cell_id', 'another-same-ah-cell'), ('measurement_boundary', 'AC'),
    ('package_code', ''), ('version', ''), ('reviewed_by', ''), ('approval_ref', '')])
def test_package_identity_and_approval_are_required(candidate, monkeypatch, field, value):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    package[field] = value
    with pytest.raises(ValueError):
        run(candidate, package)


def test_package_digest_rejects_changed_data(candidate, monkeypatch):
    forbid_core(monkeypatch)
    digest = comparison.package_sha256(candidate.package)
    package = deepcopy(candidate.package)
    package['tables']['soh_curve'][1]['Soh_Dc_Pct'] = 94
    with pytest.raises(ValueError):
        run(candidate, package, expected_package_sha256=digest)


def test_package_hash_is_deterministic_and_key_order_independent(candidate):
    reordered = dict(reversed(list(candidate.package.items())))
    assert comparison.package_sha256(candidate.package) == comparison.package_sha256(reordered)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_curve_evidence_cannot_be_hashed(candidate, value):
    package = deepcopy(candidate.package)
    package['tables']['soh_curve'][1]['Soh_Dc_Pct'] = value
    with pytest.raises(ValueError):
        comparison.package_sha256(package)


@pytest.mark.parametrize('action', ['changed', 'retired'])
def test_stale_or_retired_candidate_review_rejected_before_core(candidate, monkeypatch, action):
    forbid_core(monkeypatch)
    if action == 'changed':
        candidate.admin.update_record('dc_block', candidate.product_id, {'gross_energy_mwh': 4.2})
    else:
        candidate.service.transition(candidate.revision_id, 'candidate_only', 'retired', 'Synthetic withdrawal')
    before_db = database_contents(candidate.db_path)
    with pytest.raises(ValueError):
        run(candidate)
    assert database_contents(candidate.db_path) == before_db


@pytest.mark.parametrize('kwargs', [
    {'temperature_c': 19}, {'temperature_c': 31}, {'standby_soc_pct': 39},
    {'standby_soc_pct': 61}, {'standby_soc_pct': -1}, {'standby_soc_pct': 101}])
def test_operating_temperature_and_standby_soc_scope(candidate, monkeypatch, kwargs):
    forbid_core(monkeypatch)
    with pytest.raises(ValueError):
        run(candidate, **kwargs)


@pytest.mark.parametrize('changes', [
    {'dod_pct': 89}, {'project_life_years': 3}, {'cycles_per_year': 401},
    {'rte_curve_adjust_pp': 1}, {'rte_monotonic_enforce': False}])
def test_case_duty_must_match_approved_package(candidate, monkeypatch, changes):
    forbid_core(monkeypatch)
    with pytest.raises(ValueError):
        run(candidate, case=candidate.case.model_copy(update=changes))


@pytest.mark.parametrize('applicability', ['soh_applicability', 'rte_applicability'])
def test_every_potential_augmentation_rate_is_preflighted(candidate, monkeypatch, applicability):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    # The first frozen evaluation converges at 0.2 C, but later potential
    # counts in this budget drop to 0.1333/0.1 C and must already be covered.
    package[applicability][0]['c_rate_min'] = 0.15
    with pytest.raises(ValueError):
        run(candidate, package, max_iter=3)


def test_nearest_profile_is_never_replaced_with_an_approved_but_farther_profile(candidate, monkeypatch):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    package['soh_applicability'][0]['c_rate_min'] = 0.3
    package['tables']['soh_profile'].append(dict(Profile_Id=2, C_Rate=0.4, Cycles_Per_Year=365))
    package['tables']['soh_curve'].extend([
        dict(row, Profile_Id=2) for row in deepcopy(package['tables']['soh_curve'])])
    package['soh_applicability'].append(dict(Profile_Id=2, c_rate_min=0, c_rate_max=1,
        cycles_min=300, cycles_max=400, evidence_ref='Synthetic farther profile'))
    with pytest.raises(ValueError):
        run(candidate, package, max_iter=1)


@pytest.mark.parametrize('kind', ['soh', 'rte'])
def test_ambiguous_nearest_profile_ties_do_not_choose_by_row_order(candidate, monkeypatch, kind):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    package['tables'][f'{kind}_profile'].append(dict(package['tables'][f'{kind}_profile'][0], Profile_Id=2))
    package['tables'][f'{kind}_curve'].extend([
        dict(row, Profile_Id=2) for row in deepcopy(package['tables'][f'{kind}_curve'])])
    package[f'{kind}_applicability'].append(dict(package[f'{kind}_applicability'][0], Profile_Id=2))
    with pytest.raises(ValueError):
        run(candidate, package, max_iter=1)


@pytest.mark.parametrize('problem', ['missing-year', 'duplicate-year', 'nonmonotonic', 'no-year-zero',
                                     'missing-rte-maximum', 'rte-band-gap', 'rte-not-monotonic'])
def test_incomplete_or_implicitly_repaired_curve_tables_are_rejected(candidate, monkeypatch, problem):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    tables = package['tables']
    if problem == 'missing-year':
        tables['soh_curve'] = [row for row in tables['soh_curve'] if row['Life_Year_Index'] != 1]
    elif problem == 'duplicate-year':
        tables['soh_curve'].append(deepcopy(tables['soh_curve'][1]))
    elif problem == 'nonmonotonic':
        tables['soh_curve'][1]['Soh_Dc_Pct'] = 89
    elif problem == 'no-year-zero':
        tables['soh_curve'][0]['Soh_Dc_Pct'] = 99
    elif problem == 'missing-rte-maximum':
        for row in tables['rte_curve']:
            del row['Soh_Band_Max_Pct']
    elif problem == 'rte-band-gap':
        tables['rte_curve'][1]['Soh_Band_Max_Pct'] = 89
    elif problem == 'rte-not-monotonic':
        tables['rte_curve'][1]['Rte_Dc_Pct'] = 95
    with pytest.raises(ValueError):
        run(candidate, package)


def test_rte_coverage_uses_raw_soh_before_display_rounding(candidate, monkeypatch):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    # 89.96% displays as 90.0%, but that must not disguise the source gap.
    package['tables']['soh_curve'][2]['Soh_Dc_Pct'] = 89.96
    package['tables']['rte_curve'][1]['Soh_Band_Min_Pct'] = 90
    with pytest.raises(ValueError):
        run(candidate, package)


@pytest.mark.parametrize('applicability', ['soh_applicability', 'rte_applicability'])
def test_cycles_and_evidence_are_required_for_both_curve_families(candidate, monkeypatch, applicability):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    package[applicability][0]['cycles_max'] = 364
    with pytest.raises(ValueError):
        run(candidate, package)
    package[applicability][0]['cycles_max'] = 400
    package[applicability][0]['evidence_ref'] = ''
    with pytest.raises(ValueError):
        run(candidate, package)


def test_nonconverged_comparison_is_not_a_publishable_result(candidate):
    case = candidate.case.model_copy(update={'poi_energy_req_mwh': 9})
    with pytest.raises(ValueError):
        run(candidate, case=case, max_iter=1)
    result = run(candidate, case=case, max_iter=2)
    assert result['snapshot'].iteration_count == 2
    assert result['snapshot'].stage2.container_count == 3
    assert result['comparison_only'] is True
    assert result['downstream_ready'] is False


def test_mixed_unit_rte_bands_cannot_hide_a_monotonic_repair(candidate, monkeypatch):
    forbid_core(monkeypatch)
    package = deepcopy(candidate.package)
    package['tables']['soh_curve'] = [
        dict(Profile_Id=1, Life_Year_Index=year, Soh_Dc_Pct=soh)
        for year, soh in enumerate((100, 60, 50))]
    # Numeric source sorting puts 50 before 0.9; the frozen engine first
    # normalizes units, orders 0.9 before 0.5 and would then cummin 94 to 93.
    package['tables']['rte_curve'] = [
        dict(Profile_Id=1, Soh_Band_Min_Pct=50, Soh_Band_Max_Pct=100, Rte_Dc_Pct=94),
        dict(Profile_Id=1, Soh_Band_Min_Pct=0.9, Soh_Band_Max_Pct=100, Rte_Dc_Pct=93)]
    with pytest.raises(ValueError):
        run(candidate, package)


def test_legal_mixed_unit_rte_bands_follow_normalized_order(candidate):
    package = deepcopy(candidate.package)
    package['tables']['soh_curve'] = [
        dict(Profile_Id=1, Life_Year_Index=year, Soh_Dc_Pct=soh)
        for year, soh in enumerate((100, 60, 50))]
    package['tables']['rte_curve'] = [
        dict(Profile_Id=1, Soh_Band_Min_Pct=50, Soh_Band_Max_Pct=100, Rte_Dc_Pct=93),
        dict(Profile_Id=1, Soh_Band_Min_Pct=0.9, Soh_Band_Max_Pct=100, Rte_Dc_Pct=94)]
    result = run(candidate, package, case=candidate.case.model_copy(update={'poi_energy_req_mwh': 4}))
    assert result['snapshot'].converged
    assert [row.dc_rte_frac for row in result['snapshot'].stage3.rows] == pytest.approx([0.94, 0.93, 0.93])


def test_positive_product_unit_rounded_to_zero_is_rejected_before_core(candidate, monkeypatch):
    forbid_core(monkeypatch)
    candidate.admin.update_record('dc_block', candidate.product_id, {'gross_energy_mwh': 0.0001})
    revision_id = candidate.service.create(candidate.product_id, 'SYNTHETIC-TINY-R2', 'Synthetic tiny unit test')
    candidate.service.transition(revision_id, 'draft', 'parameter_review', 'Synthetic parameter review')
    candidate.service.transition(revision_id, 'parameter_review', 'candidate_only', 'Synthetic candidate approval')
    candidate.revision_id = revision_id
    candidate.package['product_revision_sha256'] = candidate.service.inspect(revision_id)['sha256']
    case = candidate.case.model_copy(update={'poi_power_req_mw': 1e-8, 'poi_energy_req_mwh': 1e-8})
    # One positive 0.0001 MWh product is sufficient before Stage 2's existing
    # three-decimal rounding, but the actual frozen nameplate becomes zero.
    with pytest.raises(ValueError):
        run(candidate, case=case)


@pytest.mark.parametrize('field,invalid', [
    ('eff_dc_cables', 200), ('eff_pcs', 0), ('dod_pct', 200),
    ('dod_pct', -1), ('dc_round_trip_efficiency_pct', 200),
    ('dc_round_trip_efficiency_pct', -1)])
def test_inherited_invalid_defaults_are_rejected_after_normalization(candidate, monkeypatch, field, invalid):
    forbid_core(monkeypatch)
    candidate.baseline.defaults[field] = invalid
    before = deepcopy(candidate.baseline)
    case = candidate.case.model_copy(update={field: None})
    with pytest.raises(ValueError):
        run(candidate, case=case)
    assert_bundle_equal(candidate.baseline, before)


@pytest.mark.parametrize('field,valid,normalized_field,expected', [
    ('eff_dc_cables', 99, 'eff_dc_cables_frac', 0.99),
    ('dod_pct', 95, 'dod_frac', 0.95),
    ('dc_round_trip_efficiency_pct', 94, 'dc_rte_base_frac', 0.94)])
def test_none_case_values_legitimately_inherit_approved_defaults(candidate, field, valid, normalized_field, expected):
    candidate.baseline.defaults[field] = valid
    case = candidate.case.model_copy(update={field: None})
    result = run(candidate, case=case)
    assert result['snapshot'].converged
    assert getattr(result['snapshot'].stage1, normalized_field) == pytest.approx(expected)


def test_preflight_tracks_frozen_nameplate_rounding_through_augmentation(candidate):
    candidate.admin.update_record('dc_block', candidate.product_id, {'gross_energy_mwh': 5.0004})
    revision_id = candidate.service.create(candidate.product_id, 'SYNTHETIC-ROUNDING-R2', 'Synthetic rounding test')
    candidate.service.transition(revision_id, 'draft', 'parameter_review', 'Synthetic parameter review')
    candidate.service.transition(revision_id, 'parameter_review', 'candidate_only', 'Synthetic candidate approval')
    candidate.revision_id = revision_id
    candidate.package['product_revision_sha256'] = candidate.service.inspect(revision_id)['sha256']
    case = candidate.case.model_copy(update={'poi_energy_req_mwh': 9})
    result = run(candidate, case=case)
    # Frozen Stage 2 rounds the multiplication, not the product before
    # multiplication: 2/3/4 units give 10.001/15.001/20.002 MWh.
    expected_rates = [2 / value for value in (10.001, 15.001, 20.002)]
    assert [row['effective_c_rate'] for row in result['preflight']] == pytest.approx(expected_rates)
    assert result['snapshot'].iteration_count == 2
    assert result['snapshot'].stage2.dc_nameplate_bol_mwh == 15.001
    assert result['snapshot'].stage3.meta.effective_c_rate == pytest.approx(expected_rates[1])


def test_augmentation_can_follow_two_supported_soh_and_rte_profiles(candidate):
    package = deepcopy(candidate.package)
    package['tables']['soh_profile'].append(dict(Profile_Id=2, C_Rate=0.1, Cycles_Per_Year=365))
    package['tables']['soh_curve'].extend([
        dict(Profile_Id=2, Life_Year_Index=year, Soh_Dc_Pct=soh)
        for year, soh in enumerate((100, 92, 85))])
    package['tables']['rte_profile'].append(dict(Profile_Id=2, C_Rate=0.1))
    package['tables']['rte_curve'].extend([
        dict(Profile_Id=2, Soh_Band_Min_Pct=100, Soh_Band_Max_Pct=100, Rte_Dc_Pct=93),
        dict(Profile_Id=2, Soh_Band_Min_Pct=0, Soh_Band_Max_Pct=100, Rte_Dc_Pct=92)])
    for family in ('soh', 'rte'):
        package[f'{family}_applicability'].append(dict(
            package[f'{family}_applicability'][0], Profile_Id=2,
            evidence_ref=f'Synthetic supported second {family} profile'))
    case = candidate.case.model_copy(update={'poi_energy_req_mwh': 9})
    result = run(candidate, package, case=case)
    assert [(row['soh_profile_id'], row['rte_profile_id']) for row in result['preflight']] == [(1, 1), (2, 2), (2, 2)]
    assert result['snapshot'].converged
    assert result['snapshot'].iteration_count == 2
    assert result['snapshot'].stage3.meta.soh_profile_id == 2
    assert result['snapshot'].stage3.meta.rte_profile_id == 2


@pytest.mark.parametrize('broken', ['conditions', 'curve_rows'])
def test_malformed_package_shapes_raise_validation_errors_before_core(candidate, monkeypatch, broken):
    package = deepcopy(candidate.package)
    if broken == 'conditions':
        package['conditions'] = []
    else:
        package['tables']['soh_curve'] = [None, 1]
    forbid_core(monkeypatch)
    with pytest.raises(ValueError):
        run(candidate, package)
