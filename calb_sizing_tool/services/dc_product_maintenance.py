"""Draft DC catalogue fields shared by the original form and spreadsheet import.

These fields describe intended use, not engineering approval or sizing adoption.
Existing immutable configuration relations remain owned by their registry.
"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Float
from calb_sizing_tool.infra.db.models.product_dc_block import ProductDCBlock
from calb_sizing_tool.services.dc_configuration_variant_service import _structure


DC_CONNECTION_COUNT_FIELDS = ('dc_output_count', 'max_connected_pcs')
DC_CONNECTION_FIELDS = (*DC_CONNECTION_COUNT_FIELDS, 'dc_topology_source_ref')
MAINTENANCE_FIELDS = frozenset({
    'configuration_role', 'parent_block_code', 'cell_code', 'usage_restrictions',
    *DC_CONNECTION_FIELDS,
})
_FIELD_LABELS = {
    'dimension_width_mm': 'Width (mm)', 'dimension_depth_mm': 'Depth / Length (mm)',
    'dimension_height_mm': 'Height (mm)', 'nominal_voltage_v': 'Nominal voltage (V)',
    'voltage_min_v': 'Minimum voltage (V)', 'voltage_max_v': 'Maximum voltage (V)',
    'cells_in_series': 'Cells in series', 'strings_in_parallel': 'Strings in parallel',
    'container_type': 'Container type', 'block_form': 'Block form',
    'dc_output_count': 'DC output circuits', 'max_connected_pcs': 'Maximum connected PCS',
    'dc_topology_source_ref': 'DC connection source',
}


def maintenance_message(message: str) -> str:
    """Use the original form's engineering terms in maintenance diagnostics."""
    for field, label in _FIELD_LABELS.items():
        message = message.replace(field, label)
    return message


DC_BLOCK_FILE_COLUMNS = [
    'block_code', 'block_name', 'configuration_role', 'parent_block_code', 'cell_code',
    *[column.name for column in ProductDCBlock.__table__.columns
      if column.name not in {'product_dc_block_id', 'product_cell_id', 'block_code',
                             'block_name', 'metadata_json', 'created_at', 'updated_at'}],
    'usage_restrictions', *DC_CONNECTION_FIELDS,
]


def dc_connection_value(field: str, value: Any):
    """Normalize the same optional interface value for forms and both import aliases."""
    if field == 'dc_topology_source_ref':
        if value is not None and not isinstance(value, str):
            raise ValueError('DC connection source must be text.')
        return (value or '').strip()
    if value is None or isinstance(value, str) and not value.strip():
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        number = Decimal(str(value).strip())
        # Streamlit/browser numeric controls require exact JavaScript integers.
        if (not number.is_finite() or number != number.to_integral_value()
                or not 0 < number <= 2**53 - 1):
            raise ValueError
        return int(number)
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise ValueError(f'{_FIELD_LABELS[field]}: enter a positive whole number.') from exc


def connection_issues(block: dict, fields: dict) -> tuple[list[str], list[str]]:
    """Draft interface checks for the existing reduced-string tail family.

    Counts describe interface capacity, never operating PCS quantity, electrical
    ratings or permission to parallel outputs. No count is inferred or persisted.
    """
    special = fields['configuration_role'] == 'special_tail'
    missing, conflicts, parsed = [], [], {}
    for field in DC_CONNECTION_FIELDS:
        try:
            parsed[field] = dc_connection_value(field, fields.get(field))
        except ValueError as exc:
            conflicts.append(str(exc))
    if special:
        for field in DC_CONNECTION_COUNT_FIELDS:
            if field in parsed and parsed[field] is None:
                missing.append(f'{_FIELD_LABELS[field]} required')
        if 'dc_topology_source_ref' in parsed and not parsed['dc_topology_source_ref']:
            missing.append('DC connection source required')
        # Special tails already belong to the bounded 314Ah/416S/20ft family;
        # structure_issues separately rejects known conflicting declarations.
        count = block.get('strings_in_parallel')
        expected = {10: (1, 1), 8: (2, 2)}.get(count) if type(count) is int else None
        if expected:
            for field, value in zip(DC_CONNECTION_COUNT_FIELDS, expected):
                if parsed.get(field) is not None and parsed[field] != value:
                    conflicts.append(f'{count}-string special tail requires {_FIELD_LABELS[field]} = {value}.')
    return missing, conflicts


