import copy
import json

import pytest

from calb_sizing_tool.services.dc_composition_manifest_service import (
    build_dc_composition_manifest,
    dc_composition_manifest_sha256,
)


class Revisions:
    def __init__(self):
        self.rows = {}
        for strings, energy, power in ((12, 5.0159616, 2500), (10, 4.179968, 1800), (8, 3.3439744, 1200)):
            self.rows[f'r{strings}'] = dict(
                revision_id=f'r{strings}', revision_label='Engineering draft A',
                status='draft', sha256=f'digest-{strings}', stale=False,
                candidate_review_current=False, candidate_errors=['Product is not published'],
                snapshot=dict(product=dict(
                    product_dc_block_id=f'p{strings}', block_code=f'C{strings}',
                    block_name=f'20ft {strings}-string container', block_form='container',
                    container_type='20ft', cells_in_series=416, strings_in_parallel=strings,
                    product_cell_id='exact-cell-A', gross_energy_mwh=energy,
                    nominal_power_kw=power, max_current_a=2000,
                    racks_per_block=6,  # Deliberately not the string count.
                    metadata_json=dict(energy_basis='Engineering calculation; not confirmed manufacturer nameplate',
                                       inherited_fields_basis={'outline': 'Parent envelope assumption'}),
                ), cell={'product_cell_id': 'exact-cell-A', 'nominal_capacity_ah': 314}),
            )

    def inspect(self, revision_id):
        return copy.deepcopy(self.rows[revision_id])


class Variants:
    def __init__(self):
        self.rows = {
            f'v{strings}': dict(relation_id=f'v{strings}', relation_sha256=f'variant-{strings}',
                              parent_revision_id='r12', child_revision_id=f'r{strings}',
                              child_product_id=f'p{strings}', parent_product_id='p12',
                              status='draft', stale=False,
                              use_scope='special_scenario_only',
                              candidate_review_current=False, review_current=False,
                              review_errors=['Configuration review pending'])
            for strings in (8, 10)
        }

    def list_relations(self, child_product_id=None):
        return [copy.deepcopy(row) for row in self.rows.values()
                if child_product_id is None or row['child_product_id'] == child_product_id]

    def inspect(self, relation_id):
        return copy.deepcopy(self.rows[relation_id])


@pytest.fixture
def catalogue():
    return Revisions(), Variants()


def lines(*counts):
    return [dict(revision_id=f'r{strings}', quantity=quantity, role='main' if strings == 12 else 'tail')
            for strings, quantity in counts]


def build(catalogue, selections=None, **kwargs):
    revision_service, variant_service = catalogue
    options = dict(variant_service=variant_service, allow_special_configurations=True,
                   special_reason='Site constrained tail configuration')
    options.update(kwargs)
    return build_dc_composition_manifest(revision_service, selections or lines((12, 2), (10, 1)), **options)


def partition(strings, *, power=1000, current=1000):
    energy = {12: 5.0159616, 10: 4.179968, 8: 3.3439744}[strings]
    return [dict(domain_label='Independent output A', strings=strings,
                 gross_energy_mwh=energy, nominal_power_kw=power,
                 max_current_a=current, evidence_ref='Explicit output definition drawing A')]


def test_draft_mixed_bom_preserves_physical_identity_and_source_basis(catalogue):
    manifest = build(catalogue)
    assert manifest['schema_version'] == 1
    assert manifest['comparison_only'] is True
    assert manifest['downstream_ready'] is False
    assert manifest['total_container_count'] == 3
    assert manifest['total_gross_energy_mwh'] == pytest.approx(14.2118912)
    assert manifest['aggregate_nominal_power_kw'] == 6800
    assert [(row['product_code'], row['quantity'], row['strings_in_parallel']) for row in manifest['bom']] == [
        ('C12', 2, 12), ('C10', 1, 10)]
    assert [row['unit_id'] for row in manifest['physical_units']] == ['DC-001', 'DC-002', 'DC-003']
    assert [row['revision_id'] for row in manifest['physical_units']] == ['r12', 'r12', 'r10']
    assert manifest['bom'][1]['parent_revision_id'] == 'r12'
    assert manifest['bom'][1]['relation_sha256'] == 'variant-10'
    assert 'not confirmed manufacturer' in manifest['bom'][1]['energy_basis']
    assert manifest['bom'][1]['inherited_fields_basis'] == {'outline': 'Parent envelope assumption'}
    assert not manifest['electrical_domains']
    assert manifest['capability_gates']['energy_bom_validated'] is True
    assert manifest['capability_gates']['product_reviews'] is False
    assert manifest['capability_gates']['output_domains_defined'] is False
    assert manifest['capability_gates']['ac_power_matching_pending'] is True
    assert len(manifest['approval_errors']) == 3
    assert manifest['manifest_sha256'] == dc_composition_manifest_sha256(manifest)
    json.dumps(manifest, allow_nan=False)


