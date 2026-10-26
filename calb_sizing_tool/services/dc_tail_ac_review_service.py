"""Bounded nominal review of one DC tail inside the original AC grouping.

This is an attachment to the unchanged AC result, never an adopted electrical
design. Unknown output duties remain unknown; no equipment limits are inferred.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math

from calb_sizing_tool.common.allocation import evenly_distribute
from calb_sizing_tool.services.ac_mixed_station import build_mixed_dc_allocation_plan, is_mixed_station
from calb_sizing_tool.services.ac_run_service import ac_configuration_hash
from calb_sizing_tool.services.dc_reduced_string_tail_service import (
    STANDARD_EXCEL_CODE, restored_comparison,
)
from calb_sizing_tool.services.run_persistence_service import _hash_payload


REVIEW_KEY = 'reduced_string_tail_ac_review'
POLICY = 'proportional_to_nameplate_energy'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive(value, label, *, fraction=False):
    _require(type(value) in (int, float), f'{label} must be positive finite numeric data.')
    try:
        valid = math.isfinite(value) and value > 0 and (not fraction or value <= 1)
    except (OverflowError, ValueError):
        valid = False
    _require(valid, f'{label} must be positive finite numeric data.')
    return float(value)


def _whole(value, label):
    number = _positive(value, label)
    _require(number.is_integer(), f'{label} must be a positive integer.')
    return int(number)


def _sum(values):
    try:
        total = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise ValueError('Nominal review totals must remain finite.') from exc
    _require(math.isfinite(total), 'Nominal review totals must remain finite.')
    return total


def _fits(required, declared):
    return required <= declared or math.isclose(required, declared, rel_tol=1e-9, abs_tol=1e-9)


def _json(value):
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Nominal review data must be finite JSON.') from exc


def _ac_rows(ac_output, count):
    _require(isinstance(ac_output, dict), 'An original AC output is required.')
    _require(ac_output.get('dc_unit_kind') != 'independent_cabinet_group',
             'Reduced-string container tails cannot use cabinet AC groups.')
    raw = ac_output.get('ac_block_rows')
    _require(isinstance(raw, list) and raw, 'Original AC Block rows are required.')
    rows = []
    for index, row in enumerate(raw, 1):
        _require(isinstance(row, dict), f'AC Block {index} must be a record.')
        rows.append({key: _whole(row.get(key), f'AC Block {index} {key}')
                     for key in ('pcs_count', 'pcs_kw', 'dc_blocks')})
    _require(sum(row['dc_blocks'] for row in rows) == count,
             'Original AC rows must allocate every standard DC container exactly once.')
    if 'dc_blocks_total' in ac_output:
        _require(_whole(ac_output['dc_blocks_total'], 'AC DC total') == count,
                 'AC DC total differs from the selected standard DC result.')
    if 'num_blocks' in ac_output:
        _require(_whole(ac_output['num_blocks'], 'AC Block count') == len(rows),
                 'AC Block count differs from its rows.')
    circuits = _whole(ac_output.get('dc_block_output_circuits'), 'Main DC output circuits')
    _require(circuits in (1, 2), 'Main DC output circuits must be 1 or 2.')
    topology = ac_output.get('transformer_topology')
    _require(topology in ('two_winding', 'three_winding'), 'An explicit transformer topology is required.')
    windings = 1 if topology == 'two_winding' else 2
    if 'lv_winding_count' in ac_output:
        _require(_whole(ac_output['lv_winding_count'], 'LV winding count') == windings,
                 'LV winding count conflicts with the selected transformer topology.')
    return rows, circuits, windings


def evaluate_tail_ac_review(parent_snapshot, ac_output,
                            tail_pcs_ratings_kw: dict[int, float] | None = None) -> dict | None:
    """Review the last original AC group without changing its active allocation.

    Overrides name the 1-based PCS feeders connected to the final physical DC
    box only. Their separate nameplates are preserved, never averaged into the
    original row's representative PCS rating. No new AC group is created.
    """
    comparison = restored_comparison(parent_snapshot)
    if comparison is None:
        return None
    count = parent_snapshot.stage2.container_count
    rows, circuits, winding_count = _ac_rows(ac_output, count)
    plan = build_mixed_dc_allocation_plan(rows, dc_block_output_circuits=circuits)
    # Match the ORIGINAL selected DC run, not the smaller comparison BOM.
    # Equal container counts alone do not establish the same case/duty source.
    for field, expected in (
            ('poi_power_mw', parent_snapshot.stage1.poi_power_req_mw),
            ('poi_energy_mwh', parent_snapshot.stage1.poi_energy_req_mwh),
            ('dc_total_mwh', parent_snapshot.stage2.dc_nameplate_bol_mwh)):
        if field in ac_output:
            actual = _positive(ac_output[field], f'AC source {field}')
            _require(math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-6),
                     f'AC source {field} differs from the selected original DC result.')
    if 'dc_allocation_plan' in ac_output:
        stored_plan = _json(ac_output['dc_allocation_plan'])
        _require(_hash_payload(stored_plan) == _hash_payload(plan),
                 'Saved original DC allocation differs from its AC rows; no connection was replaced.')
    tail_connection = plan[-1]['dc_block_connections'][-1]
    tail_feeders = list(tail_connection['feeder_indices'])
    strings = comparison['selected_tail_strings']
    tail_outputs = 1 if strings == 10 else 2
    overrides = {} if tail_pcs_ratings_kw is None else tail_pcs_ratings_kw
    _require(isinstance(overrides, dict), 'Tail PCS overrides must be keyed by feeder index.')
    normalized_overrides = {}
    for key, rating in overrides.items():
        _require(type(key) is int and key in tail_feeders,
                 'Only PCS feeders connected to the final tail container may be overridden.')
        normalized_overrides[key] = _positive(rating, 'Tail PCS rating')

    basis = comparison['basis']
    main_item = parent_snapshot.stage2.block_config_items[0]
    main_energy = (basis['main_energy_mwh'] if main_item.block_code == STANDARD_EXCEL_CODE else
                   _positive(comparison['parent_product_snapshot'].get('gross_energy_mwh'), 'Main energy'))
    tail_info = basis['tails'][str(strings)]
    tail_energy = tail_info['energy_mwh']
    fleet_energy = _sum(((count - 1) * main_energy, tail_energy))
    saved_total = comparison['snapshot']['stage2']['dc_nameplate_bol_mwh']
    _require(round(fleet_energy, 3) == saved_total,
             'The AC physical composition differs from the saved tail DC BOM.')
    required_kw = _positive(parent_snapshot.stage1.dc_power_required_mw, 'DC discharge duty') * 1000
    conversion = (_positive(parent_snapshot.stage1.eff_dc_cables_frac, 'DC cable efficiency', fraction=True)
                  * _positive(parent_snapshot.stage1.eff_pcs_frac, 'PCS efficiency', fraction=True))
    main_capacity = basis['main_energy_raw_mwh'] * 500
    tail_capacity = tail_info['power_kw']
    errors, pending, topology_errors = [], [], []
    if len(tail_feeders) > tail_outputs:
        topology_errors.append(f'The {strings}-string tail has {tail_outputs} DC output(s) and cannot feed '
                               f'{len(tail_feeders)} PCS in the original last AC group.')
    if strings == 8:
        pending.append('The 8-string tail has two DC outputs, but their energy, power and current partition is unknown; no 4+4 or equal split is assumed.')
        if len(tail_feeders) == 1:
            pending.append('Connecting the two 8-string outputs to one PCS needs confirmed independent input or parallel applicability; one allowed PCS is not connection approval.')
    if not comparison['meets_guarantee_year_energy']:
        errors.append('The saved DC tail comparison does not meet the guarantee-year POI energy requirement.')
    if not comparison['meets_nominal_dc_power']:
        errors.append('The saved DC tail comparison does not meet the owner 0.5C nominal DC power basis.')

    groups, physical_index = [], 0
    mixed = is_mixed_station(rows)
    for group_index, (row, original_plan) in enumerate(zip(rows, plan), 1):
        is_last = group_index == len(rows)
        main_count = row['dc_blocks'] - int(is_last)
        group_energy = _sum((main_count * main_energy, tail_energy if is_last else 0))
        group_duty = required_kw * group_energy / fleet_energy
        nominal_capacity = _sum((main_count * main_capacity, tail_capacity if is_last else 0))
        pcs_items = [dict(feeder_index=index, rating_kw=normalized_overrides.get(index, row['pcs_kw'])
                          if is_last else row['pcs_kw'], connected_tail=is_last and index in tail_feeders,
                          known_main_dc_duty_kw=0.0, known_tail_dc_duty_kw=0.0,
                          tail_output_duty_unknown=False, connected_unit_ids=[])
                     for index in range(1, row['pcs_count'] + 1)]
        connections = []
        for connection in original_plan['dc_block_connections']:
            physical_index += 1
            tail = is_last and connection['dc_block_index'] == row['dc_blocks']
            feeders = list(connection['feeder_indices'])
            energy = tail_energy if tail else main_energy
            duty = required_kw * energy / fleet_energy
            unknown = tail and (len(feeders) > tail_outputs or strings == 8 and len(feeders) == 2)
            if not tail and len(feeders) == 1 and circuits == 2:
                pending.append(f'AC Block {group_index}: the original single-feeder mapping carries a complete 12-string container; its two-output input arrangement remains to be confirmed.')
            links = []
            for feeder in feeders:
                item = pcs_items[feeder - 1]
                item['connected_unit_ids'].append(f'DC-{physical_index:03d}')
                # Main 12-string/two-feeder duty follows the evidenced 6+6
                # partition. An 8-string/two-feeder partition is NOT inferred.
                portion = None if unknown else duty / len(feeders)
                if tail:
                    item['tail_output_duty_unknown'] = unknown
                    if portion is not None:
                        item['known_tail_dc_duty_kw'] += portion
                else:
                    item['known_main_dc_duty_kw'] += portion
                links.append(dict(feeder_index=feeder, required_dc_duty_kw=portion))
            connections.append(dict(unit_id=f'DC-{physical_index:03d}',
                dc_block_index=connection['dc_block_index'], role='tail' if tail else 'main',
                product_code=comparison['product_snapshot']['block_code'] if tail else main_item.block_code,
                strings_in_parallel=strings if tail else 12, dc_energy_mwh=energy,
                required_dc_duty_kw=duty, feeder_indices=feeders,
                output_circuit_count=tail_outputs if tail else circuits,
                max_connected_pcs=tail_outputs if tail else circuits,
                per_feeder_duties=links,
                output_partition_confirmed=(tail and strings == 10 and len(feeders) == 1
                                            or not tail and circuits == 2 and len(feeders) == 2)))
        for item in pcs_items:
            unknown = item['tail_output_duty_unknown']
            dc_duty = None if unknown else _sum((item['known_main_dc_duty_kw'], item['known_tail_dc_duty_kw']))
            ac_duty = None if unknown else dc_duty * conversion
            item.update(required_dc_duty_kw=dc_duty, required_ac_duty_kw=ac_duty,
                nominal_power_check=('unknown_output_duty' if unknown else
                    'within_nominal_nameplate' if _fits(ac_duty, item['rating_kw']) else 'exceeds_pcs_nameplate'),
                meets_pcs_nameplate=None if unknown else _fits(ac_duty, item['rating_kw']))
            if unknown:
                pending.append(f'AC Block {group_index} PCS {item["feeder_index"]}: tail output duty is unknown; no per-PCS power pass can be issued.')
            elif not item['meets_pcs_nameplate']:
                errors.append(f'AC Block {group_index} PCS {item["feeder_index"]}: required PCS AC discharge exceeds its separate nominal nameplate.')
        if not _fits(group_duty, nominal_capacity):
            errors.append(f'AC Block {group_index}: required DC discharge exceeds the owner 0.5C nominal DC power basis.')

        # This is the same contiguous feeder-to-winding convention as the
        # original selected two/three-winding topology. Ratings are NOT split.
        cursor, windings = 1, []
        for winding_index, size in enumerate(evenly_distribute(row['pcs_count'], winding_count), 1):
            indices = list(range(cursor, cursor + size))
            cursor += size
            items = [pcs_items[index - 1] for index in indices]
            known = all(item['required_ac_duty_kw'] is not None for item in items)
            windings.append(dict(winding_index=winding_index, feeder_indices=indices,
                pcs_rating_kw_sum=_sum(item['rating_kw'] for item in items),
                required_ac_duty_kw=_sum(item['required_ac_duty_kw'] for item in items) if known else None,
                winding_rating_kva=None, status='pending_winding_rating'))
        bound = bool(not mixed and ac_output.get('ac_block_product_block_code')
                     and ac_output.get('transformer_mva') is not None)
        transformer_mva = (_positive(ac_output['transformer_mva'], 'Bound transformer MVA') if bound
                           else row['pcs_count'] * row['pcs_kw'] / 1000 / 0.9)
        rating_sum = _sum(item['rating_kw'] for item in pcs_items)
        transformer_review = dict(total_mva=transformer_mva,
            total_mva_basis='original_bound_product_nameplate' if bound else 'original_row_mw_divided_by_0_9_estimate',
            is_estimate=not bound, full_pcs_nameplate_at_0_9_pf_mva=rating_sum / 1000 / 0.9,
            full_nameplate_comparison_within_basis=_fits(rating_sum / 1000 / 0.9, transformer_mva),
            winding_ratings_confirmed=False, equipment_approved=False)
        if not transformer_review['full_nameplate_comparison_within_basis']:
            pending.append(f'AC Block {group_index}: separate PCS nameplates exceed the original transformer full-nameplate basis at the planning 0.9 power factor; confirm transformer capacity.')
        groups.append(dict(ac_block_index=group_index, main_count=main_count, tail_count=int(is_last),
            dc_count=row['dc_blocks'], dc_energy_mwh=group_energy, required_dc_duty_kw=group_duty,
            nominal_dc_capacity_kw=nominal_capacity, meets_nominal_dc_power=_fits(group_duty, nominal_capacity),
            pcs_rating_kw_sum=rating_sum, pcs_items=pcs_items, connections=connections,
            windings=windings, transformer_review=transformer_review))

    _require(physical_index == count and sum(group['tail_count'] for group in groups) == 1,
             'The bounded review must replace exactly one final container.')
    _require(math.isclose(_sum(group['required_dc_duty_kw'] for group in groups), required_kw, rel_tol=1e-12),
             'The physical-group duty does not conserve the original Stage1 DC discharge reference.')
    all_pcs_duties_known = all(item['required_dc_duty_kw'] is not None
                              for group in groups for item in group['pcs_items'])
    if all_pcs_duties_known:
        _require(math.isclose(_sum(item['required_dc_duty_kw']
                                  for group in groups for item in group['pcs_items']),
                             required_kw, rel_tol=1e-12),
                 'The known per-PCS duties do not conserve the original Stage1 DC discharge reference.')
    errors = list(dict.fromkeys(topology_errors + errors))
    pending.extend([
        'Owner 0.5C is a nominal BOL design basis, not a hardware current limit or a lifetime power guarantee.',
        'PCS/port voltage, continuous current, cable drop, charge duty and actual equipment derating remain unverified.',
        'Individual LV winding kVA limits are unknown; no transformer total rating was divided between windings.',
        'Transformer comparison uses full PCS nameplates at the stated planning 0.9 power factor, not confirmed project reactive-power capability.',
        'This comparison does not adopt the tail or change the active AC, SLD, layout or proposal configuration.',
    ])
    result = dict(schema_version=1, contract_type='reduced_string_tail_ac_review', comparison_only=True,
        downstream_ready=False, source=dict(dc_comparison_sha256=comparison['comparison_sha256'],
            ac_configuration_sha256=ac_configuration_hash(ac_output)),
        dispatch_policy=POLICY, selected_tail_strings=strings, tail_group_index=len(groups),
        tail_feeder_indices=tail_feeders,
        tail_pcs_rating_overrides_kw=[dict(feeder_index=index, rating_kw=normalized_overrides[index])
                                      for index in sorted(normalized_overrides)],
        total_dc_count=count, main_count=count - 1, tail_count=1,
        total_dc_energy_mwh=saved_total, total_required_dc_duty_kw=required_kw,
        total_nominal_dc_capacity_kw=_sum(group['nominal_dc_capacity_kw'] for group in groups),
        total_pcs_rating_kw_sum=_sum(group['pcs_rating_kw_sum'] for group in groups),
        pcs_dc_to_ac_efficiency_frac=conversion,
        topology_valid=not topology_errors,
        source_energy_requirement_met=comparison['meets_guarantee_year_energy'],
        meets_nominal_dc_power=comparison['meets_nominal_dc_power'],
        nominal_reference_conserved=all_pcs_duties_known and not topology_errors,
        groups=groups, errors=errors, pending_evidence=list(dict.fromkeys(pending)),
        status='fails_nominal_review' if errors else 'pending_engineering_evidence',
        engineering_approved=False)
    result = _json(result)
    result['review_sha256'] = _hash_payload(result)
    return result


def restored_tail_ac_review(parent_snapshot, ac_output) -> dict | None:
    """Validate a saved attachment by rebuilding only its finite nominal checks.

    This calls the saved DC validator; it never runs Stage3 or saves a run.
    Recomputed digests alone cannot bless an internally contradictory review.
    """
    _require(isinstance(ac_output, dict), 'An original AC output is required.')
    saved = ac_output.get(REVIEW_KEY)
    if saved is None:
        return None
    _require(isinstance(saved, dict), 'Saved tail AC review must be an object.')
    saved = deepcopy(saved)
    _require(saved.get('review_sha256') == _hash_payload({key: value for key, value in saved.items()
                                                        if key != 'review_sha256'}),
             'Saved tail AC review content has changed.')
    rows = saved.get('tail_pcs_rating_overrides_kw')
    _require(isinstance(rows, list), 'Saved tail PCS overrides are incomplete.')
    overrides = {}
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {'feeder_index', 'rating_kw'},
                 'Saved tail PCS override is malformed.')
        key = row['feeder_index']
        _require(type(key) is int and key not in overrides, 'Saved tail PCS feeder identities must be unique integers.')
        overrides[key] = row['rating_kw']
    expected = evaluate_tail_ac_review(parent_snapshot, ac_output, overrides)
    _require(expected is not None and saved == expected,
             'Saved tail AC review differs from the selected DC source, AC grouping or nominal checks.')
    return saved


__all__ = ['REVIEW_KEY', 'evaluate_tail_ac_review', 'restored_tail_ac_review']
