"""Administrative evidence revisions for local AC capability comparison only.

This registry is independent of ProductACBlock and its activation semantics.
Candidate review records an administrative evidence trail; it does not certify
manufacturer approval, enable sizing adoption, or release engineering outputs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from calb_sizing_tool.infra.db.base import utc_now
from calb_sizing_tool.infra.db.models.ac_equipment_capability import (
    EquipmentCapabilityRevision,
    EquipmentCapabilityRevisionEvent,
)
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.schemas.ac_equipment_capability import (
    EquipmentCapabilityPackage,
    capability_package_sha256,
)
from calb_sizing_tool.schemas.dc_ac_allocation import CapabilityReference


_ALLOWED_TRANSITIONS = {
    "draft": {"parameter_review", "retired"},
    "parameter_review": {"candidate_only", "retired"},
    "candidate_only": {"retired"},
    "retired": set(),
}
_STATE_FLAGS = {
    "draft": (True, False),
    "parameter_review": (True, False),
    "candidate_only": (True, True),
    "retired": (False, False),
}


def _digest(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _text(value, label, *, maximum=None):
    if not isinstance(value, str) or not value.strip() or (maximum and len(value) > maximum):
        raise ValueError(f"{label} is required")
    return value.strip()


def _kind(value):
    if value not in ("pcs", "transformer"):
        raise ValueError("Equipment kind must be pcs or transformer")
    return value


def _timestamp(value):
    if value is None:
        raise ValueError("Capability record timestamp integrity check failed")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _reserve_transaction(session, *, write):
    if session.get_bind().dialect.name == "sqlite":
        # sqlite3 otherwise postpones BEGIN past SELECT. Pin a coherent snapshot
        # for inspection, and reserve the writer before transition validation.
        session.connection().exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")


def _event_content(event, row):
    return {
        "event_id": event.event_id,
        "revision_id": event.revision_id,
        "event_number": event.event_number,
        "kind": row.kind,
        "package_code": row.package_code,
        "revision": row.revision,
        "payload_sha256": row.payload_sha256,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "actor": event.actor,
        "evidence_ref": event.evidence_ref,
        "previous_event_sha256": event.previous_event_sha256,
        "recorded_at": _timestamp(event.created_at),
    }


def _add_event(session, row, *, previous, from_status, to_status, actor, evidence):
    event = EquipmentCapabilityRevisionEvent(
        revision_id=row.revision_id,
        event_number=previous.event_number + 1 if previous else 1,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        evidence_ref=evidence,
        previous_event_sha256=previous.event_sha256 if previous else None,
        event_sha256="pending",
        created_at=utc_now(),
    )
    session.add(event)
    session.flush()
    event.event_sha256 = _digest(_event_content(event, row))
    return event


def _detail(session, row):
    try:
        parsed = EquipmentCapabilityPackage.model_validate(row.payload_json)
        payload = parsed.model_dump(mode="json")
        sha256 = capability_package_sha256(parsed)
        canonical_hash = _digest(row.payload_json)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Capability payload integrity check failed") from exc
    if (sha256 != row.payload_sha256 or canonical_hash != sha256
            or parsed.kind != row.kind or parsed.package_code != row.package_code
            or parsed.revision != row.revision):
        raise ValueError("Capability payload/identity integrity check failed")
    if row.status not in _STATE_FLAGS or (row.is_active, row.is_published) != _STATE_FLAGS[row.status]:
        raise ValueError("Capability review state/flags integrity check failed")
    events = session.query(EquipmentCapabilityRevisionEvent).filter_by(
        revision_id=row.revision_id,
    ).order_by(EquipmentCapabilityRevisionEvent.event_number).all()
    previous_status, previous_hash = None, None
    for number, event in enumerate(events, 1):
        if (event.event_number != number or event.from_status != previous_status
                or event.previous_event_sha256 != previous_hash
                or not isinstance(event.actor, str) or not event.actor.strip()
                or not isinstance(event.evidence_ref, str) or not event.evidence_ref.strip()
                or event.event_sha256 != _digest(_event_content(event, row))):
            raise ValueError("Capability review event integrity check failed")
        if number == 1:
            if event.to_status != "draft" or event.actor != row.created_by:
                raise ValueError("Capability creation event integrity check failed")
        elif event.to_status not in _ALLOWED_TRANSITIONS.get(previous_status, set()):
            raise ValueError("Capability review transition integrity check failed")
        previous_status, previous_hash = event.to_status, event.event_sha256
    if not events or previous_status != row.status:
        raise ValueError("Capability review event/state integrity check failed")
    review_token = _digest({
        "revision_id": row.revision_id,
        "payload_sha256": sha256,
        "status": row.status,
        "is_active": row.is_active,
        "is_published": row.is_published,
        "created_by": row.created_by,
        "created_at": _timestamp(row.created_at),
        "updated_at": _timestamp(row.updated_at),
        "last_event_sha256": previous_hash,
        "last_event_number": len(events),
    })
    return {
        "revision_id": row.revision_id,
        "package_code": row.package_code,
        "revision": row.revision,
        "kind": row.kind,
        "status": row.status,
        "is_active": row.is_active,
        "is_published": row.is_published,
        "payload": payload,
        "sha256": sha256,
        "created_by": row.created_by,
        "created_at": _timestamp(row.created_at),
        "updated_at": _timestamp(row.updated_at),
        "candidate_review_current": row.status == "candidate_only",
        "review_token": review_token,
        "events": [dict(_event_content(event, row), event_sha256=event.event_sha256)
                   for event in events],
        "comparison_only": True,
        "runtime_sizing_enabled": False,
    }


class EquipmentCapabilityRevisionService:
    """Admin-only, immutable capability packages and monotonic review lifecycle."""

    def __init__(self, auth_user, db_url=None):
        if (not auth_user or getattr(auth_user, "is_admin", False) is not True
                or not isinstance(getattr(auth_user, "username", None), str)
                or not auth_user.username.strip() or len(auth_user.username) > 128):
            raise PermissionError("Administrator access required")
        self.actor = auth_user.username.strip()
        self.auth_user = auth_user
        self.db_url = db_url

    def create(self, package, evidence_ref):
        evidence = _text(evidence_ref, "Source evidence")
        parsed = EquipmentCapabilityPackage.model_validate(package)
        payload = parsed.model_dump(mode="json")
        try:
            with session_scope(self.db_url) as session:
                _reserve_transaction(session, write=True)
                row = EquipmentCapabilityRevision(
                    kind=parsed.kind, package_code=parsed.package_code, revision=parsed.revision,
                    payload_json=payload, payload_sha256=capability_package_sha256(parsed),
                    status="draft", is_active=True, is_published=False, created_by=self.actor,
                )
                session.add(row)
                session.flush()
                _add_event(session, row, previous=None, from_status=None, to_status="draft",
                           actor=self.actor, evidence=evidence)
                return row.revision_id
        except IntegrityError as exc:
            raise ValueError("Equipment package code/revision already exists; create a new revision") from exc

    def inspect(self, revision_id):
        revision_id = _text(revision_id, "Capability revision identity")
        with session_scope(self.db_url) as session:
            _reserve_transaction(session, write=False)
            row = session.get(EquipmentCapabilityRevision, revision_id)
            if row is None:
                raise ValueError("Equipment capability revision not found")
            return _detail(session, row)

    def list_revisions(self, kind=None):
        if kind is not None:
            _kind(kind)
        with session_scope(self.db_url) as session:
            _reserve_transaction(session, write=False)
            query = session.query(EquipmentCapabilityRevision)
            if kind is not None:
                query = query.filter_by(kind=kind)
            rows = query.order_by(
                EquipmentCapabilityRevision.kind, EquipmentCapabilityRevision.package_code,
                EquipmentCapabilityRevision.created_at, EquipmentCapabilityRevision.revision_id,
            ).all()
            return [_detail(session, row) for row in rows]

    def resolve_reference(self, reference, kind):
        kind = _kind(kind)
        reference = CapabilityReference.model_validate(reference)
        with session_scope(self.db_url) as session:
            _reserve_transaction(session, write=False)
            row = session.query(EquipmentCapabilityRevision).filter_by(
                kind=kind, package_code=reference.package_code, revision=reference.revision,
            ).one_or_none()
            if row is None:
                raise ValueError("Equipment capability reference not found")
            detail = _detail(session, row)
            if reference.sha256.lower() != detail["sha256"]:
                raise ValueError("Equipment capability reference hash mismatch")
            return detail

    def transition(self, revision_id, expected_status, target_status, evidence_ref):
        revision_id = _text(revision_id, "Capability revision identity")
        evidence = _text(evidence_ref, "Review evidence")
        if (not isinstance(expected_status, str) or not isinstance(target_status, str)
                or target_status not in _ALLOWED_TRANSITIONS.get(expected_status, set())):
            raise ValueError("Unsupported equipment capability review transition")
        with session_scope(self.db_url) as session:
            _reserve_transaction(session, write=True)
            row = session.get(EquipmentCapabilityRevision, revision_id)
            if row is None or row.status != expected_status:
                raise ValueError("Equipment capability state changed; reload before continuing")
            _detail(session, row)
            previous = session.query(EquipmentCapabilityRevisionEvent).filter_by(
                revision_id=revision_id,
            ).order_by(EquipmentCapabilityRevisionEvent.event_number.desc()).first()
            active, published = _STATE_FLAGS[target_status]
            changed = session.execute(update(EquipmentCapabilityRevision).where(
                EquipmentCapabilityRevision.revision_id == revision_id,
                EquipmentCapabilityRevision.status == expected_status,
                EquipmentCapabilityRevision.payload_sha256 == row.payload_sha256,
                EquipmentCapabilityRevision.is_active == row.is_active,
                EquipmentCapabilityRevision.is_published == row.is_published,
                EquipmentCapabilityRevision.updated_at == row.updated_at,
            ).values(status=target_status, is_active=active, is_published=published))
            if changed.rowcount != 1:
                raise ValueError("Concurrent capability review update; reload before continuing")
            _add_event(session, row, previous=previous, from_status=expected_status,
                       to_status=target_status, actor=self.actor, evidence=evidence)


__all__ = ["EquipmentCapabilityRevisionService"]
