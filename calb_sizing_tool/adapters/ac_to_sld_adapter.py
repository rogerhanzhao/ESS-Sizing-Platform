from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from calb_sizing_tool.schemas.ac_electrical_topology import build_dc_block_connection_plan
from calb_sizing_tool.schemas.sld_authoritative_input import SldAcBlockAllocation, SldAuthoritativeAcOutput


AC_TO_SLD_AUTHORITATIVE_FIELDS_V1 = {
    "num_blocks": "Required. Total AC block count.",
    "pcs_per_block": "Required. Uniform PCS count per AC block in SLD V1.",
    "pcs_kw": "Required. Uniform PCS rating per feeder in kW.",
    "block_size_mw": "Required. Must equal pcs_per_block * pcs_kw / 1000. The adapter must not derive it silently.",
    "dc_allocation_plan": "Required. Authoritative physical DC Block output-circuit to PCS-feeder allocation.",
    "dc_blocks_total_by_block": "Derived mirror of dc_allocation_plan totals.",
    "dc_blocks_per_feeder_by_block": "Derived mirror of dc_allocation_plan feeder allocations.",
    "transformer_mva": "Required. Transformer rating per AC block.",
    "transformer_topology": "Required for new AC runs: two_winding (one common LV busbar) or three_winding (two independent LV secondary busbars).",
    "lv_winding_count": "Mirror of the selected transformer topology, never inferred from PCS count for new AC runs.",
    "transformer_count": "Optional mirror of num_blocks.",
    "pcs_count_total": "Optional mirror of sum(pcs_count_by_block).",
    "dc_blocks_total": "Optional mirror of sum(dc_blocks_total_by_block).",
    "dc_total_mwh": "Optional site-level DC energy mirror.",
    "mv_voltage_kv": "Optional MV voltage mirror from AC results.",
    "lv_voltage_v": "Optional LV voltage mirror from AC results.",
}


AC_TO_SLD_LEGACY_ALIASES_V1 = {
    "num_blocks": ("ac_blocks_total",),
    "pcs_per_block": ("pcs_count_per_ac_block",),
    "pcs_kw": ("pcs_power_kw", "pcs_rating_kw_each"),
    "dc_allocation_plan": ("dc_block_allocation",),
    "transformer_mva": ("transformer_rating_mva", "transformer_kva"),
    "lv_winding_count": ("transformer_lv_winding_count",),
    "transformer_topology": ("transformer_winding_topology",),
    "pcs_count_total": ("total_pcs",),
    "mv_voltage_kv": ("mv_kv", "grid_kv"),
    "lv_voltage_v": ("lv_v", "inverter_lv_v"),
}


class AcToSldAdapterError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _normalize_non_negative_int_list(values: Any) -> list[int] | None:
    if not isinstance(values, list) or not values:
        return None
    normalized: list[int] = []
    for item in values:
        parsed = _safe_int(item)
        if parsed is None or parsed < 0:
            return None
        normalized.append(int(parsed))
    return normalized


def _normalize_positive_float_list(values: Any) -> list[float] | None:
    if not isinstance(values, list) or not values:
        return None
    normalized: list[float] = []
    for item in values:
        parsed = _safe_float(item)
        if parsed is None or parsed <= 0:
            return None
        normalized.append(float(parsed))
    return normalized


def _resolve_field(
    field_name: str,
    payload: dict[str, Any],
    field_sources: dict[str, str],
    legacy_aliases_used: set[str],
) -> Any:
    if field_name in payload and payload.get(field_name) not in (None, ""):
        field_sources[field_name] = field_name
        return payload.get(field_name)
    for alias in AC_TO_SLD_LEGACY_ALIASES_V1.get(field_name, ()):
        if alias in payload and payload.get(alias) not in (None, ""):
            field_sources[field_name] = alias
            legacy_aliases_used.add(alias)
            return payload.get(alias)
    return None


def _resolve_required_int(
    field_name: str,
    payload: dict[str, Any],
    errors: list[str],
    field_sources: dict[str, str],
    legacy_aliases_used: set[str],
) -> int | None:
    value = _safe_int(_resolve_field(field_name, payload, field_sources, legacy_aliases_used))
    if value is None or value <= 0:
        errors.append(f"{field_name} is required in the AC->SLD contract and must be > 0.")
        return None
    return int(value)


