"""Report data must come from the saved run, never a default or a second sizing."""
import json

import pytest

from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot, RunInputSnapshotSchema
from calb_sizing_tool.schemas.stage1 import Stage1Result
from calb_sizing_tool.schemas.stage2 import Stage2ConfigItem, Stage2Result
from calb_sizing_tool.schemas.stage3 import Stage3Meta, Stage3Result, Stage3YearRecord
from calb_sizing_tool.services.cabinet_report_data_service import build_cabinet_report_data
from tests.test_cabinet_sld_renderer import cabinet_output


@pytest.fixture
def saved_cabinet():
    case = dict(project_name='Saved case project', scenario_id='cabinet_only', poi_power_req_mw=8.0,
                poi_energy_req_mwh=16.0, poi_nominal_voltage_kv=33.0, poi_frequency_hz=50.0,
                project_life_years=20, cycles_per_year=365, poi_guarantee_year=4,
                sc_time_months=3, dod_pct=95.0, dc_round_trip_efficiency_pct=94.0)
    stage1 = Stage1Result(
        project_name='Saved case project', poi_power_req_mw=8.0, poi_energy_req_mwh=16.0,
        project_life_years=20, cycles_per_year=365, poi_guarantee_year=4,
        eff_dc_cables_frac=.995, eff_pcs_frac=.985, eff_mvt_frac=.995,
        eff_ac_cables_sw_rmu_frac=.992, eff_hvt_others_frac=1.0, eff_dc_to_poi_frac=.967373228,
        sc_time_months=3, sc_loss_pct=2.0, sc_loss_frac=.02, dod_frac=.95,
        dc_round_trip_efficiency_frac=.94, dc_rte_base_frac=.94, dc_rte_effective_frac=.94,
        rte_curve_adjust_pp=0, rte_adjust_frac=0, rte_monotonic_enforce=True,
        dc_one_way_efficiency_frac=.9695359714832658, dc_usable_bol_frac=.9210591729091024,
        dc_energy_capacity_required_mwh=18.32366362820637, dc_power_required_mw=8.269817448369576,
    )
    stage2 = Stage2Result(
        mode='cabinet_only', dc_nameplate_bol_mwh=20.064, oversize_mwh=1.7403363717936315,
        config_adjustment_frac=.09497753326549074, container_count=0, cabinet_count=48, busbars_needed=5,
        block_config_items=[Stage2ConfigItem(
            block_code='CALB_0.418MWh_CAB_8P', block_name='Saved 418 kWh cabinet', form='cabinet',
            unit_capacity_mwh=.418, count=48, subtotal_mwh=20.064, total_dc_nameplate_bol_mwh=20.064)],
    )
    # A declared fixture, not a degradation model. The Year 4 record below is
    # copied verbatim from the read-only local 48-cabinet snapshot.
    annual = []
    for year in range(21):
        annual.append(Stage3YearRecord(
            year_index=year, soh_relative=1.0, soh_absolute=.98, dc_nameplate_bol_mwh=20.064,
            dc_gross_capacity_mwh=19.66272, dc_usable_mwh=18.023620756733514,
            dc_rte_frac=.931, system_rte_frac=.8712400058558113,
            poi_usable_energy_mwh=17.435568191689104, meets_poi_req=True,
            is_guarantee_year=year == 4, soh_display_pct=100.0, soh_absolute_pct=98.0,
            dc_rte_pct=93.1, system_rte_pct=87.12400058558113,
        ))
    annual[4] = Stage3YearRecord(
        year_index=4, soh_relative=.927, soh_absolute=.9087529688049976,
        dc_nameplate_bol_mwh=20.064, dc_gross_capacity_mwh=18.22734144,
        dc_usable_mwh=16.707896441491968, dc_rte_frac=.9299999999999999,
        system_rte_frac=.8703041948935601, poi_usable_energy_mwh=16.1627717136958,
        meets_poi_req=True, is_guarantee_year=True, soh_display_pct=92.7,
        soh_absolute_pct=90.87529688049976, dc_rte_pct=93.0, system_rte_pct=87.03041948935602,
    )
    meta = Stage3Meta(
        poi_power_mw=8, dc_power_mw=8.269817448369576, effective_c_rate=.41217192226722366,
        soh_profile_id=4, rte_profile_id=2, chosen_soh_c_rate=.33, chosen_soh_cycles_per_year=365,
        chosen_rte_c_rate=.33, rte_adjust_pp=0, rte_monotonic_enforce=True,
        dc_usable_bol_mwh=18.391449751768892, dc_usable_cod_mwh=18.023620756733514,
    )
    bundle = DcRunBundle(
        run_id='private-dc-run-uuid', project_id='private-project-uuid',
        project_name='Saved project', project_code='PROJECT-48', case_name='Saved case', case_code='CASE-01',
        sizing_case_id='private-case-uuid', scenario_mode='container_only',
        input_snapshot=RunInputSnapshotSchema(snapshot_kind='dc_case_input', payload={
            'case_input': case,
            'defaults': {'project_name': 'Wrong defaults', 'poi_power_req_mw': 100,
                         'poi_guarantee_year': 0, 'dod_pct': .99, 'sc_loss_pct': float('nan')},
        }),
        snapshot=DcPipelineRunSnapshot(
            stage1=stage1, stage2=stage2, stage3=Stage3Result(rows=annual, meta=meta),
            summary={'scenario_id': 'cabinet_only'}, iteration_count=5, converged=True,
            poi_usable_energy_mwh_at_guarantee_year=16.1627717136958,
        ),
    )
    ac = cabinet_output()
    ac.update(source_run_id=bundle.run_id, source_ac_run_id='private-session-token',
              poi_power_mw=8.0, poi_energy_mwh=16.0)
    return bundle, ac


