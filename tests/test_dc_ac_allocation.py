"""Integration checks for local D1a mapping, not AC equipment acceptance."""
from copy import deepcopy

import pytest

from calb_sizing_tool.services import dc_ac_allocation_service as service
from calb_sizing_tool.services.dc_composition_manifest_service import dc_composition_manifest_sha256
from tests.dc_ac_allocation_fixture import (
    json_comparison, make_allocation_fixture, resign_comparison,
)


@pytest.fixture
def study(tmp_path):
    return make_allocation_fixture(tmp_path / 'synthetic-allocation.sqlite')


def assess(study, **kwargs):
    options = dict(expected_comparison_sha256=study.expected_comparison_sha256,
                   variant_service=study.library.variants)
    options.update(kwargs)
    return service.assess_dc_ac_allocation(
        study.library.revisions, study.comparison, study.allocation, **options)


def assert_comparison_boundary(result):
    assert result['comparison_only'] is True
    assert result['downstream_ready'] is False
    assert result['discharge_feasibility_status'] == 'not_evaluated'
    assert result['source']['curve_applicability_recertified'] is False
    assert result['pending_evidence']
    assert 'no AC kW' in result['evidence_boundary']


def test_valid_mapping_preserves_actual_box_duties_at_every_level(study):
    result = assess(study)
    assert result['topology_valid'] is True
    assert result['status'] == 'pending_equipment_evidence'
    assert result['dc_duty_status'] == 'passes_declared_dc_limits'
    assert result['source_energy_requirement_met'] is True
    assert result['errors'] == []
    assert_comparison_boundary(result)
    expected = [2000 * 12 / 22, 2000 * 10 / 22]
    assert [row['requested_dc_discharge_kw'] for row in result['port_duties']] == pytest.approx(expected)
    assert [row['requested_dc_discharge_kw'] for row in result['pcs_duties']] == pytest.approx(expected)
    assert result['lv_winding_duties'][0]['upstream_dc_reference_kw'] == pytest.approx(2000)
    assert result['ac_block_duties'][0]['upstream_dc_reference_kw'] == pytest.approx(2000)
    assert result['lv_winding_duties'][0]['pcs_ids'] == ['PCS-01', 'PCS-02']
    assert result['ac_block_duties'][0]['unit_ids'] == ['DC-001', 'DC-002']
    assert result['conservation']['all_levels_conserved'] is True
    assert all(value == pytest.approx(2000)
               for value in result['conservation']['allocated_dc_reference_kw'].values())
    for row in result['lv_winding_duties'] + result['ac_block_duties']:
        assert 'requested_ac_kw' not in row and 'transformer_load_pct' not in row
        assert 'requested_dc_discharge_kw' not in row


def test_json_download_and_in_memory_models_validate_identically(study):
    original = assess(study)
    study.comparison = json_comparison(study.comparison)
    restored = assess(study)
    assert restored == original
    assert restored['source']['candidate_comparison_sha256'] == study.expected_comparison_sha256


def test_assessment_does_not_mutate_inputs_or_persist_catalogue_changes(study):
    original_comparison = deepcopy(study.comparison)
    original_allocation = deepcopy(study.allocation)
    original_catalogue = study.library.admin.snapshot()
    first = assess(study)
    assert assess(study) == first
    assert study.comparison == original_comparison
    assert study.allocation == original_allocation
    assert study.library.admin.snapshot() == original_catalogue


@pytest.mark.parametrize('mutation', ['content', 'self_digest', 'nonfinite'])
def test_modified_comparison_cannot_reuse_retained_identity(study, mutation):
    if mutation == 'content':
        study.comparison['case_input']['poi_power_req_mw'] = 99
    elif mutation == 'self_digest':
        study.comparison['comparison_sha256'] = '0' * 64
    else:
        study.comparison['case_input']['poi_power_req_mw'] = float('nan')
    with pytest.raises(ValueError):
        assess(study)


def test_rehashed_substitute_cannot_replace_separately_retained_identity(study):
    study.comparison['case_input']['project_name'] = 'Substituted comparison'
    resign_comparison(study.comparison)
    study.allocation['source']['candidate_comparison_sha256'] = study.comparison['comparison_sha256']
    with pytest.raises(ValueError, match='retained'):
        assess(study)


