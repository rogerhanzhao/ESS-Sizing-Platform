"""Explicit, versioned DC equipment composition for local planning.

This module performs no sizing search, power allocation or lifetime calculation.
It preserves each physical container and its separately evidenced output domains
so a later AC adapter cannot replace a mixed bill of equipment with an average.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping

from calb_sizing_tool.common.dc_configuration_identity import is_20ft_container_type


# This local planning contract expands physical identifiers in memory. It is not
# a site capacity rule and is not read by any sizing calculation.
MAX_MANIFEST_UNITS = 10_000


def dc_composition_manifest_sha256(manifest: dict) -> str:
    """Hash the complete contract, excluding its own digest field."""
    content = {key: value for key, value in manifest.items() if key != 'manifest_sha256'}
    encoded = json.dumps(content, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text')
    return value.strip()


def _whole(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{label} must be a positive whole number')
    return value


def _number(value, label, *, unknown=False):
    if value is None and unknown:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{label} must be finite numeric data')
    if unknown and value == 0:
        return None  # Existing catalogue rows use zero for unconfirmed ratings.
    if value <= 0:
        raise ValueError(f'{label} must be positive')
    return float(value)


def _revision_identity(detail):
    return (detail.get('sha256'), detail.get('status'), detail.get('stale'),
            detail.get('candidate_review_current'))


def _revision(revision_service, revision_id):
    detail = copy.deepcopy(revision_service.inspect(revision_id))
    if detail.get('revision_id') != revision_id or detail.get('stale') is not False:
        raise ValueError('A selected product revision is stale or has changed; reload the composition')
    if detail.get('status') == 'retired':
        raise ValueError('Retired product revisions cannot be used in a composition')
    _text(detail.get('sha256'), 'Revision digest')
    payload = detail.get('snapshot')
    if not isinstance(payload, dict) or not isinstance(payload.get('product'), dict):
        raise ValueError('Product revision snapshot is incomplete')
    product = payload['product']
    _text(product.get('product_dc_block_id'), 'Product identity')
    _text(product.get('block_code'), 'Product code')
    if product.get('block_form') != 'container':
        raise ValueError('This composition pilot requires explicit container products')
    if not is_20ft_container_type(product.get('container_type')):
        raise ValueError('This composition pilot requires an explicit 20ft container type')
    if _whole(product.get('cells_in_series'), 'Series cell count') != 416:
        raise ValueError('This composition pilot requires the 416S container family')
    if _whole(product.get('strings_in_parallel'), 'Parallel string count') not in (8, 10, 12):
        raise ValueError('Only 12-, 10- and 8-string configurations are supported in this pilot')
    cell = payload.get('cell')
    cell_id = _text(product.get('product_cell_id'), 'Cell identity')
    if not isinstance(cell, dict) or cell.get('product_cell_id') != cell_id:
        raise ValueError('Product revision must contain its exact linked cell identity')
    return detail


def _partitions(revision_id, product, supplied):
    if revision_id not in supplied:
        return None
    rows = supplied[revision_id]
    if not isinstance(rows, list) or not rows:
        raise ValueError('Electrical partitions must be a nonempty list of explicit output domains')
    result, labels = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Each electrical output domain must be an object')
        label = _text(row.get('domain_label'), 'Output domain label')
        if label.casefold() in labels:
            raise ValueError('Output domain labels must be unique within a physical container')
        labels.add(label.casefold())
        result.append(dict(
            domain_label=label,
            strings=_whole(row.get('strings'), 'Output domain string count'),
            gross_energy_mwh=_number(row.get('gross_energy_mwh'), 'Output domain gross energy'),
            nominal_power_kw=_number(row.get('nominal_power_kw'), 'Output domain nominal power', unknown=True),
            max_current_a=_number(row.get('max_current_a'), 'Output domain maximum current', unknown=True),
            evidence_ref=_text(row.get('evidence_ref'), 'Output domain evidence reference'),
        ))
    if sum(row['strings'] for row in result) != product['strings_in_parallel']:
        raise ValueError('Output domain string counts must sum to the complete physical container')
    energy = _number(product.get('gross_energy_mwh'), 'Product gross nameplate energy')
    if not math.isclose(math.fsum(row['gross_energy_mwh'] for row in result), energy,
                        rel_tol=0, abs_tol=1e-6):
        raise ValueError('Explicit output domain energies must sum to the physical container nameplate energy')
    return result


def build_dc_composition_manifest(
    revision_service,
    lines: list[dict],
    *,
    variant_service=None,
    allow_special_configurations=False,
    special_reason='',
    electrical_partitions=None,
) -> dict:
    """Build a planning-only BOM from explicit quantities and catalogue snapshots.

    Draft revisions and draft parent/child relations remain visible as approval
    gaps. A stale revision, ambiguous quantity, unrelated child, or invented
    electrical partition is rejected. Even a fully evidenced BOM does not
    establish AC power matching, lifetime performance or drawing readiness.
    """
    if not isinstance(lines, list) or not lines:
        raise ValueError('At least one explicit composition line is required')
    if not isinstance(allow_special_configurations, bool):
        raise ValueError('Special configuration opt-in must be explicit true or false')
    if not isinstance(special_reason, str):
        raise ValueError('Special configuration reason must be text')
    if electrical_partitions is None:
        electrical_partitions = {}
    if not isinstance(electrical_partitions, Mapping):
        raise ValueError('Electrical partitions must be keyed by product revision')
    supplied = copy.deepcopy(dict(electrical_partitions))
    selected, revisions, products, cell_ids = [], set(), set(), set()
    unit_count = 0
    for row in lines:
        if not isinstance(row, dict):
            raise ValueError('Each composition line must be an object')
        revision_id = _text(row.get('revision_id'), 'Revision identity')
        quantity = _whole(row.get('quantity'), 'Container quantity')
        unit_count += quantity
        if unit_count > MAX_MANIFEST_UNITS:
            raise ValueError(f'The local planning manifest supports at most {MAX_MANIFEST_UNITS:,} physical containers')
        if row.get('role') not in ('main', 'tail'):
            raise ValueError('Composition role must be main or tail')
        if revision_id in revisions:
            raise ValueError('Duplicate revision entries are ambiguous; combine their quantities')
        detail = _revision(revision_service, revision_id)
        product = detail['snapshot']['product']
        expected_role = 'main' if product['strings_in_parallel'] == 12 else 'tail'
        if row['role'] != expected_role:
            raise ValueError('The 12-string parent must be main; 8/10-string variants must be tail')
        product_id = product['product_dc_block_id']
        if product_id in products:
            raise ValueError('Multiple revisions of the same product cannot share one composition')
        revisions.add(revision_id)
        products.add(product_id)
        cell_ids.add(product['product_cell_id'])
        selected.append((detail, quantity, row['role']))
    if len(cell_ids) != 1:
        raise ValueError('All composition lines must share the exact same cell identity; equal Ah is insufficient')
    if set(supplied) - revisions:
        raise ValueError('Electrical partitions include an unselected product revision')
    parents = {detail['revision_id'] for detail, _, _ in selected
               if detail['snapshot']['product']['strings_in_parallel'] == 12}
    children = [detail for detail, _, _ in selected
                if detail['snapshot']['product']['strings_in_parallel'] in (8, 10)]
    if len(parents) != 1:
        raise ValueError('Exactly one 12-string parent revision is required for this composition family')
    if children and (not allow_special_configurations or not special_reason.strip()):
        raise ValueError('8- and 10-string variants require explicit special-scenario opt-in and a reason')
    if children and variant_service is None:
        raise ValueError('8- and 10-string variants require a registered parent-child relation')

    relations = {}
    for detail in children:
        product = detail['snapshot']['product']
        candidates = variant_service.list_relations(child_product_id=product['product_dc_block_id'])
        matching = [copy.deepcopy(item) for item in candidates
                    if item.get('child_revision_id') == detail['revision_id']
                    and item.get('parent_revision_id') in parents
                    and item.get('status') != 'retired']
        if len(matching) != 1:
            raise ValueError('Each special variant requires one unambiguous registered relation to the selected parent revision')
        relation = matching[0]
        if relation.get('stale') is not False:
            raise ValueError('A parent-child relation is stale; review the current product revisions')
        if relation.get('use_scope') != 'special_scenario_only':
            raise ValueError('Special variants must retain their special-scenario-only use scope')
        _text(relation.get('relation_id'), 'Parent-child relation identity')
        _text(relation.get('relation_sha256'), 'Parent-child relation digest')
        relations[detail['revision_id']] = relation

    bom, units, domains, approval_errors, rating_errors = [], [], [], [], []
    all_outputs_defined, all_reviews_current = True, True
    for line_number, (detail, quantity, role) in enumerate(selected, 1):
        product = detail['snapshot']['product']
        code = product['block_code']
        cell_ah = detail['snapshot']['cell'].get('nominal_capacity_ah')
        if cell_ah is not None and _number(cell_ah, 'Cell nominal capacity') != 314:
            raise ValueError('This composition pilot requires the 314Ah cell family')
        energy = _number(product.get('gross_energy_mwh'), 'Product gross nameplate energy')
        power = _number(product.get('nominal_power_kw'), 'Product nominal power', unknown=True)
        current = _number(product.get('max_current_a'), 'Product maximum current', unknown=True)
        partition = _partitions(detail['revision_id'], product, supplied)
        if partition is None:
            all_outputs_defined = False
        relation = relations.get(detail['revision_id'])
        if detail.get('candidate_review_current') is not True:
            all_reviews_current = False
            approval_errors.append(f'{code}: current product parameter review is incomplete.')
        if cell_ah is None:
            all_reviews_current = False
            approval_errors.append(f'{code}: confirmed 314Ah cell capacity is missing.')
        if relation and relation.get('candidate_review_current', relation.get('review_current')) is not True:
            all_reviews_current = False
            approval_errors.append(f'{code}: parent-child configuration review is incomplete.')
        if power is None or current is None:
            rating_errors.append(f'{code}: confirmed container power and current ratings are incomplete.')
        if partition and any(row['nominal_power_kw'] is None or row['max_current_a'] is None for row in partition):
            rating_errors.append(f'{code}: confirmed output-domain power and current ratings are incomplete.')
        metadata = product.get('metadata_json') or {}
        if not isinstance(metadata, dict):
            raise ValueError('Product metadata must be an object')
        entry = dict(
            line_number=line_number, role=role, quantity=quantity,
            product_id=product['product_dc_block_id'], product_code=code,
            product_name=product.get('block_name') or code,
            revision_id=detail['revision_id'], revision_label=detail.get('revision_label'),
            revision_sha256=detail['sha256'], product_cell_id=product['product_cell_id'],
            cells_in_series=product['cells_in_series'], strings_in_parallel=product['strings_in_parallel'],
            unit_gross_energy_mwh=energy, subtotal_gross_energy_mwh=energy * quantity,
            energy_basis=copy.deepcopy(metadata.get('energy_basis', 'Source basis not specified in catalogue metadata')),
            inherited_fields_basis=copy.deepcopy(metadata.get('inherited_fields_basis', {})),
            unit_nominal_power_kw=power, unit_max_current_a=current,
            parent_revision_id=relation['parent_revision_id'] if relation else None,
            relation_id=relation['relation_id'] if relation else None,
            relation_sha256=relation['relation_sha256'] if relation else None,
        )
        bom.append(entry)
        for _ in range(quantity):
            unit_id = f'DC-{len(units) + 1:03d}'
            domain_ids = []
            for index, domain in enumerate(partition or [], 1):
                domain_id = f'{unit_id}/D{index}'
                domain_ids.append(domain_id)
                domains.append(dict(domain, domain_id=domain_id, unit_id=unit_id,
                                    revision_id=detail['revision_id']))
            units.append(dict(unit_id=unit_id, line_number=line_number, role=role,
                              product_code=code, revision_id=detail['revision_id'],
                              revision_sha256=detail['sha256'], gross_energy_mwh=energy,
                              strings_in_parallel=product['strings_in_parallel'],
                              electrical_domain_ids=domain_ids))

    blocked_reasons = list(approval_errors)
    if not all_outputs_defined:
        blocked_reasons.append('Explicit electrical output partitions are missing; strings are not output circuits or racks.')
    blocked_reasons.extend(rating_errors)
    blocked_reasons.extend([
        'AC power matching and individual PCS assignments have not been evaluated.',
        'Recorded box and output-domain ratings are presence checks only; aggregate electrical limits remain unreconciled.',
        'Lifetime performance and usable-energy requirements have not been evaluated.',
        'SLD, layout and technical proposal generation require the validated downstream allocation contract.',
    ])
    manifest = dict(
        schema_version=1, contract_type='dc_composition_planning',
        comparison_only=True, downstream_ready=False,
        energy_boundary='DC gross nameplate energy at BOL',
        scope=dict(use_scope='special_scenario_only' if children else 'standard_parent_only',
                   allow_special_configurations=allow_special_configurations,
                   special_reason=special_reason.strip()),
        bom=bom, physical_units=units, electrical_domains=domains,
        total_container_count=sum(row['quantity'] for row in bom),
        total_gross_energy_mwh=math.fsum(row['subtotal_gross_energy_mwh'] for row in bom),
        aggregate_nominal_power_kw=(math.fsum(row['unit_nominal_power_kw'] * row['quantity'] for row in bom)
                                    if all(row['unit_nominal_power_kw'] is not None for row in bom) else None),
        capability_gates=dict(energy_bom_validated=True, product_reviews=all_reviews_current,
                              output_domains_defined=all_outputs_defined,
                              electrical_ratings_present=not rating_errors and all_outputs_defined,
                              electrical_limits_reconciled=False,
                              ac_power_matching_pending=True, lifetime_pending=True,
                              sld_pending=True, layout_pending=True, report_pending=True),
        approval_errors=approval_errors, blocked_reasons=blocked_reasons,
    )
    # Re-read both catalogue reviews and configuration reviews before returning.
    # This does not claim an atomic release; it detects changes during this build.
    for detail, _, _ in selected:
        current = revision_service.inspect(detail['revision_id'])
        if _revision_identity(current) != _revision_identity(detail):
            raise ValueError('A product revision or review changed during composition building; reload')
    for relation in relations.values():
        current = variant_service.inspect(relation['relation_id'])
        keys = ('relation_sha256', 'parent_revision_id', 'child_revision_id', 'status',
                'stale', 'candidate_review_current')
        if any(current.get(key) != relation.get(key) for key in keys):
            raise ValueError('A parent-child relation or review changed during composition building; reload')
    manifest['manifest_sha256'] = dc_composition_manifest_sha256(manifest)
    return manifest
