"""A last-group drawing preview never promotes the comparison into sizing."""
from copy import deepcopy

import pytest

from calb_sizing_tool.services import ac_run_service
from calb_sizing_tool.services import dc_reduced_string_tail_service as tails
from calb_sizing_tool.services import dc_tail_ac_review_service as review
from calb_sizing_tool.services.dc_tail_preview_service import build_tail_sld_preview
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from tests.test_dc_reduced_string_tail import example
from tests.test_dc_tail_ac_review import ac, parent


def saved(source, output=None, overrides=None):
    output = ac() if output is None else output
    output[review.REVIEW_KEY] = review.evaluate_tail_ac_review(source, output, overrides)
    return output


def test_missing_comparisons_leave_original_workflow_without_preview(example):
    assert build_tail_sld_preview(example.snapshot, {}) is None
    assert build_tail_sld_preview(parent(example), ac()) is None


@pytest.mark.parametrize('admin', [False, True])
def test_exact_fleet_and_last_physical_group_without_sizing_or_input_mutation(example, admin, monkeypatch):
    source = parent(example, admin=admin)
    output = saved(source, overrides={2: 1000.5})
    before = deepcopy((source, output))

    def forbidden(*args, **kwargs):
        raise AssertionError('A read-only drawing preview must not calculate lifetime or open a database')

    monkeypatch.setattr(tails, 'run_stage3', forbidden)
    monkeypatch.setattr(ac_run_service, 'session_scope', forbidden)
    result = build_tail_sld_preview(source, output)
    assert (source, output) == before
    assert result['preview_available'] is True
    assert result['fleet']['main_count'] == 3
    assert result['fleet']['tail_count'] == 1
    assert result['fleet']['total_dc_count'] == 4
    unit = 5.01596 if admin else 5.016
    assert result['fleet']['comparison_energy_mwh'] == round(3 * unit + 4.18, 3)
    assert result['fleet']['standard_reference_energy_mwh'] == source.stage2.dc_nameplate_bol_mwh
    assert result['scope']['ac_block_index'] == 2
    assert result['scope']['preceding_main_container_count'] == 2
    assert result['scope']['preceding_dc_energy_mwh'] == 2 * unit
    assert result['scope']['first_physical_dc_index'] == 3
    assert result['scope']['final_physical_dc_index'] == 4
    assert result['last_group'] == output[review.REVIEW_KEY]['groups'][-1]
    assert [c['unit_id'] for c in result['last_group']['connections']] == ['DC-003', 'DC-004']
    assert [p['rating_kw'] for p in result['last_group']['pcs_items']] == [1250, 1000.5]
    assert result['comparison_only'] is result['diagram_only'] is True
    assert result['engineering_approved'] is result['downstream_ready'] is False
    # The drawing consumer cannot mutate either authoritative source through the handoff.
    result['last_group']['connections'][-1]['strings_in_parallel'] = 99
    assert (source, output) == before


def test_eight_string_two_pcs_is_diagram_tbc_without_equal_split_or_winding_limits(example):
    source = parent(example, 8)
    output = saved(source, ac([
        dict(pcs_count=2, pcs_kw=1250, dc_blocks=2),
        dict(pcs_count=4, pcs_kw=1250, dc_blocks=2),
    ], topology='three_winding'), {3: 1000.5, 4: 1800})
    result = build_tail_sld_preview(source, output)
    assert result['preview_available'] is True
    assert result['status'] == 'diagram_only_with_tbc'
    assert result['unknown_output_duties'] is True
    assert result['tail_output_partition_confirmed'] is False
    assert result['single_pcs_input_arrangement_unconfirmed'] is False
    tail = result['last_group']['connections'][-1]
    assert tail['feeder_indices'] == [3, 4]
    assert [item['required_dc_duty_kw'] for item in tail['per_feeder_duties']] == [None, None]
    assert [item['required_ac_duty_kw'] for item in result['last_group']['pcs_items'][2:]] == [None, None]
    assert [item['rating_kw'] for item in result['last_group']['pcs_items'][2:]] == [1000.5, 1800]
    assert all(w['winding_rating_kva'] is None for w in result['last_group']['windings'])
    assert any('no 4+4 or equal split' in text for text in result['pending_evidence'])


def test_eight_string_one_pcs_keeps_explicit_input_arrangement_unconfirmed(example):
    source = parent(example, 8)
    result = build_tail_sld_preview(source, saved(source))
    assert result['preview_available'] is True
    assert result['status'] == 'diagram_only_with_tbc'
    assert result['unknown_output_duties'] is False
    assert result['tail_output_partition_confirmed'] is False
    assert result['single_pcs_input_arrangement_unconfirmed'] is True
    assert any('independent input or parallel applicability' in text for text in result['pending_evidence'])


@pytest.mark.parametrize('strings', [10, 8])
def test_single_pcs_three_winding_marks_unused_saved_winding_without_changing_review(example, strings):
    source = parent(example, strings)
    output = saved(source, ac([dict(pcs_count=1, pcs_kw=2500, dc_blocks=2)] * 2,
                              topology='three_winding'))
    original = deepcopy((source, output))
    result = build_tail_sld_preview(source, output)
    assert result['preview_available'] is True
    assert result['status'] == 'diagram_only_with_tbc'
    assert result['unused_lv_winding_indices'] == [2]
    assert [winding['feeder_indices'] for winding in result['last_group']['windings']] == [[1], []]
    assert result['last_group'] == output[review.REVIEW_KEY]['groups'][-1]
    assert result['source']['ac_review_sha256'] == output[review.REVIEW_KEY]['review_sha256']
    assert any('no assigned PCS' in text and 'termination and ratings remain TBC' in text
               for text in result['pending_evidence'])
    assert (source, output) == original
    assert review.restored_tail_ac_review(source, output) == output[review.REVIEW_KEY]


