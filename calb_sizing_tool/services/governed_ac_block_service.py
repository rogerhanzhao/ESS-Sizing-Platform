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

"""Bind a governed AC Block configuration to persisted Engineering Settings.

This is the glue between the governed configuration contract
(``schemas.governed_ac_block_config``) and the case-level SLD engineering
settings the owner enters in the Engineering Settings page. It maps the
owner-confirmed provisional values (transformer nameplate MVA, vector group,
Uk%, cooling) out of ``project_settings`` into the governed configuration's
``engineering_overrides``, then emits the authoritative AC->SLD output.

It never fabricates a value: provisional fields that the owner has not entered
stay unresolved and are reported back for UI badging. In particular the
transformer MVA is taken only from ``project_settings["transformer_rating_mva"]``
(saved from Engineering Settings), never derived from AC power / power factor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from calb_sizing_tool.infra.db.models import ProductACBlock
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.schemas.governed_ac_block_config import (
    GovernedACBlockConfiguration,
    decompose_governed_site,
    get_governed_configuration,
)

# Nominal ISO 40 ft footprint (length x width) used when a product record only
# names the container class. Length = container W, width = container D.
_CONTAINER_FOOTPRINT_M = {
    "40ft": (12.192, 2.438),
    "20ft": (6.058, 2.438),
}


def map_engineering_settings_to_overrides(
    project_settings: dict[str, Any] | None,
    config: GovernedACBlockConfiguration,
) -> dict[str, Any]:
    """Extract governed provisional overrides from persisted SLD settings.

    Only keys the owner actually set (and that are provisional for this
    configuration) are returned; everything else is left for the governed
    configuration to report as unresolved.
    """
    settings = project_settings or {}
    overrides: dict[str, Any] = {}

    mva = settings.get("transformer_rating_mva")
    if mva is not None:
        try:
            if float(mva) > 0:
                overrides["transformer_mva"] = float(mva)
        except (TypeError, ValueError):
            pass

    transformer = settings.get("transformer") if isinstance(settings.get("transformer"), dict) else {}
    vector_group = str(transformer.get("vector_group") or "").strip()
    if vector_group:
        overrides["transformer_vector_group"] = vector_group
    uk_percent = transformer.get("uk_percent")
    if uk_percent is not None:
        try:
            if float(uk_percent) > 0:
                overrides["transformer_uk_percent"] = float(uk_percent)
        except (TypeError, ValueError):
            pass

    equipment = settings.get("equipment_ratings") if isinstance(settings.get("equipment_ratings"), dict) else {}
    cooling = str(equipment.get("transformer_cooling") or "").strip()
    if cooling:
        overrides["transformer_cooling"] = cooling

    lv_voltage_v = settings.get("lv_voltage_v")
    if lv_voltage_v is not None:
        try:
            if float(lv_voltage_v) > 0:
                overrides["lv_voltage_v"] = float(lv_voltage_v)
        except (TypeError, ValueError):
            pass

    # Never pass a field the configuration does not treat as provisional.
    return {key: value for key, value in overrides.items() if key in config.provisional_fields}


def build_governed_ac_output_from_settings(
    configuration_code: str,
    project_settings: dict[str, Any] | None,
    *,
    dc_blocks_total: Optional[int] = None,
    extra_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the authoritative AC->SLD output for a governed configuration.

    ``project_settings`` is the persisted case-level SLD engineering settings
    dict. ``extra_overrides`` allows an explicit caller-supplied provisional
    value (e.g. a layout dimension not stored in SLD settings) and is filtered
    to provisional fields. When ``dc_blocks_total`` is given it is checked
    against the Phase A gate.

    The returned payload always carries ``provisional_unresolved`` so callers
    (UI/report) can badge the still-missing owner-confirmation values without
    ever mistaking a blank for an approved value.
    """
    config = get_governed_configuration(configuration_code)
    if dc_blocks_total is not None and not config.phase_a_eligible(dc_blocks_total):
        raise ValueError(
            f"{int(dc_blocks_total)} DC Blocks is not Phase A eligible for "
            f"{config.configuration_code}; require a multiple of {config.dc_block_count}."
        )

    overrides = map_engineering_settings_to_overrides(project_settings, config)
    if extra_overrides:
        overrides.update(
            {key: value for key, value in extra_overrides.items() if key in config.provisional_fields}
        )
    return config.to_ac_sld_output(engineering_overrides=overrides)


