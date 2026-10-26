from __future__ import annotations

"""Legacy adapter only.

This module bridges DB snapshots into legacy `stage13_output` shapes for
downstream pages that still depend on session_state. It must not be treated
as a runtime source of truth.
"""

from typing import Any
import json
import math

from calb_sizing_tool.schemas.run_snapshot import DcPipelineRunSnapshot
from calb_sizing_tool.schemas.stage2 import Stage2Result
from calb_sizing_tool.services.run_persistence_service import _hash_payload
from calb_sizing_tool.ui.stage4_interface import pack_stage13_output


def build_dc_bom_handoff(stage2: Stage2Result) -> dict[str, Any]:
    """Preserve the actual Stage 2 inventory for a downstream adapter.

    This opt-in adapter does not adopt a comparison, calculate an AC group or
    alter legacy scalar handoffs. Ordinals describe inventory order only;
    they never establish physical placement, DC outputs or PCS connections.
    There is no single-tail, final-position or mutually-exclusive SKU rule.

    Stage 2 rounds unit capacity to three decimals *after* calculating its
    subtotals from source precision. Preserve those subtotals and validate
    their rounding bounds rather than averaging them into an invented unit
    rating or demanding rounded unit capacity times count match exactly.
    """
    if not isinstance(stage2, Stage2Result):
        raise ValueError("A canonical Stage 2 result is required for the DC BOM handoff.")

    def whole(value: Any, label: str) -> int:
        if type(value) is not int or value < 0:
            raise ValueError(f"{label} must be a nonnegative integer.")
        return value

    def number(value: Any, label: str, *, positive: bool = False) -> float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{label} must be finite numeric data.")
        if value < 0 or positive and value == 0:
            raise ValueError(f"{label} must be {'positive' if positive else 'nonnegative'}.")
        return float(value)

    source_payload = stage2.model_dump(mode="json")
    try:
        json.dumps(source_payload, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("The source Stage 2 result must contain finite JSON data.") from exc

    total = number(stage2.dc_nameplate_bol_mwh, "DC nameplate total")
    expected_containers = whole(stage2.container_count, "Container count")
    expected_cabinets = whole(stage2.cabinet_count, "Cabinet count")
    items: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    counts = {"container": 0, "cabinet": 0}
    for item_ordinal, item in enumerate(stage2.block_config_items, 1):
        if item.form not in counts:
            raise ValueError("Every DC BOM item must identify container or cabinet form.")
        if not isinstance(item.block_code, str) or not item.block_code.strip():
            raise ValueError("Every DC BOM item must retain its product code.")
        if not isinstance(item.block_name, str) or not item.block_name.strip():
            raise ValueError("Every DC BOM item must retain its product name.")
        count = whole(item.count, "DC BOM item count")
        capacity = number(item.unit_capacity_mwh, "DC BOM unit capacity", positive=True)
        subtotal = number(item.subtotal_mwh, "DC BOM subtotal")
        repeated_total = number(item.total_dc_nameplate_bol_mwh, "DC BOM repeated total")
        if not math.isclose(repeated_total, total, rel_tol=0, abs_tol=1e-9):
            raise ValueError("A DC BOM item total differs from the Stage 2 total.")
        rounding_bound = 0.0005 * (count + 1) + 1e-9
        if abs(subtotal - capacity * count) > rounding_bound:
            raise ValueError("A DC BOM subtotal is inconsistent with its quantity and source precision.")
        if count == 0 and subtotal != 0:
            raise ValueError("A zero-quantity DC BOM item must have zero subtotal.")
        counts[item.form] += count
        items.append({"item_ordinal": item_ordinal, **item.model_dump(mode="json")})
        for ordinal_in_item in range(1, count + 1):
            units.append(dict(
                bom_ordinal=len(units) + 1,
                item_ordinal=item_ordinal,
                ordinal_in_item=ordinal_in_item,
                block_code=item.block_code,
                block_name=item.block_name,
                form=item.form,
                unit_capacity_mwh=capacity,
            ))

    if counts != {"container": expected_containers, "cabinet": expected_cabinets}:
        raise ValueError("DC BOM quantities differ from the Stage 2 container or cabinet count.")
    subtotal_sum = math.fsum(item["subtotal_mwh"] for item in items)
    total_rounding_bound = 0 if len(items) <= 1 else 0.0005 * (len(items) + 1)
    if abs(subtotal_sum - total) > total_rounding_bound + 1e-9:
        raise ValueError("DC BOM subtotals differ from the Stage 2 total beyond source precision.")
    return dict(
        schema_version=1,
        contract_type="dc_bom_handoff",
        source="canonical_stage2_block_config_items",
        source_stage2_sha256=_hash_payload(source_payload),
        source_mode=stage2.mode,
        items=items,
        units=units,
        totals=dict(container_count=expected_containers, cabinet_count=expected_cabinets,
                    unit_count=len(units), dc_nameplate_bol_mwh=total),
        precision=dict(capacity_decimals=3, source_subtotals_preserved=True,
                       unit_capacities_are_rounded=True),
        unit_ordinals_are_inventory_only=True,
        electrical_mapping_provided=False,
        adoption_asserted=False,
    )


def build_dc_result_summary(snapshot: DcPipelineRunSnapshot) -> dict[str, Any]:
    stage1 = snapshot.stage1
    stage2 = snapshot.stage2
    stage3_df = snapshot.stage3.dataframe()
    guarantee_row = stage3_df[stage3_df["Is_Guarantee_Year"]]
    guarantee_poi = (
        float(guarantee_row["POI_Usable_Energy_MWh"].iloc[0]) if not guarantee_row.empty else 0.0
    )
    dc_blocks_total = int(stage2.container_count + stage2.cabinet_count)
    return {
        "mode": str(stage2.mode),
        "dc_product_codes": [item.block_code for item in stage2.block_config_items],
        "target_mw": stage1.poi_power_req_mw,
        "mwh": stage1.poi_energy_req_mwh,
        "dc_nameplate_bol_mwh": stage2.dc_nameplate_bol_mwh,
        "dc_blocks_total": dc_blocks_total,
        # Legacy AC page restore contract. Keep these aliases until AC sizing
        # reads the canonical snapshot directly instead of session_state.
        "total_blocks": dc_blocks_total,
        "container_count": int(stage2.container_count),
        "cabinet_count": int(stage2.cabinet_count),
        "guarantee_year_poi_usable_mwh": guarantee_poi,
        "iterations": snapshot.iteration_count,
        "converged": snapshot.converged,
    }


def build_stage13_output(
    snapshot: DcPipelineRunSnapshot,
    *,
    dc_block_total_qty: int,
    selected_scenario: str,
    poi_nominal_voltage_kv: float,
    poi_frequency_hz: float | None = None,
) -> dict[str, Any]:
    return pack_stage13_output(
        snapshot.stage1.to_legacy_dict(),
        snapshot.stage2.to_legacy_dict(),
        snapshot.stage3.meta.to_legacy_dict(),
        dc_block_total_qty=dc_block_total_qty,
        selected_scenario=selected_scenario,
        poi_nominal_voltage_kv=poi_nominal_voltage_kv,
        poi_frequency_hz=poi_frequency_hz,
        stage3_df=snapshot.stage3.dataframe(),
    )
