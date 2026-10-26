"""Local fixed-BOM lifetime comparison using unchanged Stage 1 / Stage 3.

This is a separate experimental comparison contract, never an existing scenario,
guarantee search, adopted run or AC design. Only independently approved products
with identical numerical curve tables can share the frozen aggregate Stage 3.
"""
from __future__ import annotations

from copy import deepcopy
import math

from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.services.dc_composition_manifest_service import build_dc_composition_manifest
from calb_sizing_tool.services.dc_configuration_variant_service import DcConfigurationVariantService
from calb_sizing_tool.services.dc_input_guard_service import validate_dc_inputs
from calb_sizing_tool.services.dc_product_comparison_service import (
    _between, _fraction, _number, _require, _scope, _validate_tables,
    package_sha256, run_product_comparison,
)
from calb_sizing_tool.services.stage1_service import run_stage1
from calb_sizing_tool.services.stage2_service import _build_items
from calb_sizing_tool.services.stage3_service import run_stage3, select_soh_profile, select_rte_profile

_NUMERIC_COLUMNS = (
    ['Profile_Id', 'C_Rate', 'Cycles_Per_Year'],
    ['Profile_Id', 'Life_Year_Index', 'Soh_Dc_Pct'],
    ['Profile_Id', 'C_Rate'],
    ['Profile_Id', 'Soh_Band_Min_Pct', 'Soh_Band_Max_Pct', 'Rte_Dc_Pct'],
)


def _stage1(case_input, baseline):
    _require(case_input.scenario_id.value == 'container_only', 'Container-only comparison input required')
    errors = validate_dc_inputs(case_input.model_dump(mode='python'))
    _require(not errors, '; '.join(errors))
    result = run_stage1(case_input.model_dump(mode='python'), baseline.defaults)
    for field in ('eff_dc_cables_frac', 'eff_pcs_frac', 'eff_mvt_frac',
                  'eff_ac_cables_sw_rmu_frac', 'eff_hvt_others_frac', 'eff_dc_to_poi_frac',
                  'dod_frac', 'dc_round_trip_efficiency_frac', 'dc_rte_base_frac',
                  'dc_rte_effective_frac', 'dc_one_way_efficiency_frac', 'dc_usable_bol_frac'):
        _require(0 < _number(getattr(result, field)) <= 1, f'Normalized {field} must be within (0, 1]')
    _require(0 <= _number(result.sc_loss_frac) < 1, 'Invalid commissioning loss fraction')
    for value in (result.dc_power_required_mw, result.dc_energy_capacity_required_mwh):
        _require(_number(value) > 0, 'Positive finite DC requirements required')
    return result


def _package(detail, package, digest, stage1, temperature_c, standby_soc_pct):
    _require(isinstance(package, dict), 'Each product requires its own curve package')
    _require(package_sha256(package) == digest, 'Curve package digest mismatch')
    _require(type(package.get('schema_version')) is int and package['schema_version'] == 1
             and package.get('review_status') == 'comparison_approved', 'Approved comparison package schema required')
    product = detail['snapshot']['product']
    _require(package.get('product_revision_sha256') == detail['sha256'], 'Curve package revision mismatch')
    _require(package.get('product_cell_id') == product['product_cell_id'], 'Curve package cell mismatch')
    _require(package.get('measurement_boundary') == 'DC', 'DC-boundary RTE evidence required')
    for field in ('package_code', 'version', 'reviewed_by', 'approval_ref'):
        _require(isinstance(package.get(field), str) and bool(package[field].strip()), f'{field} is required')
    conditions = package.get('conditions')
    _require(isinstance(conditions, dict), 'Curve package conditions must be an object')
    _between(stage1.dod_frac * 100, conditions.get('dod_min_pct'), conditions.get('dod_max_pct'), 'DOD')
    _between(temperature_c, conditions.get('temperature_min_c'), conditions.get('temperature_max_c'), 'Temperature')
    _between(standby_soc_pct, conditions.get('standby_soc_min_pct'), conditions.get('standby_soc_max_pct'), 'Standby SOC')
    _require(0 <= _number(standby_soc_pct) <= 100, 'Standby SOC must be within 0..100 percent')
    _require(stage1.project_life_years <= _number(conditions.get('project_life_max_years')), 'Project life outside evidence horizon')
    _require(_number(conditions.get('rte_adjust_pp')) == stage1.rte_curve_adjust_pp, 'RTE adjustment not approved')
    _require(type(conditions.get('rte_monotonic_enforce')) is bool
             and conditions['rte_monotonic_enforce'] == stage1.rte_monotonic_enforce, 'RTE enforcement basis mismatch')
    return _validate_tables(package, stage1.project_life_years,
                            stage1.rte_monotonic_enforce, stage1.rte_adjust_frac)


