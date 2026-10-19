"""Read a cabinet technical report from one saved DC result and its AC output.

This boundary only checks and copies persisted data. It does not size equipment,
select curves, read a database, or resolve session/default values.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real
from typing import Any

from calb_diagrams.cabinet_sld import _validate_output
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


def _number(value: Any, field: str, *, minimum: float = 0, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < minimum or (not allow_zero and number == minimum):
        raise ValueError(f"{field} must be a finite {'non-negative' if allow_zero else 'positive'} number")
    return number


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer of at least {minimum}")
    return value


def _same_number(actual: Any, expected: Any, field: str, *, tolerance: float = 1e-6) -> None:
    if (isinstance(actual, bool) or isinstance(expected, bool)
            or not isinstance(actual, Real) or not isinstance(expected, Real)
            or not math.isfinite(float(actual)) or not math.isfinite(float(expected))
            or not math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=tolerance)):
        raise ValueError(f"{field} conflicts with the saved DC result")


def _finite_payload(value: Any, field: str = 'report') -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _finite_payload(item, f"{field}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite_payload(item, f"{field}[{index}]")
    elif isinstance(value, Real) and not isinstance(value, bool) and not math.isfinite(float(value)):
        raise ValueError(f"{field} contains a non-finite value")


def build_cabinet_report_data(
    run_bundle: DcRunBundle,
    ac_output: dict,
    *,
    ac_alternative_label: str | None = None,
) -> dict:
    """Return report-ready values without recomputing or rounding saved results.

    The caller owns authentication and the selected AC child's database identity.
    Here the parent, physical equipment, scenario, and saved annual data must
    agree. Internal run identifiers are checked but never returned for printing.
    """
    if not isinstance(ac_output, dict) or not run_bundle.run_id or ac_output.get('source_run_id') != run_bundle.run_id:
        raise ValueError('The cabinet AC output does not belong to this saved DC result')
    source = run_bundle.input_snapshot
    if source is None or source.snapshot_kind != 'dc_case_input':
        raise ValueError('The saved DC case input is required for a cabinet report')
    case = source.payload.get('case_input')
    if not isinstance(case, dict):
        raise ValueError('The saved DC case input is incomplete')
    snapshot = run_bundle.snapshot
    stage1 = snapshot.stage1.model_dump()
    stage2 = snapshot.stage2
    if (case.get('scenario_id') != 'cabinet_only' or stage2.mode != 'cabinet_only'
            or snapshot.summary.get('scenario_id') != 'cabinet_only'):
        raise ValueError('The saved case, DC configuration and DC summary must all be cabinet_only')

    # This is the existing cabinet contract validation only: no SVG, sizing, or
    # second allocation is produced. The container SLD contract is untouched.
    plan, _, _ = _validate_output(ac_output)
    if stage2.container_count != 0 or stage2.cabinet_count != plan['physical_cabinet_count']:
        raise ValueError('Saved DC physical cabinet/container counts conflict with the cabinet AC contract')
    _same_number(stage2.dc_nameplate_bol_mwh, plan['total_nameplate_mwh'], 'DC nameplate energy', tolerance=.00051)
    if not stage2.block_config_items or any(item.form != 'cabinet' for item in stage2.block_config_items):
        raise ValueError('Saved DC products must contain cabinets only')
    if {item.block_code for item in stage2.block_config_items} != set(plan['product_codes']):
        raise ValueError('Saved DC product codes conflict with the cabinet AC contract')
    if sum(item.count for item in stage2.block_config_items) != stage2.cabinet_count:
        raise ValueError('Saved DC product quantities do not match the physical cabinet count')
    products = []
    for item in stage2.block_config_items:
        _integer(item.count, 'DC product quantity', minimum=1)
        _same_number(item.unit_capacity_mwh, .418, 'DC cabinet unit capacity', tolerance=.00051)
        _same_number(item.subtotal_mwh, item.count * item.unit_capacity_mwh, 'DC product subtotal', tolerance=.00051)
        _same_number(item.total_dc_nameplate_bol_mwh, stage2.dc_nameplate_bol_mwh,
                     'DC product total nameplate', tolerance=.00051)
        products.append({key: getattr(item, key) for key in
                         ('block_code', 'block_name', 'unit_capacity_mwh', 'count', 'subtotal_mwh')})
    _same_number(sum(item.subtotal_mwh for item in stage2.block_config_items), stage2.dc_nameplate_bol_mwh,
                 'Summed DC product energy', tolerance=.00051)

    power = _number(case.get('poi_power_req_mw'), 'POI power requirement')
    energy = _number(case.get('poi_energy_req_mwh'), 'POI energy requirement')
    life = _integer(case.get('project_life_years'), 'Project life', minimum=1)
    guarantee = _integer(case.get('poi_guarantee_year'), 'POI guarantee year')
    if guarantee > life:
        raise ValueError('POI guarantee year exceeds the saved project life')
    cycles = _integer(case.get('cycles_per_year'), 'Cycles per year', minimum=1)
    standby_months = _integer(case.get('sc_time_months'), 'FAT-to-COD duration')
    dod = _number(case.get('dod_pct'), 'Depth of discharge')
    rte = _number(case.get('dc_round_trip_efficiency_pct'), 'DC round-trip efficiency')
    if dod > 100 or rte > 100:
        raise ValueError('Saved DOD and DC round-trip efficiency must not exceed 100 percent')
    for field in ('poi_power_req_mw', 'poi_energy_req_mwh', 'project_life_years',
                  'poi_guarantee_year', 'cycles_per_year', 'sc_time_months'):
        _same_number(stage1.get(field), case[field], f'Stage 1 {field}')
    _same_number(stage1.get('dod_frac'), dod / 100, 'Stage 1 DOD')
    _same_number(stage1.get('dc_round_trip_efficiency_frac'), rte / 100, 'Stage 1 DC round-trip efficiency')
    for field, target in (('poi_power_mw', power), ('poi_energy_mwh', energy)):
        if field in ac_output:
            _same_number(ac_output[field], target, f'AC {field}')
    voltage = case.get('poi_nominal_voltage_kv')
    frequency = case.get('poi_frequency_hz')
    if voltage is not None:
        voltage = _number(voltage, 'POI nominal voltage')
    if frequency is not None:
        frequency = _number(frequency, 'POI frequency')

    annual = [row.model_dump() for row in snapshot.stage3.rows]
    years = [row['year_index'] for row in annual]
    if any(type(year) is not int for year in years) or sorted(years) != list(range(life + 1)):
        raise ValueError('Saved annual results must cover every project year exactly once')
    flagged = [row for row in annual if row['is_guarantee_year']]
    if len(flagged) != 1 or flagged[0]['year_index'] != guarantee:
        raise ValueError('Saved annual results must mark exactly the configured guarantee year')
    for row in annual:
        _same_number(row['dc_nameplate_bol_mwh'], stage2.dc_nameplate_bol_mwh,
                     f"Year {row['year_index']} DC nameplate", tolerance=.00051)
    stage3_meta = snapshot.stage3.meta.model_dump()
    _same_number(stage3_meta.get('poi_power_mw'), power, 'Stage 3 POI power requirement')
    if snapshot.poi_usable_energy_mwh_at_guarantee_year is not None:
        _same_number(flagged[0]['poi_usable_energy_mwh'], snapshot.poi_usable_energy_mwh_at_guarantee_year,
                     'Saved guarantee-year energy')

    data = dict(
        project_name=run_bundle.project_name or case.get('project_name') or stage1['project_name'],
        case_name=run_bundle.case_name,
        project_code=run_bundle.project_code,
        case_code=run_bundle.case_code,
        ac_alternative_label=ac_alternative_label,
        poi_power_mw=power,
        poi_energy_mwh=energy,
        poi_guarantee_year=guarantee,
        project_life_years=life,
        cycles_per_year=cycles,
        sc_time_months=standby_months,
        dod_pct=dod,
        dc_round_trip_efficiency_pct=rte,
        poi_nominal_voltage_kv=voltage,
        poi_frequency_hz=frequency,
        dc_total_mwh=stage2.dc_nameplate_bol_mwh,
        physical_cabinet_count=stage2.cabinet_count,
        dc_products=products,
        annual_rows=annual,
        stage1=stage1,
        stage3_meta=stage3_meta,
    )
    _finite_payload(data)
    return data