def test_parent_only_keeps_standard_scope_and_does_not_need_variant_service(catalogue):
    revisions, _ = catalogue
    result = build_dc_composition_manifest(revisions, lines((12, 1)))
    assert result['scope']['use_scope'] == 'standard_parent_only'
    assert result['total_gross_energy_mwh'] == 5.0159616
    assert result['bom'][0]['relation_id'] is None
    assert not result['downstream_ready']


@pytest.mark.parametrize('strings,wrong_role', [(12, 'tail'), (10, 'main'), (8, 'main')])
def test_human_roles_cannot_reverse_main_and_tail(catalogue, strings, wrong_role):
    selections = lines((12, 2), (strings, 1)) if strings != 12 else lines((12, 2))
    selections[-1]['role'] = wrong_role
    with pytest.raises(ValueError, match='must be main'):
        build(catalogue, selections)


def test_known_other_cell_capacity_is_rejected_and_unknown_stays_pending(catalogue):
    revisions, _ = catalogue
    revisions.rows['r12']['snapshot']['cell']['nominal_capacity_ah'] = 588
    with pytest.raises(ValueError, match='314Ah'):
        build(catalogue, lines((12, 1)))
    revisions.rows['r12']['snapshot']['cell']['nominal_capacity_ah'] = None
    revisions.rows['r12']['candidate_review_current'] = True
    result = build(catalogue, lines((12, 1)))
    assert not result['capability_gates']['product_reviews']
    assert any('314Ah' in error for error in result['approval_errors'])


@pytest.mark.parametrize('container_type', ['20ft ISO container', '20ft DC Container', '20ftcontainer',
                                           '20 foot', '20feet'])
def test_existing_explicit_20ft_catalogue_aliases_are_recognised(catalogue, container_type):
    catalogue[0].rows['r12']['snapshot']['product']['container_type'] = container_type
    assert build(catalogue)['total_container_count'] == 3


@pytest.mark.parametrize('selections', [lines((12, 10001)), lines((12, 9999), (10, 2)), lines((12, 10 ** 1000))])
def test_local_manifest_expansion_is_bounded_before_allocating_device_identifiers(catalogue, selections):
    with pytest.raises(ValueError, match='at most 10,000'):
        build(catalogue, selections)


@pytest.mark.parametrize('quantity', [0, -1, True, False, 1.0, 1.5, '2', None, float('nan'), float('inf')])
def test_quantity_requires_strict_positive_integer(catalogue, quantity):
    with pytest.raises(ValueError, match='positive whole number'):
        build(catalogue, lines((12, quantity)))


def test_duplicate_revision_and_product_revisions_are_rejected(catalogue):
    with pytest.raises(ValueError, match='Duplicate revision'):
        build(catalogue, lines((12, 1), (12, 2)))
    revisions, _ = catalogue
    revisions.rows['r12-copy'] = copy.deepcopy(revisions.rows['r12'])
    revisions.rows['r12-copy']['revision_id'] = 'r12-copy'
    with pytest.raises(ValueError, match='Multiple revisions'):
        build(catalogue, [dict(revision_id='r12', quantity=1, role='main'),
                          dict(revision_id='r12-copy', quantity=1, role='main')])


@pytest.mark.parametrize('change', ['stale', 'retired', 'missing_cell', 'wrong_linked_cell', 'wrong_series',
                                  'cabinet', 'unknown_container', 'wrong_strings'])
def test_family_identity_and_revision_state_are_checked(catalogue, change):
    revisions, _ = catalogue
    child = revisions.rows['r10']
    product = child['snapshot']['product']
    if change == 'stale':
        child['stale'] = True
    elif change == 'retired':
        child['status'] = 'retired'
    elif change == 'missing_cell':
        child['snapshot']['cell'] = None
    elif change == 'wrong_linked_cell':
        child['snapshot']['cell']['product_cell_id'] = 'other'
    elif change == 'wrong_series':
        product['cells_in_series'] = 396
    elif change == 'cabinet':
        product['block_form'] = 'cabinet'
    elif change == 'unknown_container':
        product['container_type'] = None
    else:
        product['strings_in_parallel'] = 9
    with pytest.raises(ValueError):
        build(catalogue)


def test_equal_capacity_cell_is_not_cell_identity(catalogue):
    revisions, _ = catalogue
    revisions.rows['r10']['snapshot']['cell']['product_cell_id'] = '314Ah-other'
    revisions.rows['r10']['snapshot']['product']['product_cell_id'] = '314Ah-other'
    with pytest.raises(ValueError, match='exact same cell identity'):
        build(catalogue)


