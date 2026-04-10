from __future__ import annotations

from typing import Literal

import pandas as pd

from calb_sizing_tool.schemas.common import CanonicalBaseModel


class Stage2ConfigItem(CanonicalBaseModel):
    block_code: str
    block_name: str
    form: Literal["container", "cabinet"]
    unit_capacity_mwh: float
    count: int
    subtotal_mwh: float
    total_dc_nameplate_bol_mwh: float

    def to_legacy_record(self) -> dict:
        return {
            "Block Code": self.block_code,
            "Block Name": self.block_name,
            "Form": self.form,
            "Unit Capacity (MWh)": self.unit_capacity_mwh,
            "Count": self.count,
            "Subtotal (MWh)": self.subtotal_mwh,
            "Total DC Nameplate @BOL (MWh)": self.total_dc_nameplate_bol_mwh,
        }


class Stage2Result(CanonicalBaseModel):
    mode: str
    dc_nameplate_bol_mwh: float
    oversize_mwh: float
    config_adjustment_frac: float
    block_config_items: list[Stage2ConfigItem]
    container_count: int
    cabinet_count: int
    busbars_needed: int

    def block_config_table(self) -> pd.DataFrame:
        return pd.DataFrame([item.to_legacy_record() for item in self.block_config_items])

    def to_legacy_dict(self) -> dict:
        payload = self.model_dump()
        payload["block_config_table_records"] = [item.to_legacy_record() for item in self.block_config_items]
        payload["block_config_table"] = self.block_config_table()
        return payload