@pytest.mark.parametrize('failure', ['ten_two_pcs', 'pcs_nominal_power', 'guarantee_energy', 'dc_nominal_power'])
def test_failed_review_has_no_drawable_group(example, failure):
    source = parent(example)
    output, overrides = ac(), None
    if failure == 'ten_two_pcs':
        output = ac([dict(pcs_count=4, pcs_kw=1250, dc_blocks=2)] * 2)
    elif failure == 'pcs_nominal_power':
        overrides = {2: 1}
    else:
        if failure == 'guarantee_energy':
            source.stage1.poi_energy_req_mwh = 1e6
        else:
            source.stage1.dc_power_required_mw = 10
            source.stage1.poi_power_req_mw = 10
            source.stage3 = tails.run_stage3(source.stage1, source.stage2, example.bundle)
        product = tails.available_products(example.rows, example.basis, tails.STANDARD_EXCEL_CODE)[10]
        source.summary[tails.SUMMARY_KEY] = tails.evaluate_reduced_string_tail(
            source, example.bundle, product, example.basis)
    result = build_tail_sld_preview(source, saved(source, output, overrides))
    assert result['preview_available'] is False
    assert result['status'] == 'blocked'
    assert result['last_group'] is None
    assert result['blocking_reasons']
    assert result['downstream_ready'] is result['engineering_approved'] is False


@pytest.mark.parametrize('change', ['review', 'review_rehashed', 'review_false_pass_rehashed', 'dc_source', 'ac_group'])
def test_corrupt_or_internally_contradictory_saved_sources_cannot_be_previewed(example, change):
    source = parent(example)
    output = saved(source)
    if change in ('review', 'review_rehashed'):
        output[review.REVIEW_KEY]['groups'][-1]['pcs_items'][-1]['required_ac_duty_kw'] = 0.01
    elif change == 'review_false_pass_rehashed':
        output = saved(source, ac([dict(pcs_count=4, pcs_kw=1250, dc_blocks=2)] * 2))
        output[review.REVIEW_KEY].update(topology_valid=True, errors=[])
    elif change == 'dc_source':
        source.stage1.dc_power_required_mw += 0.01
    elif change == 'ac_group':
        output['ac_block_rows'][-1]['pcs_kw'] = 1500
    if change in ('review_rehashed', 'review_false_pass_rehashed'):
        obj = output[review.REVIEW_KEY]
        obj['review_sha256'] = _hash_payload({k: v for k, v in obj.items() if k != 'review_sha256'})
    with pytest.raises(ValueError):
        build_tail_sld_preview(source, output)


def test_only_comparison_pcs_rating_changes_full_source_and_preview_identity(example):
    source = parent(example)
    first = build_tail_sld_preview(source, saved(source, overrides={2: 1000}))
    second = build_tail_sld_preview(source, saved(source, overrides={2: 1100}))
    assert first['source']['ac_configuration_sha256'] == second['source']['ac_configuration_sha256']
    assert first['source']['dc_payload_sha256'] == second['source']['dc_payload_sha256']
    assert first['source']['ac_payload_sha256'] != second['source']['ac_payload_sha256']
    assert first['source']['ac_review_sha256'] != second['source']['ac_review_sha256']
    assert first['preview_sha256'] != second['preview_sha256']


def test_complete_ac_payload_is_bound_even_when_formal_identity_and_review_unchanged(example):
    source = parent(example)
    output = saved(source)
    first = build_tail_sld_preview(source, output)
    output['presentation_note'] = 'A source payload revision outside the AC identity'
    second = build_tail_sld_preview(source, output)
    assert first['source']['ac_configuration_sha256'] == second['source']['ac_configuration_sha256']
    assert first['source']['ac_review_sha256'] == second['source']['ac_review_sha256']
    assert first['source']['ac_payload_sha256'] != second['source']['ac_payload_sha256']
    assert first['preview_sha256'] != second['preview_sha256']


@pytest.mark.parametrize('value', [float('nan'), float('inf'), object()])
def test_nonfinite_or_nonjson_source_extension_rejected(example, value):
    source = parent(example)
    output = saved(source)
    output['unused_extension'] = value
    with pytest.raises(ValueError, match='finite JSON'):
        build_tail_sld_preview(source, output)


def test_manifest_is_deterministic_and_digest_covers_true_scope_and_unknowns(example):
    source = parent(example, 8)
    output = saved(source)
    result = build_tail_sld_preview(source, output)
    assert build_tail_sld_preview(source, output) == result
    assert result['preview_sha256'] == _hash_payload({k: v for k, v in result.items() if k != 'preview_sha256'})
    changed = deepcopy(result)
    changed['scope']['ac_block_index'] = 99
    assert _hash_payload({k: v for k, v in changed.items() if k != 'preview_sha256'}) != result['preview_sha256']
