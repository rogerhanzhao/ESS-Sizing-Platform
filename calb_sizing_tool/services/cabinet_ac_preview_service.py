"""Owner-approved cabinet grouping contract, local concept evaluation only."""
import math
from calb_sizing_tool.common.allocation import evenly_distribute
from calb_sizing_tool.services.ac_sizing_service import STANDARD_PCS_RATINGS_KW

CONTRACT_VERSION = 'cabinet-independent-groups-v1-max12'
APPROVED_CABINET_CODES = {'CALB_0.418MWh_CAB_8P', 'CALB-418KWH-DC-CABINET-314AH'}


def build_cabinet_groups(count, total_mwh, product_codes, group_count=None):
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError('Physical cabinet count must be a positive integer')
    if not math.isfinite(total_mwh) or abs(total_mwh-count*0.418)>0.00051:
        raise ValueError('This contract supports only the confirmed 418kWh cabinet')
    if not product_codes or not set(product_codes).issubset(APPROVED_CABINET_CODES):
        raise ValueError('Cabinet product identity is not approved for this contract')
    minimum = math.ceil(count/12)
    groups = minimum if group_count is None else group_count
    if not isinstance(groups, int) or isinstance(groups, bool) or not minimum<=groups<=count:
        raise ValueError(f'Independent group count must be {minimum}..{count}')
    rows, cursor = [], 1
    for idx, size in enumerate(evenly_distribute(count, groups), 1):
        members = list(range(cursor,cursor+size))
        rows.append(dict(group_index=idx,cabinet_indices=members,cabinet_count=size,
                         nameplate_mwh=round(size*0.418,3),pcs_index=idx,
                         output_domain_count=1,capability_verified=False))
        cursor += size
    return dict(contract_version=CONTRACT_VERSION,physical_cabinet_count=count,
                cabinet_group_max_count=12,groups=rows,
                total_nameplate_mwh=round(count*0.418,3),product_codes=list(product_codes))


def build_candidates(group_plan, target_mw):
    if not math.isfinite(target_mw) or target_mw<=0:
        raise ValueError('POI power must be positive')
    groups=group_plan['groups']
    candidates=[]
    for kw in STANDARD_PCS_RATINGS_KW:
        for per_ac in (1,2,4,8):
            # Consecutive, intact groups per AC block; tail PCS count is explicit.
            blocks=[]
            for start in range(0,len(groups),per_ac):
                allocated=groups[start:start+per_ac]
                blocks.append(dict(ac_block_index=len(blocks)+1,
                    group_indices=[g['group_index'] for g in allocated],
                    pcs_indices=[g['pcs_index'] for g in allocated],
                    cabinet_count=sum(g['cabinet_count'] for g in allocated),
                    nameplate_mwh=round(sum(g['nameplate_mwh'] for g in allocated),3),
                    pcs_count=len(allocated),pcs_unit_kw=kw,
                    pcs_nameplate_mw=len(allocated)*kw/1000))
            identity=(kw,tuple(tuple(b['group_indices']) for b in blocks))
            if any(c['_identity']==identity for c in candidates):
                continue
            mw=len(groups)*kw/1000
            candidates.append(dict(candidate_key=f'PCS{kw}-G{per_ac}',_identity=identity,
                ac_blocks=blocks,pcs_count=len(groups),pcs_unit_kw=kw,
                station_pcs_nameplate_mw=mw,poi_requirement_mw=target_mw,
                nameplate_delta_mw=round(mw-target_mw,6),
                nameplate_meets_poi_number=mw>=target_mw,
                poi_deliverable_mw=None,capability_verified=False,
                status='concept_pending_equipment_and_poi_validation'))
    return sorted(candidates,key=lambda c:(not c['nameplate_meets_poi_number'],abs(c['nameplate_delta_mw']),len(c['ac_blocks']),c['pcs_unit_kw']))


def attach_cabinet_allocation(group_plan, allocation):
    """Bind intact groups to original AC allocations without assuming DC port sharing."""
    import copy
    validate_cabinet_contract(group_plan)
    plan = copy.deepcopy(group_plan)
    groups = plan['groups']
    cursor = 0
    for block in allocation:
        connections = block['dc_block_connections']
        if len(connections) != block['dc_blocks_total']:
            raise ValueError('Incomplete cabinet group allocation')
        feeders = [c['feeder_indices'] for c in connections]
        if any(len(f) != 1 for f in feeders) or any(n != 1 for n in block['feeder_allocations']):
            raise ValueError('Use exactly one independent cabinet group per PCS. Adjust DC groups per AC Block or PCS count.')
        for connection in connections:
            if cursor >= len(groups):
                raise ValueError('Cabinet group allocation exceeds available groups')
            groups[cursor].update(ac_block_index=block['ac_block_index'],
                                  pcs_index=connection['feeder_indices'][0])
            cursor += 1
    if cursor != len(groups):
        raise ValueError('Cabinet group allocation is incomplete')
    validate_cabinet_contract(plan, allocated=True)
    return plan


def validate_cabinet_contract(plan, *, allocated=False):
    """Reject malformed or stale saved interfaces before rendering or promotion."""
    if not isinstance(plan, dict) or plan.get('contract_version') != CONTRACT_VERSION:
        raise ValueError('Unsupported cabinet group contract version')
    try:
        canonical = build_cabinet_groups(plan['physical_cabinet_count'],
            plan['total_nameplate_mwh'], plan['product_codes'], len(plan['groups']))
        members, group_ids, terminals = [], [], []
        for group in plan['groups']:
            count = group['cabinet_count']
            indices = group['cabinet_indices']
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 12:
                raise ValueError('Each independent group must contain 1 to 12 cabinets')
            if len(indices) != count or any(type(i) is not int for i in indices):
                raise ValueError('Invalid physical cabinet membership')
            if not math.isclose(group['nameplate_mwh'], count * .418, abs_tol=.00051):
                raise ValueError('Cabinet group energy does not match physical membership')
            if group.get('output_domain_count') != 1:
                raise ValueError('Independent cabinet groups require one output domain')
            members.extend(indices)
            group_ids.append(group['group_index'])
            if allocated:
                pair = (group['ac_block_index'], group['pcs_index'])
                if any(type(i) is not int or i < 1 for i in pair):
                    raise ValueError('Invalid AC Block / PCS assignment')
                terminals.append(pair)
        if sorted(members) != list(range(1, canonical['physical_cabinet_count'] + 1)):
            raise ValueError('Physical cabinets must be covered exactly once')
        if sorted(group_ids) != list(range(1, len(plan['groups']) + 1)):
            raise ValueError('Independent group identifiers must be unique and complete')
        if allocated and len(terminals) != len(set(terminals)):
            raise ValueError('Independent groups cannot share the same PCS')
        if plan.get('cabinet_group_max_count') != 12:
            raise ValueError('Cabinet group maximum must be 12')
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('Incomplete cabinet group contract') from exc
