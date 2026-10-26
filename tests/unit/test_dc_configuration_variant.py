from copy import deepcopy

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError, OperationalError

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import DcCatalogueRevision, ProductDCBlock
from calb_sizing_tool.infra.db.models.dc_configuration_variant import (
    DcConfigurationVariant, DcConfigurationVariantEvent,
)
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.dc_catalogue_revision_service import DcCatalogueRevisionService, _digest
from calb_sizing_tool.services.dc_configuration_variant_service import (
    DcConfigurationVariantService, _structure,
)
from calb_sizing_tool.services.product_admin_service import ProductAdminService


EVIDENCE = dict(structural_evidence_ref='electrical drawing revision A',
                footprint_evidence_ref='20ft GA revision A',
                performance_evidence_ref='independent child DC performance review A')


@pytest.fixture
def variant_library(tmp_path):
    url = f"sqlite:///{(tmp_path / 'variant.sqlite').as_posix()}"
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    actor = AuthUser('admin', 'reviewer', 'Reviewer', ['admin'])
    admin = ProductAdminService(url)
    cell = admin.create_cell(dict(cell_code='CELL-314', model_name='Exact 314Ah cell A', chemistry='LFP',
        nominal_capacity_ah=314, is_active=True, is_published=True))
    admin.create_degradation_curve(dict(curve_code='CURVE', product_cell_id=cell,
        condition_label='explicit source conditions', is_active=True, is_published=True))
    common = dict(product_cell_id=cell, block_form='container', source_ref='product source revision A',
        voltage_min_v=1164.8, nominal_voltage_v=1331.2, voltage_max_v=1497.6,
        nominal_power_kw=2000, max_current_a=1500, cells_in_series=416, container_type='20ft',
        dimension_width_mm=6058, dimension_depth_mm=2438, dimension_height_mm=2896,
        default_degradation_curve_code='CURVE', is_active=True, is_published=True)
    parent = admin.create_dc_block(dict(common, block_code='C12', block_name='12-string container',
        strings_in_parallel=12, gross_energy_mwh=5.0159616))
    child = admin.create_dc_block(dict(common, block_code='C10', block_name='10-string container',
        strings_in_parallel=10, gross_energy_mwh=4.179968))
    revisions = DcCatalogueRevisionService(actor, url)
    parent_revision, child_revision = [revisions.create(product, 'R1', 'technical source A')
                                       for product in (parent, child)]
    service = DcConfigurationVariantService(actor, url)
    return dict(url=url, actor=actor, admin=admin, cell=cell, parent=parent, child=child,
                parent_revision=parent_revision, child_revision=child_revision,
                revisions=revisions, service=service)


def approve_revisions(library):
    for revision in (library['parent_revision'], library['child_revision']):
        library['revisions'].transition(revision, 'draft', 'parameter_review', 'parameters checked')
        library['revisions'].transition(revision, 'parameter_review', 'candidate_only', 'independent source review')


def create_relation(library, evidence=None):
    return library['service'].create(library['parent_revision'], library['child_revision'], 'V1',
                                      EVIDENCE if evidence is None else evidence)


def approved_relation(library):
    approve_revisions(library)
    relation = create_relation(library)
    library['service'].transition(relation, 'draft', 'candidate_only', 'lineage review A')
    return relation


def test_relation_capture_review_scope_and_retirement_are_isolated(variant_library):
    lib = variant_library
    before = lib['admin'].snapshot()
    relation = approved_relation(lib)
    service = lib['service']
    detail = service.inspect(relation)
    assert detail['candidate_review_current'] and detail['review_current']
    assert not detail['runtime_sizing_enabled']
    assert detail['family_code'] == 'C12'
    assert detail['use_scope'] == 'special_scenario_only'
    assert service.list_relations(lib['child'])[0]['relation_id'] == relation
    assert not service.list_relations(lib['parent'])
    with pytest.raises(ValueError, match='opt-in'):
        service.assert_comparison_scope(lib['child_revision'])
    scope = service.assert_comparison_scope(lib['child_revision'],
        allow_special_configurations=True, special_reason=' bounded site tail ')
    assert scope['special_scenario'] and scope['special_reason'] == 'bounded site tail'
    assert scope['relation_sha256'] == detail['relation_sha256']
    assert service.assert_comparison_scope(lib['parent_revision'])['special_scenario'] is False
    service.transition(relation, 'candidate_only', 'retired', 'withdraw variant')
    assert [event['to_status'] for event in service.inspect(relation)['events']] == [
        'draft', 'candidate_only', 'retired']
    assert {e['actor'] for e in service.inspect(relation)['events']} == {'reviewer'}
    with pytest.raises(ValueError, match='current reviewed'):
        service.assert_comparison_scope(lib['child_revision'],
            allow_special_configurations=True, special_reason='tail')
    assert lib['admin'].snapshot() == before