def _profiles(package, tables, stage1, product, rate):
    sp, sc, rp, rc = tables
    scores = (sp.C_Rate - rate).abs() * 10 + (sp.Cycles_Per_Year - stage1.cycles_per_year).abs() / 365
    rte_scores = (rp.C_Rate - rate).abs()
    _require((scores == scores.min()).sum() == 1 and (rte_scores == rte_scores.min()).sum() == 1,
             'Ambiguous nearest-profile tie; explicit package resolution required')
    sid, _, _ = select_soh_profile(rate, stage1.cycles_per_year, sp)
    rid, _ = select_rte_profile(rate, rp)
    _scope(package.get('soh_applicability'), sid, rate, stage1.cycles_per_year)
    _scope(package.get('rte_applicability'), rid, rate, stage1.cycles_per_year)
    maximum = product.get('max_c_rate')
    if maximum is not None:
        _require(_number(maximum) > 0 and rate <= _number(maximum), 'Product maximum C-rate exceeded')
    bands = rc[rc.Profile_Id == rid].copy()
    bands['_min'], bands['_max'] = bands.Soh_Band_Min_Pct.map(_fraction), bands.Soh_Band_Max_Pct.map(_fraction)
    bands = bands.sort_values('_min', ascending=False)
    for row in sc[(sc.Profile_Id == sid) & (sc.Life_Year_Index <= stage1.project_life_years)].itertuples():
        soh = _fraction(row.Soh_Dc_Pct)
        chosen = bands[bands['_min'] <= soh].head(1)
        _require(not chosen.empty and soh <= chosen['_max'].iloc[0], 'RTE SOH-band coverage gap')
    return sid, rid


