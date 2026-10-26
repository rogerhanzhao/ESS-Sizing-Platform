"""Physical failure modes for the local, non-release D1b discharge check."""
from copy import deepcopy
import json
import sqlite3

import pytest

from pydantic import ValidationError

from calb_sizing_tool.schemas.ac_equipment_capability import DischargeDutyBasis
from calb_sizing_tool.services import dc_ac_equipment_assessment_service as service
from tests.dc_ac_allocation_fixture import json_comparison
from tests.dc_ac_equipment_fixture import make_equipment_fixture, replace_equipment_package


@pytest.fixture
def study(tmp_path):
    return make_equipment_fixture(tmp_path / 'synthetic-equipment.sqlite')


def assess(study, **kwargs):
    options = dict(expected_comparison_sha256=study.expected_comparison_sha256,
                   duty_basis=study.duty_basis, variant_service=study.lib.variants)
    options.update(kwargs)
    return service.assess_dc_ac_equipment(
        study.lib.revisions, study.comparison, study.allocation,
        study.capability_service, **options)


def checks(result, name, equipment=None):
    return [row for row in result['checks'] if row['check'] == name
            and (equipment is None or row['equipment_id'] == equipment)]


def assert_check(result, name, status, equipment=None):
    selected = checks(result, name, equipment)
    assert selected, name
    assert {row['status'] for row in selected} == {status}, selected
    return selected


def assert_release_blocked(result):
    assert result['comparison_only'] is True
    assert result['downstream_ready'] is False
    assert result['status'] != 'pass'
    assert any('charging' in value for value in result['pending_evidence'])
    assert any('terminal voltage' in value for value in result['pending_evidence'])


def test_reviewed_ratings_can_pass_reference_checks_without_releasing_full_engineering(study):
    result = assess(study)
    assert result['status'] == 'pending_engineering_evidence'
    assert result['declared_discharge_check_status'] == 'pending_evidence'
    assert result['topology_valid'] is True
    assert result['errors'] == []
    assert result['dc_duty_status'] == 'passes_declared_dc_limits'
    assert result['source_energy_requirement_met'] is True
    for name in ('pcs_ac_active_power', 'pcs_ac_apparent_power', 'aggregate_dc_current_reference',
                 'port_dc_input_power', 'lv_winding_apparent_power', 'total_transformer_apparent_power'):
        assert_check(result, name, 'pass')
    assert_check(result, 'terminal_voltage_drop', 'pending')
    assert_release_blocked(result)


def test_signed_nonunity_efficiency_chain_keeps_three_power_boundaries_distinct(tmp_path):
    study = make_equipment_fixture(
        tmp_path / 'synthetic-losses.sqlite', cable_eff_pct=96, pcs_eff_pct=95)
    result = assess(study)
    bounds = result['power_boundaries']
    assert bounds['upstream_dc_reference_kw'] == pytest.approx(2000 / .96 / .95)
    assert bounds['pcs_input_reference_kw'] == pytest.approx(2000 / .95)
    assert bounds['pcs_ac_reference_kw'] == pytest.approx(2000)
    assert bounds['poi_reference_kw'] == pytest.approx(2000)
    assert bounds['signed_poi_chain_conserved'] is True
    assert sum(row['pcs_ac_reference_kva'] for row in result['pcs_duties']) == pytest.approx(2000 / .95)
    for row in result['pcs_duties']:
        assert row['upstream_dc_reference_kw'] > row['pcs_input_reference_kw'] > row['pcs_ac_reference_kw']
    assert_release_blocked(result)


def test_pcs_kw_headroom_does_not_hide_apparent_power_overload(study):
    replace_equipment_package(study, 'PCS-01', lambda pack: pack['pcs'].update(
        ac_discharge_power_kw=1100, ac_apparent_power_kva=1120))
    result = assess(study)
    assert_check(result, 'pcs_ac_active_power', 'pass', 'PCS-01')
    assert_check(result, 'pcs_ac_apparent_power', 'fail', 'PCS-01')
    assert result['status'] == 'fails_discharge_checks'


