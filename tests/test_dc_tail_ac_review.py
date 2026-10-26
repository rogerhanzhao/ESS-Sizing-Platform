"""Nominal tail-in-last-AC-group checks; synthetic data are not OEM ratings."""
from copy import deepcopy

import pytest

from calb_sizing_tool.services import dc_tail_ac_review_service as review
from calb_sizing_tool.services import dc_reduced_string_tail_service as tails
from calb_sizing_tool.services.stage2_service import build_config_container_only
from calb_sizing_tool.services.stage3_service import run_stage3
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from tests.test_dc_reduced_string_tail import example  # Reuse the synthetic original capacity chain.


def parent(example, strings=10, count=4, *, admin=False, conversion=1):
    base = deepcopy(example.snapshot)
    unit = 5.01596 if admin else 5.016
    code = 'CATALOGUE-12' if admin else tails.STANDARD_EXCEL_CODE
    base.stage1.eff_dc_cables_frac = conversion
    base.stage1.eff_pcs_frac = 1
    base.stage2 = build_config_container_only((count - 0.5) * unit, unit, code, 'Main container')
    base.stage3 = run_stage3(base.stage1, base.stage2, example.bundle)
    product = tails.available_products(example.rows, example.basis, code)[strings]
    result = tails.evaluate_reduced_string_tail(base, example.bundle, product, example.basis)
    base.summary[tails.SUMMARY_KEY] = result
    return base


def ac(rows=None, *, circuits=2, topology='two_winding'):
    return dict(ac_block_rows=rows or [dict(pcs_count=2, pcs_kw=1250, dc_blocks=2),
                                     dict(pcs_count=2, pcs_kw=1250, dc_blocks=2)],
                dc_block_output_circuits=circuits, transformer_topology=topology)


def last(result):
    return result['groups'][-1]


def resign(result):
    result['review_sha256'] = _hash_payload({key: value for key, value in result.items()
                                            if key != 'review_sha256'})


def test_no_tail_saved_returns_none_without_reading_ac_or_creating_attachment(example):
    assert review.evaluate_tail_ac_review(example.snapshot, {}) is None
    assert review.restored_tail_ac_review(example.snapshot, {}) is None


@pytest.mark.parametrize('admin', [False, True])
def test_exactly_last_box_replaced_original_groups_and_inputs_unchanged(example, admin):
    source = parent(example, admin=admin)
    output = ac()
    originals = deepcopy((source, output))
    result = review.evaluate_tail_ac_review(source, output)
    assert (source, output) == originals
    assert result['comparison_only'] is True and result['downstream_ready'] is False
    assert result['engineering_approved'] is False
    assert len(result['groups']) == 2
    assert [(g['main_count'], g['tail_count']) for g in result['groups']] == [(2, 0), (1, 1)]
    assert [c['role'] for g in result['groups'] for c in g['connections']] == ['main'] * 3 + ['tail']
    assert [c['feeder_indices'] for c in result['groups'][0]['connections']] == [[1], [2]]
    assert result['tail_feeder_indices'] == [2]
    assert result['topology_valid'] is True
    expected_unit = 5.01596 if admin else 5.016
    assert result['groups'][0]['dc_energy_mwh'] == expected_unit * 2
    assert last(result)['dc_energy_mwh'] == expected_unit + 4.18
    assert result['total_dc_energy_mwh'] == round(expected_unit * 3 + 4.18, 3)
    assert sum(g['required_dc_duty_kw'] for g in result['groups']) == pytest.approx(2000)
    assert result['source_energy_requirement_met'] is True


def test_ten_string_cannot_feed_two_pcs_no_false_partial_power_pass(example):
    result = review.evaluate_tail_ac_review(parent(example), ac([
        dict(pcs_count=4, pcs_kw=1250, dc_blocks=2),
        dict(pcs_count=4, pcs_kw=1250, dc_blocks=2)]))
    assert result['tail_feeder_indices'] == [3, 4]
    assert result['topology_valid'] is False
    assert any('cannot feed 2 PCS' in message for message in result['errors'])
    for item in last(result)['pcs_items'][2:]:
        assert item['required_dc_duty_kw'] is None
        assert item['required_ac_duty_kw'] is None
        assert item['meets_pcs_nameplate'] is None