def test_draft_can_capture_unknown_fields_but_cannot_approve(variant_library):
    lib = variant_library
    lib['admin'].update_record('dc_block', lib['child'], {'dimension_width_mm': None,
        'nominal_power_kw': None, 'container_type': None, 'is_active': False, 'is_published': False})
    lib['child_revision'] = lib['revisions'].create(lib['child'], 'R2', 'engineering unknowns')
    relation = create_relation(lib, {})
    detail = lib['service'].inspect(relation)
    assert not detail['stale']
    assert not detail['candidate_review_current']
    assert any('dimension_width_mm' in error for error in detail['review_errors'])
    assert any('performance_evidence_ref' in error for error in detail['review_errors'])
    with pytest.raises(ValueError):
        lib['service'].transition(relation, 'draft', 'candidate_only', 'attempt review')


def test_unknown_cell_capacity_cannot_approve_a_314ah_configuration_family(variant_library):
    lib = variant_library
    lib['admin'].update_record('cell', lib['cell'], {'nominal_capacity_ah': None})
    lib['parent_revision'], lib['child_revision'] = [
        lib['revisions'].create(product, 'UNKNOWN-AH', 'Unknown cell capacity')
        for product in (lib['parent'], lib['child'])]
    approve_revisions(lib)
    relation = create_relation(lib)
    assert any('314Ah' in error for error in lib['service'].inspect(relation)['review_errors'])
    with pytest.raises(ValueError, match='314Ah'):
        lib['service'].transition(relation, 'draft', 'candidate_only', 'Attempt family review')


@pytest.mark.parametrize('field,value,match', [
    ('strings_in_parallel', 11, 'string count'), ('cells_in_series', 396, 'cells_in_series'),
    ('block_form', 'cabinet', 'block_form'), ('container_type', '40ft', '20ft'),
    ('nominal_voltage_v', 1267.2, 'nominal_voltage'), ('voltage_min_v', 1108.8, 'voltage_min'),
    ('dimension_width_mm', 10500, 'dimension_width'), ('dimension_depth_mm', -1, 'positive'),
])
def test_explicit_incompatible_child_rejected_at_capture(variant_library, field, value, match):
    lib = variant_library
    lib['admin'].update_record('dc_block', lib['child'], {field: value})
    lib['child_revision'] = lib['revisions'].create(lib['child'], 'R2', 'changed design')
    with pytest.raises(ValueError, match=match):
        create_relation(lib)


@pytest.mark.parametrize('field,value', [('strings_in_parallel', True), ('strings_in_parallel', 8.0),
    ('strings_in_parallel', '10'), ('cells_in_series', 416.0), ('cells_in_series', True),
    ('nominal_voltage_v', True), ('dimension_width_mm', float('nan'))])
def test_snapshot_structural_types_are_strict(variant_library, field, value):
    lib = variant_library
    parent = lib['revisions'].inspect(lib['parent_revision'])
    child = deepcopy(lib['revisions'].inspect(lib['child_revision']))
    child['snapshot']['product'][field] = value
    assert _structure(parent, child)[1]


def test_eight_string_supported_and_rack_count_never_replaces_string_count(variant_library):
    lib = variant_library
    lib['admin'].update_record('dc_block', lib['child'],
        {'strings_in_parallel': 8, 'racks_per_block': 4, 'racks_per_container': 4})
    lib['child_revision'] = lib['revisions'].create(lib['child'], 'R2', '8-string source')
    assert lib['service'].inspect(create_relation(lib))['child_revision']['snapshot']['product']['strings_in_parallel'] == 8


@pytest.mark.parametrize('label', ['20ft ISO container', '20ft DC Container', '20 ft container', '20-foot'])
def test_explicit_20ft_catalogue_aliases_are_accepted(variant_library, label):
    lib = variant_library
    lib['admin'].update_record('dc_block', lib['parent'], {'container_type': label})
    lib['parent_revision'] = lib['revisions'].create(lib['parent'], 'R2', 'existing 20ft naming')
    assert lib['service'].inspect(create_relation(lib))['family_code'] == 'C12'


@pytest.mark.parametrize('label', ['3 x 10ft modular units', '20ft equivalent', '10ft container'])
def test_modular_or_equivalent_enclosures_are_not_20ft_lineage(variant_library, label):
    lib = variant_library
    lib['admin'].update_record('dc_block', lib['child'], {'container_type': label})
    lib['child_revision'] = lib['revisions'].create(lib['child'], 'R2', 'modular product')
    with pytest.raises(ValueError, match='20ft'):
        create_relation(lib)


