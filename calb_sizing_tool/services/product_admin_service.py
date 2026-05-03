from __future__ import annotations

from typing import Any

import pandas as pd

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.product_admin_repository import ProductAdminRepository


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
        """Convert active ProductDCBlock records to the df_blocks schema expected by stage2 sizing.

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


def _to_dict(row: Any) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }
