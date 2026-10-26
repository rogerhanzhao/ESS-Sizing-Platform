"""Versioned 12/10/8-string lineage and explicit comparison scope only.

No product activation, parameter scaling, sizing formula or AC readiness is owned
here. Every child retains its independent product and curve review.
"""
from __future__ import annotations

import json
import math

from sqlalchemy import inspect as inspect_schema, update

from calb_sizing_tool.common.dc_configuration_identity import is_20ft_container_type
from calb_sizing_tool.infra.db.models import DcCatalogueRevision, DcCatalogueRevisionEvent
from calb_sizing_tool.infra.db.models.dc_configuration_variant import (
    DcConfigurationVariant, DcConfigurationVariantEvent,
)
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.dc_catalogue_revision_service import (
    _candidate_errors, _digest, _snapshot, _values,
)


_IMMUTABLE_FIELDS = (
    'parent_revision_id', 'child_revision_id', 'parent_product_id', 'child_product_id',
    'parent_revision_sha256', 'child_revision_sha256', 'version_label', 'family_code',
    'use_scope', 'evidence_json', 'created_by',
)
_EVIDENCE_FIELDS = ('structural_evidence_ref', 'footprint_evidence_ref', 'performance_evidence_ref')


def _revision_detail(session, revision_id):
    row = session.get(DcCatalogueRevision, revision_id)
    if row is None:
        raise ValueError('Revision not found')
    if _digest(row.snapshot_json) != row.snapshot_sha256:
        raise ValueError('Revision snapshot integrity check failed')
    stale = _digest(_snapshot(session, row.product_dc_block_id)) != row.snapshot_sha256
    errors = _candidate_errors(row.snapshot_json)
    events = session.query(DcCatalogueRevisionEvent).filter_by(revision_id=revision_id).order_by(
        DcCatalogueRevisionEvent.created_at, DcCatalogueRevisionEvent.event_id).all()
    return dict(revision_id=row.revision_id, revision_label=row.revision_label, status=row.status,
                snapshot=row.snapshot_json, sha256=row.snapshot_sha256, stale=stale,
                candidate_errors=errors,
                candidate_review_current=row.status == 'candidate_only' and not stale and not errors,
                events=[dict(_values(event), recorded_at=event.created_at.isoformat()) for event in events],
                runtime_sizing_enabled=False)


def _positive_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _reserve_review_transaction(session):
    # SQLite's driver otherwise postpones BEGIN until DML. Reserve the writer
    # before rereading catalogue tokens, so capture/review cannot race a change
    # between validation and the relation/event insert or status update.
    if session.get_bind().dialect.name == 'sqlite':
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')


def _structure(parent, child):
    """Separate unknown draft fields from positive, explicit incompatibilities."""
    p, c = parent['snapshot']['product'], child['snapshot']['product']
    missing, mismatches = [], []
    for label, product, count in (('Parent', p, 12), ('Child', c, (8, 10))):
        for key, expected in (('block_form', 'container'), ('cells_in_series', 416)):
            value = product.get(key)
            if value is None or value == '':
                missing.append(f'{label} {key} required')
            elif (key == 'cells_in_series' and type(value) is not int) or value != expected:
                mismatches.append(f'{label} must have {key}={expected}')
        strings = product.get('strings_in_parallel')
        if strings is None:
            missing.append(f'{label} strings_in_parallel required')
        elif type(strings) is not int or strings not in ((count,) if type(count) is int else count):
            mismatches.append(f'{label} string count must be {count}')
        enclosure = product.get('container_type')
        if enclosure is None or enclosure == '':
            missing.append(f'{label} explicit 20ft container_type required')
        elif not is_20ft_container_type(enclosure):
            mismatches.append(f'{label} must be an explicit 20ft container')
    pcell, ccell = parent['snapshot'].get('cell'), child['snapshot'].get('cell')
    if not p.get('product_cell_id') or not c.get('product_cell_id') or not pcell or not ccell:
        missing.append('Both exact linked cell identities and snapshots required')
    elif (p['product_cell_id'] != c['product_cell_id']
          or pcell.get('product_cell_id') != p['product_cell_id']
          or ccell.get('product_cell_id') != c['product_cell_id'] or _digest(pcell) != _digest(ccell)):
        mismatches.append('Exact cell identity and snapshot must match; equal Ah is insufficient')
    for cell in (pcell, ccell):
        if cell and cell.get('nominal_capacity_ah') is None:
            missing.append('Confirmed 314Ah cell capacity required for this configuration family')
        elif cell:
            ah = cell['nominal_capacity_ah']
            if not _positive_number(ah) or not math.isclose(ah, 314, rel_tol=0, abs_tol=1e-9):
                mismatches.append('This configuration family requires the 314Ah cell')
    for key in ('nominal_voltage_v', 'voltage_min_v', 'voltage_max_v',
                'dimension_width_mm', 'dimension_depth_mm', 'dimension_height_mm'):
        values = (p.get(key), c.get(key))
        if any(value is not None and not _positive_number(value) for value in values):
            mismatches.append(f'Both {key} values must be finite and positive')
        elif any(value is None for value in values):
            missing.append(f'Both confirmed {key} values required')
        elif not math.isclose(values[0], values[1], rel_tol=1e-9, abs_tol=1e-8):
            mismatches.append(f'Parent and child {key} must match')
    return list(dict.fromkeys(missing)), list(dict.fromkeys(mismatches))


