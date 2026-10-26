import copy

import pytest

from calb_sizing_tool.services.dc_tail_candidate_service import (
    dc_tail_candidate_plan_sha256,
    plan_tail_replacement_candidates,
)


class Revisions:
    def __init__(self):
        self.rows = {}
        for strings, energy in ((12, 5.0159616), (10, 4.179968), (8, 3.3439744)):
            self.rows[f'r{strings}'] = dict(
                revision_id=f'r{strings}', revision_label=f'{strings}-string engineering draft',
                sha256=f'sha-{strings}', status='draft', stale=False,
                candidate_review_current=False, candidate_errors=['Source review pending'],
                snapshot=dict(product=dict(
                    product_dc_block_id=f'p{strings}', block_code=f'C{strings}',
                    block_name=f'20ft {strings}-string container', block_form='container',
                    container_type='20ft', cells_in_series=416, strings_in_parallel=strings,
                    product_cell_id='exact314', gross_energy_mwh=energy,
                    nominal_power_kw=None, max_current_a=None,
                    racks_per_block=6, metadata_json={'energy_basis': 'Engineering assumption'}),
                    cell=dict(product_cell_id='exact314', nominal_capacity_ah=314)))

    def inspect(self, revision_id):
        return copy.deepcopy(self.rows[revision_id])


class Variants:
    def __init__(self):
        self.rows = {
            f'v{strings}': dict(relation_id=f'v{strings}', relation_sha256=f'relation-{strings}',
                parent_revision_id='r12', child_revision_id=f'r{strings}',
                parent_product_id='p12', child_product_id=f'p{strings}',
                status='draft', stale=False, use_scope='special_scenario_only',
                candidate_review_current=False, review_current=False,
                review_errors=['Lineage review pending']) for strings in (8, 10)
        }

    def list_relations(self, child_product_id=None):
        return [copy.deepcopy(row) for row in self.rows.values()
                if child_product_id is None or row['child_product_id'] == child_product_id]

    def inspect(self, relation_id):
        return copy.deepcopy(self.rows[relation_id])


@pytest.fixture
def catalogue():
    return Revisions(), Variants()


def plan(catalogue, count=4, children=None, **kwargs):
    revisions, variants = catalogue
    options = dict(standard_container_count=count, variant_service=variants,
                   allow_special_configurations=True, special_reason='Site tail constraint')
    options.update(kwargs)
    return plan_tail_replacement_candidates(revisions, 'r12',
        ['r8', 'r10'] if children is None else children, **options)


def test_three_options_preserve_physical_bom_and_use_no_average(catalogue):
    result = plan(catalogue)
    assert [row['candidate_key'] for row in result['candidates']] == ['standard', 'tail_10', 'tail_8']
    assert [row['label'] for row in result['candidates']] == [
        'Standard: 4 × 12-string', 'Tail option: 3 × 12 + 1 × 10', 'Tail option: 3 × 12 + 1 × 8']
    assert [(line['strings_in_parallel'], line['quantity'])
            for line in result['candidates'][1]['manifest']['bom']] == [(12, 3), (10, 1)]
    assert [row['revision_id'] for row in result['candidates'][1]['manifest']['physical_units']] == [
        'r12', 'r12', 'r12', 'r10']
    assert result['candidates'][1]['manifest']['total_gross_energy_mwh'] == pytest.approx(19.2278528)
    assert result['candidates'][2]['manifest']['total_gross_energy_mwh'] == pytest.approx(18.3918592)
    assert result['candidates'][0]['manifest']['scope']['use_scope'] == 'standard_parent_only'
    assert result['omitted_candidates'] == []
    assert result['comparison_only'] is True and result['downstream_ready'] is False
    assert result['performance_evaluated'] is False and result['ac_power_matching_evaluated'] is False
    assert result['plan_sha256'] == dc_tail_candidate_plan_sha256(result)


@pytest.mark.parametrize('count', [2, 10_000])
def test_explicit_standard_counts_are_kept_and_exactly_one_parent_replaced(catalogue, count):
    result = plan(catalogue, count)
    assert result['standard_container_count'] == count
    for row in result['candidates']:
        manifest = row['manifest']
        assert manifest['total_container_count'] == count
        assert len(manifest['physical_units']) == count
        assert sum(line['quantity'] for line in manifest['bom'] if line['role'] == 'tail') in (0, 1)
    assert result['candidates'][1]['manifest']['bom'][0]['quantity'] == count - 1


