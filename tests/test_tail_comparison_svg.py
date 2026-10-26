"""Semantic checks for the bounded last-group preview, not a second allocator."""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from calb_sizing_tool.services.dc_tail_ac_review_service import REVIEW_KEY, evaluate_tail_ac_review
from calb_sizing_tool.services.dc_tail_preview_service import build_tail_sld_preview
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from calb_sizing_tool.sld.tail_comparison_preview import render_tail_comparison_svg
from tests.test_dc_reduced_string_tail import example
from tests.test_dc_tail_ac_review import ac, parent


def manifest(example, strings=10, dc_per_group=2, pcs_per_group=None, overrides=None, topology='two_winding'):
    source = parent(example, strings=strings, count=dc_per_group * 2)
    output = ac([dict(pcs_count=pcs_per_group or dc_per_group, pcs_kw=1250, dc_blocks=dc_per_group)] * 2,
                topology=topology)
    output[REVIEW_KEY] = evaluate_tail_ac_review(source, output, overrides)
    return build_tail_sld_preview(source, output)


def nodes(root, kind):
    return [node for node in root.iter() if node.attrib.get('data-kind') == kind]


def words(root):
    return ' '.join(root.itertext())


def resign(value):
    value['preview_sha256'] = _hash_payload({key: item for key, item in value.items() if key != 'preview_sha256'})


def test_actual_last_group_units_and_individual_pcs_nameplates_are_not_averaged(example):
    source = manifest(example, overrides={2: 1000})
    before = deepcopy(source)
    root = ET.fromstring(render_tail_comparison_svg(source))
    assert source == before
    assert [(unit.attrib['data-role'], unit.attrib['data-strings'], float(unit.attrib['data-energy-mwh']))
            for unit in nodes(root, 'dc-unit')] == [('main', '12', 5.016), ('tail', '10', 4.18)]
    assert [float(item.attrib['data-rating-kw']) for item in nodes(root, 'pcs')] == [1250, 1000]
    assert 'AC Block 2' in words(root)
    assert '1 DC output -> 1 PCS' in words(root)
    assert 'COMPARISON ONLY' in words(root) and 'NOT ADOPTED' in words(root)
    assert 'NOT FOR CONSTRUCTION' in words(root)
    assert 'tail-last-group-comparison-v1' not in words(root)
    assert root.attrib['data-renderer-version'] == 'tail-last-group-comparison-v1'
    assert 'preceding 1 AC groups are outside this preview' in words(root)
    assert len(nodes(root, 'dc-unit')) == source['last_group']['dc_count']


def test_eight_string_two_outputs_keep_exact_connections_and_unknown_duties(example):
    source = manifest(example, strings=8, pcs_per_group=4, overrides={3: 900, 4: 1800})
    root = ET.fromstring(render_tail_comparison_svg(source))
    expected = [(unit['unit_id'], str(feeder)) for unit in source['last_group']['connections']
                for feeder in unit['feeder_indices']]
    assert [(link.attrib['data-unit'], link.attrib['data-feeder'])
            for link in nodes(root, 'dc-connection')] == expected
    tail_id = source['last_group']['connections'][-1]['unit_id']
    tail_links = [link for link in nodes(root, 'dc-connection') if link.attrib['data-unit'] == tail_id]
    assert len(tail_links) == 2 and all('pending-link' in link.attrib['class'] for link in tail_links)
    assert words(root).count('AC ref duty: TBC') == 2
    assert '2 output links; per-output duty / current TBC' in words(root)
    assert '4+4' not in words(root) and '50%' not in words(root)
    assert [float(item.attrib['data-rating-kw']) for item in nodes(root, 'pcs')] == [1250, 1250, 900, 1800]


def test_eight_string_one_pcs_does_not_invent_confirmed_parallel_output_wires(example):
    source = manifest(example, strings=8)
    root = ET.fromstring(render_tail_comparison_svg(source))
    tail_id = source['last_group']['connections'][-1]['unit_id']
    links = [link for link in nodes(root, 'dc-connection') if link.attrib['data-unit'] == tail_id]
    assert len(links) == 1 and 'pending-link' in links[0].attrib['class']
    assert links[0].attrib['data-input-arrangement'] == 'TBC'
    assert '2 outputs / 1 PCS: input arrangement TBC' in words(root)
    assert 'No equal split or parallel permission is assumed.' in words(root)