def _role(value: Any) -> str:
    token = str(value or 'standard').strip().lower().replace(' ', '_')
    if token in {'standard', 'standard_parent'}:
        return 'standard'
    if token in {'special_tail', 'engineering_variant'}:
        return 'special_tail'
    raise ValueError('Configuration role: use Standard or Special tail.')


def maintenance_fields(block: dict, blocks: list[dict], cells: list[dict],
                       registered_parents: dict[str, set[str]]) -> dict:
    metadata = block.get('metadata_json') or {}
    parents = registered_parents.get(block.get('product_dc_block_id'), set())
    parent_id = metadata.get('parent_product_id')
    if not parent_id and len(parents) == 1:
        parent_id = next(iter(parents))
    parent = next((row for row in blocks if row['product_dc_block_id'] == parent_id), None)
    cell = next((row for row in cells if row['product_cell_id'] == block.get('product_cell_id')), None)
    role = _role(metadata.get('configuration_role'))
    if parents:
        role = 'special_tail'
    return dict(configuration_role=role, parent_block_code=parent['block_code'] if parent else '',
                cell_code=cell['cell_code'] if cell else '',
                usage_restrictions=metadata.get('usage_restrictions') or '',
                **{field: metadata.get(field) for field in DC_CONNECTION_FIELDS})


def structure_issues(block: dict, parent: dict | None, cells: list[dict]) -> tuple[list[str], list[str]]:
    # The revision structure checker compares canonical cell payloads. Runtime
    # catalogue rows additionally carry ORM timestamps, which are not JSON data.
    by_id = {row['product_cell_id']: {key: value for key, value in row.items()
                                    if key not in {'created_at', 'updated_at'}} for row in cells}
    missing, conflicts = _structure(
        {'snapshot': {'product': parent or {}, 'cell': by_id.get((parent or {}).get('product_cell_id'))}},
        {'snapshot': {'product': block, 'cell': by_id.get(block.get('product_cell_id'))}},
    )
    return (['Parent product required'] if parent is None else []) + missing, conflicts