def test_copies_saved_values_without_defaults_rounding_rendering_or_sizing(saved_cabinet, monkeypatch):
    bundle, ac = saved_cabinet
    import calb_diagrams.cabinet_sld as renderer
    import calb_sizing_tool.infra.db.session as db
    import calb_sizing_tool.services.dc_pipeline_service as sizing

    def forbidden(*args, **kwargs):
        pytest.fail('Report data conversion must not render, access a database, or size equipment')

    monkeypatch.setattr(renderer, 'render_cabinet_sld', forbidden)
    monkeypatch.setattr(db, 'session_scope', forbidden)
    monkeypatch.setattr(sizing, 'size_with_guarantee', forbidden)
    before = json.dumps(bundle.model_dump(), sort_keys=True)
    data = build_cabinet_report_data(bundle, ac, ac_alternative_label='B')
    assert data['project_name'] == 'Saved project'
    assert data['case_code'] == 'CASE-01' and data['ac_alternative_label'] == 'B'
    assert data['poi_power_mw'] == 8.0 and data['poi_energy_mwh'] == 16.0
    assert data['poi_guarantee_year'] == 4 and data['dod_pct'] == 95.0
    assert data['dc_round_trip_efficiency_pct'] == 94.0
    assert data['dc_total_mwh'] == 20.064 and data['physical_cabinet_count'] == 48
    assert data['annual_rows'] == [row.model_dump() for row in bundle.snapshot.stage3.rows]
    assert data['stage1'] == bundle.snapshot.stage1.model_dump()
    assert data['stage3_meta'] == bundle.snapshot.stage3.meta.model_dump()
    assert data['annual_rows'][4]['poi_usable_energy_mwh'] == 16.1627717136958
    assert data['annual_rows'][4]['soh_absolute_pct'] == 90.87529688049976
    assert data['annual_rows'][4]['system_rte_pct'] == 87.03041948935602
    assert data['annual_rows'][0]['soh_display_pct'] == 100.0
    assert data['annual_rows'][0]['soh_absolute_pct'] == 98.0
    assert 'private-' not in json.dumps(data)
    assert 'source_run_id' not in data and 'source_ac_run_id' not in data
    assert before == json.dumps(bundle.model_dump(), sort_keys=True)
    json.dumps(data, allow_nan=False)  # Defaults contain NaN; report output must not.
    data['annual_rows'][0]['soh_display_pct'] = 0
    assert bundle.snapshot.stage3.rows[0].soh_display_pct == 100.0


@pytest.mark.parametrize('field,value', [
    ('poi_power_mw', 9.0), ('poi_energy_mwh', 17.0), ('source_run_id', 'different-parent'),
])
def test_ac_parent_and_poi_requirement_mismatch_are_rejected(saved_cabinet, field, value):
    bundle, ac = saved_cabinet
    ac[field] = value
    with pytest.raises(ValueError):
        build_cabinet_report_data(bundle, ac)


@pytest.mark.parametrize('location', ['case', 'stage2', 'summary'])
def test_scenarios_must_agree_with_the_saved_cabinet_run(saved_cabinet, location):
    bundle, ac = saved_cabinet
    if location == 'case':
        bundle.input_snapshot.payload['case_input']['scenario_id'] = 'container_only'
    elif location == 'stage2':
        bundle.snapshot.stage2.mode = 'hybrid'
    else:
        bundle.snapshot.summary['scenario_id'] = 'container_only'
    with pytest.raises(ValueError, match='cabinet_only'):
        build_cabinet_report_data(bundle, ac)