def _resolve_required_float(
    field_name: str,
    payload: dict[str, Any],
    errors: list[str],
    field_sources: dict[str, str],
    legacy_aliases_used: set[str],
) -> float | None:
    raw = _resolve_field(field_name, payload, field_sources, legacy_aliases_used)
    if field_name == "transformer_mva" and field_sources.get(field_name) == "transformer_kva":
        value = _safe_float(raw)
        if value is not None and value > 0:
            value = value / 1000.0
    else:
        value = _safe_float(raw)
    if value is None or value <= 0:
        errors.append(f"{field_name} is required in the AC->SLD contract and must be > 0.")
        return None
    return float(value)


def _resolve_optional_float(
    field_name: str,
    payload: dict[str, Any],
    field_sources: dict[str, str],
    legacy_aliases_used: set[str],
) -> float | None:
    value = _safe_float(_resolve_field(field_name, payload, field_sources, legacy_aliases_used))
    if value is None or value <= 0:
        return None
    return float(value)


def _resolve_optional_int(
    field_name: str,
    payload: dict[str, Any],
    field_sources: dict[str, str],
    legacy_aliases_used: set[str],
) -> int | None:
    value = _safe_int(_resolve_field(field_name, payload, field_sources, legacy_aliases_used))
    if value is None or value < 0:
        return None
    return int(value)


def _build_allocation_entry(
    *,
    source_name: str,
    ac_block_index: int,
    pcs_count: int,
    pcs_rating_kw: float,
    dc_blocks_total: int,
    feeder_allocations: list[int],
    dc_block_connections: list[dict[str, Any]] | None,
    errors: list[str],
) -> SldAcBlockAllocation | None:
    try:
        return SldAcBlockAllocation(
            ac_block_index=ac_block_index,
            pcs_count=pcs_count,
            pcs_rating_kw=pcs_rating_kw,
            dc_blocks_total=dc_blocks_total,
            feeder_allocations=feeder_allocations,
            dc_block_connections=dc_block_connections or [],
        )
    except ValidationError as exc:
        for item in exc.errors():
            location = ".".join(str(part) for part in item.get("loc", ()))
            suffix = f".{location}" if location else ""
            errors.append(f"{source_name}{suffix}: {item.get('msg')}")
        return None


def _build_dedicated_connections_from_legacy_allocation(
    feeder_allocations: list[int],
    *,
    output_circuit_count: int,
) -> list[dict[str, Any]]:
    """Preserve legacy one-DC-Block-per-feeder allocation detail exactly."""
    connections: list[dict[str, Any]] = []
    dc_block_index = 1
    for feeder_index, count in enumerate(feeder_allocations, start=1):
        for _ in range(count):
            connections.append(
                {
                    "dc_block_index": dc_block_index,
                    "feeder_indices": [feeder_index],
                    "output_circuit_count": output_circuit_count,
                    "internal_dc_busbar_mode": "common",
                }
            )
            dc_block_index += 1
    return connections


