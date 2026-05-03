from __future__ import annotations

import math
from typing import Any

import pandas as pd

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.master_data_repository import MasterDataRepository
from calb_sizing_tool.schemas.master_data import DcExcelMasterDataBundle


class MasterDataService:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url

    def has_soh_rte_data(self) -> bool:
        with session_scope(self.db_url) as session:
            return MasterDataRepository(session).has_soh_rte_data()

    def get_soh_rte_counts(self) -> dict[str, int]:
        with session_scope(self.db_url) as session:
            return MasterDataRepository(session).get_soh_rte_counts()

    def build_soh_rte_dataframes(self) -> dict[str, pd.DataFrame | None]:
        with session_scope(self.db_url) as session:
            return MasterDataRepository(session).build_soh_rte_dataframes()

    def migrate_soh_rte_from_excel_bundle(
        self,
        bundle: DcExcelMasterDataBundle,
        *,
        version_tag: str,
        source_ref: str,
    ) -> dict[str, int]:
        payload = _excel_bundle_to_soh_rte_payload(bundle)
        with session_scope(self.db_url) as session:
            return MasterDataRepository(session).replace_soh_rte_data(
                payload, version_tag=version_tag, source_ref=source_ref
            )


def _excel_bundle_to_soh_rte_payload(bundle: DcExcelMasterDataBundle) -> dict[str, list[dict[str, Any]]]:
    soh_profiles = []
    for _, row in bundle.df_soh_profile.iterrows():
        profile_id = _safe_int(row.get("Profile_Id"))
        if profile_id is None:
            continue
        soh_profiles.append({
            "source_profile_id": profile_id,
            "profile_name": _safe_str(row.get("Profile_Name")),
            "cycles_per_year": _safe_int(row.get("Cycles_Per_Year")),
            "c_rate": _safe_float(row.get("C_Rate")),
            "reference_temperature_c": _safe_float(row.get("Reference_Temperature_C")),
            "raw_row_json": {},
        })

    soh_curve_points = []
    for _, row in bundle.df_soh_curve.iterrows():
        profile_id = _safe_int(row.get("Profile_Id"))
        if profile_id is None:
            continue
        soh_curve_points.append({
            "source_profile_id": profile_id,
            "life_year_index": _safe_int(row.get("Life_Year_Index")),
            "cycle_index": _safe_int(row.get("Cycle_Index")),
            "soh_dc_pct": _safe_float(row.get("Soh_Dc_Pct")) or 0.0,
        })

    rte_profiles = []
    for _, row in bundle.df_rte_profile.iterrows():
        profile_id = _safe_int(row.get("Profile_Id"))
        if profile_id is None:
            continue
        rte_profiles.append({
            "source_profile_id": profile_id,
            "profile_name": _safe_str(row.get("Profile_Name")),
            "cycles_per_year": _safe_int(row.get("Cycles_Per_Year")),
            "c_rate": _safe_float(row.get("C_Rate")),
            "raw_row_json": {},
        })

    rte_curve_bands = []
    for _, row in bundle.df_rte_curve.iterrows():
        profile_id = _safe_int(row.get("Profile_Id"))
        if profile_id is None:
            continue
        rte_curve_bands.append({
            "source_profile_id": profile_id,
            "soh_band_min_pct": _safe_float(row.get("Soh_Band_Min_Pct")) or 0.0,
            "soh_band_max_pct": _safe_float(row.get("Soh_Band_Max_Pct")),
            "rte_dc_pct": _safe_float(row.get("Rte_Dc_Pct")) or 0.0,
        })

    return {
        "soh_profile": soh_profiles,
        "soh_curve_point": soh_curve_points,
        "rte_profile": rte_profiles,
        "rte_curve_band": rte_curve_bands,
    }


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    f = _safe_float(v)
    return None if f is None else int(f)


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("nan", "none", "n/a", "") else None
