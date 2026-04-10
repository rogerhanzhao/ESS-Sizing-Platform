from __future__ import annotations

import pandas as pd

from calb_sizing_tool.schemas.common import CanonicalBaseModel


class Stage3YearRecord(CanonicalBaseModel):
    year_index: int
    soh_relative: float
    soh_absolute: float
    dc_nameplate_bol_mwh: float
    dc_gross_capacity_mwh: float
    dc_usable_mwh: float
    dc_rte_frac: float
    system_rte_frac: float
    poi_usable_energy_mwh: float
    meets_poi_req: bool
    is_guarantee_year: bool
    soh_display_pct: float
    soh_absolute_pct: float
    dc_rte_pct: float
    system_rte_pct: float

    def to_legacy_record(self) -> dict:
        return {
            "Year_Index": self.year_index,
            "SOH_Relative": self.soh_relative,
            "SOH_Absolute": self.soh_absolute,
            "DC_Nameplate_BOL_MWh": self.dc_nameplate_bol_mwh,
            "DC_Gross_Capacity_MWh": self.dc_gross_capacity_mwh,
            "DC_Usable_MWh": self.dc_usable_mwh,
            "DC_RTE_Frac": self.dc_rte_frac,
            "System_RTE_Frac": self.system_rte_frac,
            "POI_Usable_Energy_MWh": self.poi_usable_energy_mwh,
            "Meets_POI_Req": self.meets_poi_req,
            "Is_Guarantee_Year": self.is_guarantee_year,
            "SOH_Display_Pct": self.soh_display_pct,
            "SOH_Absolute_Pct": self.soh_absolute_pct,
            "DC_RTE_Pct": self.dc_rte_pct,
            "System_RTE_Pct": self.system_rte_pct,
        }


class Stage3Meta(CanonicalBaseModel):
    poi_power_mw: float
    dc_power_mw: float
    effective_c_rate: float
    soh_profile_id: int
    rte_profile_id: int
    chosen_soh_c_rate: float
    chosen_soh_cycles_per_year: int
    chosen_rte_c_rate: float
    rte_adjust_pp: float
    rte_monotonic_enforce: bool

    def to_legacy_dict(self) -> dict:
        return self.model_dump()


class Stage3Result(CanonicalBaseModel):
    rows: list[Stage3YearRecord]
    meta: Stage3Meta

    def dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([row.to_legacy_record() for row in self.rows])
