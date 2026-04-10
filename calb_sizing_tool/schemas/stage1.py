from __future__ import annotations

from calb_sizing_tool.schemas.common import CanonicalBaseModel


class Stage1Input(CanonicalBaseModel):
    project_name: str = "CALB ESS Project"
    poi_power_req_mw: float = 100.0
    poi_energy_req_mwh: float = 400.0
    project_life_years: int = 20
    cycles_per_year: int = 365
    poi_guarantee_year: int = 0
    eff_dc_cables: float = 0.995
    eff_pcs: float = 0.985
    eff_mvt: float = 0.995
    eff_ac_cables_sw_rmu: float = 0.992
    eff_hvt_others: float = 1.0
    sc_time_months: int = 3
    dod_pct: float = 95.0
    dc_round_trip_efficiency_pct: float = 94.0
    rte_curve_adjust_pp: float = 0.0
    rte_monotonic_enforce: bool = True


class Stage1Result(CanonicalBaseModel):
    project_name: str
    poi_power_req_mw: float
    poi_energy_req_mwh: float
    project_life_years: int
    cycles_per_year: int
    poi_guarantee_year: int
    eff_dc_cables_frac: float
    eff_pcs_frac: float
    eff_mvt_frac: float
    eff_ac_cables_sw_rmu_frac: float
    eff_hvt_others_frac: float
    eff_dc_to_poi_frac: float
    sc_time_months: int
    sc_loss_pct: float
    sc_loss_frac: float
    dod_frac: float
    dc_round_trip_efficiency_frac: float
    dc_rte_base_frac: float
    dc_rte_effective_frac: float
    rte_curve_adjust_pp: float
    rte_adjust_frac: float
    rte_monotonic_enforce: bool
    dc_one_way_efficiency_frac: float
    dc_usable_bol_frac: float
    dc_energy_capacity_required_mwh: float
    dc_power_required_mw: float

    def to_legacy_dict(self) -> dict:
        return self.model_dump()
