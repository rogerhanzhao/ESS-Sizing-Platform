"""Local D1b discharge-reference checks using reviewed component revisions.

This adapter consumes the signed DC duty and existing Stage1 efficiency chain.
It does not select equipment counts, alter frozen sizing, adopt a run or release
drawings. Terminal voltage drop and full operating envelopes remain separate.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math

from calb_sizing_tool.schemas.ac_equipment_capability import DischargeDutyBasis, EquipmentCapabilityPackage
from calb_sizing_tool.schemas.dc_ac_allocation import DcAcAllocation
from calb_sizing_tool.services.dc_ac_allocation_service import assess_dc_ac_allocation
from calb_sizing_tool.services.dc_ac_allocation_source_service import comparison_json, revalidate_allocation_source
from calb_sizing_tool.services.dc_product_comparison_service import package_sha256


def output_partition_sha256(manifest: dict, revision_id: str) -> str:
    """Identity of explicit revision-level outputs, independent of unit count."""
    unit = next(row for row in manifest['physical_units'] if row['revision_id'] == revision_id)
    rows = [{key: value for key, value in row.items() if key not in ('domain_id', 'unit_id', 'revision_id')}
            for row in manifest['electrical_domains'] if row['unit_id'] == unit['unit_id']]
    return package_sha256(dict(revision_sha256=unit['revision_sha256'], output_partitions=rows))


def _finite(value, label, *, fraction=False):
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and value > 0 and (not fraction or value <= 1))
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'{label} must be positive finite numeric data' + (' within (0, 1]' if fraction else ''))
    return float(value)


def _sum(values):
    try:
        total = math.fsum(values)
    except OverflowError as exc:
        raise ValueError('The declared discharge reference exceeds finite numeric range') from exc
    if not math.isfinite(total):
        raise ValueError('The declared discharge reference exceeds finite numeric range')
    return total


class _Checks:
    def __init__(self):
        self.rows = []

    def add(self, kind, identity, code, status, message, *, required=None, declared=None, unit=None):
        self.rows.append(dict(equipment_kind=kind, equipment_id=identity, check=code, status=status,
                             required=required, declared=declared, unit=unit, message=message))

    def maximum(self, kind, identity, code, required, declared, unit):
        if required is None or declared is None:
            self.add(kind, identity, code, 'pending', f'{identity}: {code.replace("_", " ")} needs confirmed data.',
                     required=required, declared=declared, unit=unit)
            return
        passed = required <= declared or math.isclose(required, declared, rel_tol=1e-9, abs_tol=0)
        self.add(kind, identity, code, 'pass' if passed else 'fail',
                 f'{identity}: {code.replace("_", " ")} ' + ('is within the declared limit.' if passed else 'exceeds the declared limit.'),
                 required=required, declared=declared, unit=unit)

    def equal(self, kind, identity, code, required, declared, unit):
        if required is None or declared is None:
            self.add(kind, identity, code, 'pending', f'{identity}: {code.replace("_", " ")} needs confirmed data.',
                     required=required, declared=declared, unit=unit)
        else:
            passed = math.isclose(required, declared, rel_tol=1e-9, abs_tol=0)
            self.add(kind, identity, code, 'pass' if passed else 'fail',
                     f'{identity}: {code.replace("_", " ")} ' + ('matches.' if passed else 'does not match.'),
                     required=required, declared=declared, unit=unit)

    def minimum(self, kind, identity, code, required, declared, unit):
        if required is None or declared is None:
            self.add(kind, identity, code, 'pending', f'{identity}: {code.replace("_", " ")} needs confirmed data.',
                     required=required, declared=declared, unit=unit)
        else:
            passed = required >= declared or math.isclose(required, declared, rel_tol=1e-9, abs_tol=0)
            self.add(kind, identity, code, 'pass' if passed else 'fail',
                     f'{identity}: {code.replace("_", " ")} ' + ('is above the declared minimum.' if passed else 'is below the declared minimum.'),
                     required=required, declared=declared, unit=unit)

    def window(self, identity, label, required_min, required_max, declared_min, declared_max):
        # The equipment window must CONTAIN the whole source product window.
        self.minimum('pcs', identity, label + '_minimum_voltage', required_min, declared_min, 'V')
        self.maximum('pcs', identity, label + '_maximum_voltage', required_max, declared_max, 'V')

    def apparent(self, kind, identity, code, active_kw, apparent_kva, declared_kva):
        self.maximum(kind, identity, code, apparent_kva, declared_kva, 'kVA')
        # Unknown PF does not supply an actual S value. Nevertheless S >= |P|:
        # a known rating below that minimum is impossible at every valid PF.
        if (apparent_kva is None and declared_kva is not None and active_kw > declared_kva
                and not math.isclose(active_kw, declared_kva, rel_tol=1e-9, abs_tol=0)):
            self.add(kind, identity, code + '_active_lower_bound', 'fail',
                f'{identity}: the active-power lower bound already exceeds the declared apparent-power rating; power factor remains unknown.',
                required=active_kw, declared=declared_kva, unit='kVA lower bound')


def _conditions(checks, kind, identity, package, duty, frequency):
    condition = package.conditions
    temperature = duty.ambient_temperature_c
    lower, upper = condition.temperature_min_c, condition.temperature_max_c
    outside_known = temperature is not None and (
        lower is not None and temperature < lower or upper is not None and temperature > upper)
    incomplete = lower is None or upper is None
    if outside_known:
        checks.add(kind, identity, 'equipment_ambient_temperature', 'fail',
                   f'{identity}: equipment ambient temperature is outside a known declared rating limit.',
                   required=temperature, declared=[lower, upper], unit='degC')
        if incomplete:
            checks.add(kind, identity, 'equipment_temperature_range_completeness', 'pending',
                       f'{identity}: the other temperature range endpoint remains unknown; it does not cancel the known exceedance.')
    elif temperature is None or incomplete:
        checks.add(kind, identity, 'equipment_ambient_temperature', 'pending',
                   f'{identity}: equipment ambient temperature and its rated range must be specified independently of cell-curve temperature.')
    else:
        passed = condition.temperature_min_c <= temperature <= condition.temperature_max_c
        checks.add(kind, identity, 'equipment_ambient_temperature', 'pass' if passed else 'fail',
                   f'{identity}: equipment ambient temperature ' + ('is inside the declared rating range.' if passed else 'is outside the declared rating range.'),
                   required=temperature, declared=[condition.temperature_min_c, condition.temperature_max_c], unit='degC')
    checks.equal(kind, identity, 'project_frequency', frequency, condition.frequency_hz, 'Hz')


def _equipment_checks(allocation, source, packages, duty, checks):
    """Pure numerical reference checks after source and registry validation."""
    manifest, dispatch, stage1 = source['manifest'], source['dispatch'], source['stage1']
    cable_eff = _finite(stage1.get('eff_dc_cables_frac'), 'Signed DC cable efficiency', fraction=True)
    pcs_eff = _finite(stage1.get('eff_pcs_frac'), 'Signed PCS efficiency', fraction=True)
    downstream_eff = math.prod(_finite(stage1.get(key), 'Signed downstream efficiency', fraction=True)
        for key in ('eff_mvt_frac', 'eff_ac_cables_sw_rmu_frac', 'eff_hvt_others_frac'))
    frequency = _finite(source['case_input'].get('poi_frequency_hz'), 'Signed project frequency')
    domain_duty = {row['domain_id']: row for row in dispatch['domain_duties']}
    domains = {row['domain_id']: row for row in manifest['electrical_domains']}
    revision_sha = {row['revision_id']: row['revision_sha256'] for row in manifest['bom']}
    partition_hashes = {key: output_partition_sha256(manifest, key) for key in revision_sha}
    connections = defaultdict(list)
    port_links = defaultdict(list)
    for link in allocation.dc_connections:
        connections[link.pcs_id].append(link)
        port_links[link.pcs_id, link.port_id].append(link)
    declared_ports = defaultdict(list)
    for port in allocation.input_ports:
        declared_ports[port.pcs_id].append(port)
    pcs_rows, port_rows = [], []
    for instance in allocation.pcs_instances:
        identity = instance.pcs_id
        package = packages.get(('pcs', identity))
        capability = package.pcs if package else None
        source_kw = _sum(domain_duty[link.domain_id]['requested_discharge_kw'] for link in connections[identity])
        input_kw, ac_kw = source_kw * cable_eff, source_kw * cable_eff * pcs_eff
        kva = ac_kw / duty.power_factor_abs if duty.power_factor_abs is not None else None
        if kva is not None and not math.isfinite(kva):
            raise ValueError('The supplied power factor produces nonfinite apparent power')
        pcs_rows.append(dict(pcs_id=identity, ac_block_id=instance.ac_block_id,
            upstream_dc_reference_kw=source_kw, pcs_input_reference_kw=input_kw,
            pcs_ac_reference_kw=ac_kw, pcs_ac_reference_kva=kva,
            declared_ac_kw=capability.ac_discharge_power_kw if capability else None,
            declared_ac_kva=capability.ac_apparent_power_kva if capability else None))
        if package:
            _conditions(checks, 'pcs', identity, package, duty, frequency)
        checks.maximum('pcs', identity, 'pcs_dc_input_power', input_kw, capability.dc_discharge_power_kw if capability else None, 'kW')
        checks.maximum('pcs', identity, 'pcs_ac_active_power', ac_kw, capability.ac_discharge_power_kw if capability else None, 'kW')
        checks.apparent('pcs', identity, 'pcs_ac_apparent_power', ac_kw, kva, capability.ac_apparent_power_kva if capability else None)
        currents = [domain_duty[link.domain_id]['required_current_a_at_voltage_min'] for link in connections[identity]]
        current = _sum(currents) if all(value is not None for value in currents) else None
        if not duty.passive_dc_path_confirmed or not capability or capability.aggregate_current_basis != 'sum_of_port_currents':
            checks.add('pcs', identity, 'aggregate_dc_current', 'pending',
                       f'{identity}: a passive DC path and the manufacturer total-current definition are required before summing port currents.')
        else:
            checks.maximum('pcs', identity, 'aggregate_dc_current_reference', current, capability.continuous_dc_current_a, 'A')
        allowed_ports = {row.port_id: row for row in capability.ports} if capability else {}
        bus_links, model_to_declared, declared_to_model = defaultdict(list), defaultdict(set), defaultdict(set)
        for port in declared_ports[identity]:
            label = f'{identity}/{port.port_id}'
            cap = allowed_ports.get(port.port_id)
            links = port_links[identity, port.port_id]
            power = _sum(domain_duty[link.domain_id]['requested_discharge_kw'] for link in links) * cable_eff
            port_currents = [domain_duty[link.domain_id]['required_current_a_at_voltage_min'] for link in links]
            port_current = _sum(port_currents) if all(value is not None for value in port_currents) else None
            port_rows.append(dict(pcs_id=identity, port_id=port.port_id, dc_bus_id=port.dc_bus_id,
                pcs_input_reference_kw=power, source_current_reference_a=port_current,
                declared_input_kw=cap.discharge_power_kw if cap else None,
                declared_current_a=cap.continuous_current_a if cap else None))
            if capability and cap is None:
                checks.add('pcs', label, 'input_port_identity', 'fail', f'{label}: input port is absent from the reviewed PCS capability.')
            checks.maximum('pcs', label, 'port_dc_input_power', power, cap.discharge_power_kw if cap else None, 'kW')
            if duty.passive_dc_path_confirmed:
                checks.maximum('pcs', label, 'port_dc_current_reference', port_current, cap.continuous_current_a if cap else None, 'A')
            else:
                checks.add('pcs', label, 'port_dc_current_reference', 'pending', f'{label}: passive DC path evidence is required for the source-current reference screen.')
            for link in links:
                item = domain_duty[link.domain_id]
                checks.window(label + '/' + link.domain_id, 'port_nameplate', item['voltage_min_v'], item['voltage_max_v'],
                              cap.voltage_min_v if cap else None, cap.voltage_max_v if cap else None)
                checks.window(label + '/' + link.domain_id, 'pcs_nameplate', item['voltage_min_v'], item['voltage_max_v'],
                              capability.dc_voltage_min_v if capability else None, capability.dc_voltage_max_v if capability else None)
            if cap:
                model_to_declared[cap.dc_bus_group].add(port.dc_bus_id)
                declared_to_model[port.dc_bus_id].add(cap.dc_bus_group)
                bus_links[cap.dc_bus_group].extend(links)
            checks.add('pcs', label, 'terminal_voltage_drop', 'pending',
                       f'{label}: nameplate window screening does not validate PCS terminal voltage after cable drop.')
        if any(len(values) > 1 for values in [*model_to_declared.values(), *declared_to_model.values()]):
            checks.add('pcs', identity, 'input_bus_topology', 'fail', f'{identity}: declared DC buses conflict with the reviewed independent/common input arrangement.')
        elif capability:
            checks.add('pcs', identity, 'input_bus_topology', 'pass', f'{identity}: used input-port bus groups match the reviewed arrangement.')
        if capability:
            buses = {row.dc_bus_group: row for row in capability.dc_buses}
            for group, links in bus_links.items():
                if len(links) <= 1:
                    continue
                permission = buses[group]
                bus_label = f'{identity}/{group}'
                checks.maximum('pcs', bus_label, 'parallel_domain_count', len(links), permission.max_parallel_domains, 'domains')
                if not permission.parallel_evidence_ref:
                    checks.add('pcs', bus_label, 'parallel_applicability', 'pending', f'{bus_label}: parallel applicability evidence is missing.')
                for link in links:
                    revision = domains[link.domain_id]['revision_id']
                    for code, needed, approved in (
                        ('parallel_product_revision', revision_sha[revision], permission.compatible_revision_sha256),
                        ('parallel_output_partition', partition_hashes[revision], permission.compatible_output_partition_sha256)):
                        status = 'pending' if not approved else 'pass' if needed in approved else 'fail'
                        checks.add('pcs', bus_label, code, status,
                            f'{bus_label}: {code.replace("_", " ")} ' + ('is covered.' if status == 'pass' else 'is not covered by current evidence.'))
    pcs_by_id = {row['pcs_id']: row for row in pcs_rows}
    winding_links = defaultdict(list)
    for link in allocation.lv_connections:
        winding_links[link.transformer_id, link.winding_id].append(link.pcs_id)
    winding_rows, transformer_rows = [], []
    for instance in allocation.transformer_instances:
        identity = instance.transformer_id
        package = packages.get(('transformer', identity))
        cap = package.transformer if package else None
        windings = {row.winding_id: row for row in cap.windings} if cap else {}
        if package:
            _conditions(checks, 'transformer', identity, package, duty, frequency)
        checks.equal('transformer', identity, 'mv_bus_voltage', duty.mv_bus_voltage_kv, cap.hv_voltage_kv if cap else None, 'kV')
        checks.add('transformer', identity, 'vector_group_evidence', 'pass' if cap and cap.vector_group else 'pending',
                   f'{identity}: ' + ('reviewed vector group recorded; system suitability remains subject to design.' if cap and cap.vector_group else 'reviewed vector group is missing.'))
        used = []
        for winding in allocation.lv_windings:
            if winding.transformer_id != identity:
                continue
            label = f'{identity}/{winding.winding_id}'
            rated = windings.get(winding.winding_id)
            ids = winding_links[identity, winding.winding_id]
            active = _sum(pcs_by_id[key]['pcs_ac_reference_kw'] for key in ids)
            apparent = (_sum(pcs_by_id[key]['pcs_ac_reference_kva'] for key in ids)
                        if all(pcs_by_id[key]['pcs_ac_reference_kva'] is not None for key in ids) else None)
            winding_rows.append(dict(transformer_id=identity, winding_id=winding.winding_id, pcs_ids=ids,
                lv_ac_reference_kw=active, lv_ac_reference_kva=apparent,
                declared_winding_kva=rated.continuous_kva if rated else None))
            used.append(winding_rows[-1])
            if cap and rated is None:
                checks.add('transformer', label, 'lv_winding_identity', 'fail', f'{label}: winding is absent from the reviewed transformer capability.')
            checks.apparent('transformer', label, 'lv_winding_apparent_power', active, apparent, rated.continuous_kva if rated else None)
            for key in ids:
                pcs_package = packages.get(('pcs', key))
                checks.equal('transformer', label + '/' + key, 'pcs_to_lv_voltage',
                    pcs_package.pcs.ac_voltage_v if pcs_package else None, rated.voltage_v if rated else None, 'V')
        apparent = (_sum(row['lv_ac_reference_kva'] for row in used)
                    if all(row['lv_ac_reference_kva'] is not None for row in used) else None)
        transformer_rows.append(dict(transformer_id=identity, ac_block_id=instance.ac_block_id,
            lv_ac_reference_kw=_sum(row['lv_ac_reference_kw'] for row in used),
            lv_ac_reference_kva=apparent, declared_total_kva=cap.total_kva if cap else None))
        checks.apparent('transformer', identity, 'total_transformer_apparent_power',
                        transformer_rows[-1]['lv_ac_reference_kw'], apparent, cap.total_kva if cap else None)
    total_ac = _sum(row['pcs_ac_reference_kw'] for row in pcs_rows)
    poi = total_ac * downstream_eff
    requested_poi = _finite(stage1.get('poi_power_req_mw'), 'Signed POI power') * 1000
    if not math.isfinite(poi) or not math.isclose(poi, requested_poi, rel_tol=1e-9, abs_tol=0):
        raise ValueError('The discharge reference does not close the signed Stage1 efficiency chain')
    return dict(port_duties=port_rows, pcs_duties=pcs_rows, winding_duties=winding_rows,
        transformer_duties=transformer_rows,
        power_boundaries=dict(upstream_dc_reference_kw=dispatch['dc_power_required_mw'] * 1000,
            pcs_input_reference_kw=_sum(row['pcs_input_reference_kw'] for row in pcs_rows),
            pcs_ac_reference_kw=total_ac, poi_reference_kw=poi,
            dc_cable_efficiency_frac=cable_eff, pcs_efficiency_frac=pcs_eff,
            downstream_efficiency_frac=downstream_eff, signed_poi_chain_conserved=True))


def validate_equipment_source_boundary(comparison):
    """Shared AC-reference prerequisite; call only after source validation."""
    # Stage1 also supports a DC-side POI. Its loss-free reference is not an AC
    # POI duty, even when the arithmetic closes. Never infer the boundary from
    # efficiency values, or supply the missing boundary by a model default.
    case = comparison.get('case_input')
    if not isinstance(case, dict) or case.get('poi_is_dc_side') is not False:
        raise ValueError('Equipment discharge assessment requires an explicitly AC-side POI source; '
                         'DC-side or unspecified POI comparisons must be recalculated with a confirmed AC basis.')
    frequency_option = case.get('poi_frequency_option')
    if frequency_option == 'TBD':
        raise ValueError('Equipment discharge assessment requires a confirmed project frequency; '
                         'a TBD selection cannot use a default frequency for equipment checks.')
    frequency = _finite(case.get('poi_frequency_hz'), 'Signed project frequency')
    if frequency_option is not None:
        try:
            selected_frequency = float(frequency_option)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('The selected project frequency must match the signed numeric frequency') from exc
        if (isinstance(frequency_option, bool) or not math.isfinite(selected_frequency)
                or selected_frequency != frequency):
            raise ValueError('The selected project frequency must match the signed numeric frequency')


def assess_dc_ac_equipment(revision_service, comparison, allocation, capability_service, *,
                           expected_comparison_sha256, duty_basis=None, variant_service=None):
    """Assess one declared discharge point; never release full AC engineering."""
    comparison, raw = comparison_json(comparison), deepcopy(allocation)
    if isinstance(raw, DcAcAllocation):
        raw = raw.model_dump(mode='python')
    allocation = DcAcAllocation.model_validate(raw)
    raw_duty = (duty_basis.model_dump(mode='python') if isinstance(duty_basis, DischargeDutyBasis)
                else {} if duty_basis is None else deepcopy(duty_basis))
    duty = DischargeDutyBasis.model_validate(raw_duty)
    mapping = assess_dc_ac_allocation(revision_service, comparison, allocation,
        expected_comparison_sha256=expected_comparison_sha256, variant_service=variant_service)
    validate_equipment_source_boundary(comparison)
    checks = _Checks()
    packages, reviews = {}, []
    if mapping['topology_valid']:
        for kind, instances, id_field in (
                ('pcs', allocation.pcs_instances, 'pcs_id'),
                ('transformer', allocation.transformer_instances, 'transformer_id')):
            for instance in instances:
                identity, reference = getattr(instance, id_field), instance.capability_ref
                if reference is None:
                    checks.add(kind, identity, 'current_capability_review', 'pending', f'{identity}: a registered capability revision is required.')
                    continue
                detail = capability_service.resolve_reference(reference.model_dump(mode='json'), kind=kind)
                reviews.append(dict(equipment_kind=kind, equipment_id=identity, reference=reference.model_dump(mode='json'),
                    review_token=detail['review_token'], candidate_review_current=detail['candidate_review_current']))
                if not detail['candidate_review_current']:
                    checks.add(kind, identity, 'current_capability_review', 'pending', f'{identity}: the capability revision is not currently reviewed for candidate comparison.')
                    continue
                packages[kind, identity] = EquipmentCapabilityPackage.model_validate(detail['payload'])
                checks.add(kind, identity, 'current_capability_review', 'pass', f'{identity}: current candidate-only capability review verified.')
        if duty.evidence_ref is None:
            checks.add('station', 'Duty', 'project_duty_evidence', 'pending', 'The declared equipment duty point needs a project evidence reference.')
        data = _equipment_checks(allocation, comparison, packages, duty, checks)
    else:
        data = dict(port_duties=[], pcs_duties=[], winding_duties=[], transformer_duties=[], power_boundaries={})
    failed = [row['message'] for row in checks.rows if row['status'] == 'fail']
    pending = [row['message'] for row in checks.rows if row['status'] == 'pending']
    scope_pending = [
        'Actual PCS terminal voltage after cable drop remains unverified for every input.',
        'Only one static discharge point is checked; charging, complete P/Q capability, control and protection coordination remain unverified.',
        'Equipment temperature ranges are declared rating conditions; no temperature derating curve was inferred.',
        'PCS efficiency and downstream losses are signed case assumptions, not verification against equipment efficiency curves or a POI guarantee.',
        'Transformer tap range, grid interface, harmonics, fault duty and detailed design remain unverified.',
        'Curve applicability remains inherited from C2b; run adoption, SLD, layout and proposal release remain disabled.',
        'DC and equipment reviews are checked at separate read checkpoints, not one atomic release snapshot; adoption requires atomic revalidation.',
    ]
    if not mapping['topology_valid']:
        numeric_status, status = 'not_evaluated', 'invalid_mapping'
    else:
        numeric_status = 'fails_declared_limits' if failed else 'pending_evidence' if pending else 'within_declared_limits'
        status = 'fails_discharge_checks' if failed or mapping['errors'] else 'pending_engineering_evidence'
    result = dict(schema_version=1, contract_type='dc_ac_equipment_assessment_v1', comparison_only=True,
        downstream_ready=False, status=status, declared_discharge_check_status=numeric_status,
        topology_valid=mapping['topology_valid'], dc_duty_status=mapping['dc_duty_status'],
        source_energy_requirement_met=mapping['source_energy_requirement_met'], source=mapping['source'],
        review_consistency='separate_read_checkpoints', adoption_requires_atomic_revalidation=True,
        allocation_contract_sha256=mapping['allocation_contract_sha256'], allocation=allocation.model_dump(mode='json'),
        duty_basis=duty.model_dump(mode='json'), equipment_reviews=reviews, checks=checks.rows,
        errors=list(dict.fromkeys(mapping['errors'] + failed)), pending_evidence=list(dict.fromkeys(pending + scope_pending)),
        evidence_boundary='Reviewed candidate-only equipment data and one declared discharge reference; no full AC compatibility, warranty or engineering release.',
        floating_point_relative_tolerance=1e-9, **data)
    def check_equipment_reviews():
        for row in reviews:
            current = capability_service.resolve_reference(row['reference'], kind=row['equipment_kind'])
            if current['review_token'] != row['review_token'] or current['candidate_review_current'] != row['candidate_review_current']:
                raise ValueError('Equipment capability review changed during discharge assessment')

    check_equipment_reviews()
    revalidate_allocation_source(revision_service, comparison, expected_comparison_sha256, variant_service=variant_service)
    check_equipment_reviews()
    result['assessment_sha256'] = package_sha256(result)
    return result