def _resolve_dc_allocation_plan(
    payload: dict[str, Any],
    *,
    num_blocks: int,
    pcs_per_block: int,
    pcs_kw: float,
    errors: list[str],
    field_sources: dict[str, str],
    legacy_aliases_used: set[str],
    dc_block_output_circuits: int,
) -> list[SldAcBlockAllocation] | None:
    direct_plan = payload.get("dc_allocation_plan")
    if isinstance(direct_plan, list) and direct_plan:
        field_sources["dc_allocation_plan"] = "dc_allocation_plan"
        plans: list[SldAcBlockAllocation] = []
        for block_index, entry in enumerate(direct_plan, start=1):
            if not isinstance(entry, dict):
                errors.append("dc_allocation_plan entries must be dicts.")
                return None
            dc_blocks_total = _safe_int(entry.get("dc_blocks_total"))
            feeder_allocations = _normalize_non_negative_int_list(entry.get("feeder_allocations"))
            raw_connections = entry.get("dc_block_connections")
            if dc_blocks_total is None and isinstance(raw_connections, list):
                dc_blocks_total = len(raw_connections)
            if dc_blocks_total is None and feeder_allocations is not None:
                dc_blocks_total = sum(feeder_allocations)
            if dc_blocks_total is None or dc_blocks_total <= 0:
                errors.append("dc_allocation_plan dc_blocks_total must be > 0.")
                return None
            if not isinstance(raw_connections, list) or not raw_connections:
                if feeder_allocations is not None and sum(feeder_allocations) != dc_blocks_total:
                    # Preserve the previous contract error. A physical mapping
                    # must not silently repair conflicting legacy mirrors.
                    raw_connections = None
                else:
                    try:
                        if feeder_allocations is not None and dc_blocks_total >= pcs_per_block:
                            raw_connections = _build_dedicated_connections_from_legacy_allocation(
                                feeder_allocations,
                                output_circuit_count=dc_block_output_circuits,
                            )
                        else:
                            # Historic under-populated feeder counts (for
                            # example [1, 1, 0, 0]) did not express shared DC
                            # outputs. Translate those safely so every PCS has
                            # a protected DC source in the new SLD model.
                            raw_connections = build_dc_block_connection_plan(
                                dc_blocks_total,
                                pcs_per_block,
                                output_circuit_count=dc_block_output_circuits,
                            )
                    except ValueError as exc:
                        errors.append(f"dc_allocation_plan[{block_index - 1}]: {exc}")
                        return None
            if isinstance(raw_connections, list) and raw_connections:
                feeder_allocations = [
                    sum(1 for connection in raw_connections if feeder_index in connection.get("feeder_indices", []))
                    for feeder_index in range(1, pcs_per_block + 1)
                ]
            plan_entry = _build_allocation_entry(
                source_name=f"dc_allocation_plan[{block_index - 1}]",
                ac_block_index=_safe_int(entry.get("ac_block_index")) or block_index,
                pcs_count=pcs_per_block,
                pcs_rating_kw=pcs_kw,
                dc_blocks_total=dc_blocks_total,
                feeder_allocations=feeder_allocations,
                dc_block_connections=raw_connections,
                errors=errors,
            )
            if plan_entry is None:
                return None
            plans.append(plan_entry)
        if len(plans) != num_blocks:
            errors.append("dc_allocation_plan length must match num_blocks.")
            return None
        return plans

    legacy_plan = payload.get("dc_block_allocation")
    if isinstance(legacy_plan, dict):
        field_sources["dc_allocation_plan"] = "dc_block_allocation"
        legacy_aliases_used.add("dc_block_allocation")
        per_ac_block = legacy_plan.get("per_ac_block")
        if isinstance(per_ac_block, list) and per_ac_block:
            plans = []
            for block_index, entry in enumerate(per_ac_block, start=1):
                if not isinstance(entry, dict):
                    errors.append("dc_block_allocation.per_ac_block entries must be dicts.")
                    return None
                per_feeder = entry.get("per_feeder")
                feeder_allocations: list[int] | None = None
                if isinstance(per_feeder, dict):
                    ordered_keys = sorted(
                        per_feeder.keys(),
                        key=lambda key: _safe_int(str(key).lstrip("Ff")) or 0,
                    )
                    feeder_allocations = _normalize_non_negative_int_list([per_feeder[key] for key in ordered_keys])
                elif isinstance(per_feeder, list):
                    feeder_allocations = _normalize_non_negative_int_list(per_feeder)
                if feeder_allocations is None or len(feeder_allocations) != pcs_per_block:
                    errors.append("dc_block_allocation.per_ac_block.per_feeder must match pcs_per_block.")
                    return None
                dc_blocks_total = _safe_int(entry.get("dc_blocks_total"))
                if dc_blocks_total is None:
                    dc_blocks_total = sum(feeder_allocations)
                plan_entry = _build_allocation_entry(
                    source_name=f"dc_block_allocation.per_ac_block[{block_index - 1}]",
                    ac_block_index=_safe_int(entry.get("ac_block_index")) or block_index,
                    pcs_count=pcs_per_block,
                    pcs_rating_kw=pcs_kw,
                dc_blocks_total=dc_blocks_total,
                feeder_allocations=feeder_allocations,
                dc_block_connections=None,
                    errors=errors,
                )
                if plan_entry is None:
                    return None
                plans.append(plan_entry)
            if len(plans) != num_blocks:
                errors.append("dc_block_allocation.per_ac_block length must match num_blocks.")
                return None
            return plans

    errors.append(
        "dc_allocation_plan is required in the AC->SLD contract. "
        "Only the compatibility adapter may translate legacy dc_block_allocation. "
        "dc_blocks_total_by_block and dc_blocks_per_feeder_by_block are derived mirrors and cannot replace it."
    )
    return None


