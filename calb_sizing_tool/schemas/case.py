from __future__ import annotations

from calb_sizing_tool.domain.enums import ScenarioMode
from calb_sizing_tool.schemas.common import CanonicalBaseModel


class SizingCaseInput(CanonicalBaseModel):
    fixture_id: str | None = None
    project_name: str = "CALB ESS Project"
    scenario_id: ScenarioMode = ScenarioMode.CONTAINER_ONLY
    poi_power_req_mw: float = 100.0
    poi_energy_req_mwh: float = 400.0
    poi_nominal_voltage_kv: float = 33.0
    poi_frequency_hz: float = 50.0
    project_life_years: int = 20
    cycles_per_year: int = 365
    poi_guarantee_year: int = 0
    eff_dc_cables: float | None = None
    eff_pcs: float | None = None
    eff_mvt: float | None = None
    eff_ac_cables_sw_rmu: float | None = None
    eff_hvt_others: float | None = None
    sc_time_months: int | None = None
    dod_pct: float | None = None
    dc_round_trip_efficiency_pct: float | None = None
    rte_curve_adjust_pp: float = 0.0
    rte_monotonic_enforce: bool = True
    # UI operating choices are persisted with the case so a restored run
    # reopens with the same search paths and efficiency basis.
    poi_frequency_option: str | float | None = None
    enable_hybrid: bool = False
    enable_cabinet_only: bool = False
    hybrid_disable_threshold_mwh: float = 20.0
    poi_is_dc_side: bool = False
