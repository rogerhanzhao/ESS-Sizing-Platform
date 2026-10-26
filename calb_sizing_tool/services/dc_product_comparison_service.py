"""Isolated single-container comparison. No selection, persistence or activation.

The frozen engine owns all sizing. This adapter validates evidence and every
possible container count within a deliberately bounded comparison budget.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

import pandas as pd

from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.dc_input_guard_service import validate_dc_inputs
from calb_sizing_tool.services.dc_pipeline_service import size_with_guarantee
from calb_sizing_tool.services.stage1_service import run_stage1, to_frac
from calb_sizing_tool.services.stage2_service import build_config_container_only, rebuild_stage2_counts
from calb_sizing_tool.services.stage3_service import select_soh_profile, select_rte_profile


def package_sha256(package: dict) -> str:
    return hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(not isinstance(value, bool), 'Boolean is not a numeric parameter')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Finite numeric evidence required') from exc
    _require(math.isfinite(result), 'Finite numeric evidence required')
    return result


def _between(value, lower, upper, label):
    value, lower, upper = map(_number, (value, lower, upper))
    _require(lower <= upper and lower <= value <= upper, f'{label} outside approved comparison scope')


def _fraction(value):
    numeric = _number(value)
    result = to_frac(numeric)
    _require(0 <= result <= 1, 'SOH/RTE values must normalize to fractions within [0, 1]')
    return result


def _frame(records, columns, label):
    _require(isinstance(records, list) and bool(records), f'{label} table is required')
    _require(all(isinstance(row, dict) for row in records), f'{label} rows must be objects')
    frame = pd.DataFrame(deepcopy(records))
    _require(set(columns).issubset(frame.columns), f'{label} columns are incomplete')
    for col in columns:
        frame[col] = frame[col].map(_number)
    for col in ('Profile_Id', 'Life_Year_Index', 'Cycles_Per_Year'):
        if col in frame:
            _require(all(v.is_integer() for v in frame[col]), f'{label} {col} must be integer')
            frame[col] = frame[col].astype(int)
    return frame


def _scope(records, profile_id, rate, cycles=None):
    _require(isinstance(records, list), 'Profile applicability evidence required')
    _require(all(isinstance(row, dict) for row in records), 'Invalid profile applicability record')
    matches = [r for r in records if _number(r.get('Profile_Id')) == profile_id]
    _require(len(matches) == 1, 'Exactly one applicability record per selected profile required')
    row = matches[0]
    _require(bool(str(row.get('evidence_ref') or '').strip()), 'Profile applicability reference required')
    _between(rate, row.get('c_rate_min'), row.get('c_rate_max'), 'Effective C-rate')
    if cycles is not None:
        _between(cycles, row.get('cycles_min'), row.get('cycles_max'), 'Cycles per year')


def _validate_tables(package, life, monotonic, adjust):
    tables = package.get('tables', {})
    _require(isinstance(tables, dict), 'Curve tables must be a mapping')
    sp = _frame(tables.get('soh_profile'), ['Profile_Id', 'C_Rate', 'Cycles_Per_Year'], 'SOH profile')
    sc = _frame(tables.get('soh_curve'), ['Profile_Id', 'Life_Year_Index', 'Soh_Dc_Pct'], 'SOH curve')
    rp = _frame(tables.get('rte_profile'), ['Profile_Id', 'C_Rate'], 'RTE profile')
    rc = _frame(tables.get('rte_curve'), ['Profile_Id', 'Soh_Band_Min_Pct', 'Soh_Band_Max_Pct', 'Rte_Dc_Pct'], 'RTE curve')
    for profiles, curves in ((sp, sc), (rp, rc)):
        _require(not profiles.Profile_Id.duplicated().any(), 'Duplicate profile IDs')
        _require((profiles.Profile_Id > 0).all() and (profiles.C_Rate > 0).all(), 'Positive profile IDs and rates required')
        _require(set(curves.Profile_Id) == set(profiles.Profile_Id), 'Profiles and curve rows must match')
    _require((sp.Cycles_Per_Year > 0).all(), 'Positive profile cycle frequency required')
    for pid in sp.Profile_Id:
        rows = sc[sc.Profile_Id == pid].sort_values('Life_Year_Index')
        _require(not rows.Life_Year_Index.duplicated().any(), 'Duplicate SOH years')
        _require((rows.Life_Year_Index >= 0).all(), 'Negative SOH year index')
        _require(set(range(life + 1)).issubset(set(rows.Life_Year_Index)), 'SOH year coverage incomplete')
        values = rows.Soh_Dc_Pct.map(_fraction)
        _require((values > 0).all() and values.is_monotonic_decreasing, 'Invalid SOH trajectory')
        _require(abs(_fraction(rows[rows.Life_Year_Index == 0].Soh_Dc_Pct.iloc[0]) - 1) < 1e-9,
                 'Relative SOH year zero must equal 100 percent')
    for pid in rp.Profile_Id:
        rows = rc[rc.Profile_Id == pid].copy()
        rows['_min'] = rows.Soh_Band_Min_Pct.map(_fraction)
        rows = rows.sort_values('_min', ascending=False)
        mins, maxes = rows['_min'], rows.Soh_Band_Max_Pct.map(_fraction)
        values = rows.Rte_Dc_Pct.map(_fraction)
        _require(not mins.duplicated().any() and (mins <= maxes).all(), 'Invalid RTE band limits')
        _require(((values + adjust > 0) & (values + adjust <= 1)).all(), 'RTE adjustment would clip or zero the source data')
        if monotonic:
            _require(values.is_monotonic_decreasing, 'RTE source data would be silently changed by monotonic enforcement')
    return sp, sc, rp, rc


def run_product_comparison(revision_service, revision_id, case_input: SizingCaseInput,
                           baseline, package: dict, expected_package_sha256: str, *,
                           temperature_c: float, standby_soc_pct: float, max_iter: int = 10,
                           allow_special_configurations: bool = False, special_reason: str = '') -> dict:
    """Return a comparison only after all preflight and convergence checks pass.

    The package is supplied by a trusted administrative caller with a separately
    recorded digest. A matching hash detects changes; it is not a signature or
    proof that the approval reference is authentic.
    """
    _require(type(max_iter) is int and 1 <= max_iter <= 60, 'Comparison budget must be 1..60 evaluations')
    _require(case_input.scenario_id.value == 'container_only', 'C1 supports single-type container comparison only')
    errors = validate_dc_inputs(case_input.model_dump(mode='python'))
    _require(not errors, '; '.join(errors))
    detail = revision_service.inspect(revision_id)
    _require(detail['candidate_review_current'], 'A current candidate parameter review is required')
    from calb_sizing_tool.services.dc_configuration_variant_service import DcConfigurationVariantService
    variant_service = DcConfigurationVariantService(revision_service.auth_user, revision_service.db_url)
    scope = variant_service.assert_comparison_scope(revision_id,
        allow_special_configurations=allow_special_configurations, special_reason=special_reason)
    product = detail['snapshot']['product']
    _require(product['block_form'] == 'container', 'C1 requires an explicit container product')
    _require(isinstance(package, dict), 'Curve package must be an object')
    package = deepcopy(package)
    _require(package_sha256(package) == expected_package_sha256, 'Curve package digest mismatch')
    _require(type(package.get('schema_version')) is int and package['schema_version'] == 1 and
             package.get('review_status') == 'comparison_approved',
             'Approved comparison package schema required')
    _require(package.get('product_revision_sha256') == detail['sha256'], 'Curve package revision mismatch')
    _require(package.get('product_cell_id') == product['product_cell_id'], 'Curve package cell mismatch')
    _require(package.get('measurement_boundary') == 'DC', 'DC-boundary RTE evidence required')
    for key in ('package_code', 'version', 'reviewed_by', 'approval_ref'):
        _require(bool(str(package.get(key) or '').strip()), f'{key} is required')
    bundle = deepcopy(baseline)
    stage1 = run_stage1(case_input.model_dump(mode='python'), bundle.defaults)
    # The editable case guard skips None fields; workbook defaults can supply
    # those values. Validate the normalized, actually consumed values as well.
    for field in ('eff_dc_cables_frac', 'eff_pcs_frac', 'eff_mvt_frac',
                  'eff_ac_cables_sw_rmu_frac', 'eff_hvt_others_frac',
                  'eff_dc_to_poi_frac', 'dod_frac', 'dc_round_trip_efficiency_frac',
                  'dc_rte_base_frac', 'dc_rte_effective_frac',
                  'dc_one_way_efficiency_frac', 'dc_usable_bol_frac'):
        value = _number(getattr(stage1, field))
        _require(0 < value <= 1, f'Normalized {field} must be within (0, 1]')
    _require(0 <= _number(stage1.sc_loss_frac) < 1, 'Invalid commissioning loss fraction')
    for value in (stage1.dc_power_required_mw, stage1.dc_energy_capacity_required_mwh,
                  stage1.eff_dc_to_poi_frac):
        _require(_number(value) > 0, 'Positive finite DC requirements and efficiency required')
    conditions = package.get('conditions', {})
    _require(isinstance(conditions, dict), 'Curve package conditions must be an object')
    _between(stage1.dod_frac * 100, conditions.get('dod_min_pct'), conditions.get('dod_max_pct'), 'DOD')
    _between(temperature_c, conditions.get('temperature_min_c'), conditions.get('temperature_max_c'), 'Temperature')
    _between(standby_soc_pct, conditions.get('standby_soc_min_pct'), conditions.get('standby_soc_max_pct'), 'Standby SOC')
    _require(0 <= _number(standby_soc_pct) <= 100, 'Standby SOC must be within 0..100 percent')
    _require(stage1.project_life_years <= _number(conditions.get('project_life_max_years')), 'Project life outside evidence horizon')
    _require(_number(conditions.get('rte_adjust_pp')) == stage1.rte_curve_adjust_pp, 'RTE adjustment not approved')
    _require(type(conditions.get('rte_monotonic_enforce')) is bool and
             conditions['rte_monotonic_enforce'] == stage1.rte_monotonic_enforce, 'RTE enforcement basis mismatch')
    sp, sc, rp, rc = _validate_tables(package, stage1.project_life_years,
                                     stage1.rte_monotonic_enforce, stage1.rte_adjust_frac)
    unit = product.get('gross_energy_mwh') or product['rated_capacity_kwh'] / 1000
    code, name = product['block_code'], product['block_name']
    bundle.df_blocks = pd.DataFrame([dict(Dc_Block_Code=code, Dc_Block_Name=name,
        Block_Form='container', Block_Nameplate_Capacity_Mwh=unit, Is_Active=1, Is_Default_Option=1)])
    bundle.df_soh_profile, bundle.df_soh_curve = sp, sc
    bundle.df_rte_profile, bundle.df_rte_curve = rp, rc
    config = build_config_container_only(stage1.dc_energy_capacity_required_mwh, unit, code, name)
    preflight = []
    for step in range(max_iter):
        if step:
            config.container_count += 1
            config = rebuild_stage2_counts(config, required_dc_mwh=stage1.dc_energy_capacity_required_mwh,
                container_code=code, container_name=name, container_unit=unit,
                cabinet_code='', cabinet_name='', cabinet_unit=0)
        _require(_number(config.dc_nameplate_bol_mwh) > 0, 'Rounded DC nameplate must remain positive')
        rate = stage1.dc_power_required_mw / config.dc_nameplate_bol_mwh
        scores = (sp.C_Rate - rate).abs() * 10 + (sp.Cycles_Per_Year - stage1.cycles_per_year).abs() / 365
        rte_scores = (rp.C_Rate - rate).abs()
        _require((scores == scores.min()).sum() == 1 and (rte_scores == rte_scores.min()).sum() == 1,
                 'Ambiguous nearest-profile tie; explicit package resolution required')
        sid, _, _ = select_soh_profile(rate, stage1.cycles_per_year, sp)
        rid, _ = select_rte_profile(rate, rp)
        _scope(package.get('soh_applicability'), sid, rate, stage1.cycles_per_year)
        _scope(package.get('rte_applicability'), rid, rate, stage1.cycles_per_year)
        if product.get('max_c_rate'):
            _require(rate <= _number(product['max_c_rate']), 'Product maximum C-rate exceeded')
        # Validate the row the frozen selector will actually use, including its
        # declared upper band, using raw SOH rather than the display rounding.
        bands = rc[rc.Profile_Id == rid].copy()
        bands['_min'] = bands.Soh_Band_Min_Pct.map(_fraction)
        bands['_max'] = bands.Soh_Band_Max_Pct.map(_fraction)
        bands = bands.sort_values('_min', ascending=False)
        for row in sc[(sc.Profile_Id == sid) & (sc.Life_Year_Index <= stage1.project_life_years)].itertuples():
            soh = _fraction(row.Soh_Dc_Pct)
            chosen = bands[bands['_min'] <= soh].head(1)
            _require(not chosen.empty and soh <= chosen['_max'].iloc[0], 'RTE SOH-band coverage gap')
        preflight.append(dict(container_count=config.container_count, effective_c_rate=rate,
                              soh_profile_id=sid, rte_profile_id=rid))
    result = size_with_guarantee(stage1, 'container_only', bundle, max_iter=max_iter)
    _require(result.converged, 'Comparison did not converge within the approved evaluation budget')
    final = preflight[result.iteration_count - 1]
    _require(result.stage2.container_count == final['container_count'] and
             result.stage3.meta.soh_profile_id == final['soh_profile_id'] and
             result.stage3.meta.rte_profile_id == final['rte_profile_id'] and
             abs(result.stage3.meta.effective_c_rate - final['effective_c_rate']) < 1e-12,
             'Frozen output does not match the validated comparison path')
    _require(result.stage2.container_count * product['nominal_power_kw'] / 1000 >= stage1.dc_power_required_mw,
             'Installed DC product continuous power is insufficient')
    current = revision_service.inspect(revision_id)
    _require(current['candidate_review_current'] and current['sha256'] == detail['sha256'],
             'Product review changed during comparison')
    _require(variant_service.assert_comparison_scope(revision_id,
        allow_special_configurations=allow_special_configurations, special_reason=special_reason) == scope,
        'Configuration relation changed during comparison')
    return dict(snapshot=result, comparison_only=True, downstream_ready=False, preflight=preflight,
        provenance=dict(product_code=code, revision_id=revision_id, revision_sha256=detail['sha256'],
            product_cell_id=product['product_cell_id'], package_code=package['package_code'],
            package_version=package['version'], package_sha256=expected_package_sha256,
            approval_ref=package['approval_ref'], temperature_c=temperature_c,
            standby_soc_pct=standby_soc_pct, max_iter=max_iter, configuration_scope=scope))
