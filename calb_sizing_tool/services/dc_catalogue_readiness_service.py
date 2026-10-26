"""Read-only catalogue diagnostics; never activates products or sizes equipment."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from calb_sizing_tool.services.stage2_service import pick_dc_block


def _positive(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def dc_catalogue_readiness(snapshot: dict, sizing_frame: pd.DataFrame) -> list[dict]:
    """Explain the current adapter and missing future inputs separately.

    Curve linkage is only catalogue evidence, not project-duty approval. Equal
    Ah ratings never establish cell identity or electrical compatibility.
    """
    cells = {row['product_cell_id']: row for row in snapshot.get('cells', [])}
    curves = {row['curve_code']: row for row in snapshot.get('degradation_curves', [])}
    selected = set()
    if not sizing_frame.empty:
        for form in ('container', 'cabinet'):
            picked = pick_dc_block(sizing_frame, form)
            if picked:
                selected.add(picked[0])
    result = []
    adapter_active = {row.Dc_Block_Code: bool(row.Is_Active)
                      for row in sizing_frame.itertuples()}
    for block in snapshot.get('dc_blocks', []):
        issues = []
        form = str(block.get('block_form') or '').strip().lower()
        if form not in ('container', 'cabinet'):
            issues.append('Unsupported form; current adapter falls back to container')
        capacity = block.get('gross_energy_mwh')
        if not capacity:
            capacity = block.get('rated_capacity_kwh')
        if not _positive(capacity):
            issues.append('Positive nameplate energy required')
        cell = cells.get(block.get('product_cell_id'))
        if not cell:
            issues.append('Linked cell product required')
        elif not cell.get('is_active') or not cell.get('is_published'):
            issues.append('Linked cell is inactive or unpublished')
        if not all(_positive(block.get(k)) for k in ('voltage_min_v', 'voltage_max_v')):
            issues.append('Confirmed DC voltage window required')
        elif float(block['voltage_min_v']) >= float(block['voltage_max_v']):
            issues.append('DC voltage minimum must be below maximum')
        # A positive C-rate alone does not prove a guaranteed continuous power rating.
        if not _positive(block.get('nominal_power_kw')):
            issues.append('Confirmed continuous power rating required')
        if not _positive(block.get('max_current_a')):
            issues.append('Confirmed current limit required')
        if not _positive(block.get('cells_in_series')) or not _positive(block.get('strings_in_parallel')):
            issues.append('Confirmed series/parallel configuration required')
        curve = curves.get(block.get('default_degradation_curve_code'))
        if not curve:
            issues.append('Linked degradation curve required')
            curve_state = 'Missing'
        elif curve.get('product_cell_id') != block.get('product_cell_id') or not cell:
            issues.append('Curve cell linkage differs; explicit applicability review required')
            curve_state = 'Cell linkage mismatch'
        elif not curve.get('is_active') or not curve.get('is_published'):
            issues.append('Linked degradation curve is inactive or unpublished')
            curve_state = 'Inactive or unpublished'
        else:
            curve_state = 'Linked; project duty and runtime profile mapping not verified'
        code = block['block_code']
        restricted = ((block.get('metadata_json') or {}).get('configuration_role') == 'engineering_variant'
                      or (bool(block.get('is_active')) and adapter_active.get(code) is False))
        if restricted:
            current = 'Special configuration; excluded from standard search'
        elif not block.get('is_active'):
            current = 'Inactive'
        elif code in selected:
            current = 'Selected by current picker'
        else:
            current = 'Active; not selected by current picker'
        result.append({
            'Product': code,
            'Form': form or 'Missing',
            'Cell': cell.get('cell_code') if cell else 'Missing',
            'Published': bool(block.get('is_published')),
            'Current search': current,
            'Curve linkage': curve_state,
            'Parameter review': '; '.join(issues) or 'Basic fields present; engineering review still required',
        })
    return result
