from __future__ import annotations

import math
import json
from typing import Any

import pandas as pd
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.product_admin_repository import ProductAdminRepository
from calb_sizing_tool.services.dc_product_maintenance import (
    DC_BLOCK_FILE_COLUMNS, connection_issues, maintenance_fields, maintenance_message,
    prepare_maintenance, structure_issues,
)

# Columns that must be stored as int, not float, when read from CSV/Excel
_INT_COLUMNS = frozenset({
    "cycle_life_cycles", "launch_year", "cells_in_series", "strings_in_parallel",
    "racks_per_block", "packs_per_rack", "racks_per_container", "pack_count",
    "container_count", "sort_order", "pcs_count",
})


class ProductAdminService:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url

    def snapshot(self) -> dict[str, Any]:
        with session_scope(self.db_url) as session:
            repo = ProductAdminRepository(session)
            return {
                "counts": repo.counts(),
                "cells": [_to_dict(row) for row in repo.list_cells()],
                "dc_blocks": [_to_dict(row) for row in repo.list_dc_blocks()],
                "ac_blocks": [_to_dict(row) for row in repo.list_ac_blocks()],
                "assets": [_to_dict(row) for row in repo.list_assets()],
                "degradation_curves": [_to_dict(row) for row in repo.list_degradation_curves()],
                "rte_curves": [_to_dict(row) for row in repo.list_rte_curves()],
                "plugins": [_to_dict(row) for row in repo.list_plugins()],
            }

    def create_cell(self, values: dict[str, Any]) -> str:
        with session_scope(self.db_url) as session:
            row = ProductAdminRepository(session).create_cell(**values)
            return row.product_cell_id

    def create_dc_block(self, values: dict[str, Any]) -> str:
        with session_scope(self.db_url) as session:
            repo = ProductAdminRepository(session)
            blocks, cells, parents = _dc_context(session, repo)
            prepared = prepare_maintenance(values, None, blocks, cells, parents)
            row = repo.create_dc_block(**prepared)
            return row.product_dc_block_id

    def create_ac_block(self, values: dict[str, Any]) -> str:
        with session_scope(self.db_url) as session:
            row = ProductAdminRepository(session).create_ac_block(**values)
            return row.product_ac_block_id

    def create_asset(self, values: dict[str, Any]) -> str:
        with session_scope(self.db_url) as session:
            row = ProductAdminRepository(session).create_asset(**values)
            return row.product_asset_id

    def create_degradation_curve(self, values: dict[str, Any]) -> str:
        with session_scope(self.db_url) as session:
            row = ProductAdminRepository(session).create_degradation_curve(**values)
            return row.degradation_curve_id

    def create_rte_curve(self, values: dict[str, Any]) -> str:
        with session_scope(self.db_url) as session:
            row = ProductAdminRepository(session).create_rte_curve(**values)
            return row.rte_curve_id

    def create_plugin(self, values: dict[str, Any]) -> str:
        with session_scope(self.db_url) as session:
            row = ProductAdminRepository(session).create_plugin(**values)
            return row.degradation_plugin_id

    def update_record(self, entity: str, record_id: str, values: dict[str, Any]) -> bool:
        with session_scope(self.db_url) as session:
            repo = ProductAdminRepository(session)
            if entity == 'dc_block':
                existing = repo.get_record(entity, record_id)
                if existing is None:
                    return False
                blocks, cells, parents = _dc_context(session, repo)
                values = prepare_maintenance(values, _to_dict(existing), blocks, cells, parents)
            row = repo.update_record(entity, record_id, values)
            return row is not None

    def dc_block_maintenance_rows(self, snapshot: dict | None = None) -> list[dict]:
        """Original catalogue presentation; no persisted readiness or activation."""
        from calb_sizing_tool.services.dc_catalogue_readiness_service import dc_catalogue_readiness, _positive

        snapshot = snapshot if snapshot is not None else self.snapshot()
        blocks, cells = snapshot['dc_blocks'], snapshot['cells']
        with session_scope(self.db_url) as session:
            parents = _registered_dc_parents(session)
        diagnostics = {row['Product']: row for row in dc_catalogue_readiness(
            snapshot, self.df_blocks_as_sizing_dataframe())}
        by_id = {row['product_dc_block_id']: row for row in blocks}
        cells_by_id = {row['product_cell_id']: row for row in cells}
        result = []
        for block in blocks:
            fields = maintenance_fields(block, blocks, cells, parents)
            diagnostic = diagnostics[block['block_code']]['Parameter review']
            issues = [] if diagnostic.startswith('Basic fields present;') else [diagnostic]
            connection_missing, conflicts = connection_issues(block, fields)
            issues.extend(connection_missing)
            if fields['configuration_role'] == 'special_tail':
                parent_id = (block.get('metadata_json') or {}).get('parent_product_id')
                registered = parents.get(block['product_dc_block_id'], set())
                if not parent_id and len(registered) == 1:
                    parent_id = next(iter(registered))
                missing, structure_conflicts = structure_issues(block, by_id.get(parent_id), cells)
                conflicts.extend(structure_conflicts)
                issues.extend(missing)
                if registered and registered != {parent_id}:
                    conflicts.append('Parent declaration conflicts with registered lineage')
                if not fields['usage_restrictions']:
                    issues.append('Usage restrictions required')
            for key in ('nominal_voltage_v', 'dimension_width_mm', 'dimension_depth_mm', 'dimension_height_mm'):
                if not _positive(block.get(key)):
                    issues.append(f'{key}: confirmed positive value required')
            if not str(block.get('source_ref') or '').strip() or block.get('source_ref') == 'admin_portal':
                issues.append('Technical source reference required')
            if conflicts:
                status = 'Incompatible declaration'
            elif issues:
                status = 'Incomplete'
            else:
                status = 'Basic fields present; review pending'
            detail = maintenance_message('; '.join(dict.fromkeys(conflicts + issues)))
            if fields['configuration_role'] == 'special_tail':
                detail += ('; ' if detail else '') + 'Excluded from standard sizing; tail integration and engineering review pending'
            result.append(dict(block, **fields, parameter_status=status,
                parameter_details=detail or 'Engineering review still required',
                # Runtime comparisons must reject known incompatibilities without
                # turning missing engineering ratings into product approval gates.
                maintenance_conflicts=list(dict.fromkeys(conflicts)),
                linked_cell_snapshot=cells_by_id.get(block.get('product_cell_id'))))
        return result

    def export_dc_blocks_dataframe(self) -> pd.DataFrame:
        """Create-only import fields with human codes instead of internal IDs."""
        return pd.DataFrame(self.dc_block_maintenance_rows(), columns=DC_BLOCK_FILE_COLUMNS)

    def dc_block_import_preview_dataframe(self, rows: list[tuple[int, dict]]) -> pd.DataFrame:
        """Human-readable preview only; import retains the full normalized rows."""
        with session_scope(self.db_url) as session:
            blocks, cells, parents = _dc_context(session, ProductAdminRepository(session))
            display = []
            for line, values in rows[:5]:
                prepared = prepare_maintenance(values, None, blocks, cells, parents)
                fields = maintenance_fields(prepared, blocks, cells, parents)
                display.append({
                    'Row': line, 'Code': prepared.get('block_code'), 'Name': prepared.get('block_name'),
                    'Use': 'Special tail' if fields['configuration_role'] == 'special_tail' else 'Standard',
                    'Parent': fields['parent_block_code'], 'Cell': fields['cell_code'],
                    'Gross MWh': prepared.get('gross_energy_mwh'),
                    'Nominal power (kW)': prepared.get('nominal_power_kw'),
                    'Current limit (A)': prepared.get('max_current_a'),
                    'DC outputs': fields['dc_output_count'],
                    'Maximum connected PCS': fields['max_connected_pcs'],
                    'DC connection source': fields['dc_topology_source_ref'] or '',
                })
            return pd.DataFrame(display)

    def df_blocks_as_sizing_dataframe(self) -> pd.DataFrame:
        """Convert ProductDCBlock records to the df_blocks schema expected by stage2 sizing.

        Every record is carried. Existing records retain Active/Published
        semantics. Registered or explicitly marked engineering child variants
        are ineligible for the standard picker regardless of those flags;
        their separate comparison interface owns special-scenario eligibility.

        Required columns: Dc_Block_Code, Dc_Block_Name, Block_Form,
                          Block_Nameplate_Capacity_Mwh, Is_Active, Is_Default_Option
        """
        _COLS = [
            "Dc_Block_Code", "Dc_Block_Name", "Block_Form",
            "Block_Nameplate_Capacity_Mwh", "Is_Active", "Is_Default_Option",
        ]
        with session_scope(self.db_url) as session:
            # Materialize values before commit expires and detaches ORM rows.
            rows = [_to_dict(row) for row in ProductAdminRepository(session).list_dc_blocks()]
            restricted = set()
            if inspect(session.connection()).has_table('dc_configuration_variant'):
                from calb_sizing_tool.infra.db.models import DcConfigurationVariant
                restricted = set(session.scalars(select(DcConfigurationVariant.child_product_id)))
        records = []
        for row in rows:
            form = (row.get("block_form") or "").strip().lower()
            if form not in ("container", "cabinet"):
                form = "container"
            capacity = row.get("gross_energy_mwh")
            if not capacity:
                kwh = row.get("rated_capacity_kwh")
                capacity = (kwh / 1000.0) if kwh else 0.0
            records.append({
                "Dc_Block_Code": row["block_code"],
                "Dc_Block_Name": row["block_name"],
                "Block_Form": form,
                "Block_Nameplate_Capacity_Mwh": float(capacity or 0.0),
                "Is_Active": int(bool(row["is_active"]) and row['product_dc_block_id'] not in restricted
                    and (row.get('metadata_json') or {}).get('configuration_role') != 'engineering_variant'),
                "Is_Default_Option": 1 if row["is_published"] else 0,
            })
        if not records:
            return pd.DataFrame(columns=_COLS)
        return pd.DataFrame(records)


    def preview_import_from_df(self, df: pd.DataFrame, entity: str | None = None) -> dict[str, Any]:
        """Normalize spreadsheet values without writing any records."""
        if df.columns.duplicated().any():
            return {"rows": [], "errors": ["Duplicate column names are not supported."]}
        rows, errors = [], []
        for line, (_, row) in enumerate(df.iterrows(), start=2):
            try:
                values = _normalize_import_row(row)
                if entity == 'dc_block':
                    with session_scope(self.db_url) as session:
                        repo = ProductAdminRepository(session)
                        blocks, cells, parents = _dc_context(session, repo)
                        prepare_maintenance(values, None, blocks, cells, parents)
                rows.append((line, values))
            except ValueError as exc:
                errors.append(f"Row {line}: {exc}")
        return {"rows": rows, "errors": errors}

    def import_records_from_df(
        self, entity: str, df: pd.DataFrame
    ) -> dict[str, Any]:
        """Bulk-import rows from a DataFrame.

        Returns {"imported": int, "skipped": int, "errors": list[str]}.
        Each row is coerced and passed to the matching single-record create method.
        Rows that raise an exception are skipped and recorded in errors.
        """
        _create = {
            "cell": self.create_cell,
            "dc_block": self.create_dc_block,
            "ac_block": self.create_ac_block,
            "asset": self.create_asset,
            "degradation_curve": self.create_degradation_curve,
            "rte_curve": self.create_rte_curve,
            "plugin": self.create_plugin,
        }
        create_fn = _create.get(entity)
        if create_fn is None:
            return {"imported": 0, "skipped": 0, "errors": [f"Unknown entity type: {entity}"]}

        imported = skipped = 0
        errors: list[str] = []

        preview = self.preview_import_from_df(df, entity=entity)
        errors.extend(preview["errors"])
        if df.columns.duplicated().any():
            return {"imported": 0, "skipped": len(df), "errors": errors}
        skipped = len(errors)
        for line, values in preview["rows"]:
            try:
                create_fn(values)
                imported += 1
            except IntegrityError as exc:
                skipped += 1
                code = values.get("block_code") or values.get("cell_code") or values.get("asset_code") or values.get("curve_code") or values.get("plugin_key") or "record"
                if "unique" in str(exc.orig).lower() or "duplicate" in str(exc.orig).lower():
                    errors.append(f"Row {line}: Code '{code}' already exists. Existing records were not changed.")
                else:
                    errors.append(f"Row {line}: Record could not be saved. Check required fields and linked records.")
            except ValueError as exc:
                skipped += 1
                errors.append(f"Row {line}: {exc}")
            except Exception as exc:
                skipped += 1
                errors.append(f"Row {line}: Record could not be saved. Check column names and field types.")

        return {"imported": imported, "skipped": skipped, "errors": errors}