@pytest.mark.parametrize('field,check_name', [
    ('dc_discharge_power_kw', 'pcs_dc_input_power'),
    ('continuous_dc_current_a', 'aggregate_dc_current_reference'),
])
def test_adequate_ports_do_not_override_insufficient_whole_pcs_limit(study, field, check_name):
    replace_equipment_package(study, 'PCS-01', lambda pack: pack['pcs'].update({field: 500}))
    result = assess(study)
    assert_check(result, 'port_dc_input_power', 'pass')
    assert_check(result, 'port_dc_current_reference', 'pass')
    assert_check(result, check_name, 'fail', 'PCS-01')
    assert result['status'] == 'fails_discharge_checks'


def test_independent_port_current_limits_cannot_hide_an_aggregate_current_shortfall(tmp_path):
    study = make_equipment_fixture(tmp_path / 'synthetic-two-input-current.sqlite', split_outputs=True)
    replace_equipment_package(study, 'PCS-01', lambda package:
        package['pcs'].update(continuous_dc_current_a=700))
    result = assess(study)
    assert_check(result, 'port_dc_current_reference', 'pass')
    assert_check(result, 'aggregate_dc_current_reference', 'fail', 'PCS-01')
    assert_check(result, 'input_bus_topology', 'pass')
    assert result['status'] == 'fails_discharge_checks'


def test_large_whole_pcs_capacity_does_not_override_one_small_input_port(study):
    replace_equipment_package(study, 'PCS-01', lambda package:
        package['pcs']['ports'][0].update(discharge_power_kw=500))
    result = assess(study)
    assert_check(result, 'pcs_dc_input_power', 'pass')
    assert_check(result, 'port_dc_input_power', 'fail', 'PCS-01/IN-1')
    assert result['status'] == 'fails_discharge_checks'


@pytest.mark.parametrize('scope', ['pcs', 'port'])
@pytest.mark.parametrize('end', ['minimum', 'maximum'])
def test_equipment_voltage_window_must_contain_both_source_endpoints(study, scope, end):
    def narrower(package):
        target = package['pcs'] if scope == 'pcs' else package['pcs']['ports'][0]
        target[('dc_' if scope == 'pcs' else '') + 'voltage_' + ('min_v' if end == 'minimum' else 'max_v')] = (
            1200 if end == 'minimum' else 1400)
    replace_equipment_package(study, 'PCS-01', narrower)
    result = assess(study)
    selected = checks(result, f'{scope}_nameplate_{end}_voltage')
    assert next(row for row in selected if row['equipment_id'].startswith('PCS-01/'))['status'] == 'fail'
    assert next(row for row in selected if row['equipment_id'].startswith('PCS-02/'))['status'] == 'pass'
    opposite = 'maximum' if end == 'minimum' else 'minimum'
    assert_check(result, f'{scope}_nameplate_{opposite}_voltage', 'pass')
    assert result['status'] == 'fails_discharge_checks'


def test_source_voltage_endpoint_equality_passes_nameplate_screen_but_not_terminal_screen(study):
    def exact(package):
        package['pcs'].update(dc_voltage_min_v=1164.8, dc_voltage_max_v=1497.6)
        package['pcs']['ports'][0].update(voltage_min_v=1164.8, voltage_max_v=1497.6)
    replace_equipment_package(study, 'PCS-01', exact)
    result = assess(study)
    for prefix in ('pcs', 'port'):
        for endpoint in ('minimum', 'maximum'):
            assert_check(result, f'{prefix}_nameplate_{endpoint}_voltage', 'pass')
    assert_check(result, 'terminal_voltage_drop', 'pending')


def test_total_transformer_capacity_does_not_average_an_undersized_lv_winding(study):
    study.allocation['lv_windings'].append(dict(
        transformer_id='TX-01', winding_id='LV-2', lv_bus_id='LV-BUS-02'))
    study.allocation['lv_connections'][1]['winding_id'] = 'LV-2'
    def unequal(package):
        package['transformer']['windings'] = [
            dict(winding_id='LV-1', voltage_v=690, continuous_kva=500),
            dict(winding_id='LV-2', voltage_v=690, continuous_kva=4500),
        ]
    replace_equipment_package(study, 'TX-01', unequal)
    result = assess(study)
    assert_check(result, 'total_transformer_apparent_power', 'pass', 'TX-01')
    assert_check(result, 'lv_winding_apparent_power', 'fail', 'TX-01/LV-1')
    assert_check(result, 'lv_winding_apparent_power', 'pass', 'TX-01/LV-2')
    assert result['status'] == 'fails_discharge_checks'