def build_governed_site_ac_output(
    configuration_code: str,
    project_settings: dict[str, Any] | None,
    *,
    dc_blocks_total: int,
    source_fields: Optional[dict[str, Any]] = None,
    extra_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Site-level authoritative AC output for a governed configuration.

    A Phase-A site is a whole number of identical governed AC Blocks
    (``num_blocks = dc_blocks_total / dc_block_count``). This expands the
    single-unit governed payload to ``num_blocks`` uniform blocks so the AC->SLD
    contract, report and site-array all consume the governed identity directly.

    ``source_fields`` (project/case/run provenance, MV/LV voltages) is merged in
    last. As with the single-unit builder, an unresolved transformer MVA is
    simply omitted — never fabricated — so downstream SLD stays gated until the
    owner confirms it in Engineering Settings.
    """
    config = get_governed_configuration(configuration_code)
    num_blocks = config.ac_block_count_for(dc_blocks_total)

    unit = build_governed_ac_output_from_settings(
        configuration_code, project_settings, extra_overrides=extra_overrides
    )
    unit_plan = unit["dc_allocation_plan"][0]
    feeder_allocations = list(unit_plan["feeder_allocations"])
    connections = list(unit_plan["dc_block_connections"])

    site = dict(unit)
    site.update(
        {
            "num_blocks": num_blocks,
            "pcs_count_by_block": [config.pcs_count for _ in range(num_blocks)],
            "dc_allocation_plan": [
                {
                    "ac_block_index": index + 1,
                    "dc_blocks_total": config.dc_block_count,
                    "feeder_allocations": list(feeder_allocations),
                    "dc_block_connections": [dict(c) for c in connections],
                }
                for index in range(num_blocks)
            ],
            "dc_blocks_total_by_block": [config.dc_block_count for _ in range(num_blocks)],
            "dc_blocks_per_feeder_by_block": [list(feeder_allocations) for _ in range(num_blocks)],
            "dc_block_connections_by_block": [[dict(c) for c in connections] for _ in range(num_blocks)],
            "transformer_count": num_blocks,
            "pcs_count_total": num_blocks * config.pcs_count,
            "dc_blocks_total": int(dc_blocks_total),
            "total_ac_mw": round(num_blocks * config.block_size_mw, 6),
        }
    )
    if source_fields:
        site.update(source_fields)
    return site


def _product_row_to_overrides(
    row: ProductACBlock, config: GovernedACBlockConfiguration
) -> dict[str, Any]:
    """Extract governed provisional overrides from a product catalogue record.

    Transformer nameplate MVA and LV voltage come from the datasheet-derived
    product record; vector group / cooling / container footprint are recorded so
    the unresolved list shrinks. Uk% is never published on these datasheets, so
    it is not sourced here and stays an owner-confirmation item.
    """
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    overrides: dict[str, Any] = {}
    if row.transformer_kva and float(row.transformer_kva) > 0:
        overrides["transformer_mva"] = round(float(row.transformer_kva) / 1000.0, 6)
    if row.lv_voltage_v and float(row.lv_voltage_v) > 0:
        overrides["lv_voltage_v"] = float(row.lv_voltage_v)
    vector_group = str(metadata.get("transformer_vector_group") or "").strip()
    if vector_group:
        overrides["transformer_vector_group"] = vector_group
    cooling = str(metadata.get("transformer_cooling") or "").strip()
    if cooling:
        overrides["transformer_cooling"] = cooling
    footprint = _CONTAINER_FOOTPRINT_M.get(str(metadata.get("container_type") or "").strip())
    if footprint:
        overrides["ac_station_length_m"] = footprint[0]
        overrides["ac_station_width_m"] = footprint[1]
    return {key: value for key, value in overrides.items() if key in config.provisional_fields}


def product_overrides(
    product_block_code: str,
    config: GovernedACBlockConfiguration,
    *,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Provisional overrides sourced from a catalogue product, by block_code."""
    code = str(product_block_code or "").strip()
    if not code:
        return {}
    with session_scope(db_url) as session:
        row = session.query(ProductACBlock).filter(ProductACBlock.block_code == code).one_or_none()
        if row is None:
            raise ValueError(f"unknown AC Block product: {product_block_code!r}")
        return _product_row_to_overrides(row, config)


def eligible_products_for(
    configuration_code: str,
    *,
    db_url: str | None = None,
) -> list[dict[str, Any]]:
    """Catalogue products whose datasheet matches this governed configuration.

    A product qualifies when its AC power, DC-input count (or PCS inverter block
    count) and transformer topology match the governed identity — e.g. the 10 MW
    / 8-DC / three-winding skids (Sineng EH-10000, NR PCS-9567MV-10000, Kehua
    BCS10000K-C-HUD/T8).
    """
    config = get_governed_configuration(configuration_code)
    results: list[dict[str, Any]] = []
    with session_scope(db_url) as session:
        for row in session.query(ProductACBlock).order_by(ProductACBlock.block_code.asc()).all():
            metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            try:
                power_ok = abs(float(metadata.get("ac_power_mw") or 0.0) - config.ac_power_mw) < 1e-6
            except (TypeError, ValueError):
                power_ok = False
            dc_inputs = metadata.get("dc_inputs")
            inverter_blocks = metadata.get("pcs_inverter_blocks")
            count_ok = (dc_inputs == config.dc_block_count) or (inverter_blocks == config.pcs_count)
            topology_ok = metadata.get("transformer_topology") == config.transformer_topology
            if power_ok and count_ok and topology_ok:
                results.append(
                    {
                        "block_code": row.block_code,
                        "block_name": row.block_name,
                        "vendor": metadata.get("vendor"),
                        "transformer_kva": row.transformer_kva,
                        "transformer_vector_group": metadata.get("transformer_vector_group"),
                        "transformer_cooling": metadata.get("transformer_cooling"),
                        "lv_voltage_v": row.lv_voltage_v,
                    }
                )
    return results


def build_governed_ac_output_from_product(
    configuration_code: str,
    product_block_code: str,
    *,
    project_settings: dict[str, Any] | None = None,
    dc_blocks_total: int,
    source_fields: Optional[dict[str, Any]] = None,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Site-level governed AC output using a real product for provisional values.

    Precedence: product datasheet values form the base; explicit Engineering
    Settings override them (so an owner-entered Uk%/MVA always wins). The result
    still reports any remaining unresolved provisional fields (e.g. Uk%, which no
    datasheet publishes).
    """
    config = get_governed_configuration(configuration_code)
    merged = product_overrides(product_block_code, config, db_url=db_url)
    merged.update(map_engineering_settings_to_overrides(project_settings, config))
    output = build_governed_site_ac_output(
        configuration_code,
        None,
        dc_blocks_total=dc_blocks_total,
        source_fields=source_fields,
        extra_overrides=merged,
    )
    # Carry the confirmed transformer vector group / cooling through to the SLD.
    # The vector group in particular drives the winding-connection symbols
    # (e.g. Dy11y11 has an isolated LV neutral -> ungrounded-wye mark, no earth),
    # so a real product must not fall back to a generic grounded-wye preset.
    if merged.get("transformer_vector_group"):
        output["transformer_vector_group"] = merged["transformer_vector_group"]
    if merged.get("transformer_cooling"):
        output["transformer_cooling"] = merged["transformer_cooling"]
    output["governed_product_block_code"] = str(product_block_code)
    return output


@dataclass(frozen=True)
class GovernedSiteGroup:
    """One homogeneous group of identical governed AC Blocks in a mixed site."""

    configuration_code: str
    layout_variant: str
    ac_block_count: int
    dc_blocks_per_ac_block: int
    dc_blocks_total: int
    pcs_per_ac_block: int
    ac_power_mw_total: float


@dataclass(frozen=True)
class GovernedSitePlan:
    """Phase B site plan: a mix of homogeneous governed AC Block groups.

    Each group is internally uniform (one governed configuration), so it remains
    individually SLD-renderable under the SLD V1 uniform-block contract; the
    heterogeneity lives in the list of groups, not inside any single group.
    """

    dc_blocks_total: int
    ac_blocks_total: int
    ac_power_mw_total: float
    groups: tuple[GovernedSiteGroup, ...]


def build_governed_site_plan(dc_blocks_total: int) -> GovernedSitePlan:
    """Decompose a DC total into governed AC Block groups (Phase B).

    Any positive total is exactly composable (greedy 8/4/2/1); a multiple of 8
    yields a single bilateral group (equivalent to Phase A).
    """
    groups: list[GovernedSiteGroup] = []
    for config, count in decompose_governed_site(dc_blocks_total):
        groups.append(
            GovernedSiteGroup(
                configuration_code=config.configuration_code,
                layout_variant=config.layout_variant,
                ac_block_count=int(count),
                dc_blocks_per_ac_block=config.dc_block_count,
                dc_blocks_total=int(count) * config.dc_block_count,
                pcs_per_ac_block=config.pcs_count,
                ac_power_mw_total=round(int(count) * config.block_size_mw, 3),
            )
        )
    return GovernedSitePlan(
        dc_blocks_total=int(dc_blocks_total),
        ac_blocks_total=sum(g.ac_block_count for g in groups),
        ac_power_mw_total=round(sum(g.ac_power_mw_total for g in groups), 3),
        groups=tuple(groups),
    )


def unresolved_provisional_fields(
    configuration_code: str,
    project_settings: dict[str, Any] | None,
    *,
    extra_overrides: Optional[dict[str, Any]] = None,
) -> list[str]:
    """List provisional fields still awaiting owner confirmation for this config."""
    payload = build_governed_ac_output_from_settings(
        configuration_code, project_settings, extra_overrides=extra_overrides
    )
    return list(payload.get("provisional_unresolved", []))


__all__ = [
    "GovernedSiteGroup",
    "GovernedSitePlan",
    "build_governed_ac_output_from_product",
    "build_governed_ac_output_from_settings",
    "build_governed_site_ac_output",
    "build_governed_site_plan",
    "eligible_products_for",
    "map_engineering_settings_to_overrides",
    "product_overrides",
    "unresolved_provisional_fields",
]
