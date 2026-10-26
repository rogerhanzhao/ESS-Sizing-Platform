from copy import deepcopy

import pytest

from tests.dc_tail_fixture import make_tail_fixture
from calb_sizing_tool.services import dc_composition_comparison_service as service
from calb_sizing_tool.services.dc_product_comparison_service import package_sha256, run_product_comparison


@pytest.fixture
def library(tmp_path):
    return make_tail_fixture(tmp_path / 'synthetic-tail.sqlite')


def evaluate(lib, strings=10, **kwargs):
    lines = [dict(revision_id=lib.revision_ids[12], quantity=1 if strings != 12 else 2, role='main')]
    if strings != 12:
        lines.append(dict(revision_id=lib.revision_ids[strings], quantity=1, role='tail'))
    ids = {row['revision_id'] for row in lines}
    options = dict(variant_service=lib.variants, allow_special_configurations=strings != 12,
        special_reason='Synthetic tail study', temperature_c=25, standby_soc_pct=50,
        electrical_partitions={key: value for key, value in lib.partitions.items() if key in ids})
    options.update(kwargs)
    return service.evaluate_dc_composition(lib.revisions, lines, lib.case, lib.baseline,
        {key: lib.packages[key] for key in ids}, {key: lib.digests[key] for key in ids}, **options)


def compare(lib, **kwargs):
    options = dict(allow_special_configurations=True, special_reason='Synthetic replacement study',
        temperature_c=25, standby_soc_pct=50, max_iter=3, electrical_partitions=lib.partitions)
    options.update(kwargs)
    return service.run_tail_replacement_comparison(lib.revisions, lib.revision_ids[12],
        [lib.revision_ids[10], lib.revision_ids[8]], lib.case, lib.baseline, lib.packages, lib.digests, **options)


def test_standard_result_matches_unchanged_frozen_parent_comparison(library):
    lib = library
    parent = lib.revision_ids[12]
    before = lib.admin.snapshot()
    original_packages = deepcopy(lib.packages)
    expected = run_product_comparison(lib.revisions, parent, lib.case, lib.baseline,
        lib.packages[parent], lib.digests[parent], temperature_c=25, standby_soc_pct=50, max_iter=3)
    result = evaluate(lib, 12)
    assert result['stage1'].model_dump() == expected['snapshot'].stage1.model_dump()
    assert result['stage2'].dc_nameplate_bol_mwh == expected['snapshot'].stage2.dc_nameplate_bol_mwh
    assert result['stage3'].model_dump() == expected['snapshot'].stage3.model_dump()
    assert result['comparison_only'] and result['downstream_ready'] is False
    assert result['dc_duty_status'] == 'passes_declared_dc_limits'
    assert lib.admin.snapshot() == before and lib.packages == original_packages


def test_tail_options_separate_energy_from_hardware_and_keep_raw_precision(library):
    result = compare(library)
    rows = result['candidates']
    assert [row['candidate_key'] for row in rows] == ['standard', 'tail_10', 'tail_8']
    assert [row['result']['meets_guarantee_year_energy'] for row in rows] == [True, True, False]
    assert all(row['result']['dc_duty_status'] == 'passes_declared_dc_limits' for row in rows)
    tail = rows[1]['result']
    assert tail['raw_dc_nameplate_mwh'] == pytest.approx(9.1959296)
    assert tail['model_dc_nameplate_mwh'] == 9.196
    assert tail['physical_c_rate'] != tail['model_c_rate']
    assert tail['model_c_rate'] == tail['stage3'].meta.effective_c_rate
    assert tail['ac_power_matching_pending'] and not result['downstream_ready']


@pytest.mark.parametrize('change,match', [('digest', 'digest mismatch'), ('revision', 'revision mismatch'),
    ('cell', 'cell mismatch'), ('boundary', 'DC-boundary'), ('approval', 'schema'),
    ('cycles', 'Cycles per year'), ('temperature', 'Temperature'), ('soc', 'Standby SOC'),
    ('dod', 'DOD'), ('life', 'horizon'), ('adjust', 'adjustment'), ('monotonic', 'basis mismatch'),
    ('raw-rate', 'Effective C-rate'), ('tables', 'identical numerical')])
