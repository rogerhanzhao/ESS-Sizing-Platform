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

"""Governed AC Block configuration contract (Phase A).

Design basis: docs/CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md §4-§7 and
docs/GOVERNED_AC_BLOCK_10MW_8PCS_8DC_2026-07-24.md.

Why this module exists
----------------------
The current AC workflow treats "DC Blocks per AC Block" and "PCS/AC Block
model" as an unconstrained cross-product (see SIZING_LOGIC_CANON_V1 §AC-2,
ratios 1:1 / 1:2 / 1:4). That is insufficient for a fixed product: a generic
``1:8`` ratio could be paired with an incompatible model, and ``ceil`` +
``evenly_distribute`` produce tails like ``[5, 4]`` that do not represent the
owner-confirmed ``8 DC / 8 PCS / 10 MW`` product.

A *governed configuration* binds the whole product/topology/layout choice as
one atomic identity — ``ACBLK-10MW-8PCS-8DC-40FT-BILATERAL`` — and is the
single contract that AC Sizing -> SLD -> Layout -> Site Array -> Report all
consume. Downstream layers must route by ``configuration_code`` /
``layout_variant``; they must never rebuild the unit from an average
``dc_blocks_total / ac_blocks_total`` ratio.

Frozen-boundary guarantee
--------------------------
This module does NOT touch DC/AC sizing formulas, ``K_MAX_FIXED``, SOH/RTE, or
scenario semantics (SIZING_LOGIC_CANON_V1 stays frozen). It only assembles an
authoritative AC->SLD output payload from already-selected, owner-confirmed
product facts, and keeps every unconfirmed engineering value as an explicit,
provisional field that is ``None`` until the owner supplies it. In particular,
``10 MW / 0.9`` is NOT silently promoted to an approved ``11.11 MVA`` nameplate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from calb_sizing_tool.schemas.ac_electrical_topology import build_dc_block_connection_plan


# One DC-to-PCS link uses a single physical output circuit even though the DC
# Block product can expose up to two protected outputs. Connection policy and
# product output capability are deliberately independent (handoff §3).
DEDICATED_LINK_OUTPUT_CIRCUITS = 1
DC_BLOCK_PRODUCT_OUTPUT_CIRCUITS = 2


@dataclass(frozen=True)
class GovernedACBlockConfiguration:
    """A fixed, owner-confirmed AC Block product/topology/layout identity.

    Confirmed fields are owner-approved product facts. Provisional fields are
    engineering values that are NOT yet owner-confirmed; they default to
    ``None`` and are listed in :attr:`provisional_fields`. They are never
    inferred or hardcoded — a caller must inject them through Engineering
    Settings (``engineering_overrides``) for any drawing that needs them.
    """

    # --- confirmed product identity ---
    configuration_code: str
    ac_power_mw: float
    pcs_count: int
    pcs_rating_kw: int
    dc_block_count: int
    dc_block_model: str
    ac_container_type: str
    layout_variant: str
    dc_field_split: tuple[int, ...]
    dc_connection_policy: str
    dc_block_output_circuits: int  # product property, not the connection policy
    status: str

    # --- confirmed electrical topology (LV secondary arrangement) ---
    transformer_topology: str
    lv_winding_count: int
    pcs_per_lv_winding: tuple[int, ...]

    # --- confirmed duration / DC-power profile ---
    # A governed family is defined for ONE system duration: the DC Block nameplate
    # power (kW) is a function of duration (dc_block_nameplate_profile_data), and
    # the PCS rating is matched to it. The current families are the 4 h / 1250 kW
    # profile; 2/3/8 h families are not yet defined (Rule S1 / spec Option C).
    system_duration_h: float = 4.0
    dc_block_nameplate_power_kw: float = 1250.0

    # --- provisional engineering values (owner-confirmation pending) ---
    transformer_mva: Optional[float] = None
    transformer_vector_group: Optional[str] = None
    transformer_uk_percent: Optional[float] = None
    lv_voltage_v: Optional[float] = None
    transformer_cooling: Optional[str] = None
    dc_field_to_station_aisle_m: Optional[float] = None
    ac_station_length_m: Optional[float] = None
    ac_station_width_m: Optional[float] = None
    provisional_fields: frozenset[str] = field(default_factory=frozenset)

    def pcs_power_matches_dc(self, overload_factor: float = 1.10) -> bool:
        """Rule A1: PCS continuous rating × overload must cover the DC block power.

        For the dedicated 1 PCS ↔ 1 DC policy, one PCS must carry one DC Block's
        nameplate power at the family duration. The PCS nameplate is not a hard
        ceiling — short-term overload headroom is allowed (``overload_factor``).
        """
        return float(self.pcs_rating_kw) * float(overload_factor) + 1e-9 >= float(
            self.dc_block_nameplate_power_kw
        )

    # ------------------------------------------------------------------
    # Derived, purely-geometric/topological facts (no sizing formulas)
    # ------------------------------------------------------------------
    @property
    def block_size_mw(self) -> float:
        """AC Block power from the equal-PCS basis (8 x 1.25 MW = 10 MW)."""
        return round(self.pcs_count * self.pcs_rating_kw / 1000.0, 6)

    def phase_a_eligible(self, dc_blocks_total: int) -> bool:
        """Phase A gate: every generated AC Block must have exactly ``dc_block_count``.

        The safest initial gate (handoff §5 Phase A) is
        ``dc_blocks_total % dc_block_count == 0``. Mixed 8/4/2/1 tails remain a
        deferred Phase B contract upgrade and are intentionally rejected here.
        """
        total = int(dc_blocks_total or 0)
        if total <= 0:
            return False
        return total % self.dc_block_count == 0

    def ac_block_count_for(self, dc_blocks_total: int) -> int:
        """Number of governed AC Blocks for a Phase-A-eligible DC total."""
        if not self.phase_a_eligible(dc_blocks_total):
            raise ValueError(
                f"{int(dc_blocks_total)} DC Blocks is not Phase A eligible for "
                f"{self.configuration_code}; require a multiple of {self.dc_block_count}."
            )
        return int(dc_blocks_total) // self.dc_block_count

    def build_dc_block_connections(self) -> list[dict]:
        """Physical DC Block -> PCS feeder mapping for one governed AC Block.

        ``dedicated_dc_to_pcs`` gives DC-i -> PCS-i using a single output
        circuit per link. The DC Block product still exposes
        ``dc_block_output_circuits`` protected outputs; only one is used by this
        connection policy.
        """
        return build_dc_block_connection_plan(
            self.dc_block_count,
            self.pcs_count,
            output_circuit_count=DEDICATED_LINK_OUTPUT_CIRCUITS,
        )

    def build_dc_allocation_plan(self) -> list[dict]:
        """``dc_allocation_plan`` (AC's authoritative downstream output) for one unit."""
        connections = self.build_dc_block_connections()
        feeder_allocations = [
            sum(1 for connection in connections if feeder_index in connection["feeder_indices"])
            for feeder_index in range(1, self.pcs_count + 1)
        ]
        return [
            {
                "ac_block_index": 1,
                "dc_blocks_total": self.dc_block_count,
                "feeder_allocations": feeder_allocations,
                "dc_block_connections": connections,
            }
        ]

    def resolve_provisional(
        self, engineering_overrides: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """Merge caller-supplied Engineering Settings over provisional defaults.

        Only the provisional fields may be supplied here. This is the ONE place
        an unconfirmed value (e.g. transformer MVA) may enter the contract, and
        it is always caller-driven, never inferred by this module.
        """
        overrides = dict(engineering_overrides or {})
        unknown = set(overrides) - set(self.provisional_fields)
        if unknown:
            raise ValueError(
                "engineering_overrides may only set provisional fields "
                f"{sorted(self.provisional_fields)}; got unexpected {sorted(unknown)}."
            )
        resolved: dict[str, Any] = {}
        for name in self.provisional_fields:
            resolved[name] = overrides.get(name, getattr(self, name))
        return resolved

    def to_ac_sld_output(
        self, *, engineering_overrides: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Authoritative AC output payload for one governed AC Block.

        The result satisfies the AC->SLD V1 contract
        (``adapters.ac_to_sld_adapter.normalize_ac_output_for_sld``). It carries
        ``configuration_code`` and ``layout_variant`` directly so SLD / Layout /
        Site Array / Report route by the governed identity instead of an average
        DC-per-AC value. Provisional values (e.g. ``transformer_mva``) are only
        present when the caller supplies them; otherwise they are omitted so the
        strict SLD contract fails loudly rather than drawing an invented rating.
        """
        resolved = self.resolve_provisional(engineering_overrides)
        payload: dict[str, Any] = {
            # governed identity carried through the whole pipeline
            "configuration_code": self.configuration_code,
            "layout_variant": self.layout_variant,
            "dc_field_split": list(self.dc_field_split),
            "dc_connection_policy": self.dc_connection_policy,
            "governed_configuration": True,
            "governed_status": self.status,
            # AC->SLD authoritative fields
            "num_blocks": 1,
            "pcs_per_block": self.pcs_count,
            "pcs_kw": float(self.pcs_rating_kw),
            "block_size_mw": self.block_size_mw,
            "transformer_topology": self.transformer_topology,
            "lv_winding_count": self.lv_winding_count,
            "dc_block_output_circuits": DEDICATED_LINK_OUTPUT_CIRCUITS,
            "dc_allocation_plan": self.build_dc_allocation_plan(),
            # DC Block product capability, kept independent of the link policy
            "dc_block_product_output_circuits": self.dc_block_output_circuits,
        }
        transformer_mva = resolved.get("transformer_mva")
        if transformer_mva is not None:
            payload["transformer_mva"] = float(transformer_mva)
        lv_voltage_v = resolved.get("lv_voltage_v")
        if lv_voltage_v is not None:
            payload["lv_voltage_v"] = float(lv_voltage_v)
        # Record which provisional values are still unresolved so downstream UI
        # can badge them and no layer mistakes a blank for an approved value.
        payload["provisional_unresolved"] = sorted(
            name for name, value in resolved.items() if value is None
        )
        return payload


# ---------------------------------------------------------------------------
# The Phase A governed configuration (owner-confirmed geometry & topology)
# ---------------------------------------------------------------------------

ACBLK_10MW_8PCS_8DC_40FT_BILATERAL = GovernedACBlockConfiguration(
    configuration_code="ACBLK-10MW-8PCS-8DC-40FT-BILATERAL",
    ac_power_mw=10.0,
    pcs_count=8,
    pcs_rating_kw=1250,
    dc_block_count=8,
    dc_block_model="CALB_5MWh_20FT_12R",
    ac_container_type="40ft",
    layout_variant="central_40ft_bilateral_4plus4",
    dc_field_split=(4, 4),
    dc_connection_policy="dedicated_dc_to_pcs",
    dc_block_output_circuits=DC_BLOCK_PRODUCT_OUTPUT_CIRCUITS,
    status="concept_confirmed_partial",
    transformer_topology="three_winding",
    lv_winding_count=2,
    pcs_per_lv_winding=(4, 4),
    # Provisional — pending owner confirmation (handoff §10). Never inferred.
    transformer_mva=None,
    transformer_vector_group=None,
    transformer_uk_percent=None,
    lv_voltage_v=None,
    transformer_cooling=None,
    dc_field_to_station_aisle_m=None,
    ac_station_length_m=None,
    ac_station_width_m=None,
    # NOTE: transformer_uk_percent is deliberately NOT a provisional blocker.
    # Impedance is not a sizing input and is a grid-interconnection filing value
    # the owner usually lacks at concept stage; the SLD supplies a standard
    # typical by voltage class (see sld.standard_transformer_impedance), so it
    # never gates sizing or SLD generation.
    provisional_fields=frozenset(
        {
            "transformer_mva",
            "transformer_vector_group",
            "lv_voltage_v",
            "transformer_cooling",
            "dc_field_to_station_aisle_m",
            "ac_station_length_m",
            "ac_station_width_m",
        }
    ),
)


# ---------------------------------------------------------------------------
# Phase B — governed tail configurations (mixed 8/4/2/1 DC decomposition)
# ---------------------------------------------------------------------------
# Tails reuse the same 1250 kW PCS unit and the dedicated DC-to-PCS policy, so a
# site total that is not a multiple of 8 is placed into a whole number of
# smaller governed AC Blocks (never a generic ceil/average split). Each tail is
# a two-winding (single LV busbar) linear unit; only the 8-DC unit is the
# bilateral three-winding product.

_TAIL_PROVISIONAL_FIELDS = frozenset(
    {
        "transformer_mva",
        "transformer_vector_group",
        "lv_voltage_v",
        "transformer_cooling",
        "dc_field_to_station_aisle_m",
        "ac_station_length_m",
        "ac_station_width_m",
    }
)


def _make_linear_tail(
    *, configuration_code: str, dc_count: int, ac_container_type: str
) -> GovernedACBlockConfiguration:
    """Build a governed linear tail configuration of ``dc_count`` DC Blocks."""
    return GovernedACBlockConfiguration(
        configuration_code=configuration_code,
        ac_power_mw=round(dc_count * 1250 / 1000.0, 3),
        pcs_count=dc_count,
        pcs_rating_kw=1250,
        dc_block_count=dc_count,
        dc_block_model="CALB_5MWh_20FT_12R",
        ac_container_type=ac_container_type,
        layout_variant="linear_end_station",
        dc_field_split=(dc_count,),
        dc_connection_policy="dedicated_dc_to_pcs",
        dc_block_output_circuits=DC_BLOCK_PRODUCT_OUTPUT_CIRCUITS,
        status="concept_confirmed_partial",
        transformer_topology="two_winding",
        lv_winding_count=1,
        pcs_per_lv_winding=(dc_count,),
        provisional_fields=_TAIL_PROVISIONAL_FIELDS,
    )


ACBLK_5MW_4PCS_4DC_40FT_LINEAR = _make_linear_tail(
    configuration_code="ACBLK-5MW-4PCS-4DC-40FT-LINEAR", dc_count=4, ac_container_type="40ft"
)
ACBLK_2P5MW_2PCS_2DC_20FT_LINEAR = _make_linear_tail(
    configuration_code="ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR", dc_count=2, ac_container_type="20ft"
)
ACBLK_1P25MW_1PCS_1DC_20FT_LINEAR = _make_linear_tail(
    configuration_code="ACBLK-1P25MW-1PCS-1DC-20FT-LINEAR", dc_count=1, ac_container_type="20ft"
)


GOVERNED_AC_BLOCK_CONFIGURATIONS = {
    cfg.configuration_code: cfg
    for cfg in (
        ACBLK_10MW_8PCS_8DC_40FT_BILATERAL,
        ACBLK_5MW_4PCS_4DC_40FT_LINEAR,
        ACBLK_2P5MW_2PCS_2DC_20FT_LINEAR,
        ACBLK_1P25MW_1PCS_1DC_20FT_LINEAR,
    )
}

# Governed configurations usable by the Phase B decomposition, largest DC count
# first (greedy 8 -> 4 -> 2 -> 1). Since a 1-DC unit exists, ANY positive DC
# total is exactly composable.
GOVERNED_DECOMPOSITION_CONFIGS: tuple[GovernedACBlockConfiguration, ...] = (
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL,
    ACBLK_5MW_4PCS_4DC_40FT_LINEAR,
    ACBLK_2P5MW_2PCS_2DC_20FT_LINEAR,
    ACBLK_1P25MW_1PCS_1DC_20FT_LINEAR,
)


def get_governed_configuration(configuration_code: str) -> GovernedACBlockConfiguration:
    """Look up a governed configuration by its ``configuration_code``."""
    try:
        return GOVERNED_AC_BLOCK_CONFIGURATIONS[str(configuration_code)]
    except KeyError as exc:
        raise KeyError(f"unknown governed configuration_code: {configuration_code!r}") from exc


def governed_configuration_for_dc_count(dc_count: int) -> GovernedACBlockConfiguration:
    """Return the governed configuration whose AC Block holds exactly ``dc_count`` DC Blocks."""
    for cfg in GOVERNED_DECOMPOSITION_CONFIGS:
        if cfg.dc_block_count == int(dc_count):
            return cfg
    raise KeyError(f"no governed configuration with dc_block_count={dc_count}")


def decompose_governed_site(dc_blocks_total: int) -> list[tuple[GovernedACBlockConfiguration, int]]:
    """Decompose a DC total into governed AC Block groups (greedy 8/4/2/1).

    Returns an ordered list of ``(configuration, ac_block_count)`` covering the
    total exactly, largest unit first. Every governed AC Block is internally
    uniform, so each group remains individually SLD-renderable under the SLD V1
    uniform-block contract; the mix across groups is the heterogeneity.
    """
    total = int(dc_blocks_total or 0)
    if total <= 0:
        raise ValueError(f"dc_blocks_total must be > 0, got {dc_blocks_total}")
    groups: list[tuple[GovernedACBlockConfiguration, int]] = []
    remaining = total
    for cfg in GOVERNED_DECOMPOSITION_CONFIGS:
        count = remaining // cfg.dc_block_count
        if count > 0:
            groups.append((cfg, count))
            remaining -= count * cfg.dc_block_count
    if remaining != 0:  # pragma: no cover - impossible while a 1-DC unit exists
        raise ValueError(f"could not fully decompose {total} DC Blocks; remainder {remaining}")
    return groups


# Durations for which a governed AC Block family is currently DEFINED. The
# families are the 4 h / 1250 kW profile; 2/3/8 h families need their own real
# product matrix (PCS rating matched to the DC nameplate power at that duration)
# before they may be built (spec Option C — do not silently reuse the 4 h family).
GOVERNED_SUPPORTED_DURATIONS_H: tuple[float, ...] = tuple(
    sorted({cfg.system_duration_h for cfg in GOVERNED_DECOMPOSITION_CONFIGS})
)
GOVERNED_DURATION_TOLERANCE_H: float = 0.25


def governed_duration_gate(
    project_duration_h: float | None,
    *,
    tolerance: float = GOVERNED_DURATION_TOLERANCE_H,
) -> tuple[bool, str]:
    """Hard gate: is a governed family defined for this project system duration?

    ``project_duration_h`` is the project E/P ratio (poi_energy / poi_power). A
    governed family is only valid for its declared ``system_duration_h`` because
    the PCS rating is matched to the DC Block nameplate power at that duration.
    Returns ``(ok, message)``; when not ok the caller must refuse the governed
    path (fall back to legacy / adjust inputs), never build a mismatched family.
    """
    try:
        duration = float(project_duration_h) if project_duration_h is not None else None
    except (TypeError, ValueError):
        duration = None
    if duration is None or duration <= 0:
        return False, "System duration is unknown (need POI energy / POI power) — governed sizing gated."
    for supported in GOVERNED_SUPPORTED_DURATIONS_H:
        if abs(duration - supported) <= tolerance:
            return True, f"{duration:.2f} h system matches the defined {supported:g} h governed family."
    defined = ", ".join(f"{d:g} h" for d in GOVERNED_SUPPORTED_DURATIONS_H)
    return (
        False,
        f"Governed AC Block family not yet defined for a {duration:.2f} h system "
        f"(only {defined} defined). The DC Block nameplate power differs at this "
        f"duration, so the PCS/transformer must change — use the legacy path or "
        f"confirm a real {duration:.1f} h product family first.",
    )


__all__ = [
    "ACBLK_10MW_8PCS_8DC_40FT_BILATERAL",
    "GOVERNED_DURATION_TOLERANCE_H",
    "GOVERNED_SUPPORTED_DURATIONS_H",
    "governed_duration_gate",
    "ACBLK_5MW_4PCS_4DC_40FT_LINEAR",
    "ACBLK_2P5MW_2PCS_2DC_20FT_LINEAR",
    "ACBLK_1P25MW_1PCS_1DC_20FT_LINEAR",
    "DC_BLOCK_PRODUCT_OUTPUT_CIRCUITS",
    "DEDICATED_LINK_OUTPUT_CIRCUITS",
    "GOVERNED_AC_BLOCK_CONFIGURATIONS",
    "GOVERNED_DECOMPOSITION_CONFIGS",
    "GovernedACBlockConfiguration",
    "decompose_governed_site",
    "get_governed_configuration",
    "governed_configuration_for_dc_count",
]
