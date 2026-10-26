"""Planning-only discharge checks for an explicit, signed DC composition.

The requested DC duty is supplied by the caller. This module does not size PCS,
transformers, charge duty or lifetime guarantees, and does not alter the frozen
sizing pipeline. Proportional dispatch is an explicit comparison policy rather
than an inferred operating capability or a proposed electrical interconnection.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter

from calb_sizing_tool.common.dc_configuration_identity import is_20ft_container_type
from calb_sizing_tool.services.dc_composition_manifest_service import (
    MAX_MANIFEST_UNITS, dc_composition_manifest_sha256,
)


POLICY = 'proportional_to_raw_dc_nameplate_energy'


def _digest(value):
    try:
        data = json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('The assessment contract must contain finite JSON data') from exc
    return hashlib.sha256(data).hexdigest()


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f'{label} must be nonempty, trimmed text')
    return value


def _number(value, label, *, unknown=False):
    if value is None and unknown:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label} must be finite numeric data')
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f'{label} must be finite numeric data') from exc
    if not math.isfinite(result):
        raise ValueError(f'{label} must be finite numeric data')
    if unknown and result == 0:
        return None  # Historic catalogue zero means unconfirmed, not no capacity.
    if result <= 0:
        raise ValueError(f'{label} must be positive')
    return result


def _whole(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{label} must be a positive whole number')
    return value


def _close(left, right):
    # Round-off tolerance only, not engineering headroom or rating relaxation.
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=0)


def _equal_number(value, expected, label):
    if not _close(_number(value, label), expected):
        raise ValueError(f'{label} differs from its source or physical register')


def _equal_rating(value, expected, label):
    parsed = _number(value, label, unknown=True)
    if (parsed is None) != (expected is None) or (parsed is not None and not _close(parsed, expected)):
        raise ValueError(f'{label} differs from its source')


def _sum(values, label):
    try:
        result = math.fsum(values)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f'{label} must remain finite') from exc
    if not math.isfinite(result):
        raise ValueError(f'{label} must remain finite')
    return result


def _rows(value, label, *, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f'{label} must be a list of objects')
    return value


def _sources(manifest, product_revisions):
    if not isinstance(product_revisions, dict):
        raise ValueError('Product revisions must be keyed by revision identity')
    lines = _rows(manifest.get('bom'), 'Composition BOM')
    sources, product_ids, line_ids, cell_ids = {}, set(), set(), set()
    for line in lines:
        revision_id = _text(line.get('revision_id'), 'Revision identity')
        if revision_id in sources:
            raise ValueError('BOM revision identities must be unique')
        detail = product_revisions.get(revision_id)
        if not isinstance(detail, dict) or detail.get('revision_id') != revision_id:
            raise ValueError('Every BOM revision requires its exact source review')
        if detail.get('stale') is not False or detail.get('status') not in ('draft', 'parameter_review', 'candidate_only'):
            raise ValueError('Stale, retired or unknown product reviews cannot be assessed')
        if not isinstance(detail.get('candidate_review_current'), bool):
            raise ValueError('The current product review state must be explicit')
        if detail['candidate_review_current'] and detail['status'] != 'candidate_only':
            raise ValueError('A current candidate review must have candidate_only status')
        payload = detail.get('snapshot')
        if not isinstance(payload, dict) or not isinstance(payload.get('product'), dict):
            raise ValueError('Source revision snapshot is incomplete')
        if detail.get('sha256') != _digest(payload) or line.get('revision_sha256') != detail['sha256']:
            raise ValueError('Source revision snapshot digest does not match the composition')
        product, cell = payload['product'], payload.get('cell')
        for key, product_key in (('product_id', 'product_dc_block_id'), ('product_code', 'block_code'),
                                 ('product_cell_id', 'product_cell_id')):
            if _text(line.get(key), key) != _text(product.get(product_key), product_key):
                raise ValueError('BOM product identity differs from its source revision')
        product_id = product['product_dc_block_id']
        if product_id in product_ids:
            raise ValueError('Multiple revisions of one product cannot share a composition')
        product_ids.add(product_id)
        cell_ids.add(product['product_cell_id'])
        if (not isinstance(cell, dict) or cell.get('product_cell_id') != product['product_cell_id']):
            raise ValueError('The exact linked cell snapshot is required')
        capacity = _number(cell.get('nominal_capacity_ah'), 'Cell nominal capacity', unknown=True)
        if capacity is not None and capacity != 314:
            raise ValueError('This composition requires the exact 314Ah cell family')
        if product.get('block_form') != 'container' or not is_20ft_container_type(product.get('container_type')):
            raise ValueError('This composition requires explicit 20ft container products')
        if _whole(product.get('cells_in_series'), 'Series cell count') != 416:
            raise ValueError('This composition requires the 416S family')
        strings = _whole(product.get('strings_in_parallel'), 'Parallel string count')
        if strings not in (8, 10, 12) or line.get('strings_in_parallel') != strings or line.get('cells_in_series') != 416:
            raise ValueError('BOM string and series counts differ from the supported source family')
        role = 'main' if strings == 12 else 'tail'
        if line.get('role') != role:
            raise ValueError('BOM main and tail roles are inconsistent')
        line_id = _whole(line.get('line_number'), 'BOM line number')
        if line_id in line_ids:
            raise ValueError('BOM line numbers must be unique')
        line_ids.add(line_id)
        quantity = _whole(line.get('quantity'), 'BOM quantity')
        energy = _number(product.get('gross_energy_mwh'), 'Product gross energy')
        power = _number(product.get('nominal_power_kw'), 'Product nominal power', unknown=True)
        current = _number(product.get('max_current_a'), 'Product maximum current', unknown=True)
        vmin = _number(product.get('voltage_min_v'), 'Product minimum voltage', unknown=True)
        vmax = _number(product.get('voltage_max_v'), 'Product maximum voltage', unknown=True)
        if vmin is not None and vmax is not None and vmin >= vmax:
            raise ValueError('Product voltage window must be ordered')
        rate = _number(product.get('max_c_rate'), 'Product maximum C-rate', unknown=True)
        _equal_number(line.get('unit_gross_energy_mwh'), energy, 'BOM unit energy')
        _equal_number(line.get('subtotal_gross_energy_mwh'), energy * quantity, 'BOM subtotal energy')
        _equal_rating(line.get('unit_nominal_power_kw'), power, 'BOM nominal power')
        _equal_rating(line.get('unit_max_current_a'), current, 'BOM maximum current')
        sources[revision_id] = dict(detail=detail, line=line, quantity=quantity, energy=energy,
                                    power=power, current=current, vmin=vmin, vmax=vmax, rate=rate,
                                    capacity=capacity, strings=strings)
    if len(cell_ids) != 1:
        raise ValueError('All products must share one exact cell identity')
    parents = [key for key, row in sources.items() if row['strings'] == 12]
    if len(parents) != 1:
        raise ValueError('Exactly one 12-string parent revision is required')
    scope = manifest.get('scope')
    if not isinstance(scope, dict):
        raise ValueError('Composition use scope is required')
    children = [row for row in sources.values() if row['strings'] != 12]
    if children:
        if (scope.get('use_scope') != 'special_scenario_only'
                or scope.get('allow_special_configurations') is not True):
            raise ValueError('Child configurations require explicit special-scenario opt-in')
        _text(scope.get('special_reason'), 'Special-scenario reason')
        for row in children:
            if row['line'].get('parent_revision_id') != parents[0]:
                raise ValueError('Child configuration parent differs from the selected parent')
            _text(row['line'].get('relation_id'), 'Child relation identity')
            _text(row['line'].get('relation_sha256'), 'Child relation digest')
    elif scope.get('use_scope') != 'standard_parent_only':
        raise ValueError('Parent-only composition scope is inconsistent')
    return sources


def _physical_register(manifest, sources):
    units = _rows(manifest.get('physical_units'), 'Physical container register')
    if len(units) > MAX_MANIFEST_UNITS:
        raise ValueError('Physical container register exceeds the local planning limit')
    counts, identifiers = Counter(), set()
    for unit in units:
        unit_id = _text(unit.get('unit_id'), 'Physical container identity')
        if unit_id in identifiers:
            raise ValueError('Physical container identities must be unique')
        identifiers.add(unit_id)
        revision_id = unit.get('revision_id')
        if revision_id not in sources:
            raise ValueError('Physical container references an unselected revision')
        source = sources[revision_id]
        _whole(unit.get('line_number'), 'Physical container line number')
        _whole(unit.get('strings_in_parallel'), 'Physical container string count')
        for key in ('line_number', 'role', 'product_code', 'revision_sha256', 'strings_in_parallel'):
            if unit.get(key) != source['line'].get(key):
                raise ValueError('Physical container identity differs from the BOM')
        _equal_number(unit.get('gross_energy_mwh'), source['energy'], 'Physical container energy')
        domain_ids = unit.get('electrical_domain_ids')
        if not isinstance(domain_ids, list) or any(not isinstance(value, str) or not value.strip() for value in domain_ids):
            raise ValueError('Physical container output domain register must be explicit')
        if len(domain_ids) != len(set(domain_ids)):
            raise ValueError('Physical container output domain identities must be unique')
        counts[revision_id] += 1
    if counts != Counter({key: row['quantity'] for key, row in sources.items()}):
        raise ValueError('Physical container quantities differ from the BOM')
    if _whole(manifest.get('total_container_count'), 'Total container count') != len(units):
        raise ValueError('Total container count differs from the physical register')
    total_energy = _sum((sources[unit['revision_id']]['energy'] for unit in units), 'Total energy')
    _equal_number(manifest.get('total_gross_energy_mwh'), total_energy, 'Total composition energy')
    aggregate = (None if any(row['power'] is None for row in sources.values()) else
                 _sum((row['power'] * row['quantity'] for row in sources.values()), 'Aggregate power'))
    _equal_rating(manifest.get('aggregate_nominal_power_kw'), aggregate, 'Aggregate nominal power')
    domains = _rows(manifest.get('electrical_domains'), 'Electrical output domains', nonempty=False)
    domain_map, unit_map = {}, {unit['unit_id']: unit for unit in units}
    for domain in domains:
        domain_id = _text(domain.get('domain_id'), 'Electrical output domain identity')
        if domain_id in domain_map:
            raise ValueError('Electrical output domain identities must be unique')
        owner = unit_map.get(domain.get('unit_id'))
        if owner is None or domain.get('revision_id') != owner['revision_id']:
            raise ValueError('Electrical output domain owner or source revision is inconsistent')
        if domain_id not in owner['electrical_domain_ids']:
            raise ValueError('Electrical output domain is not declared by its physical owner')
        _text(domain.get('domain_label'), 'Electrical output domain label')
        _text(domain.get('evidence_ref'), 'Electrical output domain evidence')
        _whole(domain.get('strings'), 'Electrical output domain string count')
        _number(domain.get('gross_energy_mwh'), 'Electrical output domain energy')
        _number(domain.get('nominal_power_kw'), 'Electrical output domain nominal power', unknown=True)
        _number(domain.get('max_current_a'), 'Electrical output domain maximum current', unknown=True)
        domain_map[domain_id] = domain
    claimed = [value for unit in units for value in unit['electrical_domain_ids']]
    if len(claimed) != len(set(claimed)) or set(claimed) != set(domain_map):
        raise ValueError('Output domain identities are missing, reused or unclaimed')
    for unit in units:
        partition = [domain_map[key] for key in unit['electrical_domain_ids']]
        if not partition:
            continue
        if len({row['domain_label'].casefold() for row in partition}) != len(partition):
            raise ValueError('Output domain labels must be unique within each container')
        if sum(row['strings'] for row in partition) != unit['strings_in_parallel']:
            raise ValueError('Output domain strings must partition the complete physical container')
        energy = _sum((row['gross_energy_mwh'] for row in partition), 'Output domain energy')
        if not math.isclose(energy, unit['gross_energy_mwh'], rel_tol=0, abs_tol=1e-6):
            raise ValueError('Output domain energies must partition the complete physical container')
    # C2a partitions are attached to a revision and expanded per box. Rehashing
    # one box with different or absent ports must not invent another topology
    # under the same product-revision identity.
    partition_by_revision = {}
    for unit in units:
        partition = [{key: value for key, value in domain_map[domain_id].items()
                      if key not in ('domain_id', 'unit_id')}
                     for domain_id in unit['electrical_domain_ids']]
        signature = _digest(partition)
        previous = partition_by_revision.setdefault(unit['revision_id'], signature)
        if previous != signature:
            raise ValueError('Output partitions differ between containers of the same source revision')
    gates = manifest.get('capability_gates')
    if not isinstance(gates, dict) or gates.get('energy_bom_validated') is not True:
        raise ValueError('A validated energy BOM is required')
    if gates.get('output_domains_defined') is not all(unit['electrical_domain_ids'] for unit in units):
        raise ValueError('Output domain completeness gate contradicts the physical register')
    return units, domain_map, total_energy


def _limits(identifier, requested_kw, energy, source, power, current, *, check_rate):
    errors, pending, warnings = [], [], []
    required_current = (None if source['vmin'] is None else
                        _number(requested_kw * 1000 / source['vmin'], 'Required current'))
    for label, value in (('nominal power rating', power), ('maximum current rating', current),
                         ('minimum operating voltage', source['vmin']), ('maximum operating voltage', source['vmax'])):
        if value is None:
            pending.append(f'{identifier}: confirmed {label} is missing.')
    if power is not None and requested_kw > power and not _close(requested_kw, power):
        errors.append(f'{identifier}: requested discharge {requested_kw:.6g} kW exceeds declared {power:.6g} kW.')
    if current is not None and required_current is not None and required_current > current and not _close(required_current, current):
        errors.append(f'{identifier}: required current at minimum voltage {required_current:.6g} A exceeds declared {current:.6g} A.')
    rate = requested_kw / (energy * 1000)
    if check_rate:
        if source['rate'] is None:
            warnings.append(f'{identifier}: maximum C-rate is unconfirmed; only declared power/current limits can be checked.')
        elif rate > source['rate'] and not _close(rate, source['rate']):
            errors.append(f'{identifier}: requested discharge rate {rate:.6g} exceeds declared {source["rate"]:.6g}.')
    status = ('fails_declared_dc_limits' if errors else
              'pending_electrical_evidence' if pending else 'passes_declared_dc_limits')
    return dict(requested_discharge_kw=requested_kw, required_current_a_at_voltage_min=required_current,
                voltage_min_v=source['vmin'], voltage_max_v=source['vmax'],
                declared_nominal_power_kw=power, declared_max_current_a=current,
                requested_discharge_rate=rate,
                declared_max_c_rate=source['rate'] if check_rate else None,
                limit_status=status, errors=errors, pending_evidence=pending, warnings=warnings)


def assess_proportional_dc_dispatch(manifest: dict, product_revisions: dict, *, dc_power_required_mw: float) -> dict:
    """Check externally supplied discharge duty against each declared DC limit.

    Missing ratings, voltage or explicit output partitions remain pending. A
    draft product can be diagnosed but never passes the overall evidence gate.
    Each independent domain is checked as well as its physical box; summing
    port ratings cannot override a lower box rating. A relative tolerance of
    1e-9 is used only for floating-point equality, with no engineering margin.
    """
    if not isinstance(manifest, dict):
        raise ValueError('An explicit DC composition manifest is required')
    if (type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
            or manifest.get('contract_type') != 'dc_composition_planning'
            or manifest.get('comparison_only') is not True or manifest.get('downstream_ready') is not False):
        raise ValueError('Only the schema-1 planning-only DC composition contract is supported')
    if manifest.get('energy_boundary') != 'DC gross nameplate energy at BOL':
        raise ValueError('The explicit DC gross nameplate energy boundary is required')
    try:
        digest = dc_composition_manifest_sha256(manifest)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('The manifest must contain finite JSON data') from exc
    if manifest.get('manifest_sha256') != digest:
        raise ValueError('DC composition manifest digest does not match its content')
    required_mw = _number(dc_power_required_mw, 'Requested DC discharge power')
    required_kw = _number(required_mw * 1000, 'Requested DC discharge power in kW')
    sources = _sources(manifest, product_revisions)
    units, domains, total_energy = _physical_register(manifest, sources)
    errors, pending, warnings, unit_rows, domain_rows, conservation_rows = [], [], [], [], [], []
    if manifest['capability_gates'].get('product_reviews') is not True:
        pending.append('Current product and parent-child configuration reviews are incomplete.')
    for revision_id, source in sources.items():
        if source['detail']['candidate_review_current'] is not True:
            pending.append(f'{source["line"]["product_code"]}: current product parameter review is incomplete.')
        if source['capacity'] is None:
            pending.append(f'{source["line"]["product_code"]}: confirmed 314Ah cell capacity is missing.')
    for unit in units:
        source = sources[unit['revision_id']]
        requested_kw = _number(required_kw * (source['energy'] / total_energy), 'Allocated container discharge power')
        check = _limits(unit['unit_id'], requested_kw, source['energy'], source,
                        source['power'], source['current'], check_rate=True)
        row = dict(unit_id=unit['unit_id'], revision_id=unit['revision_id'],
                   product_code=unit['product_code'], strings_in_parallel=unit['strings_in_parallel'],
                   gross_energy_mwh=unit['gross_energy_mwh'], **check)
        unit_rows.append(row)
        errors.extend(check['errors']); pending.extend(check['pending_evidence']); warnings.extend(check['warnings'])
        assigned = []
        for domain_id in unit['electrical_domain_ids']:
            domain = domains[domain_id]
            duty = _number(required_kw * (domain['gross_energy_mwh'] / total_energy), 'Allocated domain discharge power')
            check = _limits(domain_id, duty, domain['gross_energy_mwh'], source,
                            _number(domain.get('nominal_power_kw'), 'Domain power rating', unknown=True),
                            _number(domain.get('max_current_a'), 'Domain current rating', unknown=True), check_rate=False)
            domain_rows.append(dict(domain_id=domain_id, unit_id=unit['unit_id'], revision_id=unit['revision_id'],
                                    domain_label=domain['domain_label'], strings=domain['strings'],
                                    gross_energy_mwh=domain['gross_energy_mwh'], evidence_ref=domain['evidence_ref'], **check))
            assigned.append(duty)
            errors.extend(check['errors']); pending.extend(check['pending_evidence'])
        domain_total = _sum(assigned, 'Domain discharge duty') if assigned else None
        if domain_total is None:
            pending.append(f'{unit["unit_id"]}: explicit output partitions are missing; no ports or PCS count were inferred.')
        elif not _close(domain_total, requested_kw):
            # A partition accepted at rounded energy precision is not silently
            # renormalized; proportional power must itself conserve duty.
            raise ValueError('Output domain discharge duty does not conserve its physical container duty')
        conservation_rows.append(dict(unit_id=unit['unit_id'], unit_discharge_kw=requested_kw,
                                      total_domain_discharge_kw=domain_total,
                                      domain_duty_conserved=None if domain_total is None else True))
    unit_total = _sum((row['requested_discharge_kw'] for row in unit_rows), 'Total container discharge duty')
    if not _close(unit_total, required_kw):
        raise ValueError('Physical container discharge duty does not conserve the requested DC duty')
    all_domains_defined = all(row['total_domain_discharge_kw'] is not None for row in conservation_rows)
    domain_total = (_sum((row['requested_discharge_kw'] for row in domain_rows), 'Total output domain duty')
                    if all_domains_defined else None)
    source_hashes = {key: row['detail']['sha256'] for key, row in sources.items()}
    assessment_input = dict(schema_version=1, policy=POLICY, manifest_sha256=digest,
                            dc_power_required_mw=required_mw, source_revision_sha256=source_hashes)
    return dict(schema_version=1, contract_type='dc_composition_discharge_assessment', policy=POLICY,
                comparison_only=True, downstream_ready=False, ac_power_matching_pending=True,
                status=('fails_declared_dc_limits' if errors else 'pending_electrical_evidence' if pending
                        else 'passes_declared_dc_limits'),
                dc_power_required_mw=required_mw, manifest_sha256=digest,
                assessment_sha256=_digest(assessment_input), source_revision_sha256=source_hashes,
                product_review_current=all(row['detail']['candidate_review_current'] for row in sources.values()),
                unit_duties=unit_rows, domain_duties=domain_rows,
                conservation=dict(requested_dc_discharge_kw=required_kw, total_unit_discharge_kw=unit_total,
                                  total_domain_discharge_kw=domain_total, unit_duty_conserved=True,
                                  all_output_partitions_defined=all_domains_defined, by_unit=conservation_rows),
                errors=errors, pending_evidence=list(dict.fromkeys(pending)), warnings=list(dict.fromkeys(warnings)),
                evidence_boundary='Declared DC discharge ratings only; no PCS, AC, charge, lifetime or certification acceptance.',
                floating_point_relative_tolerance=1e-9)
