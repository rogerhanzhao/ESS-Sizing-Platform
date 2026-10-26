"""D1a explicit DC-to-AC mapping diagnostics, separate from frozen AC sizing.

Only declared topology and upstream DC discharge references are assessed. PCS
and transformer capability checks, AC power/losses and adoption are subsequent
gates. No result from this module is an engineering release.
"""
from __future__ import annotations

from copy import deepcopy
from collections import defaultdict
import math

from calb_sizing_tool.schemas.dc_ac_allocation import DcAcAllocation
from calb_sizing_tool.services.dc_ac_allocation_source_service import (
    comparison_json, revalidate_allocation_source,
)
from calb_sizing_tool.services.dc_ac_allocation_topology import validate_allocation_topology
from calb_sizing_tool.services.dc_product_comparison_service import package_sha256


def _duties(allocation, source):
    domain_duties = {row['domain_id']: row for row in source['dispatch']['domain_duties']}
    connection_by_domain = {row.domain_id: row for row in allocation.dc_connections}
    domains = []
    domains_by_port, domains_by_pcs = defaultdict(list), defaultdict(list)
    for row in source['manifest']['electrical_domains']:
        link = connection_by_domain[row['domain_id']]
        duty = domain_duties[row['domain_id']]
        domains.append(dict(domain_id=row['domain_id'], unit_id=row['unit_id'],
            pcs_id=link.pcs_id, port_id=link.port_id,
            requested_dc_discharge_kw=duty['requested_discharge_kw'],
            required_dc_current_a_at_voltage_min=duty['required_current_a_at_voltage_min'],
            dc_limit_status=duty['limit_status']))
        domains_by_port[link.pcs_id, link.port_id].append(domains[-1])
        domains_by_pcs[link.pcs_id].append(row['domain_id'])
    ports = []
    ports_by_pcs = defaultdict(list)
    for port in allocation.input_ports:
        rows = domains_by_port[port.pcs_id, port.port_id]
        ports.append(dict(pcs_id=port.pcs_id, port_id=port.port_id, dc_bus_id=port.dc_bus_id,
            domain_ids=[row['domain_id'] for row in rows],
            requested_dc_discharge_kw=math.fsum(row['requested_dc_discharge_kw'] for row in rows)))
        ports_by_pcs[port.pcs_id].append(ports[-1])
    pcs_rows = []
    pcs_by_block = defaultdict(list)
    for pcs in allocation.pcs_instances:
        rows = ports_by_pcs[pcs.pcs_id]
        pcs_rows.append(dict(pcs_id=pcs.pcs_id, ac_block_id=pcs.ac_block_id,
            domain_ids=domains_by_pcs[pcs.pcs_id],
            requested_dc_discharge_kw=math.fsum(row['requested_dc_discharge_kw'] for row in rows)))
        pcs_by_block[pcs.ac_block_id].append(pcs_rows[-1])
    pcs_by_id = {row['pcs_id']: row for row in pcs_rows}
    pcs_by_winding, units_by_block = defaultdict(list), defaultdict(list)
    for link in allocation.lv_connections:
        pcs_by_winding[link.transformer_id, link.winding_id].append(link.pcs_id)
    for link in allocation.unit_assignments:
        units_by_block[link.ac_block_id].append(link.unit_id)
    windings = []
    for winding in allocation.lv_windings:
        ids = pcs_by_winding[winding.transformer_id, winding.winding_id]
        windings.append(dict(transformer_id=winding.transformer_id, winding_id=winding.winding_id,
            lv_bus_id=winding.lv_bus_id, pcs_ids=ids,
            upstream_dc_reference_kw=math.fsum(pcs_by_id[key]['requested_dc_discharge_kw'] for key in ids)))
    blocks = []
    for block in allocation.ac_blocks:
        rows = pcs_by_block[block.ac_block_id]
        blocks.append(dict(ac_block_id=block.ac_block_id, pcs_ids=[row['pcs_id'] for row in rows],
            unit_ids=units_by_block[block.ac_block_id],
            upstream_dc_reference_kw=math.fsum(row['requested_dc_discharge_kw'] for row in rows)))
    required = source['dispatch']['dc_power_required_mw'] * 1000
    totals = dict(ports=math.fsum(row['requested_dc_discharge_kw'] for row in ports),
        pcs=math.fsum(row['requested_dc_discharge_kw'] for row in pcs_rows),
        lv_windings=math.fsum(row['upstream_dc_reference_kw'] for row in windings),
        ac_blocks=math.fsum(row['upstream_dc_reference_kw'] for row in blocks))
    if not all(math.isfinite(value) and math.isclose(value, required, rel_tol=1e-9, abs_tol=0)
               for value in totals.values()):
        raise ValueError('The declared mapping does not conserve the signed source DC discharge duty')
    return dict(domain_connections=domains, port_duties=ports, pcs_duties=pcs_rows,
        lv_winding_duties=windings, ac_block_duties=blocks,
        conservation=dict(all_levels_conserved=True, requested_dc_discharge_kw=required,
                          allocated_dc_reference_kw=totals))