@pytest.mark.parametrize('field,value', [
    ('cabinet_count', 47), ('container_count', 1), ('dc_nameplate_bol_mwh', 20.065),
])
def test_saved_physical_dc_configuration_must_match_ac_contract(saved_cabinet, field, value):
    bundle, ac = saved_cabinet
    setattr(bundle.snapshot.stage2, field, value)
    with pytest.raises(ValueError):
        build_cabinet_report_data(bundle, ac)


@pytest.mark.parametrize('field,value', [
    ('block_code', 'CALB-418KWH-DC-CABINET-314AH'), ('form', 'container'),
    ('unit_capacity_mwh', .417), ('count', 47), ('subtotal_mwh', 19.0),
])
def test_saved_dc_product_identity_and_energy_are_checked(saved_cabinet, field, value):
    bundle, ac = saved_cabinet
    setattr(bundle.snapshot.stage2.block_config_items[0], field, value)
    with pytest.raises(ValueError):
        build_cabinet_report_data(bundle, ac)


def test_existing_cabinet_sld_validation_rejects_conflicting_pcs_mirror(saved_cabinet):
    bundle, ac = saved_cabinet
    ac['pcs_count_by_block'] = [1, 3]
    with pytest.raises(ValueError, match='PCS count by block'):
        build_cabinet_report_data(bundle, ac)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'wrong_marker', 'two_markers', 'no_marker'])
def test_annual_year_coverage_and_guarantee_marker_must_be_complete(saved_cabinet, change):
    bundle, ac = saved_cabinet
    rows = bundle.snapshot.stage3.rows
    if change == 'missing':
        rows.pop()
    elif change == 'duplicate':
        rows[-1].year_index = 19
    elif change == 'wrong_marker':
        rows[4].is_guarantee_year = False
        rows[3].is_guarantee_year = True
    elif change == 'two_markers':
        rows[3].is_guarantee_year = True
    else:
        rows[4].is_guarantee_year = False
    with pytest.raises(ValueError, match='annual'):
        build_cabinet_report_data(bundle, ac)


@pytest.mark.parametrize('location', ['case', 'annual', 'stage1', 'stage3_meta', 'frequency'])
def test_nonfinite_values_never_enter_report_data(saved_cabinet, location):
    bundle, ac = saved_cabinet
    if location == 'case':
        bundle.input_snapshot.payload['case_input']['dod_pct'] = float('nan')
    elif location == 'annual':
        bundle.snapshot.stage3.rows[0].poi_usable_energy_mwh = float('nan')
    elif location == 'stage1':
        bundle.snapshot.stage1.eff_dc_cables_frac = float('inf')
    elif location == 'stage3_meta':
        bundle.snapshot.stage3.meta.effective_c_rate = float('-inf')
    else:
        bundle.input_snapshot.payload['case_input']['poi_frequency_hz'] = float('inf')
    with pytest.raises(ValueError, match='finite'):
        build_cabinet_report_data(bundle, ac)


def test_incomplete_case_does_not_silently_use_workbook_defaults(saved_cabinet):
    bundle, ac = saved_cabinet
    bundle.input_snapshot.payload['case_input'].pop('dod_pct')
    with pytest.raises(ValueError, match='Depth of discharge'):
        build_cabinet_report_data(bundle, ac)


def test_unrecorded_optional_voltage_and_frequency_remain_unknown(saved_cabinet):
    bundle, ac = saved_cabinet
    bundle.input_snapshot.payload['case_input'].pop('poi_nominal_voltage_kv')
    bundle.input_snapshot.payload['case_input']['poi_frequency_hz'] = None
    data = build_cabinet_report_data(bundle, ac)
    assert data['poi_nominal_voltage_kv'] is None and data['poi_frequency_hz'] is None


def test_conflicting_stage1_input_is_rejected_without_resizing(saved_cabinet):
    bundle, ac = saved_cabinet
    bundle.snapshot.stage1.poi_guarantee_year = 5
    with pytest.raises(ValueError, match='Stage 1'):
        build_cabinet_report_data(bundle, ac)


def test_guarantee_summary_must_refer_to_the_same_saved_annual_record(saved_cabinet):
    bundle, ac = saved_cabinet
    bundle.snapshot.poi_usable_energy_mwh_at_guarantee_year = 17.0
    with pytest.raises(ValueError, match='guarantee-year energy'):
        build_cabinet_report_data(bundle, ac)