@pytest.mark.parametrize('circuits', [1, 2])
def test_main_configured_branch_count_is_not_presented_as_physical_hardware_outputs(example, circuits):
    source = parent(example)
    output = ac(circuits=circuits)
    output[REVIEW_KEY] = evaluate_tail_ac_review(source, output)
    root = ET.fromstring(render_tail_comparison_svg(build_tail_sld_preview(source, output)))
    assert f"{circuits} configured PCS branch{'es' if circuits == 2 else ''}" in words(root)
    # Only the owner's ten-string tail, not a main configured-branch setting,
    # is described here as a confirmed physical one-output product variant.
    assert '1 DC output -> 1 PCS' in words(root)
    assert '2 DC outputs' not in words(root)


def test_ten_string_two_pcs_is_blocked_before_any_svg_is_returned(example):
    source = manifest(example, strings=10, pcs_per_group=4)
    assert source['preview_available'] is False and source['last_group'] is None
    with pytest.raises(ValueError, match='available|blocked'):
        render_tail_comparison_svg(source)


def test_lv_assignment_is_consumed_without_redistribution_or_winding_capacity_inference(example):
    source = manifest(example, pcs_per_group=3, topology='three_winding')
    root = ET.fromstring(render_tail_comparison_svg(source))
    assert [(int(link.attrib['data-feeder']), int(link.attrib['data-winding']))
            for link in nodes(root, 'lv-assignment')] == [(1, 1), (2, 1), (3, 2)]
    assert words(root).count('Assign / kVA: TBC') == 2
    assert 'LV winding limits: TBC' in words(root)
    assert 'Planning estimate' in words(root)


def test_single_pcs_three_winding_renders_unused_winding_without_inventing_a_link(example):
    source = manifest(example, pcs_per_group=1, topology='three_winding')
    original = deepcopy(source)
    root = ET.fromstring(render_tail_comparison_svg(source))
    assert source == original
    assert source['status'] == 'diagram_only_with_tbc'
    assert len(nodes(root, 'pcs')) == 1
    assert [(node.attrib['data-winding'], node.attrib.get('data-unused', 'false'))
            for node in nodes(root, 'lv-winding')] == [('1', 'false'), ('2', 'true')]
    assert [(node.attrib['data-feeder'], node.attrib['data-winding'])
            for node in nodes(root, 'lv-assignment')] == [('1', '1')]
    assert 'Unused / no PCS' in words(root)
    assert 'Termination: TBC' in words(root) and 'Rating: TBC' in words(root)
    assert all(winding['winding_rating_kva'] is None for winding in source['last_group']['windings'])


def test_two_pcs_three_winding_keeps_both_original_assignments_and_normal_status(example):
    source = manifest(example, pcs_per_group=2, topology='three_winding')
    root = ET.fromstring(render_tail_comparison_svg(source))
    assert source['status'] == 'diagram_only'
    assert 'unused_lv_winding_indices' not in source
    assert [(node.attrib['data-feeder'], node.attrib['data-winding'])
            for node in nodes(root, 'lv-assignment')] == [('1', '1'), ('2', '2')]
    assert all('data-unused' not in node.attrib for node in nodes(root, 'lv-winding'))
    assert 'Unused / no PCS' not in words(root)


@pytest.mark.parametrize('corruption', ['unknown_feeder', 'missing_feeder', 'unmarked_unused', 'false_status'])
def test_unused_winding_does_not_relax_feeder_coverage_or_tbc_validation(example, corruption):
    source = manifest(example, pcs_per_group=1, topology='three_winding')
    if corruption == 'unknown_feeder':
        source['last_group']['windings'][0]['feeder_indices'] = [2]
    elif corruption == 'missing_feeder':
        source['last_group']['windings'][0]['feeder_indices'] = []
        source['unused_lv_winding_indices'] = [1, 2]
    elif corruption == 'unmarked_unused':
        source.pop('unused_lv_winding_indices')
    else:
        source['status'] = 'diagram_only'
    resign(source)
    with pytest.raises(ValueError, match='LV assignment|Unused LV'):
        render_tail_comparison_svg(source)


@pytest.mark.parametrize('indices', [[1, 99], [1, 1]])
def test_rehashed_out_of_range_or_duplicate_winding_indices_cannot_escape_drawing(example, indices):
    source = manifest(example, pcs_per_group=2, topology='three_winding')
    # Saved list order does not determine winding identity or reassign feeders.
    source['last_group']['windings'].reverse()
    resign(source)
    assert render_tail_comparison_svg(source)
    for winding, index in zip(source['last_group']['windings'], indices):
        winding['winding_index'] = index
    resign(source)
    with pytest.raises(ValueError, match='LV winding indices'):
        render_tail_comparison_svg(source)