def _relation_detail(session, row):
    payload = {key: getattr(row, key) for key in _IMMUTABLE_FIELDS}
    if _digest(payload) != row.relation_sha256:
        raise ValueError('Configuration relation integrity check failed')
    parent = _revision_detail(session, row.parent_revision_id)
    child = _revision_detail(session, row.child_revision_id)
    if (parent['snapshot']['product']['product_dc_block_id'] != row.parent_product_id
            or child['snapshot']['product']['product_dc_block_id'] != row.child_product_id
            or parent['sha256'] != row.parent_revision_sha256
            or child['sha256'] != row.child_revision_sha256):
        raise ValueError('Configuration relation revision binding integrity check failed')
    missing, mismatches = _structure(parent, child)
    errors = missing + mismatches
    for label, revision in (('Parent', parent), ('Child', child)):
        if not revision['candidate_review_current']:
            errors.append(f'{label} requires a current candidate-only parameter review')
    for key in _EVIDENCE_FIELDS:
        if not isinstance(row.evidence_json.get(key), str) or not row.evidence_json[key].strip():
            errors.append(f'{key} required for configuration review')
    stale = parent['stale'] or child['stale']
    events = session.query(DcConfigurationVariantEvent).filter_by(relation_id=row.relation_id).order_by(
        DcConfigurationVariantEvent.created_at, DcConfigurationVariantEvent.event_id).all()
    audit_status = None
    for event in events:
        if event.from_status != audit_status or not event.actor or not event.evidence_ref:
            raise ValueError('Configuration relation event integrity check failed')
        audit_status = event.to_status
    if not events or audit_status != row.status:
        raise ValueError('Configuration relation event/state integrity check failed')
    current = row.status == 'candidate_only' and not stale and not errors
    return dict(_values(row), parent_revision=parent, child_revision=child, stale=stale,
                review_errors=errors, candidate_review_current=current, review_current=current,
                events=[dict(_values(event), recorded_at=event.created_at.isoformat()) for event in events],
                runtime_sizing_enabled=False)