def test_equal_ah_different_cell_identity_is_rejected(variant_library):
    lib = variant_library
    other = lib['admin'].create_cell(dict(cell_code='OTHER314', model_name='Another314', chemistry='LFP',
        nominal_capacity_ah=314, is_active=True, is_published=True))
    lib['admin'].update_record('dc_block', lib['child'], {'product_cell_id': other})
    lib['child_revision'] = lib['revisions'].create(lib['child'], 'R2', 'same Ah different cell')
    with pytest.raises(ValueError, match='Exact cell identity'):
        create_relation(lib)


def test_same_cell_id_with_different_captured_cell_details_is_rejected(variant_library):
    lib = variant_library
    lib['admin'].update_record('cell', lib['cell'], {'model_name': 'Revised exact-cell description'})
    lib['child_revision'] = lib['revisions'].create(lib['child'], 'R2', 'updated cell evidence')
    with pytest.raises(ValueError, match='snapshot must match'):
        create_relation(lib)


def test_wrong_known_cell_capacity_cannot_enter_this_family(variant_library):
    lib = variant_library
    lib['admin'].update_record('cell', lib['cell'], {'nominal_capacity_ah': 588})
    for side in ('parent', 'child'):
        lib[f'{side}_revision'] = lib['revisions'].create(lib[side], 'R2', 'large-cell update')
    with pytest.raises(ValueError, match='314Ah'):
        create_relation(lib)


@pytest.mark.parametrize('target', ['parent', 'child', 'cell', 'curve'])
def test_changed_then_restored_parameters_do_not_revive_relation(variant_library, target):
    lib = variant_library
    relation = approved_relation(lib)
    if target in ('parent', 'child'):
        entity, record, field, value = 'dc_block', lib[target], 'nominal_power_kw', 1900
    elif target == 'cell':
        entity, record, field, value = 'cell', lib['cell'], 'model_name', 'Changed cell'
    else:
        curve = lib['revisions'].inspect(lib['parent_revision'])['snapshot']['curve']
        entity, record, field, value = 'degradation_curve', curve['degradation_curve_id'], 'condition_label', 'Changed curve'
    snapshot_key = {'dc_block': 'product', 'cell': 'cell', 'degradation_curve': 'curve'}[entity]
    original = lib['revisions'].inspect(lib[f'{target}_revision'] if target in ('parent', 'child')
                                      else lib['parent_revision'])['snapshot'][snapshot_key][field]
    lib['admin'].update_record(entity, record, {field: value})
    assert lib['service'].inspect(relation)['stale']
    lib['admin'].update_record(entity, record, {field: original})
    assert lib['service'].inspect(relation)['stale']
    assert not lib['service'].inspect(relation)['candidate_review_current']
    with pytest.raises(ValueError, match='current reviewed'):
        lib['service'].assert_comparison_scope(lib['child_revision'],
            allow_special_configurations=True, special_reason='tail')


def test_registered_child_cannot_bypass_scope_with_a_new_revision(variant_library):
    lib = variant_library
    approved_relation(lib)
    new = lib['revisions'].create(lib['child'], 'R2', 'new revision same values')
    with pytest.raises(ValueError, match='own reviewed configuration'):
        lib['service'].assert_comparison_scope(new, allow_special_configurations=True, special_reason='tail')


def test_unlinked_engineering_marker_is_blocked_and_regular_other_products_not_inferred(variant_library):
    lib = variant_library
    lib['admin'].update_record('dc_block', lib['child'], {'metadata_json': {'configuration_role': 'engineering_variant'}})
    marked = lib['revisions'].create(lib['child'], 'R2', 'marked variant')
    with pytest.raises(ValueError, match='own reviewed configuration'):
        lib['service'].assert_comparison_scope(marked)
    # An unrelated 8-string product is not classified by a name/capacity heuristic.
    lib['admin'].update_record('dc_block', lib['parent'], {'strings_in_parallel': 8, 'block_name': '588Ah container'})
    regular = lib['revisions'].create(lib['parent'], 'R2', 'unrelated product')
    assert not lib['service'].assert_comparison_scope(regular)['special_scenario']


def test_absent_lineage_schema_keeps_regular_flow_and_blocks_marked_product(variant_library):
    lib = variant_library
    with session_scope(lib['url']) as session:
        session.execute(text('DROP TABLE dc_configuration_variant_event'))
        session.execute(text('DROP TABLE dc_configuration_variant'))
    assert not lib['service'].assert_comparison_scope(lib['parent_revision'])['special_scenario']
    lib['admin'].update_record('dc_block', lib['child'], {'metadata_json': {'configuration_role': 'engineering_variant'}})
    marked = lib['revisions'].create(lib['child'], 'R2', 'marked variant')
    with pytest.raises(ValueError, match='schema is not available'):
        lib['service'].assert_comparison_scope(marked)