def assess_dc_ac_allocation(revision_service, comparison: dict, allocation, *,
                            expected_comparison_sha256: str, variant_service=None) -> dict:
    """Diagnose a human-declared allocation against an exact current DC source.

    The expected digest is mandatory and must come from the caller's retained
    selected-comparison identity, not be defaulted from an uploaded object's
    own digest. Equipment references remain unverified in D1a.
    """
    comparison = comparison_json(comparison)
    raw = allocation.model_dump(mode='python') if isinstance(allocation, DcAcAllocation) else deepcopy(allocation)
    allocation = DcAcAllocation.model_validate(raw)
    if allocation.source.candidate_comparison_sha256 != expected_comparison_sha256:
        raise ValueError('The allocation refers to a different retained C2b comparison identity')
    source = revalidate_allocation_source(revision_service, comparison, expected_comparison_sha256,
                                         variant_service=variant_service)
    if allocation.source.dc_manifest_sha256 != source['manifest_sha256']:
        raise ValueError('The allocation refers to a different physical DC composition manifest')
    topology = validate_allocation_topology(allocation, source['manifest'])
    errors = list(topology['errors']) + source['dispatch']['errors']
    pending = list(topology['pending_evidence']) + source['dispatch']['pending_evidence'] + [
        'PCS input-port topology, DC voltage, continuous current and power capability require separately reviewed equipment evidence.',
        'Transformer total and individual LV winding ratings, voltage and vector group require separately reviewed equipment evidence.',
        'Equipment package references are recorded only; their lifecycle and manufacturer applicability have not been validated.',
        'AC delivered power, losses, charging duty, reactive power and temperature derating have not been evaluated.',
        'Curve applicability is inherited from the retained C2b result; no new lifetime approval is issued.',
        'Run adoption and SLD, layout and technical proposal generation are not enabled for this contract.',
    ]
    energy_met = source['comparison'].get('meets_guarantee_year_energy') is True
    if not energy_met:
        errors.append('The source candidate does not satisfy its guarantee-year POI energy requirement.')
    if not topology['topology_valid']:
        status = 'invalid_mapping'
    elif source['dispatch']['errors']:
        status = 'fails_declared_dc_limits'
    elif not energy_met:
        status = 'fails_source_energy_requirement'
    else:
        status = 'pending_equipment_evidence'
    register = (_duties(allocation, source) if topology['topology_valid'] else
        dict(domain_connections=[], port_duties=[], pcs_duties=[], lv_winding_duties=[], ac_block_duties=[],
             conservation=dict(all_levels_conserved=False,
                 requested_dc_discharge_kw=source['dispatch']['dc_power_required_mw'] * 1000,
                 allocated_dc_reference_kw={})))
    contract = allocation.model_dump(mode='json')
    result = dict(schema_version=1, contract_type='dc_ac_allocation_assessment_v1',
        comparison_only=True, downstream_ready=False, status=status,
        topology_valid=topology['topology_valid'], dc_duty_status=source['dispatch']['status'],
        source_energy_requirement_met=energy_met, discharge_feasibility_status='not_evaluated',
        source=dict(candidate_comparison_sha256=source['comparison_sha256'],
            dc_manifest_sha256=source['manifest_sha256'], current_dc_reviews_verified=True,
            curve_applicability_recertified=False),
        allocation=contract, allocation_contract_sha256=package_sha256(contract),
        errors=list(dict.fromkeys(errors)), pending_evidence=list(dict.fromkeys(pending)),
        evidence_boundary='Declared mapping and upstream DC discharge reference only; no AC kW, kVA, equipment compatibility or engineering acceptance.',
        **register)
    # Detect withdrawal or catalogue changes during mapping as well as before it.
    final_source = revalidate_allocation_source(revision_service, comparison, expected_comparison_sha256,
                                               variant_service=variant_service)
    if final_source != source:
        raise ValueError('The source DC comparison changed during allocation assessment')
    result['assessment_sha256'] = package_sha256(result)
    return result