@pytest.mark.parametrize('options', [dict(allow_special_configurations=False),
                                     dict(special_reason='  '), dict(variant_service=None)])
def test_children_require_optin_reason_and_registered_lineage(catalogue, options):
    with pytest.raises(ValueError):
        build(catalogue, **options)


@pytest.mark.parametrize('change', ['missing', 'wrong_parent', 'wrong_child', 'stale', 'wrong_scope', 'retired', 'duplicate'])
def test_child_relation_must_be_current_and_unambiguous(catalogue, change):
    _, variants = catalogue
    relation = variants.rows['v10']
    if change == 'missing':
        del variants.rows['v10']
    elif change == 'wrong_parent':
        relation['parent_revision_id'] = 'r12-old'
    elif change == 'wrong_child':
        relation['child_revision_id'] = 'r10-old'
    elif change == 'stale':
        relation['stale'] = True
    elif change == 'wrong_scope':
        relation['use_scope'] = 'default'
    elif change == 'retired':
        relation['status'] = 'retired'
    else:
        variants.rows['v10-copy'] = dict(relation, relation_id='v10-copy')
    with pytest.raises(ValueError):
        build(catalogue)


def test_a_child_without_supplied_parent_cannot_be_mixed(catalogue):
    with pytest.raises(ValueError, match='12-string parent'):
        build(catalogue, lines((10, 1), (8, 1)))


def test_exact_12_10_8_partitions_expand_per_physical_container(catalogue):
    supplied = {f'r{strings}': partition(strings) for strings in (12, 10, 8)}
    # A three-output 12-string container is allowed in the new contract. The old
    # engine's one/two-circuit assumption is neither used nor modified here.
    supplied['r12'] = [dict(domain_label=f'Output {index}', strings=4,
                           gross_energy_mwh=1.6719872, nominal_power_kw=800,
                           max_current_a=800, evidence_ref='Three independent domains source')
                       for index in (1, 2, 3)]
    result = build(catalogue, lines((12, 2), (10, 1), (8, 1)), electrical_partitions=supplied)
    assert len(result['physical_units']) == 4
    assert len(result['electrical_domains']) == 8
    assert result['physical_units'][0]['electrical_domain_ids'] == ['DC-001/D1', 'DC-001/D2', 'DC-001/D3']
    assert result['physical_units'][1]['electrical_domain_ids'] == ['DC-002/D1', 'DC-002/D2', 'DC-002/D3']
    assert result['electrical_domains'][-1]['strings'] == 8
    assert result['capability_gates']['output_domains_defined'] is True
    assert result['capability_gates']['electrical_ratings_present'] is True
    assert result['capability_gates']['electrical_limits_reconciled'] is False
    assert result['downstream_ready'] is False
    assert all('pcs' not in domain for domain in result['electrical_domains'])


@pytest.mark.parametrize('mutation', ['string_sum', 'energy_sum', 'energy_missing', 'duplicate_label',
                                     'no_source', 'empty', 'fractional_strings', 'boolean_strings', 'nan_energy'])
def test_partitions_require_explicit_coherent_whole_device_definition(catalogue, mutation):
    rows = partition(10)
    if mutation == 'string_sum':
        rows[0]['strings'] = 8
    elif mutation == 'energy_sum':
        rows[0]['gross_energy_mwh'] = 5
    elif mutation == 'energy_missing':
        del rows[0]['gross_energy_mwh']
    elif mutation == 'duplicate_label':
        rows = [dict(rows[0], strings=5, gross_energy_mwh=2.089984),
                dict(rows[0], strings=5, gross_energy_mwh=2.089984, domain_label='independent OUTPUT a')]
    elif mutation == 'no_source':
        rows[0]['evidence_ref'] = ''
    elif mutation == 'empty':
        rows = []
    elif mutation == 'fractional_strings':
        rows[0]['strings'] = 10.0
    elif mutation == 'boolean_strings':
        rows[0]['strings'] = True
    else:
        rows[0]['gross_energy_mwh'] = float('nan')
    with pytest.raises(ValueError):
        build(catalogue, electrical_partitions={'r10': rows})


def test_output_definition_for_unselected_revision_is_rejected(catalogue):
    with pytest.raises(ValueError, match='unselected product revision'):
        build(catalogue, electrical_partitions={'r8': partition(8)})


