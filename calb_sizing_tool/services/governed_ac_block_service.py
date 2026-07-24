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

from typing import Any, Optional

from calb_sizing_tool.schemas.governed_ac_block_config import (
    GovernedACBlockConfiguration,
    get_governed_configuration,
)


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
    "build_governed_ac_output_from_settings",
    "build_governed_site_ac_output",
    "map_engineering_settings_to_overrides",
    "unresolved_provisional_fields",
]
