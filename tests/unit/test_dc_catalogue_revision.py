import pytest
from sqlalchemy.exc import IntegrityError

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import DcCatalogueRevision
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.services.auth_service import AuthUser
from calb_sizing_tool.services.product_admin_service import ProductAdminService
from calb_sizing_tool.services.dc_catalogue_revision_service import DcCatalogueRevisionService


@pytest.fixture
def library(tmp_path):
    url = f"sqlite:///{(tmp_path / 'revision.sqlite').as_posix()}"
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    admin = ProductAdminService(url)
    cell = admin.create_cell(dict(cell_code='314-A', model_name='314Ah A', chemistry='LFP',
                                 is_active=True, is_published=True))
    admin.create_degradation_curve(dict(curve_code='CURVE', product_cell_id=cell, condition_label='25C test basis',
                                       is_active=True, is_published=True))
    product = admin.create_dc_block(dict(block_code='C12', block_name='Container',
        product_cell_id=cell, block_form='container', gross_energy_mwh=5, source_ref='datasheet revision A',
        voltage_min_v=1000, voltage_max_v=1500, nominal_power_kw=2500, max_current_a=2500,
        cells_in_series=416, strings_in_parallel=12, default_degradation_curve_code='CURVE',
        is_active=True, is_published=True))
    actor = AuthUser(user_id='admin', username='reviewer', display_name='Reviewer', roles=['admin'])
    return url, admin, product, DcCatalogueRevisionService(actor, url)


def review(service, product):
    revision = service.create(product, 'R1', 'source register A')
    service.transition(revision, 'draft', 'parameter_review', 'parameter check A')
    return revision


def test_snapshot_and_audit_survive_review_and_retirement(library):
    _, admin, product, service = library
    before = admin.snapshot()
    rev = review(service, product)
    original = service.inspect(rev)
    service.transition(rev, 'parameter_review', 'candidate_only', 'signed parameter review A')
    service.transition(rev, 'candidate_only', 'retired', 'withdraw revision A')
    after = service.inspect(rev)
    assert after['snapshot'] == original['snapshot']
    assert after['sha256'] == original['sha256']
    assert [e['to_status'] for e in after['events']] == ['draft', 'parameter_review', 'candidate_only', 'retired']
    assert {e['actor'] for e in after['events']} == {'reviewer'}
    assert after['runtime_sizing_enabled'] is False
    assert admin.snapshot() == before


def test_changed_product_cannot_be_approved_and_history_stays_frozen(library):
    _, admin, product, service = library
    rev = review(service, product)
    original = service.inspect(rev)['snapshot']
    admin.update_record('dc_block', product, {'gross_energy_mwh': 4.2})
    assert service.inspect(rev)['stale'] is True
    with pytest.raises(ValueError, match='changed'):
        service.transition(rev, 'parameter_review', 'candidate_only', 'review B')
    assert service.inspect(rev)['snapshot'] == original
    assert len(service.inspect(rev)['events']) == 2
    second = service.create(product, 'R2', 'source B')
    assert service.inspect(second)['snapshot']['product']['gross_energy_mwh'] == 4.2


@pytest.mark.parametrize('field,value', [('max_current_a', 0), ('nominal_power_kw', None),
                                      ('block_form', 'other'), ('is_active', False),
                                      ('default_degradation_curve_code', None)])
def test_incomplete_or_inactive_products_cannot_reach_candidate(library, field, value):
    _, admin, product, service = library
    admin.update_record('dc_block', product, {field: value})
    rev = review(service, product)
    with pytest.raises(ValueError):
        service.transition(rev, 'parameter_review', 'candidate_only', 'review')
    assert service.inspect(rev)['status'] == 'parameter_review'


