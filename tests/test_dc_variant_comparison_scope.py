"""Special configuration eligibility must be enforced by service, not only UI."""
from copy import deepcopy

import pytest

from tests.test_dc_product_comparison import candidate, run, forbid_core
from tests.unit.test_dc_configuration_variant import variant_library, create_relation
from calb_sizing_tool.services.dc_configuration_variant_service import DcConfigurationVariantService
from calb_sizing_tool.services.stage2_service import pick_dc_block
from calb_sizing_tool.services.dc_catalogue_readiness_service import dc_catalogue_readiness


def test_marked_engineering_product_is_excluded_even_if_active_and_published(candidate, monkeypatch):
    candidate.admin.update_record('dc_block', candidate.product_id, {
        'metadata_json': {'configuration_role': 'engineering_variant'}})
    candidate.revision_id = candidate.service.create(candidate.product_id, 'SPECIAL', 'Synthetic marker review')
    candidate.service.transition(candidate.revision_id, 'draft', 'parameter_review', 'Synthetic parameters')
    candidate.service.transition(candidate.revision_id, 'parameter_review', 'candidate_only', 'Synthetic review')
    candidate.package['product_revision_sha256'] = candidate.service.inspect(candidate.revision_id)['sha256']
    frame = candidate.admin.df_blocks_as_sizing_dataframe()
    assert frame.iloc[0].Is_Active == 0
    assert pick_dc_block(frame, 'container') is None
    forbid_core(monkeypatch)
    with pytest.raises(ValueError, match='relation'):
        run(candidate, allow_special_configurations=True, special_reason='Synthetic special scope')


def test_registered_child_cannot_bypass_standard_picker_by_removing_marker(variant_library):
    lib = variant_library
    create_relation(lib)
    frame = lib['admin'].df_blocks_as_sizing_dataframe()
    assert frame.set_index('Dc_Block_Code').loc['C10', 'Is_Active'] == 0
    assert pick_dc_block(frame, 'container')[0] == 'C12'
    lib['admin'].update_record('dc_block', lib['child'], {'metadata_json': {},
        'is_active': True, 'is_published': True, 'gross_energy_mwh': 10})
    frame = lib['admin'].df_blocks_as_sizing_dataframe()
    assert pick_dc_block(frame, 'container')[0] == 'C12'
    row = next(row for row in dc_catalogue_readiness(lib['admin'].snapshot(), frame) if row['Product'] == 'C10')
    assert row['Current search'] == 'Special configuration; excluded from standard search'


def _reviewed_comparison_child(candidate):
    parent_id = candidate.product_id
    candidate.admin.update_record('cell', candidate.cell_id, {'nominal_capacity_ah': 314})
    candidate.admin.update_record('dc_block', parent_id, dict(container_type='20ft ISO container',
        nominal_voltage_v=1331.2, dimension_width_mm=2438, dimension_depth_mm=6058, dimension_height_mm=2896))
    parent_revision = candidate.service.create(parent_id, 'PARENT', 'Synthetic parent')
    product = deepcopy(candidate.service.inspect(parent_revision)['snapshot']['product'])
    for key in ('product_dc_block_id',):
        product.pop(key)
    product.update(block_code='SYNTHETIC-CHILD-10', block_name='Synthetic 10-string child',
        strings_in_parallel=10, gross_energy_mwh=4.179968,
        metadata_json={'configuration_role': 'engineering_variant'})
    child_id = candidate.admin.create_dc_block(product)
    child_revision = candidate.service.create(child_id, 'CHILD', 'Synthetic child')
    for revision in (parent_revision, child_revision):
        candidate.service.transition(revision, 'draft', 'parameter_review', 'Synthetic parameters')
        candidate.service.transition(revision, 'parameter_review', 'candidate_only', 'Synthetic review')
    variants = DcConfigurationVariantService(candidate.service.auth_user, candidate.url)
    relation = variants.create(parent_revision, child_revision, 'TEST', dict(
        structural_evidence_ref='Synthetic structure', footprint_evidence_ref='Synthetic envelope',
        performance_evidence_ref='Synthetic performance'))
    variants.transition(relation, 'draft', 'candidate_only', 'Synthetic lineage review')
    candidate.product_id = child_id
    candidate.revision_id = child_revision
    candidate.package['product_revision_sha256'] = candidate.service.inspect(child_revision)['sha256']
    return variants, relation


def test_comparison_rejects_reviewed_special_child_without_explicit_scope(candidate, monkeypatch):
    _reviewed_comparison_child(candidate)
    forbid_core(monkeypatch)
    with pytest.raises(ValueError, match='opt-in'):
        run(candidate)


def test_scoped_comparison_retains_variant_provenance_and_remains_isolated(candidate):
    variants, relation = _reviewed_comparison_child(candidate)
    result = run(candidate, allow_special_configurations=True, special_reason='Synthetic bounded-tail comparison')
    scope = result['provenance']['configuration_scope']
    assert scope['special_scenario'] and scope['relation_id'] == relation
    assert result['comparison_only'] and result['downstream_ready'] is False


def test_relation_retirement_during_core_evaluation_prevents_returning_result(candidate, monkeypatch):
    variants, relation = _reviewed_comparison_child(candidate)
    from calb_sizing_tool.services import dc_product_comparison_service as service
    original = service.size_with_guarantee
    def retire_after_evaluation(*args, **kwargs):
        result = original(*args, **kwargs)
        variants.transition(relation, 'candidate_only', 'retired', 'Withdraw synthetic relation during evaluation')
        return result
    monkeypatch.setattr(service, 'size_with_guarantee', retire_after_evaluation)
    with pytest.raises(ValueError, match='current reviewed'):
        run(candidate, allow_special_configurations=True, special_reason='Synthetic bounded-tail comparison')