def prepare_maintenance(values: dict, existing: dict | None, blocks: list[dict],
                        cells: list[dict], registered_parents: dict[str, set[str]]) -> dict:
    """Resolve human codes inside the same transaction as the catalogue write.

    Missing draft parameters are allowed. Known incompatible special-tail
    declarations are rejected. Raw legacy callers retain their prior semantics.
    """
    prepared = dict(values)
    strict = bool(MAINTENANCE_FIELDS & prepared.keys()) or (
        isinstance(prepared.get('metadata_json'), dict) and
        bool({'configuration_role', 'parent_product_id', *DC_CONNECTION_FIELDS} & prepared['metadata_json'].keys()))
    # CSV/XLSX is parsed as text to preserve product codes. Resolve declared
    # numeric values before the same structural checks used by the form.
    for column in ProductDCBlock.__table__.columns:
        value = prepared.get(column.name)
        if isinstance(column.type, Float) and value is not None and (strict or isinstance(value, str)):
            try:
                if isinstance(value, bool):
                    raise ValueError
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f'{column.name}: enter a finite number.') from exc
            if not math.isfinite(number):
                raise ValueError(f'{column.name}: enter a finite number.')
            prepared[column.name] = number
    previous = (existing or {}).get('metadata_json') or {}
    metadata = dict(previous)
    supplied = prepared.get('metadata_json')
    if 'metadata_json' in prepared:
        if not isinstance(supplied, dict):
            raise ValueError('Product metadata must be a mapping.')
        metadata.update(supplied)
    current = dict(existing or {})
    current.update(prepared)
    current['metadata_json'] = metadata
    parents = registered_parents.get(current.get('product_dc_block_id'), set())
    explicit = bool(MAINTENANCE_FIELDS & prepared.keys()) or bool(
        supplied and {'configuration_role', 'parent_product_id', *DC_CONNECTION_FIELDS} & supplied.keys())
    was_special = previous.get('configuration_role') == 'engineering_variant' or bool(parents)
    default_role = metadata.get('configuration_role') or ('engineering_variant' if parents else 'standard')
    if ('configuration_role' in prepared and supplied and 'configuration_role' in supplied
            and _role(prepared['configuration_role']) != _role(supplied['configuration_role'])):
        raise ValueError('Configuration role conflicts with the supplied metadata role.')
    role = _role(prepared.pop('configuration_role', default_role))
    if was_special and role != 'special_tail':
        raise ValueError('Special tail records remain excluded from standard sizing; their role cannot be changed to Standard here.')

    if 'cell_code' in prepared:
        code = str(prepared.pop('cell_code') or '').strip()
        cell = next((row for row in cells if row['cell_code'] == code), None)
        if code and cell is None:
            raise ValueError('Linked cell code was not found. Maintain the cell product first.')
        if 'product_cell_id' in prepared and prepared['product_cell_id'] != (cell or {}).get('product_cell_id'):
            raise ValueError('Linked cell code and linked cell identity differ.')
        prepared['product_cell_id'] = (cell or {}).get('product_cell_id')
        current['product_cell_id'] = prepared['product_cell_id']

    if 'parent_block_code' in prepared:
        code = str(prepared.pop('parent_block_code') or '').strip()
        parent = next((row for row in blocks if row['block_code'] == code), None)
        if code and parent is None:
            raise ValueError('Parent product code was not found. Save the parent product first.')
        parent_id = (parent or {}).get('product_dc_block_id')
        if supplied and 'parent_product_id' in supplied and supplied['parent_product_id'] != parent_id:
            raise ValueError('Parent product code and parent identity differ.')
        if parents and parents != {parent_id}:
            raise ValueError('Parent product conflicts with registered configuration lineage.')
        metadata['parent_product_id'] = parent_id
    parent_id = metadata.get('parent_product_id')
    parent_was_supplied = ('parent_block_code' in values or
                           supplied is not None and 'parent_product_id' in supplied)
    if parents and (parent_was_supplied or parent_id) and parents != {parent_id}:
        raise ValueError('Parent product conflicts with registered configuration lineage.')
    if not parent_id and len(parents) == 1:
        parent_id = next(iter(parents))
    parent = next((row for row in blocks if row['product_dc_block_id'] == parent_id), None)
    if parent_id and parent is None:
        raise ValueError('Parent product reference is no longer available.')
    if parent and (parent_id == current.get('product_dc_block_id') or parent['block_code'] == current.get('block_code')):
        raise ValueError('A product cannot be its own parent.')
    if parent and (_role((parent.get('metadata_json') or {}).get('configuration_role')) == 'special_tail'
                   or registered_parents.get(parent_id)):
        raise ValueError('A special tail cannot be used as a parent product.')
    if role == 'standard' and parent:
        raise ValueError('A parent product applies only to Special tail records.')
    if 'usage_restrictions' in prepared:
        restrictions = prepared.pop('usage_restrictions')
        if restrictions is not None and not isinstance(restrictions, str):
            raise ValueError('Usage restrictions must be text.')
        metadata['usage_restrictions'] = (restrictions or '').strip()
    for field in DC_CONNECTION_FIELDS:
        if field in prepared:
            value = dc_connection_value(field, prepared.pop(field))
            if supplied and field in supplied and dc_connection_value(field, supplied[field]) != value:
                raise ValueError(f'{_FIELD_LABELS[field]} conflicts with the supplied metadata value.')
        elif supplied is not None and field in supplied:
            value = dc_connection_value(field, supplied[field])
        else:
            continue
        if value is None or value == '':
            metadata.pop(field, None)
        else:
            metadata[field] = value
    declared_connection = any(field in metadata for field in DC_CONNECTION_COUNT_FIELDS)
    if role == 'special_tail' and (
            explicit and (parent or MAINTENANCE_FIELDS & values.keys()) or declared_connection):
        # Legacy raw drafts retain their earlier behavior. Once a product declares
        # an interface, raw structural edits must not bypass its bounded family.
        _, conflicts = structure_issues(current, parent, cells)
        if conflicts:
            raise ValueError('; '.join(conflicts))
    if explicit or supplied is not None or role == 'special_tail':
        _, conflicts = connection_issues(current, dict(
            configuration_role=role, **{field: metadata.get(field) for field in DC_CONNECTION_FIELDS}))
        if conflicts:
            raise ValueError('; '.join(conflicts))
    if role == 'special_tail':
        metadata['configuration_role'] = 'engineering_variant'
    elif 'configuration_role' in metadata:
        metadata['configuration_role'] = 'standard'
    if explicit or supplied is not None:
        prepared['metadata_json'] = metadata
    return prepared