def evaluate_dc_composition(revision_service, lines, case_input, baseline,
                            curve_packages, registered_package_sha256, *,
                            variant_service=None, allow_special_configurations=False, special_reason='',
                            temperature_c, standby_soc_pct, electrical_partitions=None):
    """Evaluate an explicit BOM; no search, growth, persistence or adoption."""
    case_input, baseline = deepcopy(case_input), deepcopy(baseline)
    variant_service = variant_service or DcConfigurationVariantService(
        revision_service.auth_user, revision_service.db_url)
    manifest = build_dc_composition_manifest(revision_service, deepcopy(lines),
        variant_service=variant_service, allow_special_configurations=allow_special_configurations,
        special_reason=special_reason, electrical_partitions=deepcopy(electrical_partitions))
    tails = [row for row in manifest['bom'] if row['strings_in_parallel'] != 12]
    _require(len(tails) <= 1 and all(row['quantity'] == 1 for row in tails),
             'C2b is limited to one tail container of one reduced-string specification')
    _require(manifest['capability_gates']['product_reviews'], 'Current product and parent-child parameter reviews required')
    stage1 = _stage1(case_input, baseline)
    selected_order = [row['revision_id'] for row in manifest['bom']]
    selected = set(selected_order)
    _require(isinstance(curve_packages, dict) and set(curve_packages) == selected,
             'Exactly one curve package per selected product revision required')
    _require(isinstance(registered_package_sha256, dict) and set(registered_package_sha256) == selected,
             'Separately registered digests must cover exactly the selected product revisions')
    packages = deepcopy(curve_packages)
    registered_package_sha256 = deepcopy(registered_package_sha256)
    details, scopes, tables, evidence = {}, {}, {}, []
    for row in manifest['bom']:
        revision = row['revision_id']
        detail = revision_service.inspect(revision)
        _require(detail['candidate_review_current'] and detail['sha256'] == row['revision_sha256'],
                 'Product review changed before composition evaluation')
        details[revision] = detail
        scopes[revision] = variant_service.assert_comparison_scope(revision,
            allow_special_configurations=allow_special_configurations, special_reason=special_reason)
        tables[revision] = _package(detail, packages[revision], registered_package_sha256[revision],
                                     stage1, temperature_c, standby_soc_pct)
        evidence.append(dict(product_code=row['product_code'], revision_id=revision,
            revision_sha256=detail['sha256'], package_code=packages[revision]['package_code'],
            package_version=packages[revision]['version'], package_sha256=registered_package_sha256[revision],
            approval_ref=packages[revision]['approval_ref'], configuration_scope=scopes[revision]))
    anchor = manifest['bom'][0]['revision_id']
    for revision in selected_order:
        _require(all(left[columns].equals(right[columns])
                     for left, right, columns in zip(tables[anchor], tables[revision], _NUMERIC_COLUMNS)),
                 'C2b requires identical numerical SOH/RTE tables independently approved for every product; '
                 'different curves require a separate evaluation contract')
    # Use the frozen record builder, including its existing 3-decimal total.
    # The raw physical BOM and its signature remain unchanged alongside it.
    items = _build_items([{'Block Code': row['product_code'], 'Block Name': row['product_name'],
        'Form': 'container', 'Unit Capacity (MWh)': row['unit_gross_energy_mwh'],
        'Count': row['quantity']} for row in manifest['bom']])
    total = _number(items[0].total_dc_nameplate_bol_mwh)
    _require(total > 0, 'Rounded comparison energy must remain positive')
    stage2 = Stage2Result(mode='composition_comparison_only', dc_nameplate_bol_mwh=total,
        oversize_mwh=total - stage1.dc_energy_capacity_required_mwh,
        config_adjustment_frac=total / stage1.dc_energy_capacity_required_mwh - 1,
        block_config_items=items, container_count=manifest['total_container_count'], cabinet_count=0, busbars_needed=0)
    model_rate = stage1.dc_power_required_mw / total
    physical_rate = stage1.dc_power_required_mw / manifest['total_gross_energy_mwh']
    profiles = None
    for revision in selected_order:
        product = details[revision]['snapshot']['product']
        model_profiles = _profiles(packages[revision], tables[revision], stage1, product, model_rate)
        physical_profiles = _profiles(packages[revision], tables[revision], stage1, product, physical_rate)
        _require(model_profiles == physical_profiles, 'Source precision changes profile selection between raw and rounded energy')
        if profiles is None:
            profiles = model_profiles
        _require(model_profiles == profiles, 'Common curve profile selection is inconsistent')
    bundle = deepcopy(baseline)
    bundle.df_soh_profile, bundle.df_soh_curve, bundle.df_rte_profile, bundle.df_rte_curve = tables[anchor]
    from calb_sizing_tool.services.dc_composition_dispatch_service import assess_proportional_dc_dispatch
    dispatch = assess_proportional_dc_dispatch(manifest, details,
                                               dc_power_required_mw=stage1.dc_power_required_mw)
    stage3 = run_stage3(stage1, stage2, bundle)
    _require(stage3.meta.soh_profile_id == profiles[0] and stage3.meta.rte_profile_id == profiles[1]
             and math.isclose(stage3.meta.effective_c_rate, model_rate, rel_tol=0, abs_tol=1e-12),
             'Frozen output does not match the validated comparison basis')
    for record in stage3.rows:
        _require(math.isfinite(record.poi_usable_energy_mwh), 'Nonfinite comparison output')
    poi_energy = next(row.poi_usable_energy_mwh for row in stage3.rows
                      if row.year_index == stage1.poi_guarantee_year)
    for revision in selected_order:
        current = revision_service.inspect(revision)
        _require(current['candidate_review_current'] and current['sha256'] == details[revision]['sha256'],
                 'Product review changed during composition evaluation')
        _require(variant_service.assert_comparison_scope(revision,
            allow_special_configurations=allow_special_configurations, special_reason=special_reason) == scopes[revision],
            'Configuration relation changed during composition evaluation')
    result = dict(contract_version=1, comparison_only=True, downstream_ready=False,
        dispatch_policy='proportional_to_raw_dc_nameplate_energy', common_curve_requirement=True,
        stage1=stage1, stage2=stage2, stage3=stage3, manifest=manifest, dispatch=dispatch,
        raw_dc_nameplate_mwh=manifest['total_gross_energy_mwh'], model_dc_nameplate_mwh=total,
        physical_c_rate=physical_rate, model_c_rate=model_rate,
        guarantee_year=stage1.poi_guarantee_year, poi_energy_at_guarantee_year_mwh=poi_energy,
        meets_guarantee_year_energy=poi_energy + 1e-6 >= stage1.poi_energy_req_mwh,
        dc_duty_status=dispatch['status'], ac_power_matching_pending=True,
        evidence=evidence, case_input=case_input.model_dump(mode='json'),
        assumptions=['Static DC discharge power proportional to raw BOL nameplate energy.',
                     'Identical numerical curves independently applicable to each product revision.',
                     'Frozen Stage 3 energy conventions and Stage 2 total rounding retained.',
                     'No PCS mapping, AC feasibility, charge-duty or control dispatch validation.'])
    result['comparison_sha256'] = package_sha256({key: value.model_dump(mode='json')
        if hasattr(value, 'model_dump') else value for key, value in result.items()})
    return result