def _compare_optional_list(name: str, expected: list[int], candidate: Any, errors: list[str]) -> None:
    normalized = _normalize_non_negative_int_list(candidate)
    if normalized is None:
        return
    if normalized != expected:
        errors.append(f"{name} conflicts with the authoritative AC->SLD normalization result.")


def _compare_optional_matrix(name: str, expected: list[list[int]], candidate: Any, errors: list[str]) -> None:
    if not isinstance(candidate, list):
        return
    normalized: list[list[int]] = []
    for row in candidate:
        parsed = _normalize_non_negative_int_list(row)
        if parsed is None:
            return
        normalized.append(parsed)
    if normalized != expected:
        errors.append(f"{name} conflicts with the authoritative AC->SLD normalization result.")


def _compare_optional_float(name: str, expected: float, candidate: Any, errors: list[str]) -> None:
    value = _safe_float(candidate)
    if value is None:
        return
    if abs(float(value) - float(expected)) > 1e-6:
        errors.append(f"{name} conflicts with the authoritative AC->SLD normalization result.")


def _compare_optional_int(name: str, expected: int, candidate: Any, errors: list[str]) -> None:
    value = _safe_int(candidate)
    if value is None:
        return
    if int(value) != int(expected):
        errors.append(f"{name} conflicts with the authoritative AC->SLD normalization result.")


