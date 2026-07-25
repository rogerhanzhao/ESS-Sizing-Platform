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
            # A product qualifies unless it declares a CONTRADICTING topology.
            # Most tail-size datasheets do not publish the vector group, so an
            # unknown (None) topology must not exclude an otherwise-matching
            # product; a declared value must still match.
            product_topology = metadata.get("transformer_topology")
            topology_ok = product_topology is None or product_topology == config.transformer_topology
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
    eligible_product_codes: tuple[str, ...] = ()


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


def build_governed_site_plan(
    dc_blocks_total: int, *, db_url: str | None = None, with_products: bool = False
) -> GovernedSitePlan:
    """Decompose a DC total into governed AC Block groups (Phase B).

    Any positive total is exactly composable (greedy 8/4/2/1); a multiple of 8
    yields a single bilateral group (equivalent to Phase A). When ``with_products``
    is set, each group is annotated with the catalogue products eligible to
    supply it (matched by power / DC-input count / non-contradicting topology).
    """
    eligible_cache: dict[str, tuple[str, ...]] = {}

    def _eligible(code: str) -> tuple[str, ...]:
        if not with_products:
            return ()
        if code not in eligible_cache:
            try:
                eligible_cache[code] = tuple(
                    p["block_code"] for p in eligible_products_for(code, db_url=db_url)
                )
            except Exception:  # pragma: no cover - defensive (no DB / empty table)
                eligible_cache[code] = ()
        return eligible_cache[code]

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
                eligible_product_codes=_eligible(config.configuration_code),
            )
        )
    return GovernedSitePlan(
        dc_blocks_total=int(dc_blocks_total),
        ac_blocks_total=sum(g.ac_block_count for g in groups),
        ac_power_mw_total=round(sum(g.ac_power_mw_total for g in groups), 3),
        groups=tuple(groups),
    )


@dataclass(frozen=True)
class GovernedSiteRunGroup:
    """One homogeneous governed group with its own authoritative AC output.

    A group covering ``ac_block_count`` identical AC Blocks is represented by a
    single uniform ``SldAuthoritativeAcOutput`` (``ac_output``) — every block in
    the group is identical, so exactly one SLD drawing represents the group under
    the SLD V1 uniform-block contract. ``bound_product_code`` records the real
    catalogue product supplying the group's provisional values (or ``None`` when
    the run is settings-only or no product qualifies).
    """

    configuration_code: str
    layout_variant: str
    ac_block_count: int
    dc_blocks_per_ac_block: int
    dc_blocks_total: int
    pcs_per_ac_block: int
    ac_power_mw_total: float
    bound_product_code: Optional[str]
    eligible_product_codes: tuple[str, ...]
    ac_output: dict[str, Any]
    provisional_unresolved: tuple[str, ...]


@dataclass(frozen=True)
class GovernedSiteRun:
    """A fully-orchestrated mixed governed site: one AC output per group.

    This turns the Phase B decomposition into a runnable multi-block site: each
    ``GovernedSiteRunGroup`` carries a valid, individually SLD-renderable AC
    output, and the run aggregates the site totals plus the union of every
    provisional field still awaiting owner confirmation across all groups.
    """

    dc_blocks_total: int
    ac_blocks_total: int
    ac_power_mw_total: float
    groups: tuple[GovernedSiteRunGroup, ...]
    provisional_unresolved: tuple[str, ...]


def build_governed_site_run(
    dc_blocks_total: int,
    *,
    project_settings: dict[str, Any] | None = None,
    source_fields: Optional[dict[str, Any]] = None,
    db_url: str | None = None,
    bind_products: bool = False,
) -> GovernedSiteRun:
    """Orchestrate a mixed governed site into one AC output per governed group.

    The site is decomposed (greedy 8/4/2/1) into homogeneous groups; each group
    is expanded into its own authoritative ``SldAuthoritativeAcOutput`` so a
    heterogeneous site becomes N valid, individually SLD-renderable AC outputs
    (one per governed configuration present) instead of a single per-group demo.

    When ``bind_products`` is set, each group binds the first catalogue product
    eligible for its configuration (datasheet-sourced MVA / vector group /
    cooling); otherwise the group is built from ``project_settings`` alone. Either
    way a provisional value is never fabricated — unresolved fields are reported
    per group and unioned onto the run, so downstream SLD/report stay gated until
    the owner confirms them.
    """
    plan = build_governed_site_plan(
        dc_blocks_total, db_url=db_url, with_products=bind_products
    )
    groups: list[GovernedSiteRunGroup] = []
    run_unresolved: list[str] = []
    for group in plan.groups:
        eligible = group.eligible_product_codes
        bound_code: Optional[str] = None
        if bind_products and eligible:
            bound_code = eligible[0]
            ac_output = build_governed_ac_output_from_product(
                group.configuration_code,
                bound_code,
                project_settings=project_settings,
                dc_blocks_total=group.dc_blocks_total,
                source_fields=source_fields,
                db_url=db_url,
            )
        else:
            ac_output = build_governed_site_ac_output(
                group.configuration_code,
                project_settings,
                dc_blocks_total=group.dc_blocks_total,
                source_fields=source_fields,
            )
        unresolved = tuple(ac_output.get("provisional_unresolved", ()) or ())
        for field in unresolved:
            if field not in run_unresolved:
                run_unresolved.append(field)
        groups.append(
            GovernedSiteRunGroup(
                configuration_code=group.configuration_code,
                layout_variant=group.layout_variant,
                ac_block_count=group.ac_block_count,
                dc_blocks_per_ac_block=group.dc_blocks_per_ac_block,
                dc_blocks_total=group.dc_blocks_total,
                pcs_per_ac_block=group.pcs_per_ac_block,
                ac_power_mw_total=group.ac_power_mw_total,
                bound_product_code=bound_code,
                eligible_product_codes=eligible,
                ac_output=ac_output,
                provisional_unresolved=unresolved,
            )
        )
    return GovernedSiteRun(
        dc_blocks_total=plan.dc_blocks_total,
        ac_blocks_total=plan.ac_blocks_total,
        ac_power_mw_total=plan.ac_power_mw_total,
        groups=tuple(groups),
        provisional_unresolved=tuple(run_unresolved),
    )