def test_oversized_json_integer_duty_is_a_controlled_validation_error(study):
    study.comparison = json_comparison(study.comparison)
    study.comparison['stage1']['dc_power_required_mw'] = 10 ** 1000
    resign_comparison(study.comparison)
    study.expected_comparison_sha256 = study.comparison['comparison_sha256']
    study.allocation['source']['candidate_comparison_sha256'] = study.expected_comparison_sha256
    with pytest.raises(ValueError, match='positive finite DC discharge duty'):
        assess(study)


@pytest.mark.parametrize('digest', ['', 'bad', 'A' * 64, '0' * 64, None])
def test_expected_source_identity_is_mandatory_and_exact(study, digest):
    with pytest.raises(ValueError):
        assess(study, expected_comparison_sha256=digest)


@pytest.mark.parametrize('field', ['candidate_comparison_sha256', 'dc_manifest_sha256'])
def test_allocation_cannot_reference_another_source(study, field):
    study.allocation['source'][field] = '0' * 64
    with pytest.raises(ValueError):
        assess(study)


@pytest.mark.parametrize('change', ['manifest', 'dispatch', 'duty_status', 'product_evidence', 'scope'])
def test_rehashed_source_still_requires_rebuilt_manifest_and_dc_assessment(study, change):
    if change == 'manifest':
        study.comparison['manifest']['physical_units'][1]['gross_energy_mwh'] += .1
    elif change == 'dispatch':
        study.comparison['dispatch']['unit_duties'][1]['requested_discharge_kw'] = 1
    elif change == 'duty_status':
        study.comparison['dc_duty_status'] = 'passes_everything'
    elif change == 'product_evidence':
        study.comparison['evidence'][1]['revision_sha256'] = '0' * 64
    else:
        study.comparison['evidence'][1]['configuration_scope']['special_reason'] = 'Changed scope'
    resign_comparison(study.comparison)
    study.expected_comparison_sha256 = study.comparison['comparison_sha256']
    study.allocation['source']['candidate_comparison_sha256'] = study.expected_comparison_sha256
    with pytest.raises(ValueError):
        assess(study)


@pytest.mark.parametrize('change', ['product_parameters', 'product_retired', 'relation_retired'])
def test_withdrawn_or_changed_source_reviews_cannot_be_mapped(study, change):
    lib = study.library
    if change == 'product_parameters':
        lib.admin.update_record('dc_block', lib.product_ids[10], {'nominal_power_kw': 2000})
    elif change == 'product_retired':
        lib.revisions.transition(lib.revision_ids[10], 'candidate_only', 'retired', 'Synthetic withdrawal')
    else:
        lib.variants.transition(lib.relations[10], 'candidate_only', 'retired', 'Synthetic withdrawal')
    with pytest.raises(ValueError):
        assess(study)


@pytest.mark.parametrize('change', ['product_parameters', 'product_retired', 'relation_retired'])
def test_source_withdrawal_during_mapping_is_rejected(study, monkeypatch, change):
    original = service._duties

    def withdraw(*args, **kwargs):
        result = original(*args, **kwargs)
        lib = study.library
        if change == 'product_parameters':
            lib.admin.update_record('dc_block', lib.product_ids[10], {'nominal_power_kw': 2000})
        elif change == 'product_retired':
            lib.revisions.transition(lib.revision_ids[10], 'candidate_only', 'retired', 'Synthetic withdrawal')
        else:
            lib.variants.transition(lib.relations[10], 'candidate_only', 'retired', 'Synthetic withdrawal')
        return result

    monkeypatch.setattr(service, '_duties', withdraw)
    with pytest.raises(ValueError):
        assess(study)


def test_valid_topology_does_not_hide_underpowered_tail(tmp_path):
    study = make_allocation_fixture(tmp_path / 'underpowered.sqlite', tail_power_kw=400)
    result = assess(study)
    assert result['topology_valid'] is True
    assert result['source_energy_requirement_met'] is True
    assert result['status'] == 'fails_declared_dc_limits'
    assert result['dc_duty_status'] == 'fails_declared_dc_limits'
    assert result['pcs_duties'][1]['requested_dc_discharge_kw'] == pytest.approx(2000 * 10 / 22)
    assert result['errors']
    assert result['conservation']['all_levels_conserved'] is True
    assert_comparison_boundary(result)