def test_same_ah_curve_identity_and_linked_changes_are_checked(library):
    _, admin, product, service = library
    other = admin.create_cell(dict(cell_code='314-B', model_name='314Ah B', chemistry='LFP'))
    admin.update_record('dc_block', product, {'product_cell_id': other})
    rev = review(service, product)
    assert any('identity mismatch' in e for e in service.inspect(rev)['candidate_errors'])


def test_no_runtime_release_or_reopening_or_stale_state_transition(library):
    _, _, product, service = library
    rev = review(service, product)
    with pytest.raises(ValueError, match='state changed'):
        service.transition(rev, 'draft', 'parameter_review', 'duplicate click')
    with pytest.raises(ValueError, match='not enabled'):
        service.transition(rev, 'parameter_review', 'released', 'release')
    service.transition(rev, 'parameter_review', 'retired', 'withdraw')
    with pytest.raises(ValueError):
        service.transition(rev, 'retired', 'draft', 'reopen')


def test_actor_evidence_and_revision_label_are_required(library):
    _, _, product, service = library
    with pytest.raises(PermissionError):
        DcCatalogueRevisionService(AuthUser('guest', 'guest', None, ['guest']))
    with pytest.raises(ValueError):
        service.create(product, '', 'evidence')
    with pytest.raises(ValueError):
        service.create(product, 'R1', '')
    rev = service.create(product, 'R1', 'evidence')
    with pytest.raises(IntegrityError):
        service.create(product, 'R1', 'duplicate')
    with pytest.raises(ValueError):
        service.transition(rev, 'draft', 'parameter_review', '')


def test_snapshot_tampering_is_detected(library):
    url, _, product, service = library
    rev = service.create(product, 'R1', 'source')
    with session_scope(url) as session:
        session.get(DcCatalogueRevision, rev).snapshot_json = {'schema_version': 999}
    with pytest.raises(ValueError, match='integrity'):
        service.inspect(rev)


def test_reverting_parameters_creates_new_revision_not_history_rewrite(library):
    _, admin, product, service = library
    rev = service.create(product, 'R1', 'original source')
    service.transition(rev, 'draft', 'retired', 'withdraw')
    admin.update_record('dc_block', product, {'gross_energy_mwh': 4.2})
    second = service.create(product, 'R2', 'new design')
    admin.update_record('dc_block', product, {'gross_energy_mwh': 5.0})
    third = service.create(product, 'R3', 'restore reviewed parameters')
    assert service.inspect(rev)['status'] == 'retired'
    assert service.inspect(second)['stale']
    assert service.inspect(third)['snapshot']['product'] == service.inspect(rev)['snapshot']['product']
    assert service.inspect(third)['sha256'] != service.inspect(rev)['sha256']
    assert service.inspect(rev)['stale']


@pytest.mark.parametrize('target', ['product_value', 'product_active', 'cell_value', 'curve_value'])
def test_restored_catalogue_values_never_revive_old_candidate_review(library, target):
    _, admin, product, service = library
    rev = review(service, product)
    service.transition(rev, 'parameter_review', 'candidate_only', 'review A')
    detail = service.inspect(rev)
    assert detail['candidate_review_current']
    snapshot = detail['snapshot']
    entity, record, field, changed = {
        'product_value': ('dc_block', product, 'gross_energy_mwh', 4.2),
        'product_active': ('dc_block', product, 'is_active', False),
        'cell_value': ('cell', snapshot['cell']['product_cell_id'], 'model_name', 'Revised model'),
        'curve_value': ('degradation_curve', snapshot['curve']['degradation_curve_id'],
                        'condition_label', 'Changed condition'),
    }[target]
    original = snapshot[{'dc_block': 'product', 'cell': 'cell', 'degradation_curve': 'curve'}[entity]][field]
    admin.update_record(entity, record, {field: changed})
    assert service.inspect(rev)['stale']
    admin.update_record(entity, record, {field: original})
    restored = service.inspect(rev)
    assert restored['stale']
    assert not restored['candidate_review_current']
    assert len(restored['events']) == 3