def build_governed_primary_ac_output(
    dc_blocks_total: int,
    *,
    project_settings: dict[str, Any] | None = None,
    source_fields: Optional[dict[str, Any]] = None,
    head_product_block_code: Optional[str] = None,
    db_url: str | None = None,
) -> dict[str, Any]:
    """The AC output the AC Sizing page stores for ANY governed DC total.

    This is the single entry the UI uses so a non-multiple-of-8 project still
    reaches the governed identity instead of silently falling back to the generic
    average-ratio grouping. It decomposes the site (Phase B, greedy 8/4/2/1) and
    returns the **head (largest) governed group's uniform AC output** — which
    stays a valid, single-drawing ``SldAuthoritativeAcOutput`` so the SLD renders
    the governed head cleanly (Dy11y11, no override preset).

    For a mixed site the head output additionally carries the honest SITE rollup
    (``governed_is_mixed`` + ``governed_site_*`` totals + ``governed_groups``) so
    the report states the true site (e.g. 92 DC → 11×10 MW bilateral + 1×5 MW
    tail = 115 MW / 12 AC Blocks) and enumerates every governed group with its
    bound product — never an average 23×4-PCS reconstruction, never a fabricated
    ``MW ÷ PF`` nameplate. A pure multiple-of-8 total yields a single group and
    the plain uniform output (no rollup), identical to Phase A.
    """
    run = build_governed_site_run(
        dc_blocks_total,
        project_settings=project_settings,
        source_fields=source_fields,
        db_url=db_url,
        bind_products=True,
    )
    head = run.groups[0]
    head_code = head.configuration_code

    # The head group honours the owner's explicit product choice. When none is
    # selected it is built settings-only (no silent auto-bind), so an unconfirmed
    # transformer MVA stays TBD instead of adopting an arbitrary catalogue value.
    if head_product_block_code:
        head_output = build_governed_ac_output_from_product(
            head_code,
            head_product_block_code,
            project_settings=project_settings,
            dc_blocks_total=head.dc_blocks_total,
            source_fields=source_fields,
            db_url=db_url,
        )
        head_product = head_product_block_code
    else:
        head_output = build_governed_site_ac_output(
            head_code,
            project_settings,
            dc_blocks_total=head.dc_blocks_total,
            source_fields=source_fields,
        )
        head_product = None
    head_unresolved = list(head_output.get("provisional_unresolved", ()))

    if len(run.groups) == 1:
        return head_output

    # Mixed site: overlay the true site rollup (never mutate the SLD-authoritative
    # uniform fields, so the head SLD stays renderable). The tails keep their
    # auto-bound catalogue product from the run; the head reflects the choice above.
    def _group_summary(g: GovernedSiteRunGroup, product, mva, unresolved, confirmation) -> dict[str, Any]:
        return {
            "configuration_code": g.configuration_code,
            "ac_block_count": g.ac_block_count,
            "pcs_per_ac_block": g.pcs_per_ac_block,
            "dc_blocks_per_ac_block": g.dc_blocks_per_ac_block,
            "ac_power_mw_total": g.ac_power_mw_total,
            "bound_product_code": product,
            # product_confirmation records HOW the product got bound so the report
            # never presents an auto-bound tail product as owner-confirmed:
            #   owner_selected  — the owner explicitly picked it (head only, today)
            #   provisional_auto — auto-bound "first eligible" (tails); NOT confirmed
            #   none            — no catalogue product bound (settings-only)
            "product_confirmation": confirmation,
            "transformer_mva": mva,
            "provisional_unresolved": list(unresolved),
        }

    head_confirmation = "owner_selected" if head_product else "none"
    groups_summary = [
        _group_summary(head, head_product, head_output.get("transformer_mva"), head_unresolved, head_confirmation)
    ]
    union_unresolved: set[str] = set(head_unresolved)
    for g in run.groups[1:]:
        tail_confirmation = "provisional_auto" if g.bound_product_code else "none"
        groups_summary.append(
            _group_summary(
                g, g.bound_product_code, g.ac_output.get("transformer_mva"),
                g.provisional_unresolved, tail_confirmation,
            )
        )
        union_unresolved |= set(g.provisional_unresolved)

    output = dict(head_output)
    output["governed_is_mixed"] = True
    output["governed_site_ac_blocks_total"] = run.ac_blocks_total
    output["governed_site_pcs_total"] = sum(
        g.pcs_per_ac_block * g.ac_block_count for g in run.groups
    )
    output["governed_site_total_ac_mw"] = run.ac_power_mw_total
    output["governed_site_dc_blocks_total"] = run.dc_blocks_total
    output["governed_groups"] = groups_summary
    output["provisional_unresolved"] = sorted(union_unresolved)
    return output


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
    "GovernedSiteRun",
    "GovernedSiteRunGroup",
    "build_governed_ac_output_from_product",
    "build_governed_ac_output_from_settings",
    "build_governed_primary_ac_output",
    "build_governed_site_ac_output",
    "build_governed_site_plan",
    "build_governed_site_run",
    "eligible_products_for",
    "map_engineering_settings_to_overrides",
    "product_overrides",
    "unresolved_provisional_fields",
]