def test_valid_topology_does_not_hide_source_energy_failure(tmp_path):
    study = make_allocation_fixture(tmp_path / 'insufficient-energy.sqlite', tail_strings=8)
    result = assess(study)
    assert result['topology_valid'] is True
    assert result['dc_duty_status'] == 'passes_declared_dc_limits'
    assert result['source_energy_requirement_met'] is False
    assert result['status'] == 'fails_source_energy_requirement'
    assert result['errors']
    assert_comparison_boundary(result)


def test_capability_references_are_recorded_without_claiming_approval(study):
    reference = dict(package_code='SYNTHETIC-UNVERIFIED', revision='TEST-1',
                     sha256='a' * 64, evidence_ref='Synthetic unverified equipment reference')
    for equipment in study.allocation['pcs_instances'] + study.allocation['transformer_instances']:
        equipment['capability_ref'] = deepcopy(reference)
    result = assess(study)
    assert result['topology_valid'] is True
    assert result['status'] == 'pending_equipment_evidence'
    assert result['allocation']['pcs_instances'][0]['capability_ref'] == reference
    assert_comparison_boundary(result)


def test_explicit_two_domain_container_keeps_complete_box_duty(tmp_path):
    study = make_allocation_fixture(tmp_path / 'two-outputs.sqlite', split_domains=True)
    result = assess(study)
    assert result['topology_valid'] is True
    assert len(result['domain_connections']) == 4
    assert all(len(row['domain_ids']) == 2 for row in result['port_duties'])
    assert [row['requested_dc_discharge_kw'] for row in result['pcs_duties']] == pytest.approx(
        [2000 * 12 / 22, 2000 * 10 / 22])
    assert result['conservation']['all_levels_conserved'] is True
    assert result['status'] == 'pending_equipment_evidence'
    assert any('parallel' in note.lower() for note in result['pending_evidence'])


def test_invalid_mapping_never_publishes_partial_aggregate_register(study):
    study.allocation['dc_connections'].pop()
    result = assess(study)
    assert result['topology_valid'] is False
    assert result['status'] == 'invalid_mapping'
    assert result['errors']
    assert result['conservation']['all_levels_conserved'] is False
    assert not result['port_duties'] and not result['pcs_duties']
    assert not result['lv_winding_duties'] and not result['ac_block_duties']
    assert_comparison_boundary(result)


def test_missing_explicit_output_partitions_cannot_pass_empty_set_coverage(tmp_path):
    study = make_allocation_fixture(tmp_path / 'missing-outputs.sqlite', explicit_partitions=False)
    result = assess(study)
    assert result['topology_valid'] is False
    assert result['status'] == 'invalid_mapping'
    assert not result['port_duties']
    assert_comparison_boundary(result)


@pytest.mark.parametrize('malformed', [
    'bom_non_dict', 'bom_missing_revision_id', 'bom_quantity_bool',
    'unit_non_dict', 'unit_missing_unit_id', 'domain_non_dict',
    'domain_revision_id_list', 'evidence_non_dict', 'evidence_revision_id_list',
])
def test_resigned_malformed_source_records_raise_controlled_validation_error(study, malformed):
    manifest = study.comparison['manifest']
    if malformed == 'bom_non_dict':
        manifest['bom'][0] = 'invalid BOM row'
    elif malformed == 'bom_missing_revision_id':
        manifest['bom'][0].pop('revision_id')
    elif malformed == 'bom_quantity_bool':
        manifest['bom'][0]['quantity'] = True
    elif malformed == 'unit_non_dict':
        manifest['physical_units'][0] = None
    elif malformed == 'unit_missing_unit_id':
        manifest['physical_units'][0].pop('unit_id')
    elif malformed == 'domain_non_dict':
        manifest['electrical_domains'][0] = False
    elif malformed == 'domain_revision_id_list':
        manifest['electrical_domains'][0]['revision_id'] = ['unhashable identity']
    elif malformed == 'evidence_non_dict':
        study.comparison['evidence'][0] = []
    else:
        study.comparison['evidence'][0]['revision_id'] = ['unhashable identity']
    manifest['manifest_sha256'] = dc_composition_manifest_sha256(manifest)
    resign_comparison(study.comparison)
    study.expected_comparison_sha256 = study.comparison['comparison_sha256']
    study.allocation['source'].update(
        candidate_comparison_sha256=study.expected_comparison_sha256,
        dc_manifest_sha256=manifest['manifest_sha256'],
    )
    with pytest.raises(ValueError, match='records|quantities'):
        assess(study)