@pytest.mark.parametrize('dc_count', [1, 2, 4, 8])
def test_actual_group_sizes_scale_without_omission_or_geometry_outside_viewbox(example, dc_count):
    source = manifest(example, strings=8, dc_per_group=dc_count, pcs_per_group=dc_count * 2)
    root = ET.fromstring(render_tail_comparison_svg(source))
    width, height = (float(value) for value in root.attrib['viewBox'].split()[2:])
    assert len(nodes(root, 'dc-unit')) == dc_count
    assert len(nodes(root, 'pcs')) == dc_count * 2
    assert len(nodes(root, 'dc-connection')) == dc_count * 2
    for node in root.iter():
        if node.tag.endswith('rect'):
            x, y = float(node.attrib.get('x', 0)), float(node.attrib.get('y', 0))
            assert 0 <= x < width and 0 <= y < height
            assert x + float(node.attrib['width']) <= width
            assert y + float(node.attrib['height']) <= height
        elif node.tag.endswith('polyline'):
            for coordinate in node.attrib['points'].split():
                x, y = map(float, coordinate.split(','))
                assert 0 <= x <= width and 0 <= y <= height
        elif node.tag.endswith('text'):
            assert 0 <= float(node.attrib['x']) <= width
            assert 0 <= float(node.attrib['y']) <= height
            assert float(node.attrib['font-size']) >= 17
    # Cards themselves remain separate even at the largest supported size.
    for kind in ('dc-unit', 'pcs'):
        boxes = sorted(nodes(root, kind), key=lambda node: float(node.attrib['y']))
        assert all(float(left.attrib['y']) + float(left.attrib['height']) < float(right.attrib['y'])
                   for left, right in zip(boxes, boxes[1:]))


def test_labels_and_attribute_values_are_xml_escaped(example):
    source = manifest(example)
    source['last_group']['connections'][0]['unit_id'] = '<script>&"unit'
    resign(source)
    svg = render_tail_comparison_svg(source)
    root = ET.fromstring(svg)
    assert not any(node.tag.endswith('script') for node in root.iter())
    assert '<script>&"unit' in words(root)
    assert nodes(root, 'dc-unit')[0].attrib['data-unit'] == '<script>&"unit'


@pytest.mark.parametrize('field,value', [('comparison_only', False), ('diagram_only', False),
    ('downstream_ready', True), ('engineering_approved', True), ('preview_available', False),
    ('status', 'official'), ('blocking_reasons', ['Global nominal review failure'])])
def test_approved_or_blocked_manifest_cannot_be_mislabeled_as_safe_preview(example, field, value):
    source = manifest(example)
    source[field] = value
    resign(source)
    with pytest.raises(ValueError):
        render_tail_comparison_svg(source)


def test_changed_manifest_needs_new_source_validation_before_render(example):
    source = manifest(example)
    source['last_group']['pcs_items'][-1]['rating_kw'] = 999
    with pytest.raises(ValueError, match='changed'):
        render_tail_comparison_svg(source)


@pytest.mark.parametrize('field', ['source_energy_requirement_met', 'meets_nominal_dc_power', 'topology_valid'])
def test_failed_global_nominal_gate_cannot_render_even_if_available_flag_is_incorrect(example, field):
    source = manifest(example)
    source['nominal_review'][field] = False
    resign(source)
    with pytest.raises(ValueError, match='failed global'):
        render_tail_comparison_svg(source)


@pytest.mark.parametrize('field,value', [('dc_count', 3), ('main_count', 5), ('ac_block_index', 999)])
def test_rehashed_inconsistent_scope_or_counts_fail_closed(example, field, value):
    source = manifest(example)
    source['last_group'][field] = value
    resign(source)
    with pytest.raises(ValueError):
        render_tail_comparison_svg(source)


def test_invalid_output_count_or_unknown_pcs_reference_is_rejected_even_with_new_digest(example):
    source = manifest(example)
    source['last_group']['connections'][-1]['feeder_indices'] = [1, 2]
    resign(source)
    with pytest.raises(ValueError, match='declared outputs'):
        render_tail_comparison_svg(source)
    source = manifest(example)
    source['last_group']['connections'][-1]['feeder_indices'] = [99]
    resign(source)
    with pytest.raises(ValueError, match='unavailable PCS'):
        render_tail_comparison_svg(source)


def test_renderer_is_deterministic_and_sample_is_not_a_registered_artifact(example, tmp_path):
    source = manifest(example, strings=8, dc_per_group=8, pcs_per_group=16, topology='three_winding')
    rendered = render_tail_comparison_svg(source)
    assert rendered == render_tail_comparison_svg(source)
    sample = tmp_path / 'preview.svg'
    sample.write_text(rendered, encoding='utf-8')
    assert ET.parse(sample).getroot().attrib['role'] == 'img'