def test_unknown_winding_rating_is_not_filled_from_total_transformer_capacity(study):
    replace_equipment_package(study, 'TX-01', lambda package:
        package['transformer']['windings'][0].update(continuous_kva=None))
    result = assess(study)
    assert_check(result, 'total_transformer_apparent_power', 'pass')
    assert_check(result, 'lv_winding_apparent_power', 'pending')
    assert result['winding_duties'][0]['declared_winding_kva'] is None


def test_unknown_power_factor_never_defaults_to_unity_for_pcs_or_transformer(study):
    study.duty_basis['power_factor_abs'] = None
    result = assess(study)
    assert all(row['pcs_ac_reference_kva'] is None for row in result['pcs_duties'])
    assert all(row['lv_ac_reference_kva'] is None for row in result['winding_duties'])
    assert all(row['lv_ac_reference_kva'] is None for row in result['transformer_duties'])
    for name in ('pcs_ac_apparent_power', 'lv_winding_apparent_power', 'total_transformer_apparent_power'):
        assert_check(result, name, 'pending')
    assert result['status'] == 'pending_engineering_evidence'


@pytest.mark.parametrize('power_factor', [-0.1, 0])
def test_mutated_typed_duty_cannot_bypass_power_factor_validation(study, power_factor):
    duty = DischargeDutyBasis.model_validate(study.duty_basis)
    duty.power_factor_abs = power_factor
    with pytest.raises(ValidationError):
        assess(study, duty_basis=duty)


@pytest.mark.parametrize('temperature', [-21, 51])
def test_equipment_ambient_is_independent_of_the_25c_cell_curve(study, temperature):
    study.duty_basis['ambient_temperature_c'] = temperature
    result = assess(study)
    assert_check(result, 'equipment_ambient_temperature', 'fail')
    assert result['status'] == 'fails_discharge_checks'
    assert study.lib.packages[study.lib.revision_ids[12]]['conditions']['temperature_max_c'] == 30


def test_unknown_equipment_ambient_is_not_inferred_from_cell_curve(study):
    study.duty_basis['ambient_temperature_c'] = None
    result = assess(study)
    assert_check(result, 'equipment_ambient_temperature', 'pending')


def test_equipment_frequency_must_match_the_signed_project_frequency(study):
    replace_equipment_package(study, 'PCS-01', lambda package:
        package['conditions'].update(frequency_hz=60))
    result = assess(study)
    row = assert_check(result, 'project_frequency', 'fail', 'PCS-01')[0]
    assert row['required'] == 50 and row['declared'] == 60
    assert result['status'] == 'fails_discharge_checks'


def test_mv_bus_voltage_is_explicit_and_is_not_automatically_the_poi_voltage(study):
    study.duty_basis['mv_bus_voltage_kv'] = None
    result = assess(study)
    assert_check(result, 'mv_bus_voltage', 'pending')
    assert result['status'] == 'pending_engineering_evidence'


@pytest.mark.parametrize('state', ['draft', 'retired'])
def test_unreviewed_and_retired_packages_do_not_supply_numeric_ratings(study, state):
    replace_equipment_package(study, 'PCS-01', lambda package:
        package['pcs'].update(dc_discharge_power_kw=1, ac_discharge_power_kw=1,
                              ac_apparent_power_kva=1), status=state)
    result = assess(study)
    assert_check(result, 'current_capability_review', 'pending', 'PCS-01')
    assert_check(result, 'pcs_ac_active_power', 'pending', 'PCS-01')
    assert_check(result, 'pcs_ac_apparent_power', 'pending', 'PCS-01')
    assert next(row for row in result['pcs_duties'] if row['pcs_id'] == 'PCS-01')['declared_ac_kw'] is None
    assert result['status'] == 'pending_engineering_evidence'
    assert result['errors'] == []


