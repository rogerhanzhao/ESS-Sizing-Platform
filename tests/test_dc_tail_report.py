"""Fixed-count comparisons and read-only customer exports, on synthetic data."""
from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile

from docx import Document
import pytest

from calb_sizing_tool.reporting.dc_tail_report import build_tail_dc_report, tail_report_filename
from calb_sizing_tool.services import dc_reduced_string_tail_service as tails
from calb_sizing_tool.services.dc_tail_ac_review_service import evaluate_tail_ac_review
from calb_sizing_tool.services.dc_tail_preview_service import build_tail_sld_preview
from calb_sizing_tool.services.stage2_service import build_config_container_only
from calb_sizing_tool.services.stage3_service import run_stage3
from tests.test_dc_reduced_string_tail import example, selected, resign


def multi_parent(example, strings=10, quantity=4):
    parent = deepcopy(example.snapshot)
    parent.stage2 = build_config_container_only(29, 5.016, tails.STANDARD_EXCEL_CODE, 'Standard 12-string container')
    parent.stage3 = run_stage3(parent.stage1, parent.stage2, example.bundle)
    parent.poi_usable_energy_mwh_at_guarantee_year = parent.stage3.rows[-1].poi_usable_energy_mwh
    parent.summary[tails.SUMMARY_KEY] = tails.evaluate_reduced_string_tail(
        parent, example.bundle, selected(example, strings), example.basis, tail_count=quantity)
    return parent


def document_text(data):
    doc = Document(BytesIO(data))
    text = '\n'.join([p.text for p in doc.paragraphs] +
                     [c.text for t in doc.tables for r in t.rows for c in r.cells])
    return doc, text


@pytest.mark.parametrize('quantity', [1, 2, 3, 4])
@pytest.mark.parametrize('strings', [8, 10])
def test_fixed_count_composition_actual_projection_and_report(example, quantity, strings):
    parent = multi_parent(example, strings, quantity)
    original = parent.model_dump(mode='json')
    comparison = tails.restored_comparison(parent)
    result = comparison['snapshot']
    assert result['stage2']['container_count'] == parent.stage2.container_count == 6
    assert [i['count'] for i in result['stage2']['block_config_items']] == [6 - quantity, quantity]
    expected = round((6 - quantity) * 5.016 + quantity * example.basis['tails'][strings]['energy_mwh'], 3)
    assert result['stage2']['dc_nameplate_bol_mwh'] == expected
    assert result['stage3']['meta']['effective_c_rate'] == pytest.approx(parent.stage1.dc_power_required_mw / expected)
    nominal = (6 - quantity) * example.basis['main_energy_raw_mwh'] * .5 + quantity * example.basis['tails'][strings]['power_kw'] / 1000
    assert comparison['nominal_dc_power_mw'] == pytest.approx(nominal)
    doc, text = document_text(build_tail_dc_report(parent))
    assert f'Total container count remains 6.' in text
    assert f'{quantity} × {strings}-string containers' in text
    assert f'{expected:.3f}' in text
    assert f'{comparison["poi_energy_at_guarantee_year_mwh"]:.3f}' in text
    assert 'Nominal power check' in text and 'Capacity reduction' in text
    assert doc.tables[0].rows[1].cells[1].text == doc.tables[0].rows[1].cells[2].text == '6'
    assert len(doc.inline_shapes) == 1  # The actual baseline/comparison chart.
    assert parent.model_dump(mode='json') == original
    if quantity > 1:
        assert evaluate_tail_ac_review(parent, {}) is None
        assert build_tail_sld_preview(parent, {}) is None


@pytest.mark.parametrize('quantity', [0, 5, -1, True, 1.0, '2', None])
def test_invalid_quantities_rejected_without_mutating_standard(example, quantity):
    before = example.snapshot.model_dump(mode='json')
    with pytest.raises(ValueError, match='between 1 and 4'):
        tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, selected(example), example.basis, tail_count=quantity)
    assert before == example.snapshot.model_dump(mode='json')


def test_all_containers_cannot_become_tails(example):
    assert example.snapshot.stage2.container_count == 2
    with pytest.raises(ValueError, match='retain at least one'):
        tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, selected(example), example.basis, tail_count=2)


@pytest.mark.parametrize('corruption', ['quantity', 'missing_quantity', 'version', 'baseline', 'hash'])
def test_report_rejects_tampered_or_mismatched_saved_comparison(example, corruption):
    parent = multi_parent(example)
    result = parent.summary[tails.SUMMARY_KEY]
    if corruption == 'quantity':
        result['tail_container_count'] = 3
    elif corruption == 'missing_quantity':
        result.pop('tail_container_count')
    elif corruption == 'version':
        result['schema_version'] = 1
    elif corruption == 'baseline':
        parent.stage1.poi_energy_req_mwh += 1
    else:
        result['comparison_sha256'] = 'changed'
    if corruption != 'hash':
        resign(result)
    with pytest.raises(ValueError):
        build_tail_dc_report(parent)


def test_legacy_one_tail_export_no_ids_and_no_sizing_call(example, monkeypatch):
    parent = multi_parent(example, quantity=1)
    assert 'tail_container_count' not in parent.summary[tails.SUMMARY_KEY]
    assert parent.summary[tails.SUMMARY_KEY]['schema_version'] == 1
    def forbidden(*args, **kwargs):
        raise AssertionError('Export must not calculate or save')
    monkeypatch.setattr(tails, 'run_stage3', forbidden)
    monkeypatch.setattr(tails, 'evaluate_reduced_string_tail', forbidden)
    data = build_tail_dc_report(parent, case_name='Case B (AC run 627dcd48-bb9c-4312-8c5e-1b8243f0e725)')
    doc, text = document_text(data)
    assert 'Case: Case B' in text
    assert '627dcd48' not in text and 'profile ID' not in text
    assert parent.summary[tails.SUMMARY_KEY]['comparison_sha256'] not in text
    assert '94.00%' in text
    assert '1x10String' in tail_report_filename(parent)
    with ZipFile(BytesIO(data)) as archive:
        assert any(p.startswith('word/media/') for p in archive.namelist())


def test_failed_guarantee_is_exported_as_failure_with_same_count(example):
    # Standard 2 x 5.016 meets Y2, but 1 x 5.016 + 1 x 3.344 does not.
    example.snapshot.stage1.dc_energy_capacity_required_mwh *= 6.5 / 6
    example.snapshot.stage1.poi_energy_req_mwh = 6.5
    example.snapshot.stage3 = run_stage3(example.snapshot.stage1, example.snapshot.stage2, example.bundle)
    result = tails.evaluate_reduced_string_tail(example.snapshot, example.bundle, selected(example, 8), example.basis)
    assert not result['meets_guarantee_year_energy']
    parent = deepcopy(example.snapshot)
    parent.summary[tails.SUMMARY_KEY] = result
    _, text = document_text(build_tail_dc_report(parent))
    assert 'DC comparison requirements not met' in text
    assert 'POI energy check at Y2' in text and 'Not met' in text
    assert 'Total container count remains 2.' in text


def test_standard_run_has_no_tail_report(example):
    with pytest.raises(ValueError, match='saved reduced-string'):
        build_tail_dc_report(example.snapshot)
