import copy
import hashlib
import json

import pytest

from calb_sizing_tool.services.dc_composition_dispatch_service import assess_proportional_dc_dispatch
from calb_sizing_tool.services.dc_composition_manifest_service import (
    build_dc_composition_manifest, dc_composition_manifest_sha256,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


class Revisions:
    def __init__(self):
        self.rows = {}
        for strings in (12, 10, 8):
            payload = dict(schema_version=2, product=dict(
                product_dc_block_id=f'p{strings}', block_code=f'C{strings}',
                block_name=f'{strings}-string test container', block_form='container', container_type='20ft',
                product_cell_id='same-cell', cells_in_series=416, strings_in_parallel=strings,
                gross_energy_mwh=strings * .4, nominal_power_kw=strings * 200.,
                max_current_a=strings * 3e2, voltage_min_v=1000., voltage_max_v=1500.,
                max_c_rate=.5, metadata_json={}),
                cell=dict(product_cell_id='same-cell', nominal_capacity_ah=314))
            self.rows[f'r{strings}'] = dict(revision_id=f'r{strings}', revision_label='Reviewed test',
                                           status='candidate_only', stale=False, candidate_review_current=True,
                                           sha256=digest(payload), snapshot=payload)

    def inspect(self, key):
        return copy.deepcopy(self.rows[key])


class Variants:
    def __init__(self):
        self.rows = {f'v{s}': dict(relation_id=f'v{s}', relation_sha256=f'digest-{s}', parent_revision_id='r12',
                                  child_revision_id=f'r{s}', child_product_id=f'p{s}', status='reviewed',
                                  stale=False, use_scope='special_scenario_only', candidate_review_current=True)
                     for s in (8, 10)}

    def list_relations(self, child_product_id):
        return [copy.deepcopy(row) for row in self.rows.values() if row['child_product_id'] == child_product_id]

    def inspect(self, key):
        return copy.deepcopy(self.rows[key])


def fixture(*, counts=((12, 1), (8, 1)), mutate=None, partitions=True, ports=1):
    revisions = Revisions()
    if mutate:
        mutate(revisions.rows)
    for row in revisions.rows.values():
        row['sha256'] = digest(row['snapshot'])
    supplied = {}
    if partitions:
        for strings, _ in counts:
            product = revisions.rows[f'r{strings}']['snapshot']['product']
            assert strings % ports == 0
            supplied[f'r{strings}'] = [dict(domain_label=f'Output {index}', strings=strings // ports,
                                             gross_energy_mwh=product['gross_energy_mwh'] / ports,
                                             nominal_power_kw=product['nominal_power_kw'] / ports if product['nominal_power_kw'] else None,
                                             max_current_a=product['max_current_a'] / ports if product['max_current_a'] else None,
                                             evidence_ref='Explicit test drawing')
                                      for index in range(ports)]
    manifest = build_dc_composition_manifest(
        revisions, [dict(revision_id=f'r{s}', quantity=n, role='main' if s == 12 else 'tail') for s, n in counts],
        variant_service=Variants(), allow_special_configurations=True,
        special_reason='Test tail application', electrical_partitions=supplied)
    return manifest, revisions.rows


def assess(manifest, revisions, power=3.):
    return assess_proportional_dc_dispatch(manifest, revisions, dc_power_required_mw=power)


def resign(manifest):
    manifest['manifest_sha256'] = dc_composition_manifest_sha256(manifest)


def test_explicit_proportional_dispatch_preserves_each_box_and_domain():
    manifest, revisions = fixture(counts=((12, 2), (10, 1), (8, 1)), ports=2)
    before = copy.deepcopy((manifest, revisions))
    result = assess(manifest, revisions, 6.)
    assert result['status'] == 'passes_declared_dc_limits'
    assert result['policy'] == 'proportional_to_raw_dc_nameplate_energy'
    assert [row['strings_in_parallel'] for row in result['unit_duties']] == [12, 12, 10, 8]
    assert [row['requested_discharge_kw'] for row in result['unit_duties']] == pytest.approx([12000/7, 12000/7, 10000/7, 8000/7])
    assert len(result['domain_duties']) == 8
    for row in result['conservation']['by_unit']:
        assert row['unit_discharge_kw'] == pytest.approx(row['total_domain_discharge_kw'])
    assert result['conservation']['total_unit_discharge_kw'] == pytest.approx(6000)
    assert result['conservation']['total_domain_discharge_kw'] == pytest.approx(6000)
    assert result['comparison_only'] and not result['downstream_ready']
    assert result['ac_power_matching_pending'] is True
    assert result['assessment_sha256'] == assess(manifest, revisions, 6.)['assessment_sha256']
    assert result['assessment_sha256'] != assess(manifest, revisions, 5.)['assessment_sha256']
    assert (manifest, revisions) == before


def test_short_tail_fails_even_when_total_catalogue_power_exceeds_demand():
    def mutate(rows):
        rows['r12']['snapshot']['product']['nominal_power_kw'] = 4000
        rows['r12']['snapshot']['product']['max_c_rate'] = None
        rows['r8']['snapshot']['product']['nominal_power_kw'] = 500
    manifest, revisions = fixture(mutate=mutate)
    assert manifest['aggregate_nominal_power_kw'] == 4500
    result = assess(manifest, revisions, 3.)
    assert result['status'] == 'fails_declared_dc_limits'
    assert result['unit_duties'][1]['requested_discharge_kw'] == pytest.approx(1200)
    assert any('DC-002:' in error and '500 kW' in error for error in result['errors'])


def test_lower_box_rating_is_not_replaced_by_sum_of_output_ratings():
    manifest, revisions = fixture(counts=((12, 1),), ports=2,
                                  mutate=lambda rows: rows['r12']['snapshot']['product'].update(nominal_power_kw=1000))
    for domain in manifest['electrical_domains']:
        domain['nominal_power_kw'] = 2000
    resign(manifest)
    result = assess(manifest, revisions, 1.5)
    assert result['status'] == 'fails_declared_dc_limits'
    assert result['unit_duties'][0]['limit_status'] == 'fails_declared_dc_limits'
    assert all(row['limit_status'] == 'passes_declared_dc_limits' for row in result['domain_duties'])


def test_oversubscribed_port_nameplate_is_not_rejected_when_actual_duties_fit():
    manifest, revisions = fixture(counts=((12, 1),), ports=2)
    for domain in manifest['electrical_domains']:
        domain['nominal_power_kw'] = 2400
    resign(manifest)
    assert assess(manifest, revisions, 2.)['status'] == 'passes_declared_dc_limits'


def test_individual_domain_power_limit_is_independently_checked():
    manifest, revisions = fixture(counts=((12, 1),), ports=2)
    manifest['electrical_domains'][0]['nominal_power_kw'] = 300
    resign(manifest)
    result = assess(manifest, revisions, 1.)
    assert result['unit_duties'][0]['limit_status'] == 'passes_declared_dc_limits'
    assert result['domain_duties'][0]['limit_status'] == 'fails_declared_dc_limits'
    assert result['domain_duties'][1]['limit_status'] == 'passes_declared_dc_limits'


def test_current_uses_minimum_voltage_not_nominal_or_maximum_voltage():
    manifest, revisions = fixture(counts=((12, 1),), mutate=lambda rows: rows['r12']['snapshot']['product'].update(
        max_current_a=800, nominal_voltage_v=1331.2))
    result = assess(manifest, revisions, 1.)
    assert result['status'] == 'fails_declared_dc_limits'
    assert result['unit_duties'][0]['required_current_a_at_voltage_min'] == 1000
    assert any('minimum voltage' in error for error in result['errors'])


def test_domain_current_uses_box_voltage_and_independent_limit():
    manifest, revisions = fixture(counts=((12, 1),), ports=2)
    manifest['electrical_domains'][1]['max_current_a'] = 400
    resign(manifest)
    result = assess(manifest, revisions, 1.)
    assert not result['unit_duties'][0]['errors']
    assert result['domain_duties'][1]['required_current_a_at_voltage_min'] == 500
    assert result['status'] == 'fails_declared_dc_limits'


def test_maximum_c_rate_is_an_additional_actual_duty_limit():
    manifest, revisions = fixture(counts=((12, 1),), mutate=lambda rows: rows['r12']['snapshot']['product'].update(max_c_rate=.1))
    result = assess(manifest, revisions, 1.)
    assert result['status'] == 'fails_declared_dc_limits'
    assert any('discharge rate' in error for error in result['errors'])


@pytest.mark.parametrize('unknown', [None, 0])
def test_unknown_maximum_c_rate_does_not_hide_confirmed_power_current_checks(unknown):
    manifest, revisions = fixture(counts=((12, 1),), mutate=lambda rows: rows['r12']['snapshot']['product'].update(max_c_rate=unknown))
    result = assess(manifest, revisions, 1.)
    assert result['status'] == 'passes_declared_dc_limits'
    assert any('C-rate is unconfirmed' in warning for warning in result['warnings'])


def test_missing_output_partitions_remain_pending_without_inventing_ports():
    manifest, revisions = fixture(partitions=False)
    result = assess(manifest, revisions)
    assert result['status'] == 'pending_electrical_evidence'
    assert result['domain_duties'] == []
    assert result['conservation']['total_domain_discharge_kw'] is None
    assert not result['conservation']['all_output_partitions_defined']
    assert all(row['domain_duty_conserved'] is None for row in result['conservation']['by_unit'])
    assert any('no ports or PCS count were inferred' in item for item in result['pending_evidence'])


@pytest.mark.parametrize('key', ['nominal_power_kw', 'max_current_a', 'voltage_min_v', 'voltage_max_v'])
@pytest.mark.parametrize('unknown', [None, 0])
def test_unconfirmed_box_ratings_and_voltage_remain_pending(key, unknown):
    manifest, revisions = fixture(counts=((12, 1),), mutate=lambda rows: rows['r12']['snapshot']['product'].update({key: unknown}))
    result = assess(manifest, revisions, 1.)
    assert result['status'] == 'pending_electrical_evidence'
    assert result['pending_evidence']
    if key == 'voltage_min_v':
        assert result['unit_duties'][0]['required_current_a_at_voltage_min'] is None


@pytest.mark.parametrize('key', ['nominal_power_kw', 'max_current_a'])
def test_missing_domain_rating_remains_pending(key):
    manifest, revisions = fixture(counts=((12, 1),))
    manifest['electrical_domains'][0][key] = None
    resign(manifest)
    assert assess(manifest, revisions, 1.)['status'] == 'pending_electrical_evidence'


def test_product_or_lineage_review_gaps_never_produce_overall_pass():
    manifest, revisions = fixture(mutate=lambda rows: rows['r8'].update(status='draft', candidate_review_current=False))
    result = assess(manifest, revisions)
    assert result['status'] == 'pending_electrical_evidence'
    assert result['product_review_current'] is False
    assert all(row['limit_status'] == 'passes_declared_dc_limits' for row in result['unit_duties'])
    manifest, revisions = fixture()
    manifest['capability_gates']['product_reviews'] = False
    resign(manifest)
    assert assess(manifest, revisions)['status'] == 'pending_electrical_evidence'


def test_failure_is_not_hidden_by_missing_evidence():
    manifest, revisions = fixture(partitions=False, mutate=lambda rows: rows['r8']['snapshot']['product'].update(nominal_power_kw=100))
    result = assess(manifest, revisions)
    assert result['status'] == 'fails_declared_dc_limits'
    assert result['errors'] and result['pending_evidence']


@pytest.mark.parametrize('power', [None, True, False, '1', 0, -1, float('nan'), float('inf'), 1e308, 10**1000])
def test_requested_power_requires_finite_positive_numeric_value(power):
    manifest, revisions = fixture()
    with pytest.raises(ValueError):
        assess(manifest, revisions, power)


@pytest.mark.parametrize('key', ['nominal_power_kw', 'max_current_a', 'voltage_min_v', 'voltage_max_v', 'max_c_rate'])
@pytest.mark.parametrize('bad', [True, -1, float('inf'), '1000'])
def test_invalid_product_ratings_are_rejected(key, bad):
    # Some invalid values are already rejected while building the C2a contract.
    with pytest.raises(ValueError):
        manifest, revisions = fixture(counts=((12, 1),), partitions=False,
                                      mutate=lambda rows: rows['r12']['snapshot']['product'].update({key: bad}))
        assess(manifest, revisions, 1.)


def test_digest_tampering_and_changed_source_snapshot_are_rejected():
    manifest, revisions = fixture()
    manifest['total_gross_energy_mwh'] += 1
    with pytest.raises(ValueError, match='manifest digest'):
        assess(manifest, revisions)
    manifest, revisions = fixture()
    revisions['r8']['snapshot']['product']['nominal_power_kw'] *= 100
    with pytest.raises(ValueError, match='snapshot digest'):
        assess(manifest, revisions)


@pytest.mark.parametrize('state', ['stale', 'retired', 'missing', 'identity', 'hash', 'false_review'])
def test_source_revision_identity_and_review_state_are_verified(state):
    manifest, revisions = fixture()
    if state == 'stale':
        revisions['r8']['stale'] = True
    elif state == 'retired':
        revisions['r8']['status'] = 'retired'
    elif state == 'missing':
        del revisions['r8']
    elif state == 'identity':
        revisions['r8']['revision_id'] = 'other'
    elif state == 'hash':
        revisions['r8']['sha256'] = 'another'
    else:
        revisions['r8']['status'] = 'draft'
    with pytest.raises(ValueError):
        assess(manifest, revisions)


@pytest.mark.parametrize('change', ['quantity', 'energy', 'unit_count', 'units_removed', 'unit_duplicate',
                                  'unit_source', 'unit_sha', 'unit_code', 'role', 'line_number', 'power'])
def test_rehashed_manifest_still_must_match_bom_and_physical_sources(change):
    manifest, revisions = fixture()
    if change == 'quantity':
        manifest['bom'][0]['quantity'] += 1
    elif change == 'energy':
        manifest['physical_units'][0]['gross_energy_mwh'] += .01
    elif change == 'unit_count':
        manifest['total_container_count'] += 1
    elif change == 'units_removed':
        manifest['physical_units'].pop()
    elif change == 'unit_duplicate':
        manifest['physical_units'][1]['unit_id'] = manifest['physical_units'][0]['unit_id']
    elif change == 'unit_source':
        manifest['physical_units'][1]['revision_id'] = 'r10'
    elif change == 'unit_sha':
        manifest['physical_units'][1]['revision_sha256'] = 'stale'
    elif change == 'unit_code':
        manifest['physical_units'][1]['product_code'] = 'C12'
    elif change == 'role':
        manifest['bom'][1]['role'] = 'main'
    elif change == 'line_number':
        manifest['bom'][1]['line_number'] = 1
    else:
        manifest['bom'][1]['unit_nominal_power_kw'] *= 100
    resign(manifest)
    with pytest.raises(ValueError):
        assess(manifest, revisions)


@pytest.mark.parametrize('change', ['duplicate', 'missing', 'extra', 'reused', 'wrong_owner', 'wrong_source',
                                  'strings', 'energy', 'label', 'empty_evidence', 'boolean_current'])
def test_partition_identity_and_exact_coverage_are_checked_even_after_rehash(change):
    manifest, revisions = fixture(ports=2)
    if change == 'duplicate':
        manifest['electrical_domains'].append(copy.deepcopy(manifest['electrical_domains'][0]))
    elif change == 'missing':
        manifest['electrical_domains'].pop()
    elif change == 'extra':
        extra = copy.deepcopy(manifest['electrical_domains'][0])
        extra['domain_id'] = 'extra'
        manifest['electrical_domains'].append(extra)
    elif change == 'reused':
        manifest['physical_units'][1]['electrical_domain_ids'][0] = manifest['physical_units'][0]['electrical_domain_ids'][0]
    elif change == 'wrong_owner':
        manifest['electrical_domains'][0]['unit_id'] = 'DC-002'
    elif change == 'wrong_source':
        manifest['electrical_domains'][0]['revision_id'] = 'r8'
    elif change == 'strings':
        manifest['electrical_domains'][0]['strings'] += 1
    elif change == 'energy':
        manifest['electrical_domains'][0]['gross_energy_mwh'] += .01
    elif change == 'label':
        manifest['electrical_domains'][0]['domain_label'] = manifest['electrical_domains'][1]['domain_label']
    elif change == 'empty_evidence':
        manifest['electrical_domains'][0]['evidence_ref'] = ' '
    else:
        manifest['electrical_domains'][0]['max_current_a'] = True
    resign(manifest)
    with pytest.raises(ValueError):
        assess(manifest, revisions)


@pytest.mark.parametrize('key,value', [('schema_version', True), ('schema_version', 2), ('comparison_only', False),
                                     ('downstream_ready', True), ('contract_type', 'runtime')])
def test_only_planning_schema_is_accepted(key, value):
    manifest, revisions = fixture()
    manifest[key] = value
    resign(manifest)
    with pytest.raises(ValueError):
        assess(manifest, revisions)


def test_invalid_voltage_window_is_rejected():
    manifest, revisions = fixture(mutate=lambda rows: rows['r8']['snapshot']['product'].update(voltage_max_v=900))
    with pytest.raises(ValueError, match='voltage window'):
        assess(manifest, revisions)


def test_float_equality_does_not_create_an_engineering_power_margin():
    manifest, revisions = fixture(counts=((12, 1),))
    assert assess(manifest, revisions, 2.4 * (1 + 1e-11))['status'] == 'passes_declared_dc_limits'
    assert assess(manifest, revisions, 2.4 * (1 + 1e-7))['status'] == 'fails_declared_dc_limits'


def test_rehashed_containers_cannot_invent_different_topologies_for_one_revision():
    manifest, revisions = fixture(counts=((12, 2),), ports=2)
    manifest['electrical_domains'][2]['nominal_power_kw'] = 999
    resign(manifest)
    with pytest.raises(ValueError, match='same source revision'):
        assess(manifest, revisions, 1.)


def test_boolean_physical_line_number_is_not_an_integer_identity():
    manifest, revisions = fixture(counts=((12, 1),))
    manifest['physical_units'][0]['line_number'] = True
    resign(manifest)
    with pytest.raises(ValueError, match='positive whole number'):
        assess(manifest, revisions, 1.)


def test_relabelled_energy_boundary_is_not_accepted_after_rehash():
    manifest, revisions = fixture()
    manifest['energy_boundary'] = 'Usable AC energy'
    resign(manifest)
    with pytest.raises(ValueError, match='energy boundary'):
        assess(manifest, revisions)