def test_eight_string_two_pcs_preserves_unknown_per_output_duty(example):
    result = review.evaluate_tail_ac_review(parent(example, 8), ac([
        dict(pcs_count=2, pcs_kw=1250, dc_blocks=2),
        dict(pcs_count=4, pcs_kw=1250, dc_blocks=2)]))
    assert result['topology_valid'] is True
    assert result['tail_feeder_indices'] == [3, 4]
    tail = last(result)['connections'][-1]
    assert tail['output_circuit_count'] == 2
    assert [item['required_dc_duty_kw'] for item in tail['per_feeder_duties']] == [None, None]
    assert tail['required_dc_duty_kw'] > 0
    for item in last(result)['pcs_items'][2:]:
        assert item['required_ac_duty_kw'] is None and item['meets_pcs_nameplate'] is None
        assert item['nominal_power_check'] == 'unknown_output_duty'
    assert result['nominal_reference_conserved'] is False
    assert any('no 4+4 or equal split' in text for text in result['pending_evidence'])


def test_eight_string_one_pcs_is_count_compatible_but_connection_remains_pending(example):
    result = review.evaluate_tail_ac_review(parent(example, 8), ac())
    assert result['topology_valid'] is True
    assert result['tail_feeder_indices'] == [2]
    assert last(result)['pcs_items'][1]['required_dc_duty_kw'] > 0
    assert last(result)['connections'][-1]['output_partition_confirmed'] is False
    assert any('independent input or parallel applicability' in text for text in result['pending_evidence'])
    assert result['status'] == 'pending_engineering_evidence'


def test_separate_pcs_ratings_are_summed_never_averaged_or_written_into_head(example):
    output = ac([dict(pcs_count=2, pcs_kw=1250, dc_blocks=2),
                 dict(pcs_count=4, pcs_kw=1250, dc_blocks=2)])
    before = deepcopy(output)
    result = review.evaluate_tail_ac_review(parent(example, 8), output, {3: 900.5, 4: 1800})
    assert [item['rating_kw'] for item in last(result)['pcs_items']] == [1250, 1250, 900.5, 1800]
    assert last(result)['pcs_rating_kw_sum'] == 5200.5
    assert result['total_pcs_rating_kw_sum'] == 7700.5
    assert output == before
    assert last(result)['transformer_review']['total_mva'] == pytest.approx(5000 / 1000 / 0.9)
    assert last(result)['transformer_review']['is_estimate'] is True


def test_same_pcs_model_still_reports_actual_dc_tail(example):
    result = review.evaluate_tail_ac_review(parent(example), ac())
    assert last(result)['tail_count'] == 1
    assert last(result)['connections'][-1]['strings_in_parallel'] == 10
    assert len(result['groups']) == 2


def test_dc_to_pcs_ac_power_comparison_uses_signed_efficiency_boundary(example):
    source = parent(example, conversion=0.8)
    result = review.evaluate_tail_ac_review(source, ac())
    item = last(result)['pcs_items'][1]
    assert item['required_ac_duty_kw'] == pytest.approx(item['required_dc_duty_kw'] * 0.8)
    between = (item['required_ac_duty_kw'] + item['required_dc_duty_kw']) / 2
    changed = review.evaluate_tail_ac_review(source, ac(), {2: between})
    assert last(changed)['pcs_items'][1]['meets_pcs_nameplate'] is True
    failed = review.evaluate_tail_ac_review(source, ac(), {2: item['required_ac_duty_kw'] / 2})
    assert last(failed)['pcs_items'][1]['meets_pcs_nameplate'] is False
    assert any('required PCS AC discharge exceeds' in text for text in failed['errors'])


