"""One to four reduced-string tails beside an unchanged container sizing run.

This local comparison consumes the owner's 2026-10-22 capacity/power/curve
basis. It neither adopts the BOM nor supplies an AC/SLD design or a warranty.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math

import pandas as pd

from calb_sizing_tool.common.dc_configuration_identity import is_20ft_container_type
from calb_sizing_tool.common.nameplate import apply_block_nameplate_recalc
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.schemas.stage3 import Stage3Result
from calb_sizing_tool.services.dc_input_guard_service import validate_soh_curve_support
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from calb_sizing_tool.services.stage2_service import _build_items
from calb_sizing_tool.services.stage3_service import run_stage3

STANDARD_EXCEL_CODE = 'CALB_5MWh_20FT_12R'
BASIS_AUTHORITY = 'owner_reduced_string_basis_2026_10_22'
SUMMARY_KEY = 'reduced_string_tail_comparison'
COMPARISON_MODE = 'reduced_string_tail_comparison_only'
_RAW_TABLES = ('battery_cell_type_314_data', 'pack_type_314_data',
               'rack_type_314_data', 'dc_block_template_314_data')
_CURVE_TABLES = ('df_soh_profile', 'df_soh_curve', 'df_rte_profile', 'df_rte_curve')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive(value, label):
    _require(not isinstance(value, bool), f'{label} must be a positive finite number.')
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'{label} must be a positive finite number.') from exc
    _require(math.isfinite(value) and value > 0, f'{label} must be a positive finite number.')
    return value


def _same(left, right, *, tolerance=1e-8):
    try:
        return math.isclose(_positive(left, 'Value'), _positive(right, 'Expected value'),
                            rel_tol=1e-10, abs_tol=tolerance)
    except ValueError:
        return False


def _row(frame, column, value):
    _require(isinstance(frame, pd.DataFrame) and column in frame, 'Capacity source table is incomplete.')
    rows = frame[frame[column] == value]
    _require(len(rows) == 1, f'Exactly one capacity source row is required for {column}={value}.')
    return rows.iloc[0].to_dict()


def _json(value):
    """Copy only serializable snapshot data; never retain mutable ORM objects."""
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def derive_reduced_string_basis(bundle) -> dict:
    """Validate and reuse the original cell -> pack -> rack -> block chain."""
    raw = bundle.raw_sheets
    _require(all(key in raw for key in _RAW_TABLES), 'Original cell, pack, rack and block tables are required.')
    cell_frame, pack_frame, rack_frame, block_frame = [raw[key] for key in _RAW_TABLES]
    block = _row(block_frame, 'Dc_Block_Code', STANDARD_EXCEL_CODE)
    _require(str(block.get('Block_Form')).lower() == 'container'
             and _same(block.get('Container_Length_Ft'), 20)
             and _same(block.get('Racks_Per_Block'), 12), 'The original 20ft / 12-rack main container is required.')
    rack = _row(rack_frame, 'Rack_Type_Id', block.get('Rack_Type_Id'))
    pack = _row(pack_frame, 'Pack_Type_Id', rack.get('Pack_Type_Id'))
    cell = _row(cell_frame, 'Cell_Type_Id', pack.get('Cell_Type_Id'))
    capacity = _positive(cell.get('Cell_Capacity_Ah'), 'Cell capacity')
    voltage = _positive(cell.get('Cell_Nominal_Voltage_V'), 'Cell nominal voltage')
    series = _positive(pack.get('Cells_In_Series'), 'Pack series cells')
    parallel = _positive(pack.get('Cells_In_Parallel'), 'Pack parallel cells')
    packs = _positive(rack.get('Packs_Per_Rack'), 'Packs per rack')
    _require(capacity == 314 and voltage == 3.2 and series * packs == 416 and parallel == 1
             and series.is_integer() and packs.is_integer(), 'Only the original 314Ah / 3.2V / 416S / 1P chain is supported.')
    declared_wh = cell.get('Cell_Energy_Wh')
    if declared_wh is not None and not pd.isna(declared_wh):
        _require(_same(declared_wh, capacity * voltage), 'Cell energy conflicts with the original Ah/voltage chain.')
    source = pd.DataFrame([{**block, 'Dc_Block_Code': f'tail-{strings}', 'Racks_Per_Block': strings}
                           for strings in (12, 10, 8)])
    calculated = apply_block_nameplate_recalc(source, rack_frame, pack_frame, cell_frame)
    rack_energy = capacity * voltage * series * parallel * packs / 1e6
    energies = dict(zip((12, 10, 8), calculated.Block_Nameplate_Capacity_Mwh.tolist()))
    for strings, energy in energies.items():
        _require(_same(energy, round(rack_energy * strings, 3)), 'Original capacity calculation did not resolve the selected chain.')
    basis = dict(schema_version=1, authority=BASIS_AUTHORITY,
        standard_excel_code=STANDARD_EXCEL_CODE, cell_model=str(cell.get('Cell_Model') or ''),
        cell_capacity_ah=capacity, cell_nominal_voltage_v=voltage, cells_per_pack=int(series),
        cells_in_parallel=int(parallel), packs_per_rack=int(packs), cells_in_series=416,
        rack_energy_raw_mwh=rack_energy, main_energy_raw_mwh=rack_energy * 12,
        main_energy_mwh=energies[12], default_power_c_rate=0.5,
        tails={strings: dict(strings_in_parallel=strings, energy_raw_mwh=rack_energy * strings,
            energy_mwh=energies[strings], power_kw=rack_energy * strings * 500,
            dc_output_count=1 if strings == 10 else 2,
            max_connected_pcs=1 if strings == 10 else 2) for strings in (10, 8)})
    basis['basis_sha256'] = _hash_payload(_json(basis))
    return basis


def _validate_basis(basis):
    _require(isinstance(basis, dict) and basis.get('authority') == BASIS_AUTHORITY
             and basis.get('standard_excel_code') == STANDARD_EXCEL_CODE,
             'The owner-authorized reduced-string basis is required.')
    _require(basis.get('basis_sha256') == _hash_payload(_json({key: value for key, value in basis.items()
                                                       if key != 'basis_sha256'})), 'Capacity basis content has changed.')
    _require(basis.get('cell_capacity_ah') == 314 and basis.get('cell_nominal_voltage_v') == 3.2
             and basis.get('cells_in_series') == 416 and basis.get('cells_in_parallel') == 1
             and basis.get('default_power_c_rate') == 0.5, 'Saved capacity basis is outside the supported family.')
    rack_energy = 314 * 3.2 * 416 / 1e6
    _require(_same(basis.get('rack_energy_raw_mwh'), rack_energy)
             and _same(basis.get('main_energy_raw_mwh'), rack_energy * 12)
             and _same(basis.get('main_energy_mwh'), round(rack_energy * 12, 3)),
             'Saved main capacity differs from the original cell chain.')
    for strings in (10, 8):
        tail = _tail_basis(basis, strings)
        _require(isinstance(tail, dict) and tail.get('strings_in_parallel') == strings
                 and _same(tail.get('energy_raw_mwh'), rack_energy * strings)
                 and _same(tail.get('energy_mwh'), round(rack_energy * strings, 3))
                 and _same(tail.get('power_kw'), rack_energy * strings * 500)
                 and tail.get('dc_output_count') == (1 if strings == 10 else 2)
                 and tail.get('max_connected_pcs') == (1 if strings == 10 else 2),
                 'Saved reduced-string capacity or interface basis is inconsistent.')


def _tail_basis(basis, strings):
    return basis['tails'].get(strings, basis['tails'].get(str(strings)))


def _metadata(row):
    value = row.get('metadata_json')
    return value if isinstance(value, dict) else {}


def _current_structure_compatible(row, parent):
    """Reuse known maintenance conflicts while retaining legacy saved comparisons.

    New catalogue reads include actual linked cells and machine-readable
    conflicts. Historical snapshots without these fields keep their existing
    saved interpretation; incomplete current/voltage/dimension ratings alone
    do not disable the owner's bounded comparison assumption.
    """
    from calb_sizing_tool.services.dc_configuration_variant_service import _structure

    for product in (row, parent):
        if 'maintenance_conflicts' in product:
            conflicts = product['maintenance_conflicts']
            if not isinstance(conflicts, list) or conflicts:
                return False
    if not any('linked_cell_snapshot' in product for product in (row, parent)):
        return True
    snapshots = []
    for product in (parent, row):
        cell = product.get('linked_cell_snapshot')
        if (not isinstance(cell, dict) or cell.get('product_cell_id') != product.get('product_cell_id')
                or not _same(cell.get('nominal_capacity_ah'), 314)
                or cell.get('nominal_voltage_v') is not None and not _same(cell['nominal_voltage_v'], 3.2)
                or cell.get('is_active') not in (True, 1) or cell.get('is_published') not in (True, 1)):
            return False
        snapshots.append(dict(snapshot=dict(product=product, cell={
            key: value for key, value in cell.items() if key not in ('created_at', 'updated_at')})))
    _, conflicts = _structure(*snapshots)
    return not conflicts


def _product_eligible(row, parent, basis, main_code):
    from calb_sizing_tool.services.dc_product_maintenance import DC_CONNECTION_FIELDS, dc_connection_value

    meta = _metadata(row)
    try:
        connection = {key: dc_connection_value(key, meta.get(key)) for key in DC_CONNECTION_FIELDS}
    except ValueError:
        return False
    strings = row.get('strings_in_parallel')
    if type(strings) is not int or strings not in (10, 8):
        return False
    expected = _tail_basis(basis, strings)
    role = str(row.get('configuration_role') or meta.get('configuration_role') or '').lower().replace(' ', '_')
    parent_matches = row.get('parent_block_code') == parent.get('block_code')
    selected_matches = (row.get('parent_block_code') == main_code if main_code != STANDARD_EXCEL_CODE
                        else meta.get('standard_excel_code') == STANDARD_EXCEL_CODE)
    return bool(role in ('special_tail', 'engineering_variant') and parent_matches and selected_matches
        and _current_structure_compatible(row, parent)
        and row.get('is_active') in (True, 1) and row.get('is_published') in (True, 1)
        and parent.get('is_active') in (True, 1) and parent.get('is_published') in (True, 1)
        and row.get('product_cell_id') and row.get('product_cell_id') == parent.get('product_cell_id')
        and row.get('block_form') == parent.get('block_form') == 'container'
        and is_20ft_container_type(row.get('container_type')) and is_20ft_container_type(parent.get('container_type'))
        and row.get('cells_in_series') == parent.get('cells_in_series') == 416
        and parent.get('strings_in_parallel') == 12
        and (_same(parent.get('gross_energy_mwh'), basis['main_energy_raw_mwh'], tolerance=1e-5)
             or _same(parent.get('gross_energy_mwh'), basis['main_energy_mwh']))
        and (_same(row.get('gross_energy_mwh'), expected['energy_raw_mwh'], tolerance=1e-7)
             or _same(row.get('gross_energy_mwh'), expected['energy_mwh']))
        and _same(row.get('nominal_power_kw'), expected['power_kw'], tolerance=0.00051)
        and _same(row.get('max_c_rate'), 0.5)
        and meta.get('reduced_string_basis_authority') == BASIS_AUTHORITY
        and connection.get('dc_output_count') == expected['dc_output_count']
        and connection.get('max_connected_pcs') == expected['max_connected_pcs']
        and bool(connection.get('dc_topology_source_ref')))


def available_products(rows: list[dict], basis: dict, main_code: str) -> dict[int, dict]:
    """Return unambiguous maintained owner-basis tails for the exact main box."""
    _validate_basis(basis)
    parents = {row.get('block_code'): row for row in rows}
    matches = {10: [], 8: []}
    for row in rows:
        parent = parents.get(row.get('parent_block_code'))
        if parent and _product_eligible(row, parent, basis, main_code):
            result = deepcopy(row)
            result['_tail_parent'] = deepcopy(parent)
            result['_tail_main_code'] = main_code
            matches[row['strings_in_parallel']].append(result)
    return {strings: values[0] for strings, values in matches.items() if len(values) == 1}


def _baseline_sha(snapshot):
    return _hash_payload({key: getattr(snapshot, key).model_dump(mode='json')
                          for key in ('stage1', 'stage2', 'stage3')})


def _curve_fingerprints(bundle):
    # Pandas converts empty optional table cells to JSON null consistently.
    return {key: _hash_payload({'rows': json.loads(getattr(bundle, key).to_json(orient='records', double_precision=15))})
            for key in _CURVE_TABLES}


def _stage2_for_tail(parent, product, basis, tail_count=1):
    original = parent.stage2
    _require(type(tail_count) is int and 1 <= tail_count <= 4,
             'Select between 1 and 4 reduced-string containers.')
    _require(parent.converged is True and original.mode == 'container_only' and original.cabinet_count == 0
             and type(original.container_count) is int and original.container_count >= 2
             and len(original.block_config_items) == 1, 'A standard container-only result with at least two main containers is required.')
    _require(original.container_count > tail_count,
             'The comparison must retain at least one standard 12-string container; total container count stays unchanged.')
    main = original.block_config_items[0]
    # Excel has already run the original round-3 nameplate recalculation. The
    # Admin adapter instead supplies its catalogue's raw unit capacity; the
    # frozen builder rounds that unit for display only after summing the fleet.
    selected_unit = (basis['main_energy_mwh'] if main.block_code == STANDARD_EXCEL_CODE
                     else _positive(product['_tail_parent'].get('gross_energy_mwh'), 'Selected main capacity'))
    _require(main.form == 'container' and main.count == original.container_count
             and main.block_code == product.get('_tail_main_code')
             and _same(main.unit_capacity_mwh, round(selected_unit, 3))
             and _same(original.dc_nameplate_bol_mwh, round(main.count * selected_unit, 3)),
             'The selected standard result does not match the validated 12-string capacity basis.')
    strings = product['strings_in_parallel']
    tail = _tail_basis(basis, strings)
    # Preserve the exact unit precision of the selected standard input path.
    items = _build_items([
        {'Block Code': main.block_code, 'Block Name': main.block_name, 'Form': 'container',
         'Unit Capacity (MWh)': selected_unit, 'Count': main.count - tail_count},
        {'Block Code': product['block_code'], 'Block Name': product['block_name'], 'Form': 'container',
         'Unit Capacity (MWh)': tail['energy_mwh'], 'Count': tail_count}])
    total = items[0].total_dc_nameplate_bol_mwh
    required = _positive(parent.stage1.dc_energy_capacity_required_mwh, 'Required DC energy')
    return Stage2Result(mode=COMPARISON_MODE, dc_nameplate_bol_mwh=total,
        oversize_mwh=total - required, config_adjustment_frac=total / required - 1,
        block_config_items=items, container_count=original.container_count, cabinet_count=0, busbars_needed=0)


def evaluate_reduced_string_tail(parent_snapshot, bundle, product: dict, basis: dict, *, tail_count=1) -> dict:
    """Evaluate N-k mains plus k identical tails, k=1..4, without adoption."""
    _validate_basis(basis)
    _require(derive_reduced_string_basis(bundle) == basis, 'The capacity source changed before comparison.')
    parent = deepcopy(parent_snapshot)
    source = product.get('_tail_parent')
    _require(isinstance(source, dict) and _product_eligible(product, source, basis, product.get('_tail_main_code')),
             'A current eligible maintained tail and its exact parent are required.')
    stage2 = _stage2_for_tail(parent, product, basis, tail_count)
    stage3 = run_stage3(parent.stage1, stage2, bundle)
    unsupported = validate_soh_curve_support(bundle.df_soh_curve, stage3.meta.soh_profile_id,
        chosen_c_rate=stage3.meta.chosen_soh_c_rate, effective_c_rate=stage3.meta.effective_c_rate)
    _require(not unsupported, unsupported or '')
    _require(all(math.isfinite(row.poi_usable_energy_mwh) and math.isfinite(row.dc_gross_capacity_mwh)
                 for row in stage3.rows), 'Comparison contains nonfinite lifetime output.')
    guarantee_year = parent.stage1.poi_guarantee_year
    guaranteed = [row for row in stage3.rows if row.year_index == guarantee_year]
    _require(len(guaranteed) == 1, 'The comparison has no unique guarantee-year result.')
    tail = _tail_basis(basis, product['strings_in_parallel'])
    count = parent.stage2.container_count
    nominal_power_mw = ((count - tail_count) * basis['main_energy_raw_mwh'] * 0.5 + tail_count * tail['power_kw'] / 1000)
    power_required = _positive(parent.stage1.dc_power_required_mw, 'Required DC power')
    annual_rate_review = [dict(year_index=row.year_index,
        current_capacity_c_rate=power_required / row.dc_gross_capacity_mwh if row.dc_gross_capacity_mwh > 0 else None,
        within_0_5c_current_capacity=(row.dc_gross_capacity_mwh > 0 and
                                    power_required <= row.dc_gross_capacity_mwh * 0.5 + 1e-9))
        for row in stage3.rows]
    result = dict(schema_version=1, contract_type='reduced_string_tail_comparison',
        comparison_only=True, downstream_ready=False, authority=BASIS_AUTHORITY,
        baseline_sha256=_baseline_sha(parent), basis=deepcopy(basis),
        selected_tail_strings=product['strings_in_parallel'],
        product_snapshot=_json({key: value for key, value in product.items() if not key.startswith('_')}),
        parent_product_snapshot=_json(source),
        snapshot=dict(stage1=parent.stage1.model_dump(mode='json'), stage2=stage2.model_dump(mode='json'),
            stage3=stage3.model_dump(mode='json'), iteration_count=1,
            poi_usable_energy_mwh_at_guarantee_year=guaranteed[0].poi_usable_energy_mwh,
            converged=guaranteed[0].poi_usable_energy_mwh + 1e-6 >= parent.stage1.poi_energy_req_mwh,
            summary={'scenario_id': COMPARISON_MODE, 'comparison_only': True, 'downstream_ready': False}),
        curve_table_sha256=_curve_fingerprints(bundle),
        curve_basis='Owner-authorized reuse of the current standard 12-string 314Ah runtime SOH/RTE tables; not a supplier warranty.',
        nominal_power_basis='Owner default 0.5C at raw BOL nameplate energy; not a lifetime power guarantee.',
        nominal_dc_power_mw=nominal_power_mw, dc_power_required_mw=power_required,
        meets_nominal_dc_power=power_required <= nominal_power_mw + 1e-9,
        guarantee_year=guarantee_year, poi_energy_at_guarantee_year_mwh=guaranteed[0].poi_usable_energy_mwh,
        meets_guarantee_year_energy=guaranteed[0].poi_usable_energy_mwh + 1e-6 >= parent.stage1.poi_energy_req_mwh,
        annual_current_capacity_rate_review=annual_rate_review,
        lifetime_power_guaranteed=False, ac_power_matching_pending=True,
        output_partition_pending=product['strings_in_parallel'] == 8,
        limitations=['DC comparison only; standard configuration remains active for AC / SLD.',
                     'No PCS, per-output electrical current, AC, charge-duty or layout validation.',
                     'Annual current-capacity rate review does not model hardware power degradation.'])
    # Preserve the original single-tail payload and hash. Version 2 is explicitly
    # DC-only; existing single-tail AC/SLD reviews cannot consume multiple tails.
    if tail_count > 1:
        result.update(schema_version=2, tail_container_count=tail_count)
    # JSON object keys (including tail counts) have their saved form before hashing.
    result = _json(result)
    result['comparison_sha256'] = _hash_payload(result)
    return result


def restored_comparison(parent_snapshot) -> dict | None:
    """Read a saved optional comparison without replacing any standard output."""
    value = parent_snapshot.summary.get(SUMMARY_KEY)
    if value is None:
        return None
    _require(isinstance(value, dict), 'Saved tail comparison is incomplete.')
    result = deepcopy(value)
    _require(result.get('schema_version') in (1, 2) and result.get('contract_type') == 'reduced_string_tail_comparison'
             and result.get('authority') == BASIS_AUTHORITY and result.get('comparison_only') is True
             and result.get('downstream_ready') is False and result.get('lifetime_power_guaranteed') is False
             and result.get('ac_power_matching_pending') is True,
             'Saved tail comparison cannot be adopted or used downstream.')
    _require(result.get('comparison_sha256') == _hash_payload({key: value for key, value in result.items()
                                                              if key != 'comparison_sha256'}),
             'Saved tail comparison content has changed.')
    _require(result.get('baseline_sha256') == _baseline_sha(parent_snapshot),
             'Saved tail comparison belongs to a different standard result.')
    basis = result.get('basis')
    _validate_basis(basis)
    product = deepcopy(result.get('product_snapshot') or {})
    product['_tail_parent'] = result.get('parent_product_snapshot')
    product['_tail_main_code'] = parent_snapshot.stage2.block_config_items[0].block_code
    _require(isinstance(product['_tail_parent'], dict)
             and _product_eligible(product, product['_tail_parent'], basis, product['_tail_main_code']),
             'Saved tail product and parent are inconsistent.')
    tail_count = result.get('tail_container_count', 1)
    _require((result['schema_version'] == 1 and type(tail_count) is int and tail_count == 1)
             or (result['schema_version'] == 2 and type(tail_count) is int and 2 <= tail_count <= 4),
             'Saved tail quantity is inconsistent with its comparison version.')
    expected_stage2 = _stage2_for_tail(parent_snapshot, product, basis, tail_count)
    nested = result.get('snapshot')
    _require(isinstance(nested, dict) and nested.get('stage1') == parent_snapshot.stage1.model_dump(mode='json'),
             'Saved tail input differs from its standard result.')
    saved_stage2 = Stage2Result.model_validate(nested.get('stage2') or {})
    _require(saved_stage2 == expected_stage2 and result.get('selected_tail_strings') == product['strings_in_parallel'],
             'Saved tail BOM is inconsistent with the standard result.')
    stage3 = Stage3Result.model_validate(nested.get('stage3') or {})
    _require([row.year_index for row in stage3.rows] == [row.year_index for row in parent_snapshot.stage3.rows]
             and all(_same(row.dc_nameplate_bol_mwh, saved_stage2.dc_nameplate_bol_mwh) for row in stage3.rows)
             and _same(stage3.meta.dc_power_mw, parent_snapshot.stage1.dc_power_required_mw)
             and _same(stage3.meta.effective_c_rate,
                       parent_snapshot.stage1.dc_power_required_mw / saved_stage2.dc_nameplate_bol_mwh),
             'Saved tail lifetime result is inconsistent with its BOM or duty.')
    _require(all(math.isfinite(row.poi_usable_energy_mwh) and math.isfinite(row.dc_gross_capacity_mwh)
                 for row in stage3.rows), 'Saved tail result contains nonfinite annual values.')
    year = parent_snapshot.stage1.poi_guarantee_year
    guarantee = [row for row in stage3.rows if row.year_index == year]
    _require(len(guarantee) == 1, 'Saved tail result has no unique guarantee-year record.')
    expected_energy = guarantee[0].poi_usable_energy_mwh
    energy_passes = expected_energy + 1e-6 >= parent_snapshot.stage1.poi_energy_req_mwh
    tail = _tail_basis(basis, product['strings_in_parallel'])
    expected_power = ((parent_snapshot.stage2.container_count - tail_count) * basis['main_energy_raw_mwh'] * 0.5
                      + tail_count * tail['power_kw'] / 1000)
    required_power = parent_snapshot.stage1.dc_power_required_mw
    expected_annual = [dict(year_index=row.year_index,
        current_capacity_c_rate=required_power / row.dc_gross_capacity_mwh if row.dc_gross_capacity_mwh > 0 else None,
        within_0_5c_current_capacity=(row.dc_gross_capacity_mwh > 0 and
                                    required_power <= row.dc_gross_capacity_mwh * 0.5 + 1e-9))
        for row in stage3.rows]
    _require(result.get('guarantee_year') == year
             and result.get('poi_energy_at_guarantee_year_mwh') == expected_energy
             and nested.get('poi_usable_energy_mwh_at_guarantee_year') == expected_energy
             and result.get('meets_guarantee_year_energy') is energy_passes
             and nested.get('converged') is energy_passes and nested.get('iteration_count') == 1
             and _same(result.get('nominal_dc_power_mw'), expected_power)
             and _same(result.get('dc_power_required_mw'), required_power)
             and result.get('meets_nominal_dc_power') is (required_power <= expected_power + 1e-9)
             and result.get('annual_current_capacity_rate_review') == expected_annual
             and result.get('output_partition_pending') is (product['strings_in_parallel'] == 8),
             'Saved tail feasibility summary contradicts its annual result or declared power basis.')
    return result
