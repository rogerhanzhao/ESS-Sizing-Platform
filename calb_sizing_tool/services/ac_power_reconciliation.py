# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

"""AC Sizing power reconciliation (POI <-> AC Block), per AC_SIZING_SPEC_V1.

Read-only check that the governed AC configuration reconciles the two AC-Sizing
lines within the adjustment band. It does NOT change any sizing:

- Line 1 (power, top-down from POI): refer the POI power requirement back to the
  AC-block MV terminal through only the MV->POI losses, and compare against the
  governed AC aggregate rated power.
- Line 2 (DC-side power): dc_power_required = poi_power / eff_chain (this is the
  FROZEN Stage 1 value; reproduced here only for the DC:AC ratio, never recomputed
  as sizing).

The band is intentionally soft (PCS overload, DC:AC over-provisioning, oversize
tolerance) — the goal is landing on a clean product configuration inside the
band, not an exact equality. The constants below are TYPICAL / PROVISIONAL and
are the single place to tune once the owner confirms them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- tunable typical/provisional band constants (single source of truth) ------
# PCS continuous nameplate is not a hard ceiling; short-term overload headroom.
# Ties to the existing safety_factor=1.1 used in ac_sizing_service.
PCS_OVERLOAD_FACTOR: float = 1.10
# POI power closure band — matches evaluate_ac_sizing_feasibility (0.95 / 1.05).
POI_POWER_CLOSURE_MIN: float = 0.95
POI_POWER_CLOSURE_MAX: float = 1.05
# DC nominal power : AC rated power over-provisioning band (typical).
DC_AC_RATIO_MIN: float = 1.00
DC_AC_RATIO_MAX: float = 1.50

BAND_BASIS = (
    "typical/provisional band — PCS overload 1.10, POI closure 0.95-1.05, "
    "DC:AC 1.00-1.50; tune in ac_power_reconciliation once owner-confirmed"
)


@dataclass(frozen=True)
class PowerReconciliation:
    """Result of the POI <-> AC Block power reconciliation (informational)."""

    poi_power_mw: float
    eff_mv_to_poi: float                 # eff_ac_cables_sw_rmu * eff_hvt_others
    eff_chain: float                     # full DC->POI one-way efficiency
    ac_aggregate_needed_mw: float        # Line 1: poi_power / eff_mv_to_poi
    ac_rated_total_mw: float             # governed Σ AC-block rated power
    ac_poi_deliverable_mw: float         # ac_rated_total_mw * eff_mv_to_poi
    poi_coverage_frac: Optional[float]   # ac_poi_deliverable / poi_power
    dc_power_required_mw: Optional[float]  # FROZEN Stage 1: poi_power / eff_chain
    dc_ac_ratio: Optional[float]         # dc_power_required / ac_rated_total
    discharge_duration_h: Optional[float]
    pcs_kw: Optional[float]
    dc_block_power_kw: Optional[float]
    pcs_utilization_frac: Optional[float]  # dc_block_power / pcs_kw
    poi_within_band: bool
    dc_ac_within_band: bool
    pcs_within_overload: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reconciled(self) -> bool:
        return self.poi_within_band and self.dc_ac_within_band and self.pcs_within_overload


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    try:
        if a is None or b is None or float(b) == 0.0:
            return None
        return float(a) / float(b)
    except (TypeError, ValueError):
        return None


def reconcile_governed_power(
    *,
    poi_power_mw: float,
    eff_ac_cables_sw_rmu: float,
    eff_hvt_others: float,
    eff_chain: float,
    ac_rated_total_mw: float,
    poi_energy_mwh: Optional[float] = None,
    pcs_kw: Optional[float] = None,
    dc_block_power_kw: Optional[float] = None,
) -> PowerReconciliation:
    """Reconcile POI power against a governed AC aggregate (read-only).

    All efficiencies are fractions in (0, 1]. ``ac_rated_total_mw`` is the sum of
    the governed AC Blocks' rated grid power. ``dc_block_power_kw`` (the DC Block
    nameplate power at the project duration) and ``pcs_kw`` are optional; when
    given, the PCS overload headroom is evaluated.
    """
    poi_power_mw = float(poi_power_mw or 0.0)
    eff_mv_to_poi = float(eff_ac_cables_sw_rmu or 0.0) * float(eff_hvt_others or 0.0)
    eff_chain = float(eff_chain or 0.0)
    ac_rated_total_mw = float(ac_rated_total_mw or 0.0)

    ac_aggregate_needed_mw = _safe_div(poi_power_mw, eff_mv_to_poi) or 0.0
    ac_poi_deliverable_mw = ac_rated_total_mw * eff_mv_to_poi
    poi_coverage = _safe_div(ac_poi_deliverable_mw, poi_power_mw)

    dc_power_required_mw = _safe_div(poi_power_mw, eff_chain)
    dc_ac_ratio = _safe_div(dc_power_required_mw, ac_rated_total_mw)
    discharge_duration_h = _safe_div(poi_energy_mwh, poi_power_mw)
    pcs_utilization = _safe_div(dc_block_power_kw, pcs_kw)

    notes: list[str] = []
    poi_within = poi_coverage is not None and POI_POWER_CLOSURE_MIN <= poi_coverage <= POI_POWER_CLOSURE_MAX
    if poi_coverage is not None and poi_coverage < POI_POWER_CLOSURE_MIN:
        notes.append(
            f"AC POI-deliverable power {ac_poi_deliverable_mw:.2f} MW is below the POI "
            f"requirement ({poi_coverage*100:.1f}% < {POI_POWER_CLOSURE_MIN*100:.0f}%) — add AC Blocks."
        )
    elif poi_coverage is not None and poi_coverage > POI_POWER_CLOSURE_MAX:
        notes.append(
            f"AC POI-deliverable power exceeds the requirement by {(poi_coverage-1)*100:.1f}% "
            f"(> {(POI_POWER_CLOSURE_MAX-1)*100:.0f}% oversize) — consider fewer/smaller AC Blocks."
        )

    dc_ac_within = dc_ac_ratio is not None and DC_AC_RATIO_MIN <= dc_ac_ratio <= DC_AC_RATIO_MAX
    if dc_ac_ratio is not None and not dc_ac_within:
        notes.append(
            f"DC:AC power ratio {dc_ac_ratio:.2f} is outside the typical "
            f"{DC_AC_RATIO_MIN:.2f}–{DC_AC_RATIO_MAX:.2f} over-provisioning band."
        )

    # PCS overload headroom: only a violation when the DC block power exceeds the
    # PCS continuous nameplate times the overload factor.
    pcs_within = True
    if pcs_utilization is not None:
        pcs_within = pcs_utilization <= PCS_OVERLOAD_FACTOR + 1e-9
        if not pcs_within:
            notes.append(
                f"DC Block power {dc_block_power_kw:.0f} kW exceeds PCS {pcs_kw:.0f} kW × "
                f"overload {PCS_OVERLOAD_FACTOR:.2f} — PCS rating insufficient at this duration."
            )

    return PowerReconciliation(
        poi_power_mw=poi_power_mw,
        eff_mv_to_poi=eff_mv_to_poi,
        eff_chain=eff_chain,
        ac_aggregate_needed_mw=ac_aggregate_needed_mw,
        ac_rated_total_mw=ac_rated_total_mw,
        ac_poi_deliverable_mw=ac_poi_deliverable_mw,
        poi_coverage_frac=poi_coverage,
        dc_power_required_mw=dc_power_required_mw,
        dc_ac_ratio=dc_ac_ratio,
        discharge_duration_h=discharge_duration_h,
        pcs_kw=pcs_kw,
        dc_block_power_kw=dc_block_power_kw,
        pcs_utilization_frac=pcs_utilization,
        poi_within_band=poi_within,
        dc_ac_within_band=dc_ac_within,
        pcs_within_overload=pcs_within,
        notes=tuple(notes),
    )


__all__ = [
    "BAND_BASIS",
    "DC_AC_RATIO_MAX",
    "DC_AC_RATIO_MIN",
    "PCS_OVERLOAD_FACTOR",
    "POI_POWER_CLOSURE_MAX",
    "POI_POWER_CLOSURE_MIN",
    "PowerReconciliation",
    "reconcile_governed_power",
]