def test_undersized_main_group_is_not_hidden_by_adequate_tail_pcs(example):
    source = parent(example)
    output = ac([dict(pcs_count=2, pcs_kw=100, dc_blocks=2),
                 dict(pcs_count=2, pcs_kw=1250, dc_blocks=2)])
    original_source, original_output = deepcopy(source), deepcopy(output)
    result = review.evaluate_tail_ac_review(source, output)
    assert result['topology_valid'] is True
    assert result['meets_nominal_dc_power'] is True
    assert all(item['meets_pcs_nameplate'] is False for item in result['groups'][0]['pcs_items'])
    assert all(item['meets_pcs_nameplate'] is True for item in last(result)['pcs_items'])
    assert any('AC Block 1 PCS' in message for message in result['errors'])
    assert not any('AC Block 2 PCS' in message for message in result['errors'])
    assert result['status'] == 'fails_nominal_review'
    assert source == original_source and output == original_output


def test_three_winding_lists_actual_pcs_without_dividing_transformer_rating(example):
    output = ac([dict(pcs_count=3, pcs_kw=1250, dc_blocks=2),
                 dict(pcs_count=3, pcs_kw=1250, dc_blocks=2)], topology='three_winding')
    result = review.evaluate_tail_ac_review(parent(example), output)
    assert [w['feeder_indices'] for w in last(result)['windings']] == [[1, 2], [3]]
    assert [w['pcs_rating_kw_sum'] for w in last(result)['windings']] == [2500, 1250]
    assert all(w['winding_rating_kva'] is None for w in last(result)['windings'])
    output.update(ac_block_product_block_code='SYNTHETIC-BOUND', transformer_mva=5)
    bound = review.evaluate_tail_ac_review(parent(example), output)
    assert last(bound)['transformer_review']['total_mva'] == 5
    assert last(bound)['transformer_review']['is_estimate'] is False


@pytest.mark.parametrize('field', ['pcs_count', 'pcs_kw', 'dc_blocks'])
@pytest.mark.parametrize('value', [-1, 0, True, False, float('nan'), float('inf'), 1.2, '2', None])
def test_invalid_original_ac_numbers_rejected_without_coercion(example, field, value):
    output = ac()
    output['ac_block_rows'][0][field] = value
    with pytest.raises(ValueError):
        review.evaluate_tail_ac_review(parent(example), output)


@pytest.mark.parametrize('override', [{1: 1000}, {3: 1000}, {'2': 1000}, {True: 1000},
                                     {2: -1}, {2: 0}, {2: True}, {2: float('nan')},
                                     {2: float('inf')}, {2: '1000'}, []])
def test_override_only_positive_nominal_rating_on_actual_tail_feeder(example, override):
    with pytest.raises(ValueError):
        review.evaluate_tail_ac_review(parent(example), ac(), override)


@pytest.mark.parametrize('field,value', [('dc_block_output_circuits', True),
    ('dc_block_output_circuits', 3), ('transformer_topology', None),
    ('lv_winding_count', 2), ('dc_blocks_total', 5), ('num_blocks', 3),
    ('dc_unit_kind', 'independent_cabinet_group')])
def test_known_ac_contract_conflicts_rejected(example, field, value):
    output = ac()
    output[field] = value
    with pytest.raises(ValueError):
        review.evaluate_tail_ac_review(parent(example), output)


def test_source_energy_failure_is_visible_not_hidden_by_pcs_capacity(example):
    source = parent(example)
    source.stage1.poi_energy_req_mwh = 1e6
    product = tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)[10]
    source.summary[tails.SUMMARY_KEY] = tails.evaluate_reduced_string_tail(
        source, example.bundle, product, example.basis)
    result = review.evaluate_tail_ac_review(source, ac())
    assert result['source_energy_requirement_met'] is False
    assert any('guarantee-year' in message for message in result['errors'])