def test_sql_errors_never_silently_permit_registered_child(variant_library):
    lib = variant_library
    approved_relation(lib)
    with session_scope(lib['url']) as session:
        session.execute(text('DROP TABLE dc_configuration_variant_event'))
    with pytest.raises(OperationalError):
        lib['service'].assert_comparison_scope(lib['child_revision'],
            allow_special_configurations=True, special_reason='tail')


@pytest.mark.parametrize('changes', [{'family_code': 'FAKE'}, {'evidence_json': {}},
    {'child_product_id': 'missing'}, {'parent_revision_sha256': '0' * 64}])
def test_immutable_relation_tamper_detected(variant_library, changes):
    lib = variant_library
    relation = create_relation(lib)
    with session_scope(lib['url']) as session:
        row = session.get(DcConfigurationVariant, relation)
        # Invalid foreign keys must be rejected by the database itself.
        if 'child_product_id' in changes:
            with pytest.raises(IntegrityError):
                for key, value in changes.items():
                    setattr(row, key, value)
                session.flush()
            session.rollback()
            return
        for key, value in changes.items():
            setattr(row, key, value)
    with pytest.raises(ValueError, match='integrity'):
        lib['service'].inspect(relation)


def test_revision_tamper_detected_even_after_relation_capture(variant_library):
    lib = variant_library
    relation = create_relation(lib)
    with session_scope(lib['url']) as session:
        session.get(DcCatalogueRevision, lib['child_revision']).snapshot_json = {'tampered': True}
    with pytest.raises(ValueError, match='integrity'):
        lib['service'].inspect(relation)


def test_raw_status_change_without_review_event_does_not_approve_relation(variant_library):
    lib = variant_library
    approve_revisions(lib)
    relation = create_relation(lib)
    with session_scope(lib['url']) as session:
        session.get(DcConfigurationVariant, relation).status = 'candidate_only'
    with pytest.raises(ValueError, match='event/state integrity'):
        lib['service'].assert_comparison_scope(lib['child_revision'],
            allow_special_configurations=True, special_reason='tail')


def test_unique_child_revision_fks_and_audit_rows_protect_history(variant_library):
    lib = variant_library
    relation = create_relation(lib)
    with pytest.raises(IntegrityError):
        create_relation(lib)
    for model, key, value in ((DcCatalogueRevision, 'revision_id', lib['child_revision']),
                              (ProductDCBlock, 'product_dc_block_id', lib['parent']),
                              (DcConfigurationVariant, 'relation_id', relation)):
        with pytest.raises(IntegrityError), session_scope(lib['url']) as session:
            session.execute(delete(model).where(getattr(model, key) == value))


def test_permissions_inputs_and_optimistic_status_are_enforced(variant_library):
    lib = variant_library
    with pytest.raises(PermissionError):
        DcConfigurationVariantService(AuthUser('guest', 'guest', None, ['guest']), lib['url'])
    for label, evidence in (('', EVIDENCE), ('x' * 65, EVIDENCE), ('V1', []), ('V1', {'bad': float('nan')})):
        with pytest.raises(ValueError):
            lib['service'].create(lib['parent_revision'], lib['child_revision'], label, evidence)
    with pytest.raises(ValueError, match='different'):
        lib['service'].create(lib['parent_revision'], lib['parent_revision'], 'V1', EVIDENCE)
    relation = create_relation(lib)
    with pytest.raises(ValueError, match='state changed'):
        lib['service'].transition(relation, 'candidate_only', 'retired', 'stale client')
    with pytest.raises(ValueError, match='evidence'):
        lib['service'].transition(relation, 'draft', 'retired', '')
    with pytest.raises(ValueError, match='not enabled'):
        lib['service'].transition(relation, 'draft', 'released', 'release')
    lib['service'].transition(relation, 'draft', 'retired', 'withdraw')
    with pytest.raises(ValueError):
        lib['service'].transition(relation, 'retired', 'draft', 'reopen')


@pytest.mark.parametrize('allow,reason', [(False, 'tail'), (1, 'tail'), (True, ''), (True, None)])
def test_special_scope_requires_boolean_opt_in_and_reason(variant_library, allow, reason):
    lib = variant_library
    approved_relation(lib)
    with pytest.raises(ValueError, match='opt-in'):
        lib['service'].assert_comparison_scope(lib['child_revision'],
            allow_special_configurations=allow, special_reason=reason)