def test_one_standard_box_never_becomes_child_only(catalogue):
    result = plan(catalogue, 1)
    assert [row['candidate_key'] for row in result['candidates']] == ['standard']
    assert [row['candidate_key'] for row in result['omitted_candidates']] == ['tail_10', 'tail_8']
    assert all(row['reason'] == 'needs_parent_maintained' for row in result['omitted_candidates'])
    assert result['candidates'][0]['manifest']['bom'][0]['quantity'] == 1
    assert len(result['relation_identities']) == 2


def test_single_box_still_rejects_invalid_selected_child(catalogue):
    catalogue[0].rows['r8']['snapshot']['product']['product_cell_id'] = 'foreign314'
    catalogue[0].rows['r8']['snapshot']['cell']['product_cell_id'] = 'foreign314'
    with pytest.raises(ValueError, match='exact same cell'):
        plan(catalogue, 1)


@pytest.mark.parametrize('count', [0, -1, True, False, 1.0, 1.5, '4', None,
                                   float('nan'), float('inf'), 10_001, 10 ** 100])
def test_count_types_and_expansion_bound_are_strict(catalogue, count):
    with pytest.raises(ValueError, match='positive whole|at most 10,000'):
        plan(catalogue, count)


@pytest.mark.parametrize('children', [('r8',), 'r8', None, [None], [''], ['r8', 'r8'],
                                    ['r12'], ['r8', 'r10', 'r8']])
def test_invalid_or_duplicate_child_selections_are_rejected(catalogue, children):
    revisions, variants = catalogue
    with pytest.raises(ValueError):
        plan_tail_replacement_candidates(revisions, 'r12', children,
            standard_container_count=3, variant_service=variants,
            allow_special_configurations=True, special_reason='tail')


def test_two_revisions_of_the_same_child_string_count_are_rejected(catalogue):
    revisions, _ = catalogue
    revisions.rows['r10-other'] = copy.deepcopy(revisions.rows['r10'])
    revisions.rows['r10-other']['revision_id'] = 'r10-other'
    with pytest.raises(ValueError, match='one child revision per string count'):
        plan(catalogue, children=['r10', 'r10-other'])


@pytest.mark.parametrize('overrides', [dict(allow_special_configurations=False),
    dict(allow_special_configurations=1), dict(special_reason=' '),
    dict(special_reason=None), dict(variant_service=None)])
def test_special_options_require_explicit_scope(catalogue, overrides):
    with pytest.raises(ValueError):
        plan(catalogue, **overrides)


def test_standard_plan_needs_no_children_lineage_or_special_scope(catalogue):
    result = plan(catalogue, children=[], variant_service=None,
                  allow_special_configurations=False, special_reason='')
    assert len(result['candidates']) == 1
    assert result['relation_identities'] == []


@pytest.mark.parametrize('revision_id', ['r12', 'r10', 'r8'])
@pytest.mark.parametrize('field,value', [('stale', True), ('status', 'retired')])
def test_stale_or_retired_revisions_cannot_be_planned(catalogue, revision_id, field, value):
    catalogue[0].rows[revision_id][field] = value
    with pytest.raises(ValueError, match='stale or retired'):
        plan(catalogue)


@pytest.mark.parametrize('field,value', [('cells_in_series', 396), ('cells_in_series', True),
    ('block_form', 'cabinet'), ('container_type', '20ft equivalent'),
    ('strings_in_parallel', 10), ('strings_in_parallel', 12.0)])
def test_parent_must_be_the_explicit_standard_family(catalogue, field, value):
    catalogue[0].rows['r12']['snapshot']['product'][field] = value
    with pytest.raises(ValueError):
        plan(catalogue)


@pytest.mark.parametrize('ah', [None, 588, True, '314', float('nan'), float('inf')])
def test_confirmed_314ah_is_required_not_guessed(catalogue, ah):
    catalogue[0].rows['r12']['snapshot']['cell']['nominal_capacity_ah'] = ah
    with pytest.raises(ValueError, match='314Ah'):
        plan(catalogue)


def test_equal_ah_different_exact_cell_is_rejected(catalogue):
    catalogue[0].rows['r10']['snapshot']['product']['product_cell_id'] = 'other314'
    catalogue[0].rows['r10']['snapshot']['cell']['product_cell_id'] = 'other314'
    with pytest.raises(ValueError, match='exact same cell'):
        plan(catalogue)


def test_same_cell_id_with_changed_captured_cell_is_rejected(catalogue):
    catalogue[0].rows['r10']['snapshot']['cell']['model_name'] = 'Unmatched cell snapshot'
    with pytest.raises(ValueError, match='exact same cell identity and snapshot'):
        plan(catalogue)