class DcConfigurationVariantService:
    def __init__(self, auth_user, db_url=None):
        if not auth_user or not auth_user.is_admin or not auth_user.username:
            raise PermissionError('Administrator access required')
        self.actor, self.auth_user, self.db_url = auth_user.username, auth_user, db_url

    def create(self, parent_revision_id, child_revision_id, version_label, evidence):
        if not isinstance(version_label, str) or not version_label.strip() or len(version_label.strip()) > 64:
            raise ValueError('Configuration version label is required and limited to 64 characters')
        if not isinstance(evidence, dict):
            raise ValueError('Configuration evidence must be a mapping')
        try:
            evidence = json.loads(json.dumps(evidence, allow_nan=False))
        except (ValueError, TypeError) as exc:
            raise ValueError('Configuration evidence must be finite JSON data') from exc
        if parent_revision_id == child_revision_id:
            raise ValueError('Parent and child revisions must be different')
        with session_scope(self.db_url) as session:
            _reserve_review_transaction(session)
            parent, child = (_revision_detail(session, value) for value in
                             (parent_revision_id, child_revision_id))
            p, c = parent['snapshot']['product'], child['snapshot']['product']
            if p['product_dc_block_id'] == c['product_dc_block_id']:
                raise ValueError('Parent and child must be independent products')
            _, mismatches = _structure(parent, child)
            if mismatches:
                raise ValueError('; '.join(mismatches))
            payload = dict(parent_revision_id=parent_revision_id, child_revision_id=child_revision_id,
                           parent_product_id=p['product_dc_block_id'], child_product_id=c['product_dc_block_id'],
                           parent_revision_sha256=parent['sha256'], child_revision_sha256=child['sha256'],
                           version_label=version_label.strip(), family_code=p['block_code'],
                           use_scope='special_scenario_only', evidence_json=evidence, created_by=self.actor)
            row = DcConfigurationVariant(**payload, relation_sha256=_digest(payload), status='draft')
            session.add(row)
            session.flush()
            session.add(DcConfigurationVariantEvent(relation_id=row.relation_id, from_status=None,
                to_status='draft', actor=self.actor, evidence_ref=json.dumps(evidence, sort_keys=True)))
            return row.relation_id

    def inspect(self, relation_id):
        with session_scope(self.db_url) as session:
            row = session.get(DcConfigurationVariant, relation_id)
            if row is None:
                raise ValueError('Configuration relation not found')
            return _relation_detail(session, row)

    def list_relations(self, child_product_id=None):
        with session_scope(self.db_url) as session:
            query = session.query(DcConfigurationVariant)
            if child_product_id is not None:
                query = query.filter_by(child_product_id=child_product_id)
            return [_relation_detail(session, row) for row in query.order_by(
                DcConfigurationVariant.created_at, DcConfigurationVariant.relation_id).all()]

    def transition(self, relation_id, expected_status, target_status, evidence_ref):
        allowed = {'draft': {'candidate_only', 'retired'}, 'candidate_only': {'retired'}}
        if target_status not in allowed.get(expected_status, set()):
            raise ValueError('Unsupported configuration transition; runtime release is not enabled')
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise ValueError('Configuration review evidence is required')
        with session_scope(self.db_url) as session:
            _reserve_review_transaction(session)
            row = session.get(DcConfigurationVariant, relation_id)
            if row is None or row.status != expected_status:
                raise ValueError('Configuration state changed; reload before continuing')
            detail = _relation_detail(session, row)
            if target_status != 'retired' and detail['review_errors']:
                raise ValueError('; '.join(detail['review_errors']))
            changed = session.execute(update(DcConfigurationVariant).where(
                DcConfigurationVariant.relation_id == relation_id,
                DcConfigurationVariant.status == expected_status).values(status=target_status))
            if changed.rowcount != 1:
                raise ValueError('Concurrent configuration update; reload before continuing')
            session.add(DcConfigurationVariantEvent(relation_id=relation_id, from_status=expected_status,
                to_status=target_status, actor=self.actor, evidence_ref=evidence_ref.strip()))

    def assert_comparison_scope(self, revision_id, *, allow_special_configurations=False, special_reason=''):
        with session_scope(self.db_url) as session:
            revision = _revision_detail(session, revision_id)
            product = revision['snapshot']['product']
            metadata = product.get('metadata_json')
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                raise ValueError('Product configuration metadata must be a mapping')
            marked = metadata.get('configuration_role') == 'engineering_variant'
            table_exists = inspect_schema(session.get_bind()).has_table(DcConfigurationVariant.__tablename__)
            rows = session.query(DcConfigurationVariant).filter_by(
                child_product_id=product['product_dc_block_id']).all() if table_exists else []
            if not rows and not marked:
                return dict(special_scenario=False, revision_id=revision_id,
                            revision_sha256=revision['sha256'])
            if not table_exists:
                raise ValueError('Special configuration lineage schema is not available')
            exact = next((row for row in rows if row.child_revision_id == revision_id), None)
            if exact is None:
                raise ValueError('This child product revision requires its own reviewed configuration relation')
            detail = _relation_detail(session, exact)
            if not detail['candidate_review_current']:
                raise ValueError('Special configuration requires a current reviewed relation')
            if allow_special_configurations is not True or not isinstance(special_reason, str) or not special_reason.strip():
                raise ValueError('Special configuration requires explicit opt-in and a scenario reason')
            return dict(special_scenario=True, relation_id=exact.relation_id,
                        relation_sha256=exact.relation_sha256, version_label=exact.version_label,
                        revision_id=revision_id, revision_sha256=revision['sha256'],
                        family_code=exact.family_code, use_scope=exact.use_scope,
                        special_reason=special_reason.strip())
