from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from calb_sizing_tool.common.nameplate import apply_block_nameplate_recalc
from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle


REQUIRED_DC_SHEETS = [
    "ess_sizing_case",
    "dc_block_template_314_data",
    "battery_cell_type_314_data",
    "pack_type_314_data",
    "rack_type_314_data",
    "soh_profile_314_data",
    "soh_curve_314_template",
    "rte_profile_314_data",
    "rte_curve_314_template",
]


def _build_defaults(df_case: pd.DataFrame) -> dict:
    defaults: dict[str, object] = {}
    for _, row in df_case.iterrows():
        field_name = row.get("Field Name")
        if isinstance(field_name, str) and field_name.strip():
            defaults[field_name.strip()] = row.get("Default Value")
    return defaults


@lru_cache(maxsize=4)
def _load_cached_bundle(path_str: str) -> DcExcelMasterDataBundle:
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(f"Data file not found at {path}")

    xls = pd.ExcelFile(path)
    missing = [sheet for sheet in REQUIRED_DC_SHEETS if sheet not in xls.sheet_names]
    if missing:
        raise ValueError(f"Workbook missing required sheets: {', '.join(missing)}")

    raw = {sheet: pd.read_excel(xls, sheet) for sheet in REQUIRED_DC_SHEETS}
    df_blocks = raw["dc_block_template_314_data"].copy()
    try:
        df_blocks = apply_block_nameplate_recalc(
            df_blocks,
            raw["rack_type_314_data"],
            raw["pack_type_314_data"],
            raw["battery_cell_type_314_data"],
        )
    except Exception:
        pass

    return DcExcelMasterDataBundle(
        workbook_path=path,
        defaults=_build_defaults(raw["ess_sizing_case"]),
        df_blocks=df_blocks,
        df_soh_profile=raw["soh_profile_314_data"].copy(),
        df_soh_curve=raw["soh_curve_314_template"].copy(),
        df_rte_profile=raw["rte_profile_314_data"].copy(),
        df_rte_curve=raw["rte_curve_314_template"].copy(),
        raw_sheets=raw,
    )


def load_dc_excel_bundle_from_path(path: Path) -> DcExcelMasterDataBundle:
    return _load_cached_bundle(str(path.resolve()))


def bundle_to_legacy_tuple(bundle: DcExcelMasterDataBundle) -> tuple:
    return (
        dict(bundle.defaults),
        bundle.df_blocks.copy(),
        bundle.df_soh_profile.copy(),
        bundle.df_soh_curve.copy(),
        bundle.df_rte_profile.copy(),
        bundle.df_rte_curve.copy(),
    )