def test_capability_retirement_during_assessment_rejects_the_entire_result(study, monkeypatch):
    original = service._equipment_checks
    def retire_after_computing(*args, **kwargs):
        result = original(*args, **kwargs)
        study.capability_service.transition(study.capability_revision_ids['PCS-01'],
            'candidate_only', 'retired', 'SYNTHETIC mid-assessment withdrawal')
        return result
    monkeypatch.setattr(service, '_equipment_checks', retire_after_computing)
    with pytest.raises(ValueError, match='review changed'):
        assess(study)


def test_reference_hash_mismatch_is_rejected_before_using_the_ratings(study):
    study.allocation['pcs_instances'][0]['capability_ref']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='hash mismatch'):
        assess(study)


def test_no_passive_dc_path_evidence_keeps_source_current_comparison_pending(study):
    study.duty_basis['passive_dc_path_confirmed'] = False
    result = assess(study)
    assert_check(result, 'port_dc_current_reference', 'pending')
    assert_check(result, 'aggregate_dc_current', 'pending')
    assert not checks(result, 'aggregate_dc_current_reference')


def test_aggregate_current_definition_is_required_even_if_every_port_has_a_rating(study):
    replace_equipment_package(study, 'PCS-01', lambda package:
        package['pcs'].update(aggregate_current_basis=None, continuous_dc_current_a=1))
    result = assess(study)
    assert_check(result, 'port_dc_current_reference', 'pass')
    assert_check(result, 'aggregate_dc_current', 'pending', 'PCS-01')
    assert result['status'] == 'pending_engineering_evidence'


def _join_ports_to_common_bus(study, *, permission=True):
    """Explicit synthetic parallel example, never inferred from shared cell Ah."""
    manifest = study.comparison['manifest']
    first_unit = manifest['physical_units'][0]
    revision = first_unit['revision_id']
    first_port = next(row for row in study.allocation['input_ports'] if row['pcs_id'] == 'PCS-01')
    for port in study.allocation['input_ports']:
        if port['pcs_id'] == 'PCS-01':
            port['dc_bus_id'] = first_port['dc_bus_id']
    def common(package):
        for port in package['pcs']['ports']:
            port['dc_bus_group'] = 'B1'
        package['pcs']['dc_buses'] = [dict(dc_bus_group='B1')]
        if permission:
            package['pcs']['dc_buses'][0].update(
                max_parallel_domains=2,
                compatible_revision_sha256=[first_unit['revision_sha256']],
                compatible_output_partition_sha256=[service.output_partition_sha256(manifest, revision)],
                parallel_evidence_ref='SYNTHETIC exact revision/output parallel applicability')
    replace_equipment_package(study, 'PCS-01', common)


def test_exact_parallel_revision_partition_count_and_evidence_can_pass_the_local_screen(tmp_path):
    study = make_equipment_fixture(tmp_path / 'synthetic-parallel.sqlite', split_outputs=True)
    _join_ports_to_common_bus(study)
    result = assess(study)
    for name in ('parallel_domain_count', 'parallel_product_revision', 'parallel_output_partition'):
        assert_check(result, name, 'pass')
    assert result['status'] == 'pending_engineering_evidence'
    assert_release_blocked(result)


@pytest.mark.parametrize('missing,check_name', [
    ('max_parallel_domains', 'parallel_domain_count'),
    ('parallel_evidence_ref', 'parallel_applicability'),
    ('compatible_revision_sha256', 'parallel_product_revision'),
    ('compatible_output_partition_sha256', 'parallel_output_partition'),
])
def test_parallel_permission_needs_all_four_independent_evidence_parts(tmp_path, missing, check_name):
    study = make_equipment_fixture(tmp_path / 'synthetic-parallel-gap.sqlite', split_outputs=True)
    _join_ports_to_common_bus(study)
    def remove(package):
        package['pcs']['dc_buses'][0][missing] = [] if missing.startswith('compatible_') else None
    replace_equipment_package(study, 'PCS-01', remove)
    result = assess(study)
    assert_check(result, check_name, 'pending')
    assert result['status'] == 'pending_engineering_evidence'


