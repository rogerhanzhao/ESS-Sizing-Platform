from __future__ import annotations

import math

import pandas as pd

from calb_sizing_tool.schemas.stage2 import Stage2ConfigItem, Stage2Result


K_MAX_FIXED = 10


def pick_dc_block(df_blocks: pd.DataFrame, form: str):
    df = df_blocks.copy()
    df["Block_Form_L"] = df["Block_Form"].astype(str).str.lower()
    candidates = df[(df["Block_Form_L"] == form.lower()) & (df["Is_Active"] == 1)]
    if candidates.empty:
        return None
    preferred = candidates[candidates["Is_Default_Option"] == 1]
    if preferred.empty:
        preferred = candidates
    preferred = preferred.sort_values("Block_Nameplate_Capacity_Mwh", ascending=False)
    row = preferred.iloc[0]
    return str(row["Dc_Block_Code"]), str(row["Dc_Block_Name"]), float(row["Block_Nameplate_Capacity_Mwh"])


def _build_items(rows: list[dict]) -> list[Stage2ConfigItem]:
    if not rows:
        return []
    total = round(sum(float(row["Unit Capacity (MWh)"]) * int(row["Count"]) for row in rows), 3)
    items: list[Stage2ConfigItem] = []
    for row in rows:
        subtotal = round(float(row["Unit Capacity (MWh)"]) * int(row["Count"]), 3)
        items.append(
            Stage2ConfigItem(
                block_code=str(row["Block Code"]),
                block_name=str(row["Block Name"]),
                form=str(row["Form"]),
                unit_capacity_mwh=round(float(row["Unit Capacity (MWh)"]), 3),
                count=int(row["Count"]),
                subtotal_mwh=subtotal,
                total_dc_nameplate_bol_mwh=total,
            )
        )
    return items


def build_config_container_only(required_dc_mwh: float, container_unit: float, container_code: str, container_name: str) -> Stage2Result:
    count = int(math.ceil(required_dc_mwh / container_unit)) if required_dc_mwh > 0 else 0
    items = _build_items(
        [
            {
                "Block Code": container_code,
                "Block Name": container_name,
                "Form": "container",
                "Unit Capacity (MWh)": container_unit,
                "Count": count,
            }
        ]
    )
    total = items[0].total_dc_nameplate_bol_mwh if items else 0.0
    return Stage2Result(
        mode="container_only",
        dc_nameplate_bol_mwh=total,
        oversize_mwh=total - required_dc_mwh,
        config_adjustment_frac=(total / required_dc_mwh - 1.0) if required_dc_mwh > 0 else 0.0,
        block_config_items=items,
        container_count=count,
        cabinet_count=0,
        busbars_needed=0,
    )


def build_config_cabinet_only(required_dc_mwh: float, cabinet_unit: float, cabinet_code: str, cabinet_name: str, k_max: int = K_MAX_FIXED) -> Stage2Result:
    count = int(math.ceil(required_dc_mwh / cabinet_unit)) if required_dc_mwh > 0 else 0
    items = _build_items(
        [
            {
                "Block Code": cabinet_code,
                "Block Name": cabinet_name,
                "Form": "cabinet",
                "Unit Capacity (MWh)": cabinet_unit,
                "Count": count,
            }
        ]
    )
    total = items[0].total_dc_nameplate_bol_mwh if items else 0.0
    return Stage2Result(
        mode="cabinet_only",
        dc_nameplate_bol_mwh=total,
        oversize_mwh=total - required_dc_mwh,
        config_adjustment_frac=(total / required_dc_mwh - 1.0) if required_dc_mwh > 0 else 0.0,
        block_config_items=items,
        container_count=0,
        cabinet_count=count,
        busbars_needed=int(math.ceil(count / k_max)) if count > 0 else 0,
    )


def build_config_hybrid(
    required_dc_mwh: float,
    container_unit: float,
    container_code: str,
    container_name: str,
    cabinet_unit: float,
    cabinet_code: str,
    cabinet_name: str,
    k_max: int = K_MAX_FIXED,
) -> Stage2Result:
    if required_dc_mwh <= 0:
        container_count = 0
        cabinet_count = 0
    else:
        container_count = int(math.floor(required_dc_mwh / container_unit))
        remainder = required_dc_mwh - container_count * container_unit
        if remainder <= 1e-9:
            cabinet_count = 0
        else:
            cabinet_count = int(math.ceil(remainder / cabinet_unit))
            if cabinet_count > k_max:
                container_count += 1
                cabinet_count = 0

    rows: list[dict] = []
    if container_count > 0:
        rows.append(
            {
                "Block Code": container_code,
                "Block Name": container_name,
                "Form": "container",
                "Unit Capacity (MWh)": container_unit,
                "Count": container_count,
            }
        )
    if cabinet_count > 0:
        rows.append(
            {
                "Block Code": cabinet_code,
                "Block Name": cabinet_name,
                "Form": "cabinet",
                "Unit Capacity (MWh)": cabinet_unit,
                "Count": cabinet_count,
            }
        )
    items = _build_items(rows)
    total = items[0].total_dc_nameplate_bol_mwh if items else 0.0
    return Stage2Result(
        mode="hybrid",
        dc_nameplate_bol_mwh=total,
        oversize_mwh=total - required_dc_mwh,
        config_adjustment_frac=(total / required_dc_mwh - 1.0) if required_dc_mwh > 0 else 0.0,
        block_config_items=items,
        container_count=container_count,
        cabinet_count=cabinet_count,
        busbars_needed=1 if cabinet_count > 0 else 0,
    )


def rebuild_stage2_counts(
    stage2: Stage2Result,
    *,
    required_dc_mwh: float,
    container_code: str,
    container_name: str,
    container_unit: float,
    cabinet_code: str,
    cabinet_name: str,
    cabinet_unit: float,
    k_max: int = K_MAX_FIXED,
) -> Stage2Result:
    rows: list[dict] = []
    if stage2.container_count > 0:
        rows.append(
            {
                "Block Code": container_code,
                "Block Name": container_name,
                "Form": "container",
                "Unit Capacity (MWh)": container_unit,
                "Count": stage2.container_count,
            }
        )
    if stage2.cabinet_count > 0:
        rows.append(
            {
                "Block Code": cabinet_code,
                "Block Name": cabinet_name,
                "Form": "cabinet",
                "Unit Capacity (MWh)": cabinet_unit,
                "Count": stage2.cabinet_count,
            }
        )
    items = _build_items(rows)
    total = items[0].total_dc_nameplate_bol_mwh if items else 0.0
    busbars_needed = stage2.busbars_needed
    if stage2.mode == "cabinet_only":
        busbars_needed = int(math.ceil(stage2.cabinet_count / k_max)) if stage2.cabinet_count > 0 else 0
    elif stage2.mode == "hybrid":
        busbars_needed = 1 if stage2.cabinet_count > 0 else 0
    elif stage2.mode == "container_only":
        busbars_needed = 0

    return Stage2Result(
        mode=stage2.mode,
        dc_nameplate_bol_mwh=total,
        oversize_mwh=total - required_dc_mwh,
        config_adjustment_frac=(total / required_dc_mwh - 1.0) if required_dc_mwh > 0 else 0.0,
        block_config_items=items,
        container_count=stage2.container_count,
        cabinet_count=stage2.cabinet_count,
        busbars_needed=busbars_needed,
    )