def test_each_child_requires_independent_approved_applicability(library, monkeypatch, change, match):
    lib = library
    revision = lib.revision_ids[10]
    package = lib.packages[revision]
    if change == 'revision': package['product_revision_sha256'] = lib.revisions.inspect(lib.revision_ids[12])['sha256']
    if change == 'cell': package['product_cell_id'] = 'another-same-Ah-cell'
    if change == 'boundary': package['measurement_boundary'] = 'AC'
    if change == 'approval': package['review_status'] = 'draft'
    if change == 'cycles': package['soh_applicability'][0]['cycles_max'] = 364
    if change == 'temperature': package['conditions']['temperature_max_c'] = 24
    if change == 'soc': package['conditions']['standby_soc_max_pct'] = 49
    if change == 'dod': package['conditions']['dod_max_pct'] = 94
    if change == 'life': package['conditions']['project_life_max_years'] = 1
    if change == 'adjust': package['conditions']['rte_adjust_pp'] = 1
    if change == 'monotonic': package['conditions']['rte_monotonic_enforce'] = False
    if change == 'tables': package['tables']['soh_curve'][-1]['Soh_Dc_Pct'] = 89
    if change == 'raw-rate':
        package['soh_applicability'][0]['c_rate_max'] = (2 / 9.196 + 2 / 9.1959296) / 2
    lib.digests[revision] = 'bad' if change == 'digest' else package_sha256(package)
    monkeypatch.setattr(service, 'run_stage3', lambda *args: pytest.fail('Invalid evidence reached Stage 3'))
    with pytest.raises(ValueError, match=match):
        evaluate(lib)


def test_declared_global_power_cannot_hide_underpowered_tail(library):
    lib = library
    old = lib.revision_ids[10]
    lib.admin.update_record('dc_block', lib.product_ids[10], {'nominal_power_kw': 400})
    new = lib.revisions.create(lib.product_ids[10], 'SYNTHETIC-LOW-POWER', 'Synthetic short-tail limit')
    lib.revisions.transition(new, 'draft', 'parameter_review', 'Synthetic parameter check')
    lib.revisions.transition(new, 'parameter_review', 'candidate_only', 'Synthetic parameter review')
    relation = lib.variants.create(lib.revision_ids[12], new, 'LOW-POWER', dict(
        structural_evidence_ref='Synthetic structure', footprint_evidence_ref='Synthetic envelope',
        performance_evidence_ref='Synthetic revised continuous power'))
    lib.variants.transition(relation, 'draft', 'candidate_only', 'Synthetic lineage review')
    lib.revision_ids[10] = new
    package = deepcopy(lib.packages.pop(old))
    package['product_revision_sha256'] = lib.revisions.inspect(new)['sha256']
    lib.packages[new], lib.digests[new] = package, package_sha256(package)
    lib.digests.pop(old)
    lib.partitions[new] = lib.partitions.pop(old)
    result = evaluate(lib)
    assert result['meets_guarantee_year_energy']
    assert result['dc_duty_status'] == 'fails_declared_dc_limits'
    assert result['manifest']['aggregate_nominal_power_kw'] == 2900
    assert result['stage1'].dc_power_required_mw == 2
    assert not result['downstream_ready']


def test_missing_output_evidence_does_not_become_an_ac_pass(library):
    result = evaluate(library, electrical_partitions=None)
    assert result['meets_guarantee_year_energy']
    assert result['dc_duty_status'] == 'pending_electrical_evidence'
    assert result['ac_power_matching_pending'] and not result['downstream_ready']


def test_withdrawal_during_frozen_evaluation_rejects_result(library, monkeypatch):
    original = service.run_stage3
    def withdraw(*args):
        result = original(*args)
        library.variants.transition(library.relations[10], 'candidate_only', 'retired', 'Synthetic withdrawal')
        return result
    monkeypatch.setattr(service, 'run_stage3', withdraw)
    with pytest.raises(ValueError, match='current reviewed'):
        evaluate(library)


@pytest.mark.parametrize('kind', ['soh', 'rte'])
def test_rounding_cannot_silently_select_a_different_profile(library, monkeypatch, kind):
    lib = library
    midpoint = (2 / 9.196 + 2 / 9.1959296) / 2
    for revision, package in lib.packages.items():
        tables = package['tables']
        profile_key, curve_key = ('soh_profile', 'soh_curve') if kind == 'soh' else ('rte_profile', 'rte_curve')
        tables[profile_key][0]['C_Rate'] = midpoint - 0.01
        tables[profile_key].append(dict(tables[profile_key][0], Profile_Id=2, C_Rate=midpoint + 0.01))
        tables[curve_key].extend([dict(row, Profile_Id=2) for row in deepcopy(tables[curve_key])])
        scope_key = 'soh_applicability' if kind == 'soh' else 'rte_applicability'
        package[scope_key].append(dict(package[scope_key][0], Profile_Id=2))
        lib.digests[revision] = package_sha256(package)
    monkeypatch.setattr(service, 'run_stage3', lambda *args: pytest.fail('Rounding mismatch reached Stage 3'))
    with pytest.raises(ValueError, match='precision changes'):
        evaluate(lib)