@pytest.mark.parametrize('changes', [dict(parent_revision_id='other-parent'),
    dict(child_revision_id='other-child'), dict(status='retired'), dict(stale=True),
    dict(use_scope='standard')])
def test_wrong_stale_retired_or_unbounded_lineage_is_rejected(catalogue, changes):
    catalogue[1].rows['v10'].update(changes)
    with pytest.raises(ValueError, match='registered relation|current and special'):
        plan(catalogue)


@pytest.mark.parametrize('field,value', [('parent_product_id', 'foreign-parent'),
    ('child_product_id', 'foreign-child'), ('parent_revision_sha256', 'foreign-parent-digest'),
    ('child_revision_sha256', 'foreign-child-digest')])
def test_relation_cannot_bind_foreign_products_or_revision_digests(catalogue, field, value):
    catalogue[1].rows['v10'][field] = value
    with pytest.raises(ValueError, match='product identities|revision digest|registered relation'):
        plan(catalogue)


def test_drafts_keep_approval_errors_and_never_activate_or_match_ac(catalogue):
    result = plan(catalogue)
    for candidate in result['candidates']:
        manifest = candidate['manifest']
        assert manifest['approval_errors']
        assert not manifest['capability_gates']['product_reviews']
        assert not manifest['downstream_ready']
        assert manifest['capability_gates']['ac_power_matching_pending']
        assert manifest['capability_gates']['lifetime_pending']
    assert {row['status'] for row in result['revision_identities']} == {'draft'}
    assert {row['status'] for row in result['relation_identities']} == {'draft'}


def test_child_order_does_not_change_ranking_or_plan_hash(catalogue):
    forward = plan(catalogue, children=['r8', 'r10'])
    reverse = plan(catalogue, children=['r10', 'r8'])
    assert forward == reverse
    assert forward['plan_sha256'] == reverse['plan_sha256']


def test_signature_covers_count_scope_revision_and_relation_state(catalogue):
    baseline = plan(catalogue)
    hashes = {baseline['plan_sha256'], plan(catalogue, 3)['plan_sha256'],
              plan(catalogue, special_reason='Other site boundary')['plan_sha256']}
    catalogue[0].rows['r10']['sha256'] = 'new-revision-digest'
    hashes.add(plan(catalogue)['plan_sha256'])
    catalogue[1].rows['v10']['status'] = 'candidate_only'
    hashes.add(plan(catalogue)['plan_sha256'])
    assert len(hashes) == 5
    mutated = copy.deepcopy(baseline)
    mutated['candidates'][1]['manifest']['physical_units'][-1]['gross_energy_mwh'] = 4
    assert dc_tail_candidate_plan_sha256(mutated) != baseline['plan_sha256']


@pytest.mark.parametrize('field,value', [('sha256', 'changed'), ('status', 'candidate_only'),
    ('candidate_review_current', True), ('stale', True)])
def test_aggregate_revision_recheck_detects_change_after_earlier_candidate(catalogue, field, value):
    revisions, _ = catalogue
    original = revisions.inspect
    seen = False

    def changing(revision_id):
        nonlocal seen
        # r8's second inspection is in the final candidate, after r10's
        # candidate was built and individually rechecked.
        result = original(revision_id)
        if revision_id == 'r8':
            if seen:
                revisions.rows['r10'][field] = value
            seen = True
        return result

    revisions.inspect = changing
    with pytest.raises(ValueError, match='changed during candidate planning'):
        plan(catalogue)


@pytest.mark.parametrize('field,value', [('relation_sha256', 'changed'),
    ('status', 'candidate_only'), ('candidate_review_current', True), ('stale', True)])
def test_aggregate_relation_recheck_detects_change_after_earlier_candidate(catalogue, field, value):
    revisions, variants = catalogue
    original = revisions.inspect
    seen = False

    def changing(revision_id):
        nonlocal seen
        result = original(revision_id)
        if revision_id == 'r8':
            if seen:
                variants.rows['v10'][field] = value
            seen = True
        return result

    revisions.inspect = changing
    with pytest.raises(ValueError, match='relation or review changed during candidate planning'):
        plan(catalogue)


def test_no_input_or_catalogue_state_is_mutated(catalogue):
    revisions, variants = catalogue
    before = copy.deepcopy((revisions.rows, variants.rows))
    children = ['r8', 'r10']
    result = plan(catalogue, children=children)
    result['candidates'][1]['manifest']['bom'][0]['quantity'] = 999
    assert (revisions.rows, variants.rows) == before
    assert children == ['r8', 'r10']
