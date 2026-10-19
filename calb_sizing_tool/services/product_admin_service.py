from __future__ import annotations

import math
import json
from typing import Any

import pandas as pd
from sqlalchemy.exc import IntegrityError

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.product_admin_repository import ProductAdminRepository

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
            row = ProductAdminRepository(session).create_dc_block(**values)
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
            row = ProductAdminRepository(session).update_record(entity, record_id, values)
            return row is not None

    def df_blocks_as_sizing_dataframe(self) -> pd.DataFrame:
        """Convert ProductDCBlock records to the df_blocks schema expected by stage2 sizing.

        Every record is carried, active or not, with its state in `Is_Active` —
        `stage2_service.pick_dc_block` is the one place that filters on it, so
        the caller must not pre-filter and call the result the sizing input.

        Required columns: Dc_Block_Code, Dc_Block_Name, Block_Form,
                          Block_Nameplate_Capacity_Mwh, Is_Active, Is_Default_Option
        """
        _COLS = [
            "Dc_Block_Code", "Dc_Block_Name", "Block_Form",
            "Block_Nameplate_Capacity_Mwh", "Is_Active", "Is_Default_Option",
        ]
        with session_scope(self.db_url) as session:
            rows = ProductAdminRepository(session).list_dc_blocks()
        records = []
        for row in rows:
            form = (getattr(row, "block_form", None) or "").strip().lower()
            if form not in ("container", "cabinet"):
                form = "container"
            capacity = getattr(row, "gross_energy_mwh", None)
            if not capacity:
                kwh = getattr(row, "rated_capacity_kwh", None)
                capacity = (kwh / 1000.0) if kwh else 0.0
            records.append({
                "Dc_Block_Code": row.block_code,
                "Dc_Block_Name": row.block_name,
                "Block_Form": form,
                "Block_Nameplate_Capacity_Mwh": float(capacity or 0.0),
                "Is_Active": 1 if row.is_active else 0,
                "Is_Default_Option": 1 if row.is_published else 0,
            })
        if not records:
            return pd.DataFrame(columns=_COLS)
        return pd.DataFrame(records)


    def preview_import_from_df(self, df: pd.DataFrame) -> dict[str, Any]:
        """Normalize spreadsheet values without writing any records."""
        if df.columns.duplicated().any():
            return {"rows": [], "errors": ["Duplicate column names are not supported."]}
        rows, errors = [], []
        for line, (_, row) in enumerate(df.iterrows(), start=2):
            try:
                rows.append((line, _normalize_import_row(row)))
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

        preview = self.preview_import_from_df(df)
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