def normalize_ac_output_for_sld(ac_output: dict[str, Any]) -> SldAuthoritativeAcOutput:
    """Compatibility adapter.

    This is the single allowed place where legacy AC aliases are translated into the
    authoritative AC->SLD V1 contract.
    """
    if not isinstance(ac_output, dict) or not ac_output:
        raise AcToSldAdapterError(["ac_output is required to build the SLD authoritative input."])

    errors: list[str] = []
    field_sources: dict[str, str] = {}
    legacy_aliases_used: set[str] = set()

    num_blocks = _resolve_required_int("num_blocks", ac_output, errors, field_sources, legacy_aliases_used)
    pcs_per_block = _resolve_required_int("pcs_per_block", ac_output, errors, field_sources, legacy_aliases_used)
    pcs_kw = _resolve_required_float("pcs_kw", ac_output, errors, field_sources, legacy_aliases_used)
    block_size_mw = _resolve_required_float("block_size_mw", ac_output, errors, field_sources, legacy_aliases_used)
    transformer_mva = _resolve_required_float("transformer_mva", ac_output, errors, field_sources, legacy_aliases_used)

    if errors:
        raise AcToSldAdapterError(errors)

    pcs_count_by_block = [pcs_per_block for _ in range(num_blocks)]
    pcs_rating_kw_list_by_block = [[pcs_kw for _ in range(pcs_per_block)] for _ in range(num_blocks)]
    transformer_topology_raw = _resolve_field("transformer_topology", ac_output, field_sources, legacy_aliases_used)
    transformer_topology = str(transformer_topology_raw or "").strip() or None
    lv_winding_count = _resolve_optional_int(
        "lv_winding_count", ac_output, field_sources, legacy_aliases_used
    )
    if transformer_topology not in {None, "two_winding", "three_winding"}:
        errors.append("transformer_topology must be two_winding or three_winding.")
    if transformer_topology is None:
        # Compatibility only for historic runs. New AC sizing output always
        # provides the topology explicitly.
        if lv_winding_count is None:
            lv_winding_count = (pcs_per_block + 1) // 2
            field_sources["lv_winding_count"] = "legacy_derived_from_pcs_per_block"
        transformer_topology = "three_winding" if lv_winding_count > 1 else "two_winding"
        field_sources["transformer_topology"] = "legacy_derived_from_lv_winding_count"
    expected_windings = 1 if transformer_topology == "two_winding" else 2
    if lv_winding_count is None:
        lv_winding_count = expected_windings
        field_sources["lv_winding_count"] = "derived_from_transformer_topology"
    elif lv_winding_count != expected_windings:
        errors.append("lv_winding_count conflicts with transformer_topology.")
    dc_block_output_circuits = _resolve_optional_int(
        "dc_block_output_circuits", ac_output, field_sources, legacy_aliases_used
    ) or 2
    if dc_block_output_circuits not in (1, 2):
        errors.append("dc_block_output_circuits must be 1 or 2.")
    dc_allocation_plan = _resolve_dc_allocation_plan(
        ac_output,
        num_blocks=num_blocks,
        pcs_per_block=pcs_per_block,
        pcs_kw=pcs_kw,
        errors=errors,
        field_sources=field_sources,
        legacy_aliases_used=legacy_aliases_used,
        dc_block_output_circuits=dc_block_output_circuits,
    )
    if dc_allocation_plan is None:
        raise AcToSldAdapterError(errors)

    dc_blocks_total_by_block = [entry.dc_blocks_total for entry in dc_allocation_plan]
    dc_blocks_per_feeder_by_block = [list(entry.feeder_allocations) for entry in dc_allocation_plan]
    dc_block_connections_by_block = [list(entry.dc_block_connections) for entry in dc_allocation_plan]
    transformer_count = _resolve_optional_int("transformer_count", ac_output, field_sources, legacy_aliases_used)
    if transformer_count is None:
        transformer_count = num_blocks
        field_sources["transformer_count"] = "derived_from_num_blocks"
    pcs_count_total = _resolve_optional_int("pcs_count_total", ac_output, field_sources, legacy_aliases_used)
    if pcs_count_total is None:
        pcs_count_total = sum(pcs_count_by_block)
        field_sources["pcs_count_total"] = "derived_from_pcs_count_by_block"
    dc_blocks_total = _resolve_optional_int("dc_blocks_total", ac_output, field_sources, legacy_aliases_used)
    if dc_blocks_total is None:
        dc_blocks_total = sum(dc_blocks_total_by_block)
        field_sources["dc_blocks_total"] = "derived_from_dc_allocation_plan"
    dc_total_mwh = _resolve_optional_float("dc_total_mwh", ac_output, field_sources, legacy_aliases_used)
    mv_voltage_kv = _resolve_optional_float("mv_voltage_kv", ac_output, field_sources, legacy_aliases_used)
    lv_voltage_v = _resolve_optional_float("lv_voltage_v", ac_output, field_sources, legacy_aliases_used)

    _compare_optional_list("pcs_count_by_block", pcs_count_by_block, ac_output.get("pcs_count_by_block"), errors)
    _compare_optional_matrix(
        "dc_blocks_per_feeder_by_block",
        dc_blocks_per_feeder_by_block,
        ac_output.get("dc_blocks_per_feeder_by_block"),
        errors,
    )
    _compare_optional_list("dc_blocks_total_by_block", dc_blocks_total_by_block, ac_output.get("dc_blocks_total_by_block"), errors)
    _compare_optional_int("transformer_count", transformer_count, ac_output.get("transformer_count"), errors)
    _compare_optional_int("pcs_count_total", pcs_count_total, ac_output.get("pcs_count_total") or ac_output.get("total_pcs"), errors)
    _compare_optional_int("dc_blocks_total", dc_blocks_total, ac_output.get("dc_blocks_total"), errors)
    _compare_optional_float("block_size_mw", block_size_mw, ac_output.get("block_size_mw"), errors)

    if errors:
        raise AcToSldAdapterError(errors)

    try:
        return SldAuthoritativeAcOutput(
            num_blocks=num_blocks,
            pcs_per_block=pcs_per_block,
            pcs_count_by_block=pcs_count_by_block,
            pcs_kw=pcs_kw,
            pcs_rating_kw_list_by_block=pcs_rating_kw_list_by_block,
            block_size_mw=block_size_mw,
            dc_allocation_plan=dc_allocation_plan,
            dc_blocks_total_by_block=dc_blocks_total_by_block,
            dc_blocks_per_feeder_by_block=dc_blocks_per_feeder_by_block,
            dc_blocks_total=dc_blocks_total,
            dc_total_mwh=dc_total_mwh,
            transformer_mva=transformer_mva,
            lv_winding_count=lv_winding_count,
            transformer_topology=transformer_topology,
            dc_block_connections_by_block=dc_block_connections_by_block,
            transformer_count=transformer_count,
            pcs_count_total=pcs_count_total,
            mv_voltage_kv=mv_voltage_kv,
            lv_voltage_v=lv_voltage_v,
            legacy_aliases_used=sorted(legacy_aliases_used),
            field_sources=field_sources,
        )
    except ValidationError as exc:
        normalized = [f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()]
        raise AcToSldAdapterError(normalized) from exc
