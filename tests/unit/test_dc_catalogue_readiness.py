from copy import deepcopy

import pandas as pd
import pytest

from calb_sizing_tool.services.dc_catalogue_readiness_service import dc_catalogue_readiness


def catalogue():
    block = dict(block_code='C12', block_form='container', gross_energy_mwh=5.0,
                 product_cell_id='cell', is_active=True, is_published=True,
                 voltage_min_v=1000, voltage_max_v=1500, nominal_power_kw=2500,
                 max_current_a=2500, cells_in_series=416, strings_in_parallel=12,
                 default_degradation_curve_code='curve')
    snapshot = dict(dc_blocks=[block], cells=[dict(product_cell_id='cell', cell_code='314-A',
                    is_active=True, is_published=True)], degradation_curves=[dict(
                    curve_code='curve', product_cell_id='cell', is_active=True, is_published=True)])
    frame = pd.DataFrame([dict(Dc_Block_Code='C12', Dc_Block_Name='12 string', Block_Form='container',
                              Block_Nameplate_Capacity_Mwh=5, Is_Active=1, Is_Default_Option=1)])
    return snapshot, frame


def test_review_is_read_only_and_does_not_claim_duty_approval():
    snapshot, frame = catalogue()
    before = deepcopy(snapshot)
    frame_before = frame.copy(deep=True)
    row = dc_catalogue_readiness(snapshot, frame)[0]
    assert row['Current search'] == 'Selected by current picker'
    assert 'not verified' in row['Curve linkage']
    assert 'engineering review still required' in row['Parameter review']
    assert snapshot == before
    pd.testing.assert_frame_equal(frame, frame_before)


def test_active_unpublished_remains_current_picker_candidate():
    snapshot, frame = catalogue()
    snapshot['dc_blocks'][0]['is_published'] = False
    frame['Is_Default_Option'] = 0
    row = dc_catalogue_readiness(snapshot, frame)[0]
    assert row['Published'] is False
    assert row['Current search'] == 'Selected by current picker'


def test_published_smaller_variant_is_not_enumerated_by_current_picker():
    snapshot, frame = catalogue()
    snapshot['dc_blocks'].append(dict(snapshot['dc_blocks'][0], block_code='C8', gross_energy_mwh=3.3))
    frame.loc[1] = ['C8', '8 string', 'container', 3.3, 1, 1]
    rows = dc_catalogue_readiness(snapshot, frame)
    assert rows[1]['Current search'] == 'Active; not selected by current picker'


@pytest.mark.parametrize('value', [None, 0, -1, float('nan'), float('inf')])
def test_c_rate_cannot_replace_missing_power_or_current(value):
    snapshot, frame = catalogue()
    snapshot['dc_blocks'][0].update(nominal_power_kw=value, max_current_a=value, max_c_rate=0.5)
    issues = dc_catalogue_readiness(snapshot, frame)[0]['Parameter review']
    assert 'continuous power rating required' in issues
    assert 'current limit required' in issues


def test_same_ah_is_not_cell_identity():
    snapshot, frame = catalogue()
    snapshot['degradation_curves'][0]['product_cell_id'] = 'other-314-cell'
    row = dc_catalogue_readiness(snapshot, frame)[0]
    assert row['Curve linkage'] == 'Cell linkage mismatch'


def test_inactive_cell_and_curve_are_explained():
    snapshot, frame = catalogue()
    snapshot['cells'][0]['is_active'] = False
    snapshot['degradation_curves'][0]['is_published'] = False
    issues = dc_catalogue_readiness(snapshot, frame)[0]['Parameter review']
    assert 'Linked cell is inactive' in issues
    assert 'curve is inactive or unpublished' in issues


def test_invalid_window_and_form_are_not_silently_approved():
    snapshot, frame = catalogue()
    snapshot['dc_blocks'][0].update(block_form='unknown', voltage_min_v=1600)
    issues = dc_catalogue_readiness(snapshot, frame)[0]['Parameter review']
    assert 'falls back to container' in issues
    assert 'minimum must be below maximum' in issues


def test_empty_library():
    assert dc_catalogue_readiness({}, pd.DataFrame()) == []
