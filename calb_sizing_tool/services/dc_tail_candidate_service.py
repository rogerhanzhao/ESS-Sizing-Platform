"""Bounded, planning-only tail replacements for the existing 12-string family.

The caller supplies the container count from a separate standard sizing result.
This service neither derives that count nor evaluates performance or selects an
optimum. Every option retains its physical catalogue identities through the C2a
composition contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from calb_sizing_tool.services.dc_composition_manifest_service import (
    MAX_MANIFEST_UNITS,
    build_dc_composition_manifest,
)


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def dc_tail_candidate_plan_sha256(plan: dict) -> str:
    """Sign the complete planning contract, excluding its own digest field."""
    return _digest({key: value for key, value in plan.items() if key != 'plan_sha256'})


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text')
    return value.strip()


def _revision_token(detail):
    # The snapshot is retained in the token as well as its stored digest. This
    # checks the whole collection after all individual manifests are built.
    return dict(revision_id=detail.get('revision_id'),
                revision_label=detail.get('revision_label'),
                revision_sha256=detail.get('sha256'),
                status=detail.get('status'), stale=detail.get('stale'),
                candidate_review_current=detail.get('candidate_review_current'),
                candidate_errors=copy.deepcopy(detail.get('candidate_errors')),
                snapshot_sha256=_digest(detail.get('snapshot')))


def _relation_token(detail):
    keys = ('relation_id', 'relation_sha256', 'parent_revision_id',
            'child_revision_id', 'parent_product_id', 'child_product_id',
            'parent_revision_sha256', 'child_revision_sha256', 'version_label',
            'use_scope', 'status', 'stale', 'candidate_review_current',
            'review_current', 'review_errors')
    return {key: copy.deepcopy(detail.get(key)) for key in keys}


def _selected_revision(revision_service, revision_id, *, parent):
    detail = copy.deepcopy(revision_service.inspect(revision_id))
    if not isinstance(detail, dict) or detail.get('revision_id') != revision_id:
        raise ValueError('Selected product revision identity does not match')
    if detail.get('stale') is not False or detail.get('status') == 'retired':
        raise ValueError('Selected product revision is stale or retired; reload the candidate plan')
    payload = detail.get('snapshot')
    if not isinstance(payload, dict) or not isinstance(payload.get('product'), dict):
        raise ValueError('Selected product revision snapshot is incomplete')
    product, cell = payload['product'], payload.get('cell')
    strings = product.get('strings_in_parallel')
    expected = (12,) if parent else (8, 10)
    if type(strings) is not int or strings not in expected:
        raise ValueError('Parent requires 12 strings; child requires 8 or 10 strings')
    if not isinstance(cell, dict):
        raise ValueError('An explicit linked 314Ah cell snapshot is required')
    ah = cell.get('nominal_capacity_ah')
    if type(ah) not in (int, float) or not math.isfinite(ah) or ah != 314:
        raise ValueError('An explicit 314Ah cell capacity is required for this candidate family')
    # The composition builder performs the shared 20ft/416S/exact-cell and
    # structural role checks; do not duplicate or weaken that contract here.
    return detail


def plan_tail_replacement_candidates(
    revision_service,
    parent_revision_id,
    child_revision_ids: list,
    *,
    standard_container_count: int,
    variant_service,
    allow_special_configurations=False,
    special_reason='',
) -> dict:
    """Return the standard composition and at most two one-tail replacements.

    Draft product/relation reviews remain explicit approval gaps. This is a
    planning enumeration, not mixed sizing, guaranteed-energy evaluation, AC
    matching, activation, or a downstream adoption contract.
    """
    if type(standard_container_count) is not int or standard_container_count <= 0:
        raise ValueError('Standard container count must be a positive whole number')
    if standard_container_count > MAX_MANIFEST_UNITS:
        raise ValueError(f'The local candidate plan supports at most {MAX_MANIFEST_UNITS:,} physical containers')
    if not isinstance(child_revision_ids, list) or len(child_revision_ids) > 2:
        raise ValueError('Select a list containing at most two child revisions, one per string count')
    if not isinstance(allow_special_configurations, bool):
        raise ValueError('Special configuration opt-in must be explicit true or false')
    if not isinstance(special_reason, str):
        raise ValueError('Special configuration reason must be text')
    parent_id = _identifier(parent_revision_id, 'Parent revision identity')
    child_ids = [_identifier(value, 'Child revision identity') for value in child_revision_ids]
    if len(set(child_ids)) != len(child_ids) or parent_id in child_ids:
        raise ValueError('Duplicate parent or child revisions are not allowed')
    if child_ids and (not allow_special_configurations or not special_reason.strip()):
        raise ValueError('Child candidates require explicit special-scenario opt-in and a reason')
    if child_ids and variant_service is None:
        raise ValueError('Child candidates require a registered parent-child relation')

    parent = _selected_revision(revision_service, parent_id, parent=True)
    children = [_selected_revision(revision_service, value, parent=False) for value in child_ids]
    string_counts = [item['snapshot']['product']['strings_in_parallel'] for item in children]
    if len(set(string_counts)) != len(string_counts):
        raise ValueError('Only one child revision per string count may be selected')
    for child in children:
        if (child['snapshot']['product'].get('product_cell_id')
                != parent['snapshot']['product'].get('product_cell_id')
                or _digest(child['snapshot']['cell']) != _digest(parent['snapshot']['cell'])):
            raise ValueError('All candidate configurations must share the exact same cell identity and snapshot; equal Ah is insufficient')
    children.sort(key=lambda item: item['snapshot']['product']['strings_in_parallel'], reverse=True)
    selected = [parent, *children]
    revision_tokens = [_revision_token(item) for item in selected]
    relation_tokens = {}
    for child in children:
        product = child['snapshot']['product']
        matches = [copy.deepcopy(item) for item in variant_service.list_relations(
            child_product_id=product.get('product_dc_block_id'))
            if item.get('child_revision_id') == child['revision_id']
            and item.get('parent_revision_id') == parent_id
            and item.get('status') != 'retired']
        if len(matches) != 1:
            raise ValueError('Each child requires one unambiguous registered relation to the selected parent revision')
        relation = matches[0]
        if (relation.get('stale') is not False
                or relation.get('use_scope') != 'special_scenario_only'):
            raise ValueError('The registered relation must be current and special-scenario-only')
        if (relation.get('parent_product_id') != parent['snapshot']['product'].get('product_dc_block_id')
                or relation.get('child_product_id') != product.get('product_dc_block_id')):
            raise ValueError('Registered relation product identities must match their selected revisions')
        for prefix, revision in (('parent', parent), ('child', child)):
            bound_digest = relation.get(f'{prefix}_revision_sha256')
            if bound_digest is not None and bound_digest != revision.get('sha256'):
                raise ValueError('Registered relation revision digest does not match the selected revision')
        relation_id = _identifier(relation.get('relation_id'), 'Parent-child relation identity')
        relation_tokens[relation_id] = _relation_token(relation)
    options = dict(variant_service=variant_service,
                   allow_special_configurations=allow_special_configurations,
                   special_reason=special_reason.strip())

    def build(lines):
        result = build_dc_composition_manifest(revision_service, lines, **options)
        # Capture the relationship state used by this candidate, then verify the
        # entire collection once more after the last candidate is complete.
        for row in result['bom']:
            relation_id = row['relation_id']
            if relation_id:
                detail = variant_service.inspect(relation_id)
                if (detail.get('relation_sha256') != row['relation_sha256']
                        or detail.get('parent_revision_id') != parent_id
                        or detail.get('child_revision_id') != row['revision_id']
                        or detail.get('stale') is not False
                        or detail.get('status') == 'retired'
                        or _relation_token(detail) != relation_tokens.get(relation_id)):
                    raise ValueError('A parent-child relation changed during candidate planning; reload')
        return result

    baseline = build([dict(revision_id=parent_id, quantity=standard_container_count, role='main')])
    candidates = [dict(candidate_key='standard',
                       label=f'Standard: {standard_container_count} × 12-string',
                       kind='standard', manifest=baseline,
                       scope=copy.deepcopy(baseline['scope']))]
    omitted = []
    for child in children:
        child_id = child['revision_id']
        strings = child['snapshot']['product']['strings_in_parallel']
        # A one-box standard run has no retained parent after replacement.
        # Validate its selected child through the shared composition contract,
        # but never return a child-only candidate or call it feasible.
        parent_count = max(1, standard_container_count - 1)
        manifest = build([dict(revision_id=parent_id, quantity=parent_count, role='main'),
                          dict(revision_id=child_id, quantity=1, role='tail')])
        key = f'tail_{strings}'
        if standard_container_count == 1:
            omitted.append(dict(candidate_key=key, child_revision_id=child_id,
                                strings_in_parallel=strings, reason='needs_parent_maintained',
                                explanation='A tail replacement must retain at least one 12-string parent container.'))
            continue
        candidates.append(dict(candidate_key=key,
                               label=f'Tail option: {parent_count} × 12 + 1 × {strings}',
                               kind='tail_replacement', manifest=manifest,
                               scope=copy.deepcopy(manifest['scope'])))

    for original, token in zip(selected, revision_tokens):
        current = revision_service.inspect(original['revision_id'])
        if _revision_token(current) != token:
            raise ValueError('A product revision or review changed during candidate planning; reload')
    for relation_id, token in relation_tokens.items():
        if _relation_token(variant_service.inspect(relation_id)) != token:
            raise ValueError('A parent-child relation or review changed during candidate planning; reload')
    plan = dict(schema_version=1, contract_type='dc_tail_replacement_candidate_plan',
                comparison_only=True, downstream_ready=False,
                standard_container_count=standard_container_count,
                count_basis='Caller-supplied count from a separate standard sizing result; not recalculated here.',
                scope=dict(allow_special_configurations=allow_special_configurations,
                           special_reason=special_reason.strip()),
                revision_identities=revision_tokens,
                relation_identities=[relation_tokens[key] for key in sorted(relation_tokens)],
                candidates=candidates, omitted_candidates=omitted,
                performance_evaluated=False, ac_power_matching_evaluated=False)
    plan['plan_sha256'] = dc_tail_candidate_plan_sha256(plan)
    return plan