@pytest.mark.parametrize('field', ['poi_power_mw', 'poi_energy_mwh', 'dc_total_mwh'])
@pytest.mark.parametrize('value', [999, True, None, float('nan')])
def test_same_count_ac_from_other_case_or_invalid_source_mirror_rejected(example, field, value):
    output = ac()
    output[field] = value
    with pytest.raises(ValueError, match='AC source'):
        review.evaluate_tail_ac_review(parent(example), output)


def test_source_mirrors_match_original_standard_bom_not_smaller_comparison(example):
    source, output = parent(example), ac()
    output.update(poi_power_mw=source.stage1.poi_power_req_mw,
                  poi_energy_mwh=source.stage1.poi_energy_req_mwh,
                  dc_total_mwh=source.stage2.dc_nameplate_bol_mwh)
    result = review.evaluate_tail_ac_review(source, output)
    assert result['total_dc_energy_mwh'] < output['dc_total_mwh']
    output['dc_total_mwh'] = result['total_dc_energy_mwh']
    with pytest.raises(ValueError, match='AC source dc_total_mwh'):
        review.evaluate_tail_ac_review(source, output)


@pytest.mark.parametrize('mutation', ['feeder', 'circuits', 'count', 'boolean', 'missing'])
def test_saved_original_connections_cannot_be_silently_replaced(example, mutation):
    output = ac()
    output['dc_allocation_plan'] = review.build_mixed_dc_allocation_plan(output['ac_block_rows'])
    before = deepcopy(output)
    assert review.evaluate_tail_ac_review(parent(example), output)
    assert output == before
    if mutation == 'feeder':
        output['dc_allocation_plan'][-1]['dc_block_connections'][-1]['feeder_indices'] = [1]
    elif mutation == 'circuits':
        output['dc_allocation_plan'][-1]['dc_block_connections'][-1]['output_circuit_count'] = 1
    elif mutation == 'count':
        output['dc_allocation_plan'][-1]['dc_blocks_total'] = 99
    elif mutation == 'boolean':
        output['dc_allocation_plan'][-1]['dc_block_connections'][0]['feeder_indices'] = [True]
    else:
        output['dc_allocation_plan'].pop()
    with pytest.raises(ValueError, match='Saved original DC allocation'):
        review.evaluate_tail_ac_review(parent(example), output)


def test_roundtrip_restore_does_not_run_stage3_and_input_is_unchanged(example, monkeypatch):
    source, output = parent(example, 8), ac()
    result = review.evaluate_tail_ac_review(source, output, {2: 1000.5})
    output[review.REVIEW_KEY] = result
    before = deepcopy(output)
    def forbidden(*args, **kwargs):
        raise AssertionError('Saved review must not rerun lifetime calculation')
    monkeypatch.setattr(tails, 'run_stage3', forbidden)
    assert review.restored_tail_ac_review(source, output) == result
    assert output == before


@pytest.mark.parametrize('change', ['ac_configuration', 'dc_source', 'review', 'review_rehashed', 'override_duplicate'])
def test_saved_source_and_internal_review_mismatch_rejected(example, change):
    source, output = parent(example), ac()
    output['grid_kv'] = 33
    output[review.REVIEW_KEY] = review.evaluate_tail_ac_review(source, output, {2: 1200})
    saved = output[review.REVIEW_KEY]
    if change == 'ac_configuration':
        output['grid_kv'] = 22
    elif change == 'dc_source':
        source.stage1.dc_power_required_mw += 0.1
    elif change in ('review', 'review_rehashed'):
        saved['groups'][-1]['pcs_items'][1]['required_ac_duty_kw'] = 1
        if change == 'review_rehashed':
            resign(saved)
    else:
        saved['tail_pcs_rating_overrides_kw'].append(deepcopy(saved['tail_pcs_rating_overrides_kw'][0]))
        resign(saved)
    with pytest.raises(ValueError):
        review.restored_tail_ac_review(source, output)