def _normalize_import_row(row: pd.Series) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for col, val in row.items():
        if not col or str(col).startswith("_"):
            continue
        missing = val is None or (not isinstance(val, (list, dict)) and pd.isna(val))
        if missing or (isinstance(val, str) and not val.strip()):
            # Blank optional fields keep model defaults, including JSON containers.
            continue
        if col in {"is_active", "is_published", "is_primary"}:
            token = str(val).strip().lower()
            if token in {"true", "1", "1.0", "yes"}:
                values[col] = True
            elif token in {"false", "0", "0.0", "no"}:
                values[col] = False
            else:
                raise ValueError(f"{col}: use true/false or 1/0")
        elif col in _INT_COLUMNS:
            try:
                number = float(val)
            except (TypeError, ValueError):
                # Retain legacy optional nonnumeric-to-null behavior.
                if col == "pcs_count":
                    raise ValueError("pcs_count: must be a positive integer")
                values[col] = None
                continue
            if not math.isfinite(number) or not number.is_integer():
                raise ValueError(f"{col}: must be a finite integer")
            if col == "pcs_count" and number <= 0:
                raise ValueError("pcs_count: must be a positive integer")
            values[col] = int(number)
        elif str(col).endswith("_json"):
            try:
                parsed = json.loads(val) if isinstance(val, str) else val
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{col}: invalid JSON") from exc
            expected = list if col in {"cycle_points_json", "calendar_points_json"} else dict
            if not isinstance(parsed, expected):
                raise ValueError(f"{col}: expected JSON {expected.__name__}")
            values[col] = parsed
        else:
            values[col] = val.strip() if isinstance(val, str) else val
    return values


def _to_dict(row: Any) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


def _registered_dc_parents(session) -> dict[str, set[str]]:
    if not inspect(session.connection()).has_table('dc_configuration_variant'):
        return {}
    from calb_sizing_tool.infra.db.models import DcConfigurationVariant
    result: dict[str, set[str]] = {}
    for child, parent in session.execute(select(
        DcConfigurationVariant.child_product_id, DcConfigurationVariant.parent_product_id)):
        result.setdefault(child, set()).add(parent)
    return result


def _dc_context(session, repo):
    return ([_to_dict(row) for row in repo.list_dc_blocks()],
            [_to_dict(row) for row in repo.list_cells()], _registered_dc_parents(session))