def test_product_metadata_columns_do_not_replace_numerical_curve_identity(library):
    for revision, package in library.packages.items():
        for records in package['tables'].values():
            for row in records:
                row['source_comment'] = 'Independent approval for ' + revision
        library.digests[revision] = package_sha256(package)
    result = evaluate(library)
    assert result['meets_guarantee_year_energy']


def test_parent_parameter_change_during_evaluation_rejects_result(library, monkeypatch):
    original = service.run_stage3
    def mutate_parent(*args):
        result = original(*args)
        library.admin.update_record('dc_block', library.product_ids[12], {'nominal_power_kw': 2300})
        return result
    monkeypatch.setattr(service, 'run_stage3', mutate_parent)
    with pytest.raises(ValueError, match='changed during'):
        evaluate(library)


def test_later_candidate_cannot_return_an_earlier_withdrawn_option(library, monkeypatch):
    original = service.evaluate_dc_composition
    calls = []
    def withdraw_previous_after_last_candidate(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        if len(calls) == 3:
            library.variants.transition(library.relations[10], 'candidate_only', 'retired', 'Synthetic late withdrawal')
        return result
    monkeypatch.setattr(service, 'evaluate_dc_composition', withdraw_previous_after_last_candidate)
    with pytest.raises(ValueError, match='relation|changed'):
        compare(library)


def test_direct_c2b_cannot_expand_to_multiple_tail_containers(library):
    lib = library
    ids = [lib.revision_ids[12], lib.revision_ids[10]]
    with pytest.raises(ValueError, match='one tail container'):
        service.evaluate_dc_composition(lib.revisions, [dict(revision_id=ids[0], quantity=2, role='main'),
            dict(revision_id=ids[1], quantity=2, role='tail')], lib.case, lib.baseline,
            {key: lib.packages[key] for key in ids}, {key: lib.digests[key] for key in ids},
            variant_service=lib.variants, allow_special_configurations=True, special_reason='Synthetic study',
            temperature_c=25, standby_soc_pct=50)


@pytest.mark.parametrize('kind', ['soh', 'rte'])
def test_ambiguous_nearest_profiles_are_rejected_before_stage3(library, monkeypatch, kind):
    lib = library
    for revision, package in lib.packages.items():
        tables = package['tables']
        profile_key, curve_key = ('soh_profile', 'soh_curve') if kind == 'soh' else ('rte_profile', 'rte_curve')
        tables[profile_key].append(dict(tables[profile_key][0], Profile_Id=2))
        tables[curve_key].extend([dict(row, Profile_Id=2) for row in deepcopy(tables[curve_key])])
        scope_key = 'soh_applicability' if kind == 'soh' else 'rte_applicability'
        package[scope_key].append(dict(package[scope_key][0], Profile_Id=2))
        lib.digests[revision] = package_sha256(package)
    monkeypatch.setattr(service, 'run_stage3', lambda *args: pytest.fail('Ambiguous evidence reached Stage 3'))
    with pytest.raises(ValueError, match='Ambiguous'):
        evaluate(lib)


def test_invalid_inherited_efficiency_is_not_silently_used(library, monkeypatch):
    library.case = library.case.model_copy(update={'eff_pcs': None})
    library.baseline.defaults['eff_pcs'] = 200
    monkeypatch.setattr(service, 'run_stage3', lambda *args: pytest.fail('Invalid defaults reached Stage 3'))
    with pytest.raises(ValueError, match='Normalized'):
        evaluate(library)


def test_all_candidates_use_one_detached_package_input_snapshot(library, monkeypatch):
    original = service.evaluate_dc_composition
    calls = []
    def mutate_caller_after_first_result(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        if len(calls) == 1:
            library.packages[library.revision_ids[10]]['tables']['soh_curve'][-1]['Soh_Dc_Pct'] = 10
        return result
    monkeypatch.setattr(service, 'evaluate_dc_composition', mutate_caller_after_first_result)
    result = compare(library)
    assert len(result['candidates']) == 3
    assert result['candidates'][1]['result']['meets_guarantee_year_energy']
