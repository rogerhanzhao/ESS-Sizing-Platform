"""A diagram consumer must reconcile real DC inventory with AC assignments."""
from copy import deepcopy

import pytest

from calb_sizing_tool.adapters.session_state_adapter import build_dc_bom_handoff
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.services.dc_reduced_string_tail_service import restored_comparison
from calb_sizing_tool.services.dc_tail_ac_review_service import REVIEW_KEY
from calb_sizing_tool.services.dc_tail_preview_service import (
    _validate_ac_inventory, build_tail_sld_preview,
)
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from tests.test_dc_reduced_string_tail import example
from tests.test_dc_tail_ac_review import parent
from tests.test_dc_tail_preview import saved


@pytest.mark.parametrize('strings', [10, 8])
@pytest.mark.parametrize('admin', [False, True])
def test_actual_preview_carries_saved_inventory_without_averaging_or_adoption(example, strings, admin):
    source = parent(example, strings, admin=admin)
    output = saved(source)
    original = deepcopy((source, output))
    result = build_tail_sld_preview(source, output)
    comparison = restored_comparison(source)
    stage2 = comparison['snapshot']['stage2']
    inventory = result['dc_inventory']
    assert inventory['source_stage2_sha256'] == _hash_payload(stage2)
    assert [row['block_code'] for row in inventory['items']] == [
        row['block_code'] for row in stage2['block_config_items']]
    assert len({unit['unit_capacity_mwh'] for unit in inventory['units']}) == 2
    assert inventory['totals']['dc_nameplate_bol_mwh'] == stage2['dc_nameplate_bol_mwh']
    assert inventory['unit_ordinals_are_inventory_only'] is True
    assert inventory['electrical_mapping_provided'] is inventory['adoption_asserted'] is False
    result['dc_inventory']['items'][0]['count'] = 999
    assert (source, output) == original


@pytest.mark.parametrize('error', [
    'duplicate_physical_unit', 'missing_physical_id', 'unknown_product',
    'wrong_unit_energy', 'wrong_group_count', 'wrong_fleet_energy', 'missing_unit',
])
def test_inventory_rejects_ac_assignment_disagreement(example, error):
    source = parent(example)
    output = saved(source)
    review = deepcopy(output[REVIEW_KEY])
    comparison = restored_comparison(source)
    inventory = build_dc_bom_handoff(Stage2Result.model_validate(comparison['snapshot']['stage2']))
    tail = review['groups'][-1]['connections'][-1]
    if error == 'duplicate_physical_unit':
        tail['unit_id'] = review['groups'][0]['connections'][0]['unit_id']
    elif error == 'missing_physical_id':
        tail['unit_id'] = ' '
    elif error == 'unknown_product':
        tail['product_code'] = 'SAME-AH-BUT-UNRELATED-PRODUCT'
    elif error == 'wrong_unit_energy':
        tail['dc_energy_mwh'] = 5.016
    elif error == 'wrong_group_count':
        review['groups'][-1]['dc_count'] += 1
    elif error == 'wrong_fleet_energy':
        review['total_dc_energy_mwh'] += 1
    else:
        review['groups'][-1]['connections'].pop()
        review['groups'][-1]['dc_count'] -= 1
    with pytest.raises(ValueError):
        _validate_ac_inventory(inventory, review)


def test_inventory_order_does_not_invent_physical_or_electrical_position(example):
    source = parent(example)
    output = saved(source)
    comparison = restored_comparison(source)
    stage2 = Stage2Result.model_validate(comparison['snapshot']['stage2'])
    stage2.block_config_items.reverse()
    inventory = build_dc_bom_handoff(stage2)
    assert inventory['units'][0]['block_code'] == comparison['product_snapshot']['block_code']
    # Same products/quantities, but different BOM row order is not a wiring change.
    _validate_ac_inventory(inventory, output[REVIEW_KEY])
