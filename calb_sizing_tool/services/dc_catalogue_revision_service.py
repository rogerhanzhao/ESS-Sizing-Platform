"""Administrative revision workflow. Not consumed by the frozen sizing pipeline."""
from __future__ import annotations

import hashlib
import json
from datetime import timezone

from sqlalchemy import update

from calb_sizing_tool.infra.db.models import (
    DcCatalogueRevision, DcCatalogueRevisionEvent, DegradationCurve, ProductCell, ProductDCBlock,
)
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.dc_catalogue_readiness_service import _positive


def _values(row):
    if row is None:
        return None
    return {col.name: getattr(row, col.name) for col in row.__table__.columns
            if col.name not in ('created_at', 'updated_at')}


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def _snapshot(session, product_id):
    product = session.get(ProductDCBlock, product_id)
    if product is None:
        raise ValueError('DC product not found')
    cell = session.get(ProductCell, product.product_cell_id) if product.product_cell_id else None
    curve = session.query(DegradationCurve).filter_by(
        curve_code=product.default_degradation_curve_code).one_or_none() if product.default_degradation_curve_code else None
    def version(row):
        if row is None:
            return None
        value = row.updated_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    # Content restored to an earlier value must not revive its old approval.
    # These timestamps are maintained by the existing catalogue write service.
    return dict(schema_version=2, product=_values(product), cell=_values(cell), curve=_values(curve),
                source_versions=dict(product=version(product), cell=version(cell), curve=version(curve)))


def _candidate_errors(payload):
    product, cell, curve = (payload[k] for k in ('product', 'cell', 'curve'))
    errors = []
    for name, row in (('Product', product), ('Cell', cell), ('Curve', curve)):
        if not row or not row.get('is_active') or not row.get('is_published'):
            errors.append(f'{name} must be linked, active and published')
    if product.get('block_form') not in ('container', 'cabinet'):
        errors.append('Explicit container or cabinet form required')
    energy = product.get('gross_energy_mwh') or (product.get('rated_capacity_kwh') or 0) / 1000
    if not _positive(energy):
        errors.append('Positive nameplate energy required')
    for key in ('voltage_min_v', 'voltage_max_v', 'nominal_power_kw', 'max_current_a',
                'cells_in_series', 'strings_in_parallel'):
        if not _positive(product.get(key)):
            errors.append(f'Confirmed positive {key} required')
    if _positive(product.get('voltage_min_v')) and _positive(product.get('voltage_max_v')):
        if product['voltage_min_v'] >= product['voltage_max_v']:
            errors.append('Invalid DC voltage window')
    if cell and curve and curve.get('product_cell_id') != cell['product_cell_id']:
        errors.append('Curve cell identity mismatch; equal Ah is insufficient')
    if not product.get('source_ref') or product['source_ref'] == 'admin_portal':
        errors.append('Product technical source reference required')
    return errors


class DcCatalogueRevisionService:
    def __init__(self, auth_user, db_url=None):
        if not auth_user or not auth_user.is_admin or not auth_user.username:
            raise PermissionError('Administrator access required')
        self.actor = auth_user.username
        self.auth_user = auth_user
        self.db_url = db_url

    def list_revisions(self, product_id):
        with session_scope(self.db_url) as session:
            return [dict(revision_id=row.revision_id, revision_label=row.revision_label, status=row.status)
                    for row in session.query(DcCatalogueRevision).filter_by(
                        product_dc_block_id=product_id).order_by(DcCatalogueRevision.created_at).all()]

    def create(self, product_id, revision_label, evidence_ref):
        label, evidence = revision_label.strip(), evidence_ref.strip()
        if not label or len(label) > 64 or not evidence:
            raise ValueError('Revision label and source evidence are required')
        with session_scope(self.db_url) as session:
            payload = _snapshot(session, product_id)
            row = DcCatalogueRevision(product_dc_block_id=product_id, revision_label=label,
                status='draft', snapshot_json=payload, snapshot_sha256=_digest(payload), created_by=self.actor)
            session.add(row)
            session.flush()
            session.add(DcCatalogueRevisionEvent(revision_id=row.revision_id, from_status=None,
                to_status='draft', actor=self.actor, evidence_ref=evidence))
            return row.revision_id

    def inspect(self, revision_id):
        with session_scope(self.db_url) as session:
            row = session.get(DcCatalogueRevision, revision_id)
            if row is None:
                raise ValueError('Revision not found')
            if _digest(row.snapshot_json) != row.snapshot_sha256:
                raise ValueError('Revision snapshot integrity check failed')
            current = _snapshot(session, row.product_dc_block_id)
            stale = _digest(current) != row.snapshot_sha256
            errors = _candidate_errors(row.snapshot_json)
            events = session.query(DcCatalogueRevisionEvent).filter_by(revision_id=revision_id).order_by(
                DcCatalogueRevisionEvent.created_at, DcCatalogueRevisionEvent.event_id).all()
            return dict(revision_id=row.revision_id, revision_label=row.revision_label, status=row.status,
                snapshot=row.snapshot_json, sha256=row.snapshot_sha256,
                stale=stale, candidate_errors=errors,
                candidate_review_current=row.status == 'candidate_only' and not stale and not errors,
                events=[dict(_values(event), recorded_at=event.created_at.isoformat()) for event in events],
                runtime_sizing_enabled=False)

    def transition(self, revision_id, expected_status, target_status, evidence_ref):
        allowed = {'draft': {'parameter_review', 'retired'},
                   'parameter_review': {'candidate_only', 'retired'}, 'candidate_only': {'retired'}}
        if target_status not in allowed.get(expected_status, set()):
            raise ValueError('Unsupported transition; runtime sizing release is not enabled in Phase B')
        if not evidence_ref.strip():
            raise ValueError('Review evidence is required')
        with session_scope(self.db_url) as session:
            row = session.get(DcCatalogueRevision, revision_id)
            if row is None or row.status != expected_status:
                raise ValueError('Revision state changed; reload before continuing')
            if _digest(row.snapshot_json) != row.snapshot_sha256:
                raise ValueError('Revision snapshot integrity check failed')
            if target_status != 'retired':
                if _digest(_snapshot(session, row.product_dc_block_id)) != row.snapshot_sha256:
                    raise ValueError('Product or linked evidence changed; create a new revision')
                errors = _candidate_errors(row.snapshot_json)
                if target_status == 'candidate_only' and errors:
                    raise ValueError('; '.join(errors))
            changed = session.execute(update(DcCatalogueRevision).where(
                DcCatalogueRevision.revision_id == revision_id,
                DcCatalogueRevision.status == expected_status).values(status=target_status))
            if changed.rowcount != 1:
                raise ValueError('Concurrent revision update; reload before continuing')
            session.add(DcCatalogueRevisionEvent(revision_id=revision_id, from_status=expected_status,
                to_status=target_status, actor=self.actor, evidence_ref=evidence_ref.strip()))