def test_missing_ratings_remain_unknown_not_scaled_or_averaged(catalogue):
    revisions, _ = catalogue
    revisions.rows['r10']['snapshot']['product']['nominal_power_kw'] = 0
    revisions.rows['r10']['snapshot']['product']['max_current_a'] = None
    outputs = {'r12': partition(12), 'r10': partition(10, power=None, current=None)}
    result = build(catalogue, electrical_partitions=outputs)
    assert result['aggregate_nominal_power_kw'] is None
    assert result['bom'][1]['unit_nominal_power_kw'] is None
    assert result['electrical_domains'][-1]['nominal_power_kw'] is None
    assert result['capability_gates']['output_domains_defined'] is True
    assert result['capability_gates']['electrical_ratings_present'] is False
    assert any('ratings are incomplete' in reason for reason in result['blocked_reasons'])


@pytest.mark.parametrize('field,value', [('gross_energy_mwh', 0), ('gross_energy_mwh', None),
                                       ('gross_energy_mwh', float('nan')),
                                       ('nominal_power_kw', float('inf')), ('max_current_a', -1)])
def test_invalid_numeric_source_cannot_enter_canonical_contract(catalogue, field, value):
    catalogue[0].rows['r10']['snapshot']['product'][field] = value
    with pytest.raises(ValueError):
        build(catalogue)


def test_complete_reviews_do_not_claim_ac_lifetime_or_drawings_ready(catalogue):
    revisions, variants = catalogue
    for row in revisions.rows.values():
        row['status'] = 'candidate_only'
        row['candidate_review_current'] = True
    for row in variants.rows.values():
        row['status'] = 'reviewed'
        row['candidate_review_current'] = True
        row['review_current'] = True
    result = build(catalogue, electrical_partitions={'r12': partition(12), 'r10': partition(10)})
    assert result['capability_gates']['product_reviews'] is True
    assert result['approval_errors'] == []
    assert result['capability_gates']['lifetime_pending'] is True
    assert result['capability_gates']['sld_pending'] is True
    assert result['capability_gates']['layout_pending'] is True
    assert result['capability_gates']['report_pending'] is True
    assert not result['downstream_ready']


def test_signature_covers_quantities_scope_versions_basis_and_outputs(catalogue):
    baseline = build(catalogue)
    assert baseline == build(catalogue)
    hashes = {baseline['manifest_sha256']}
    hashes.add(build(catalogue, lines((12, 3), (10, 1)))['manifest_sha256'])
    hashes.add(build(catalogue, special_reason='Different site constraint')['manifest_sha256'])
    hashes.add(build(catalogue, electrical_partitions={'r12': partition(12), 'r10': partition(10)})['manifest_sha256'])
    catalogue[0].rows['r10']['sha256'] = 'new-digest'
    hashes.add(build(catalogue)['manifest_sha256'])
    catalogue[0].rows['r10']['snapshot']['product']['metadata_json']['energy_basis'] = 'Revised engineering assumption'
    hashes.add(build(catalogue)['manifest_sha256'])
    assert len(hashes) == 6
    # Self-digest is never recursively included; JSON key order is immaterial.
    reversed_manifest = dict(reversed(list(baseline.items())))
    reversed_manifest['manifest_sha256'] = 'untrusted digest'
    assert dc_composition_manifest_sha256(reversed_manifest) == baseline['manifest_sha256']


@pytest.mark.parametrize('field,value', [('sha256', 'new'), ('status', 'retired'),
                                       ('stale', True), ('candidate_review_current', True)])
def test_revision_reinspection_detects_midbuild_changes(catalogue, field, value):
    revisions, _ = catalogue
    original = revisions.inspect
    calls = {}

    def changing(revision_id):
        calls[revision_id] = calls.get(revision_id, 0) + 1
        result = original(revision_id)
        if revision_id == 'r10' and calls[revision_id] >= 2:
            result[field] = value
        return result

    revisions.inspect = changing
    with pytest.raises(ValueError, match='changed during composition'):
        build(catalogue)


def test_relation_reinspection_detects_midbuild_changes(catalogue):
    _, variants = catalogue
    original = variants.inspect

    def changing(relation_id):
        result = original(relation_id)
        result['relation_sha256'] = 'changed-during-build'
        return result

    variants.inspect = changing
    with pytest.raises(ValueError, match='relation or review changed'):
        build(catalogue)


def test_input_snapshots_and_partition_definitions_are_not_mutated(catalogue):
    revisions, variants = catalogue
    before_revisions, before_variants = copy.deepcopy(revisions.rows), copy.deepcopy(variants.rows)
    selections, outputs = lines((12, 2), (8, 1)), {'r8': partition(8)}
    before_selections, before_outputs = copy.deepcopy(selections), copy.deepcopy(outputs)
    result = build(catalogue, selections, electrical_partitions=outputs)
    result['bom'][1]['inherited_fields_basis']['outline'] = 'caller mutation'
    assert revisions.rows == before_revisions
    assert variants.rows == before_variants
    assert selections == before_selections
    assert outputs == before_outputs
