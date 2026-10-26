"""Reject ambiguous POI boundaries without changing a signed DC comparison."""
from copy import deepcopy

import pytest

from calb_sizing_tool.services.dc_ac_allocation_service import assess_dc_ac_allocation
from calb_sizing_tool.services.dc_ac_equipment_assessment_service import assess_dc_ac_equipment
from tests.dc_ac_allocation_fixture import resign_comparison
from tests.dc_ac_equipment_fixture import make_equipment_fixture, replace_equipment_package


def assess(study):
    return assess_dc_ac_equipment(
        study.lib.revisions, study.comparison, study.allocation,
        study.capability_service,
        expected_comparison_sha256=study.expected_comparison_sha256,
        duty_basis=study.duty_basis, variant_service=study.lib.variants,
    )


def test_valid_dc_side_comparison_is_not_an_ac_poi_equipment_duty(tmp_path):
    # Compute a genuine C2b DC-side source with the unchanged Stage1/3 path.
    # Do not relabel an existing AC calculation or infer its boundary from 100%.
    study = make_equipment_fixture(
        tmp_path / 'dc-side.sqlite', case_overrides={'poi_is_dc_side': True})
    original = deepcopy(study.comparison)
    mapping = assess_dc_ac_allocation(
        study.lib.revisions, study.comparison, study.allocation,
        expected_comparison_sha256=study.expected_comparison_sha256,
        variant_service=study.lib.variants,
    )
    assert mapping['topology_valid'] is True
    assert study.comparison['case_input']['poi_is_dc_side'] is True
    with pytest.raises(ValueError, match='explicitly AC-side POI'):
        assess(study)
    assert study.comparison == original


@pytest.mark.parametrize('boundary', ['missing', None, 0, 1, 'false', 'true'])
def test_missing_or_untyped_poi_boundary_is_not_defaulted_to_ac(tmp_path, boundary):
    study = make_equipment_fixture(tmp_path / 'unknown-boundary.sqlite')
    if boundary == 'missing':
        study.comparison['case_input'].pop('poi_is_dc_side')
    else:
        study.comparison['case_input']['poi_is_dc_side'] = boundary
    # Synthetic content identities are deliberately recomputed here to test the
    # boundary guard after digest verification, not merely a hash mismatch.
    resign_comparison(study.comparison)
    study.expected_comparison_sha256 = study.comparison['comparison_sha256']
    study.allocation['source']['candidate_comparison_sha256'] = study.expected_comparison_sha256
    with pytest.raises(ValueError, match='explicitly AC-side POI'):
        assess(study)


def test_explicit_ac_side_with_loss_free_assumptions_keeps_its_boundary(tmp_path):
    study = make_equipment_fixture(tmp_path / 'ac-side.sqlite')
    assert study.comparison['case_input']['poi_is_dc_side'] is False
    result = assess(study)
    assert result['power_boundaries']['signed_poi_chain_conserved'] is True
    assert result['power_boundaries']['poi_reference_kw'] == pytest.approx(2000)
    assert result['downstream_ready'] is False


def test_tbd_project_frequency_cannot_be_replaced_by_model_default(tmp_path):
    study = make_equipment_fixture(
        tmp_path / 'tbd.sqlite', case_overrides={'poi_frequency_option': 'TBD'})
    assert study.comparison['case_input']['poi_frequency_hz'] == 50
    with pytest.raises(ValueError, match='TBD selection cannot use a default frequency'):
        assess(study)


def test_sixty_hz_source_checks_each_piece_of_equipment_against_sixty_hz(tmp_path):
    study = make_equipment_fixture(
        tmp_path / 'sixty-hz.sqlite',
        case_overrides={'poi_frequency_hz': 60.0, 'poi_frequency_option': 60.0,
                        'poi_nominal_voltage_kv': 22.0})
    result = assess(study)
    frequency_checks = [row for row in result['checks'] if row['check'] == 'project_frequency']
    assert len(frequency_checks) == 3
    assert all(row['required'] == 60 and row['declared'] == 50
               and row['status'] == 'fail' for row in frequency_checks)
    for identity in study.capability_packages.copy():
        replace_equipment_package(study, identity,
            lambda package: package['conditions'].update(frequency_hz=60))
    result = assess(study)
    assert all(row['required'] == 60 and row['declared'] == 60 and row['status'] == 'pass'
               for row in result['checks'] if row['check'] == 'project_frequency')
    # The independently declared equipment MV bus is not silently changed to
    # project POI voltage. They can be distinct electrical boundaries.
    assert result['duty_basis']['mv_bus_voltage_kv'] == 33
    assert result['downstream_ready'] is False


@pytest.mark.parametrize('option', [60.0, '60', True, 'unknown', 'inf'])
def test_inconsistent_or_invalid_frequency_selection_is_rejected(tmp_path, option):
    study = make_equipment_fixture(
        tmp_path / 'frequency-conflict.sqlite', case_overrides={'poi_frequency_option': option})
    assert study.comparison['case_input']['poi_frequency_hz'] == 50
    with pytest.raises(ValueError, match='selected project frequency must match'):
        assess(study)