def run_tail_replacement_comparison(revision_service, parent_revision_id, child_revision_ids,
                                     case_input, baseline, curve_packages, registered_package_sha256, *,
                                     allow_special_configurations=False, special_reason='',
                                     temperature_c, standby_soc_pct, max_iter=10, electrical_partitions=None):
    """Anchor the bounded alternatives to a converged unchanged C1 parent run."""
    from calb_sizing_tool.services.dc_tail_candidate_service import plan_tail_replacement_candidates
    case_input, baseline = deepcopy(case_input), deepcopy(baseline)
    _require(isinstance(child_revision_ids, list) and all(isinstance(key, str) for key in child_revision_ids),
             'Child revision identities must be a list of text values')
    requested = set(child_revision_ids) | {parent_revision_id}
    _require(electrical_partitions is None or isinstance(electrical_partitions, dict),
             'Electrical partitions must be a revision mapping')
    _require(not (set(electrical_partitions or {}) - requested), 'Electrical partitions contain unrequested products')
    _require(isinstance(curve_packages, dict) and parent_revision_id in curve_packages,
             'Parent curve package required')
    _require(isinstance(registered_package_sha256, dict) and parent_revision_id in registered_package_sha256,
             'Separately registered parent package digest required')
    _require(set(curve_packages) == requested and set(registered_package_sha256) == requested,
             'Curve packages and registered digests must cover exactly the requested products')
    child_revision_ids = deepcopy(child_revision_ids)
    curve_packages, registered_package_sha256 = deepcopy(curve_packages), deepcopy(registered_package_sha256)
    electrical_partitions = deepcopy(electrical_partitions)
    parent = run_product_comparison(revision_service, parent_revision_id, case_input, baseline,
        curve_packages[parent_revision_id], registered_package_sha256[parent_revision_id],
        temperature_c=temperature_c, standby_soc_pct=standby_soc_pct, max_iter=max_iter)
    variants = DcConfigurationVariantService(revision_service.auth_user, revision_service.db_url)
    plan = plan_tail_replacement_candidates(revision_service, parent_revision_id, child_revision_ids,
        standard_container_count=parent['snapshot'].stage2.container_count, variant_service=variants,
        allow_special_configurations=allow_special_configurations, special_reason=special_reason)
    results = []
    for candidate in plan['candidates']:
        lines = [dict(revision_id=row['revision_id'], quantity=row['quantity'], role=row['role'])
                 for row in candidate['manifest']['bom']]
        ids = {row['revision_id'] for row in lines}
        _require(ids.issubset(curve_packages) and ids.issubset(registered_package_sha256),
                 'All planned products require independently approved curve packages and registered digests')
        result = evaluate_dc_composition(revision_service, lines, case_input, baseline,
            {key: curve_packages[key] for key in ids}, {key: registered_package_sha256[key] for key in ids},
            variant_service=variants, allow_special_configurations=allow_special_configurations,
            special_reason=special_reason, temperature_c=temperature_c, standby_soc_pct=standby_soc_pct,
            electrical_partitions={key: value for key, value in (electrical_partitions or {}).items() if key in ids})
        results.append(dict(candidate_key=candidate['candidate_key'], label=candidate['label'], result=result))
    _require(results[0]['result']['stage3'].model_dump() == parent['snapshot'].stage3.model_dump(),
             'Standard comparison baseline differs from the frozen parent run')
    final_plan = plan_tail_replacement_candidates(revision_service, parent_revision_id, child_revision_ids,
        standard_container_count=parent['snapshot'].stage2.container_count, variant_service=variants,
        allow_special_configurations=allow_special_configurations, special_reason=special_reason)
    _require(final_plan['plan_sha256'] == plan['plan_sha256'], 'Candidate product reviews changed during comparison')
    return dict(contract_version=1, comparison_only=True, downstream_ready=False,
        plan=plan, candidates=results, standard_provenance=parent['provenance'],
        selection_policy='No automatic adoption or cost ranking; review energy and declared DC duty separately.')
