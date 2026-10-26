"""Independent synthetic evidence registry; no product sizing/release authority."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, update

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import (
    EquipmentCapabilityRevision, EquipmentCapabilityRevisionEvent, ProductACBlock,
)
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.schemas.ac_equipment_capability import capability_package_sha256
from calb_sizing_tool.services.ac_equipment_capability_service import EquipmentCapabilityRevisionService


def package(kind="pcs", *, revision="1", code=None):
    result = dict(package_code=code or "SYNTHETIC-" + kind.upper(), revision=revision,
                  kind=kind, model="Synthetic device", manufacturer="SYNTHETIC ONLY",
                  source_ref="synthetic:test:no-manufacturer-approval", conditions={})
    if kind == "pcs":
        result["pcs"] = dict(ports=[dict(port_id="P1", dc_bus_group="B1")],
                             dc_buses=[dict(dc_bus_group="B1")])
    else:
        result["transformer"] = dict(windings=[dict(winding_id="LV1")])
    return result


@pytest.fixture
def registry(tmp_path):
    url = "sqlite:///" + (tmp_path / "capability.sqlite").as_posix()
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    actor = SimpleNamespace(username="synthetic-reviewer", is_admin=True)
    return EquipmentCapabilityRevisionService(actor, url)


def review(registry, revision_id):
    registry.transition(revision_id, "draft", "parameter_review", "synthetic:parameters")
    registry.transition(revision_id, "parameter_review", "candidate_only", "synthetic:review")
    return registry.inspect(revision_id)


def reference(detail):
    return {key: detail[key] for key in ("package_code", "revision", "sha256")} | {
        "evidence_ref": "synthetic:reference-only"}


@pytest.mark.parametrize("actor", [None, SimpleNamespace(username="admin", is_admin=False),
    SimpleNamespace(username="admin", is_admin="yes"), SimpleNamespace(username=" ", is_admin=True),
    SimpleNamespace(username=None, is_admin=True), SimpleNamespace(username="x" * 129, is_admin=True),
    SimpleNamespace(is_admin=True)])
def test_admin_only(actor):
    with pytest.raises(PermissionError, match="Administrator"):
        EquipmentCapabilityRevisionService(actor)


@pytest.mark.parametrize("kind", ["pcs", "transformer"])
def test_creation_is_typed_immutable_draft_and_has_bound_event(registry, kind):
    payload = package(kind)
    revision_id = registry.create(payload, "synthetic:source")
    payload["model"] = "Caller mutation"
    detail = registry.inspect(revision_id)
    assert detail["status"] == "draft"
    assert detail["is_active"] is True and detail["is_published"] is False
    assert detail["candidate_review_current"] is False
    assert detail["payload"]["model"] == "Synthetic device"
    assert detail["sha256"] == capability_package_sha256(package(kind))
    assert detail["payload"]["schema_version"] == 1
    assert len(detail["events"]) == 1
    event = detail["events"][0]
    assert event["event_number"] == 1 and event["from_status"] is None
    assert event["to_status"] == "draft" and event["actor"] == "synthetic-reviewer"
    assert event["previous_event_sha256"] is None
    assert event["payload_sha256"] == detail["sha256"]
    assert detail["comparison_only"] and not detail["runtime_sizing_enabled"]
    detail["payload"]["model"] = "Returned dictionary mutation"
    assert registry.inspect(revision_id)["payload"]["model"] == "Synthetic device"


def test_complete_lifecycle_changes_tokens_and_never_releases_product(registry):
    with session_scope(registry.db_url) as db:
        db.add(ProductACBlock(block_code="EXISTING", block_name="Existing", is_active=False,
                              is_published=False))
    revision_id = registry.create(package(), "synthetic:source")
    previous = registry.inspect(revision_id)
    tokens = [previous["review_token"]]
    for start, target in [("draft", "parameter_review"), ("parameter_review", "candidate_only"),
                          ("candidate_only", "retired")]:
        registry.transition(revision_id, start, target, "synthetic:" + target)
        detail = registry.inspect(revision_id)
        assert detail["sha256"] == previous["sha256"]
        assert detail["review_token"] != tokens[-1]
        assert detail["candidate_review_current"] is (target == "candidate_only")
        assert detail["is_active"] is (target != "retired")
        assert detail["is_published"] is (target == "candidate_only")
        assert detail["events"][-1]["previous_event_sha256"] == previous["events"][-1]["event_sha256"]
        tokens.append(detail["review_token"])
        previous = detail
    assert len(set(tokens)) == 4
    with session_scope(registry.db_url) as db:
        old = db.query(ProductACBlock).filter_by(block_code="EXISTING").one()
        assert old.is_active is False and old.is_published is False


@pytest.mark.parametrize("state", ["draft", "parameter_review", "candidate_only"])
def test_retirement_available_from_every_non_retired_state(registry, state):
    revision_id = registry.create(package(), "synthetic:source")
    if state in ("parameter_review", "candidate_only"):
        registry.transition(revision_id, "draft", "parameter_review", "synthetic:parameters")
    if state == "candidate_only":
        registry.transition(revision_id, "parameter_review", "candidate_only", "synthetic:review")
    registry.transition(revision_id, state, "retired", "synthetic:withdrawn")
    assert not registry.inspect(revision_id)["candidate_review_current"]
    with pytest.raises(ValueError, match="Unsupported"):
        registry.transition(revision_id, "retired", "draft", "synthetic:revive")


@pytest.mark.parametrize("start,target", [("draft", "candidate_only"), ("draft", "draft"),
    ("candidate_only", "parameter_review"), ("retired", "candidate_only"), ("unknown", "draft"),
    ([], "retired"), ("draft", True)])
def test_unsupported_transitions_do_not_write(registry, start, target):
    revision_id = registry.create(package(), "synthetic:source")
    before = registry.inspect(revision_id)
    with pytest.raises(ValueError, match="Unsupported"):
        registry.transition(revision_id, start, target, "synthetic:evidence")
    assert registry.inspect(revision_id) == before


@pytest.mark.parametrize("evidence", [None, "", " \t", 123, False])
def test_blank_or_nontext_evidence_never_writes(registry, evidence):
    with pytest.raises(ValueError, match="Source evidence"):
        registry.create(package(), evidence)
    revision_id = registry.create(package(), "synthetic:source")
    before = registry.inspect(revision_id)
    with pytest.raises(ValueError, match="Review evidence"):
        registry.transition(revision_id, "draft", "parameter_review", evidence)
    assert registry.inspect(revision_id) == before


def test_duplicate_identity_requires_new_revision(registry):
    revision_id = registry.create(package(), "synthetic:source")
    with pytest.raises(ValueError, match="already exists"):
        registry.create(package(), "synthetic:duplicate")
    second = registry.create(package(revision="2"), "synthetic:new-version")
    transformer = registry.create(package("transformer", code="SYNTHETIC-PCS"), "synthetic:kind")
    assert len({revision_id, second, transformer}) == 3
    assert len(registry.list_revisions()) == 3
    assert len(registry.list_revisions("pcs")) == 2
    assert len(registry.list_revisions("transformer")) == 1
    assert not hasattr(registry, "update")


@pytest.mark.parametrize("mutation", [lambda value: value.update(unknown=True),
    lambda value: value.update(schema_version=True), lambda value: value.update(kind="transformer"),
    lambda value: value["pcs"]["ports"][0].update(continuous_current_a=0),
    lambda value: value["pcs"].update(dc_discharge_power_kw=float("nan"))])
def test_invalid_packages_rejected_without_registry_rows(registry, mutation):
    payload = package()
    mutation(payload)
    with pytest.raises(ValueError):
        registry.create(payload, "synthetic:source")
    assert registry.list_revisions() == []


def test_reference_exact_identity_hash_and_diagnostic_draft_retired(registry):
    revision_id = registry.create(package(), "synthetic:source")
    draft = registry.inspect(revision_id)
    ref = reference(draft)
    assert registry.resolve_reference(ref, "pcs")["candidate_review_current"] is False
    candidate = review(registry, revision_id)
    assert registry.resolve_reference(ref, "pcs")["candidate_review_current"] is True
    assert registry.resolve_reference(ref | {"evidence_ref": "arbitrary citation"}, "pcs")["review_token"] == candidate["review_token"]
    assert registry.resolve_reference(ref | {"sha256": ref["sha256"].upper()}, "pcs")["sha256"] == ref["sha256"]
    registry.transition(revision_id, "candidate_only", "retired", "synthetic:withdrawn")
    assert registry.resolve_reference(ref, "pcs")["candidate_review_current"] is False
    assert registry.resolve_reference(ref, "pcs")["review_token"] != candidate["review_token"]


@pytest.mark.parametrize("change,kind,message", [({"revision": "unknown"}, "pcs", "not found"),
    ({"package_code": "unknown"}, "pcs", "not found"), ({}, "transformer", "not found"),
    ({"sha256": "0" * 64}, "pcs", "hash mismatch"), ({}, "battery", "kind")])
def test_reference_failures_are_controlled(registry, change, kind, message):
    detail = registry.inspect(registry.create(package(), "synthetic:source"))
    with pytest.raises(ValueError, match=message):
        registry.resolve_reference(reference(detail) | change, kind)


@pytest.mark.parametrize("values", [dict(status="candidate_only", is_published=True),
    dict(is_published=True), dict(is_active=False), dict(created_by="other"),
    dict(payload_sha256="0" * 64), dict(package_code="renamed")])
def test_direct_state_flags_identity_hash_and_creator_cannot_bypass_review(registry, values):
    revision_id = registry.create(package(), "synthetic:source")
    with session_scope(registry.db_url) as db:
        db.execute(update(EquipmentCapabilityRevision).where(
            EquipmentCapabilityRevision.revision_id == revision_id).values(**values))
    with pytest.raises(ValueError, match="integrity"):
        registry.inspect(revision_id)
    with pytest.raises(ValueError):
        registry.transition(revision_id, values.get("status", "draft"), "retired", "synthetic:retire")


def test_rehashed_payload_tamper_still_invalidates_event_binding(registry):
    revision_id = registry.create(package(), "synthetic:source")
    payload = registry.inspect(revision_id)["payload"]
    payload["model"] = "Tampered even with recomputed content hash"
    with session_scope(registry.db_url) as db:
        db.execute(update(EquipmentCapabilityRevision).where(
            EquipmentCapabilityRevision.revision_id == revision_id).values(
            payload_json=payload, payload_sha256=capability_package_sha256(payload)))
    with pytest.raises(ValueError, match="event integrity"):
        registry.inspect(revision_id)


@pytest.mark.parametrize("mutation", [dict(evidence_ref="altered"), dict(actor="other"),
    dict(from_status="candidate_only"), dict(to_status="retired"), dict(event_sha256="0" * 64),
    dict(previous_event_sha256="0" * 64), dict(event_number=2)])
def test_event_tampering_rejected(registry, mutation):
    revision_id = registry.create(package(), "synthetic:source")
    with session_scope(registry.db_url) as db:
        db.execute(update(EquipmentCapabilityRevisionEvent).where(
            EquipmentCapabilityRevisionEvent.revision_id == revision_id).values(**mutation))
    with pytest.raises(ValueError, match="integrity"):
        registry.inspect(revision_id)


@pytest.mark.parametrize("number", [1, 2, 3])
def test_deleted_review_event_rejected(registry, number):
    revision_id = registry.create(package(), "synthetic:source")
    review(registry, revision_id)
    with session_scope(registry.db_url) as db:
        db.execute(delete(EquipmentCapabilityRevisionEvent).where(
            EquipmentCapabilityRevisionEvent.revision_id == revision_id,
            EquipmentCapabilityRevisionEvent.event_number == number))
    with pytest.raises(ValueError, match="integrity"):
        registry.inspect(revision_id)


def test_stale_expected_state_never_adds_duplicate_event(registry):
    revision_id = registry.create(package(), "synthetic:source")
    registry.transition(revision_id, "draft", "parameter_review", "synthetic:parameters")
    before = registry.inspect(revision_id)
    with pytest.raises(ValueError, match="state changed"):
        registry.transition(revision_id, "draft", "parameter_review", "synthetic:stale")
    assert registry.inspect(revision_id) == before


def test_concurrent_transition_reserves_writer_and_only_one_review_event(registry):
    revision_id = registry.create(package(), "synthetic:source")
    barrier = Barrier(2)
    def worker(number):
        service = EquipmentCapabilityRevisionService(
            SimpleNamespace(username="synthetic-reviewer-" + str(number), is_admin=True), registry.db_url)
        barrier.wait()
        try:
            service.transition(revision_id, "draft", "parameter_review", "synthetic:parallel")
            return "updated"
        except ValueError as exc:
            assert "state changed" in str(exc)
            return "stale"
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(worker, (1, 2)))
    assert sorted(results) == ["stale", "updated"]
    detail = registry.inspect(revision_id)
    assert detail["status"] == "parameter_review"
    assert len(detail["events"]) == 2


def test_missing_records_and_invalid_kind_controlled(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.inspect("unknown")
    with pytest.raises(ValueError, match="state changed"):
        registry.transition("unknown", "draft", "parameter_review", "synthetic:missing")
    with pytest.raises(ValueError, match="kind"):
        registry.list_revisions("battery")