@pytest.mark.parametrize('wrong,check_name,value', [
    ('max_parallel_domains', 'parallel_domain_count', 1),
    ('compatible_revision_sha256', 'parallel_product_revision', ['0' * 64]),
    ('compatible_output_partition_sha256', 'parallel_output_partition', ['0' * 64]),
])
def test_known_parallel_evidence_conflicts_are_failures_not_missing_data(tmp_path, wrong, check_name, value):
    study = make_equipment_fixture(tmp_path / 'synthetic-parallel-conflict.sqlite', split_outputs=True)
    _join_ports_to_common_bus(study)
    replace_equipment_package(study, 'PCS-01', lambda package:
        package['pcs']['dc_buses'][0].update({wrong: value}))
    result = assess(study)
    assert_check(result, check_name, 'fail')
    assert result['status'] == 'fails_discharge_checks'


@pytest.mark.parametrize('reviewed_topology', ['independent', 'common'])
def test_common_and_independent_port_bus_declarations_cannot_be_interchanged(tmp_path, reviewed_topology):
    study = make_equipment_fixture(tmp_path / 'synthetic-bus-mismatch.sqlite', split_outputs=True)
    if reviewed_topology == 'independent':
        ports = [row for row in study.allocation['input_ports'] if row['pcs_id'] == 'PCS-01']
        ports[1]['dc_bus_id'] = ports[0]['dc_bus_id']
    else:
        def change(package):
            for port in package['pcs']['ports']:
                port['dc_bus_group'] = 'B1'
            package['pcs']['dc_buses'] = [dict(dc_bus_group='B1')]
        replace_equipment_package(study, 'PCS-01', change)
    result = assess(study)
    assert result['topology_valid'] is True  # D1a cannot verify the component internals.
    assert_check(result, 'input_bus_topology', 'fail', 'PCS-01')
    assert result['status'] == 'fails_discharge_checks'


def test_known_weak_tail_still_fails_with_large_pcs_and_transformer_ratings(tmp_path):
    study = make_equipment_fixture(tmp_path / 'synthetic-weak-tail.sqlite', tail_power_kw=400)
    result = assess(study)
    assert result['topology_valid'] is True
    assert result['source_energy_requirement_met'] is True
    assert result['dc_duty_status'] == 'fails_declared_dc_limits'
    assert result['status'] == 'fails_discharge_checks'
    assert result['errors']
    assert_check(result, 'pcs_dc_input_power', 'pass')
    assert_check(result, 'total_transformer_apparent_power', 'pass')


def _run_records(study):
    with sqlite3.connect(study.lib.url.removeprefix('sqlite:///')) as conn:
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%run%'")]
        return {name: conn.execute('SELECT * FROM "' + name + '"').fetchall() for name in names}


def test_assessment_is_deterministic_immutable_and_does_not_write_formal_runs(study):
    original_comparison = deepcopy(study.comparison)
    original_allocation = deepcopy(study.allocation)
    original_duty = deepcopy(study.duty_basis)
    original_catalogue = study.lib.admin.snapshot()
    original_reviews = study.capability_service.list_revisions()
    original_runs = _run_records(study)
    first = assess(study)
    assert assess(study) == first
    assert study.comparison == original_comparison
    assert study.allocation == original_allocation
    assert study.duty_basis == original_duty
    assert study.lib.admin.snapshot() == original_catalogue
    assert study.capability_service.list_revisions() == original_reviews
    assert _run_records(study) == original_runs


def test_json_source_roundtrip_preserves_the_same_equipment_diagnostic(study):
    first = assess(study)
    study.comparison = json_comparison(study.comparison)
    study.allocation = json.loads(json.dumps(study.allocation))
    study.duty_basis = json.loads(json.dumps(study.duty_basis))
    assert assess(study) == first


def test_invalid_mapping_does_not_return_partial_equipment_loads(study):
    study.allocation['input_ports'][1]['dc_bus_id'] = study.allocation['input_ports'][0]['dc_bus_id']
    result = assess(study)
    assert result['status'] == 'invalid_mapping'
    assert result['topology_valid'] is False
    assert result['declared_discharge_check_status'] == 'not_evaluated'
    assert result['pcs_duties'] == result['port_duties'] == result['winding_duties'] == []
    assert result['power_boundaries'] == {}
