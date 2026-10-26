"""Read-only handoff for a single last-group tail drawing preview.

The original standard DC / AC configuration stays authoritative.  A preview is
neither an adopted configuration nor permission to generate formal artifacts.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
import math

from calb_sizing_tool.adapters.session_state_adapter import build_dc_bom_handoff
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.services.dc_reduced_string_tail_service import restored_comparison
from calb_sizing_tool.services.dc_tail_ac_review_service import restored_tail_ac_review
from calb_sizing_tool.services.run_persistence_service import _hash_payload


def _finite_json(value):
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Tail preview sources must contain finite JSON data.') from exc


def _validate_ac_inventory(inventory, review):
    """Cross-check electrical assignments against the actual saved DC BOM.

    BOM ordinals are not physical locations. Match products, quantities and
    capacities rather than using their list positions to infer a connection.
    The current producer still reviews one final tail; this inventory check
    introduces no permanent quantity, position or exclusive-SKU rule.
    """
    expected = Counter(unit['block_code'] for unit in inventory['units'])
    capacities = {}
    for unit in inventory['units']:
        code = unit['block_code']
        capacity = unit['unit_capacity_mwh']
        if code in capacities and not math.isclose(capacities[code], capacity, rel_tol=0, abs_tol=1e-9):
            raise ValueError('One DC product has conflicting saved unit capacities.')
        capacities[code] = capacity
    assigned, identifiers = Counter(), set()
    for group in review['groups']:
        connections = group['connections']
        if len(connections) != group['dc_count']:
            raise ValueError('AC group assignments do not match its DC quantity.')
        for connection in connections:
            code, identifier = connection['product_code'], connection['unit_id']
            if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
                raise ValueError('AC assignments must identify every physical DC unit exactly once.')
            identifiers.add(identifier)
            assigned[code] += 1
            capacity = connection['dc_energy_mwh']
            if (code not in capacities or type(capacity) not in (int, float)
                    or not math.isfinite(capacity)
                    or not math.isclose(capacity, capacities[code], rel_tol=0, abs_tol=0.000500001)):
                raise ValueError('AC assignment product or capacity differs from the saved DC BOM.')
    if assigned != expected:
        raise ValueError('AC assigned products or quantities differ from the saved DC BOM.')
    if round(review['total_dc_energy_mwh'], 3) != inventory['totals']['dc_nameplate_bol_mwh']:
        raise ValueError('AC inventory energy differs from the saved DC BOM total.')


def build_tail_sld_preview(parent_snapshot, ac_output) -> dict | None:
    """Bind an existing saved comparison and review without calculating sizing.

    Missing attachments yield no preview. Corrupt or contradictory saved data
    raise ``ValueError`` through their existing validators. A valid review with
    hard failures yields a blocked manifest with no drawable last group. Unknown
    eight-string output duties may be drawn only as explicit TBC values.

    The caller owns access control and exact persisted run/snapshot identity.
    This pure adapter additionally binds the complete DC and AC payloads, so a
    changed comparison-only PCS rating cannot reuse an earlier preview identity.
    """
    comparison = restored_comparison(parent_snapshot)
    if comparison is None:
        return None
    if not isinstance(ac_output, dict):
        raise ValueError('A saved original AC output is required for a tail preview.')
    output = _finite_json(ac_output)
    review = restored_tail_ac_review(parent_snapshot, output)
    if review is None:
        return None
    inventory = build_dc_bom_handoff(Stage2Result.model_validate(comparison['snapshot']['stage2']))
    _validate_ac_inventory(inventory, review)
    parent_payload = _finite_json(parent_snapshot.model_dump(mode='json'))

    reasons = list(review['errors'])
    for field, message in (
        ('topology_valid', 'The tail connection is incompatible with the selected PCS feeders.'),
        ('source_energy_requirement_met', 'The tail comparison does not meet the guarantee-year POI energy requirement.'),
        ('meets_nominal_dc_power', 'The tail comparison does not meet the owner 0.5C nominal DC power basis.'),
    ):
        if review[field] is not True:
            reasons.append(message)
    reasons = list(dict.fromkeys(reasons))
    available = not reasons

    # Saved validators have already rebuilt every group and checked that the
    # only replacement is the final physical DC container. Keep those identities
    # and exact values; no new feeder assignment or power split is introduced.
    last_group = review['groups'][-1]
    prior_groups = review['groups'][:-1]
    tail_connection = last_group['connections'][-1]
    unknown = any(item['required_dc_duty_kw'] is None for item in last_group['pcs_items'])
    single_pcs_input_unconfirmed = (
        review['selected_tail_strings'] == 8
        and len(tail_connection['feeder_indices']) == 1
    )
    unused_windings = [winding['winding_index'] for winding in last_group['windings']
                       if not winding['feeder_indices']]
    pending_evidence = deepcopy(review['pending_evidence'])
    if unused_windings:
        pending_evidence.append(
            'LV winding(s) ' + ', '.join(map(str, unused_windings))
            + ' have no assigned PCS in the saved comparison; unused winding termination and ratings remain TBC.')

    result = dict(
        schema_version=1,
        contract_type='reduced_string_tail_last_group_sld_preview',
        comparison_only=True,
        diagram_only=True,
        downstream_ready=False,
        engineering_approved=False,
        dc_inventory=inventory,
        preview_available=available,
        status=('blocked' if not available else
                'diagram_only_with_tbc' if unknown or single_pcs_input_unconfirmed or unused_windings
                else 'diagram_only'),
        blocking_reasons=reasons,
        source=dict(
            dc_payload_sha256=_hash_payload(parent_payload),
            dc_comparison_sha256=comparison['comparison_sha256'],
            ac_payload_sha256=_hash_payload(output),
            ac_configuration_sha256=review['source']['ac_configuration_sha256'],
            ac_review_sha256=review['review_sha256'],
        ),
        scope=dict(
            kind='last_physical_ac_group_only',
            ac_block_index=review['tail_group_index'],
            preceding_ac_group_count=len(prior_groups),
            preceding_main_container_count=sum(group['main_count'] for group in prior_groups),
            preceding_dc_energy_mwh=math.fsum(group['dc_energy_mwh'] for group in prior_groups),
            first_physical_dc_index=sum(group['dc_count'] for group in prior_groups) + 1,
            final_physical_dc_index=review['total_dc_count'],
        ),
        fleet=dict(
            total_ac_group_count=len(review['groups']),
            total_dc_count=review['total_dc_count'],
            main_count=review['main_count'],
            tail_count=review['tail_count'],
            selected_tail_strings=review['selected_tail_strings'],
            standard_reference_energy_mwh=parent_snapshot.stage2.dc_nameplate_bol_mwh,
            comparison_energy_mwh=review['total_dc_energy_mwh'],
            total_pcs_rating_kw_sum=review['total_pcs_rating_kw_sum'],
        ),
        nominal_review=dict(
            source_energy_requirement_met=review['source_energy_requirement_met'],
            meets_nominal_dc_power=review['meets_nominal_dc_power'],
            topology_valid=review['topology_valid'],
            dispatch_policy=review['dispatch_policy'],
            pcs_dc_to_ac_efficiency_frac=review['pcs_dc_to_ac_efficiency_frac'],
            nominal_reference_conserved=review['nominal_reference_conserved'],
        ),
        unknown_output_duties=unknown,
        tail_output_partition_confirmed=tail_connection['output_partition_confirmed'],
        single_pcs_input_arrangement_unconfirmed=single_pcs_input_unconfirmed,
        last_group=deepcopy(last_group) if available else None,
        pending_evidence=pending_evidence,
    )
    # Preserve existing nonempty-winding manifests and saved AC review hashes.
    # This describes the drawing's unknown, not a new electrical allocation.
    if unused_windings:
        result['unused_lv_winding_indices'] = unused_windings
    result = _finite_json(result)
    result['preview_sha256'] = _hash_payload(result)
    return result


__all__ = ['build_tail_sld_preview']
