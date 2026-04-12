from __future__ import annotations

from typing import Any, Sequence

from calb_sizing_tool.common.allocation import allocate_dc_blocks, evenly_distribute
from calb_sizing_tool.schemas.sld_render_input import (
    SldCanonicalInput,
    SldEquipmentRatings,
    SldInputOverride,
    SldLabels,
    legacy_sld_override_preset,
)
from calb_sizing_tool.schemas.sld_topology import (
    SldEdge,
    SldEquipment,
    SldLabel,
    SldNode,
    SldTopology,
    SldTopologySummary,
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_counts(values: Sequence[Any], expected_len: int) -> list[int]:
    if not isinstance(values, (list, tuple)) or expected_len <= 0:
        return []
    counts = [_safe_int(entry, 0) for entry in values]
    if len(counts) == expected_len:
        return counts
    if len(counts) > expected_len:
        return counts[:expected_len]
    counts.extend([0 for _ in range(expected_len - len(counts))])
    return counts


def _base_equipment_payload() -> dict[str, Any]:
    preset = legacy_sld_override_preset()
    return {
        "labels": dict(preset["labels"]),
        "equipment_ratings": {
            "rmu": dict(preset["equipment_ratings"]["rmu"]),
            "lv_busbar": dict(preset["equipment_ratings"]["lv_busbar"]),
            "cables": dict(preset["equipment_ratings"]["cables"]),
            "dc_fuse": dict(preset["equipment_ratings"]["dc_fuse"]),
            "transformer_tap_range": preset["equipment_ratings"]["transformer_tap_range"],
            "transformer_cooling": preset["equipment_ratings"]["transformer_cooling"],
        },
        "transformer_vector_group": preset["transformer_vector_group"],
        "transformer_uk_percent": preset["transformer_uk_percent"],
        "dc_block_voltage_v": 1500.0,
    }


def _merge_legacy_equipment_payload(sld_inputs: dict[str, Any]) -> tuple[SldLabels, SldEquipmentRatings, str, float, float]:
    payload = _base_equipment_payload()

    mv_labels = sld_inputs.get("mv_labels")
    if isinstance(mv_labels, dict):
        payload["labels"].update({key: value for key, value in mv_labels.items() if value not in (None, "")})

    equipment_list = sld_inputs.get("equipment_list")
    if isinstance(equipment_list, dict):
        labels = equipment_list.get("mv_labels")
        if isinstance(labels, dict):
            payload["labels"].update({key: value for key, value in labels.items() if value not in (None, "")})
        for key in ("rmu", "lv_busbar", "cables", "dc_fuse"):
            candidate = equipment_list.get(key)
            if isinstance(candidate, dict):
                payload["equipment_ratings"][key].update(
                    {name: value for name, value in candidate.items() if value not in (None, "")}
                )
        transformer_equipment = equipment_list.get("transformer")
        if isinstance(transformer_equipment, dict):
            if transformer_equipment.get("vector_group"):
                payload["transformer_vector_group"] = transformer_equipment["vector_group"]
            if transformer_equipment.get("uk_percent") not in (None, ""):
                payload["transformer_uk_percent"] = transformer_equipment["uk_percent"]
            if transformer_equipment.get("tap_range"):
                payload["equipment_ratings"]["transformer_tap_range"] = transformer_equipment["tap_range"]
            if transformer_equipment.get("cooling"):
                payload["equipment_ratings"]["transformer_cooling"] = transformer_equipment["cooling"]
        if equipment_list.get("dc_block_voltage_v") not in (None, ""):
            payload["dc_block_voltage_v"] = equipment_list["dc_block_voltage_v"]

    for key in ("rmu", "lv_busbar", "cables", "dc_fuse"):
        candidate = sld_inputs.get(key)
        if isinstance(candidate, dict):
            payload["equipment_ratings"][key].update(
                {name: value for name, value in candidate.items() if value not in (None, "")}
            )

    transformer_input = sld_inputs.get("transformer")
    if isinstance(transformer_input, dict):
        if transformer_input.get("vector_group"):
            payload["transformer_vector_group"] = transformer_input["vector_group"]
        if transformer_input.get("uk_percent") not in (None, ""):
            payload["transformer_uk_percent"] = transformer_input["uk_percent"]
        if transformer_input.get("tap_range"):
            payload["equipment_ratings"]["transformer_tap_range"] = transformer_input["tap_range"]
        if transformer_input.get("cooling"):
            payload["equipment_ratings"]["transformer_cooling"] = transformer_input["cooling"]

    if sld_inputs.get("dc_block_voltage_v") not in (None, ""):
        payload["dc_block_voltage_v"] = sld_inputs["dc_block_voltage_v"]

    return (
        SldLabels.model_validate(payload["labels"]),
        SldEquipmentRatings.model_validate(payload["equipment_ratings"]),
        str(payload["transformer_vector_group"]),
        float(payload["transformer_uk_percent"]),
        float(payload["dc_block_voltage_v"]),
    )


def _resolve_pcs_count_by_block(ac_output: dict[str, Any], ac_blocks_total: int) -> list[int]:
    pcs_counts = _normalize_counts(ac_output.get("pcs_count_by_block"), ac_blocks_total)
    if pcs_counts:
        return pcs_counts

    pcs_units = ac_output.get("pcs_units")
    if isinstance(pcs_units, list) and pcs_units:
        return [len(pcs_units) for _ in range(ac_blocks_total or 1)]

    pcs_count_per_block = _safe_int(ac_output.get("pcs_count_per_ac_block"), 0)
    if ac_blocks_total > 0 and pcs_count_per_block > 0:
        return [pcs_count_per_block for _ in range(ac_blocks_total)]

    pcs_per_block = _safe_int(ac_output.get("pcs_per_block"), 0)
    total_pcs = _safe_int(ac_output.get("total_pcs"), 0)
    if ac_blocks_total > 0 and total_pcs > 0:
        return evenly_distribute(total_pcs, ac_blocks_total)
    if ac_blocks_total > 0 and pcs_per_block > 0:
        return [pcs_per_block for _ in range(ac_blocks_total)]
    return [4] if ac_blocks_total == 1 else []


def _resolve_dc_blocks_total_by_block(
    ac_output: dict[str, Any],
    stage13_output: dict[str, Any],
    dc_summary: dict[str, Any],
    ac_blocks_total: int,
) -> list[int]:
    allocation = ac_output.get("dc_block_allocation")
    if isinstance(allocation, dict):
        per_ac_block = allocation.get("per_ac_block")
        if isinstance(per_ac_block, list) and per_ac_block:
            totals: list[int] = []
            for entry in per_ac_block:
                total = entry.get("dc_blocks_total")
                if total is None:
                    per_feeder = entry.get("per_feeder")
                    if isinstance(per_feeder, dict):
                        total = sum(_safe_int(v, 0) for v in per_feeder.values())
                totals.append(_safe_int(total, 0))
            normalized = _normalize_counts(totals, ac_blocks_total)
            if normalized:
                return normalized

    totals = _normalize_counts(ac_output.get("dc_blocks_total_by_block"), ac_blocks_total)
    if totals:
        return totals

    dc_per_ac = _safe_int(ac_output.get("dc_blocks_per_ac"), 0)
    if ac_blocks_total > 0 and dc_per_ac > 0:
        return [dc_per_ac for _ in range(ac_blocks_total)]

    total_dc_blocks = _safe_int(stage13_output.get("dc_block_total_qty"), 0)
    if total_dc_blocks <= 0:
        total_dc_blocks = _safe_int(stage13_output.get("container_count"), 0) + _safe_int(
            stage13_output.get("cabinet_count"), 0
        )
    if total_dc_blocks <= 0 and isinstance(dc_summary, dict):
        dc_block = dc_summary.get("dc_block")
        if dc_block is not None:
            total_dc_blocks = _safe_int(getattr(dc_block, "count", 0))

    if ac_blocks_total > 0:
        return evenly_distribute(total_dc_blocks, ac_blocks_total)
    return []


def build_legacy_sld_canonical_input(
    stage13_output: dict[str, Any],
    ac_output: dict[str, Any],
    dc_summary: dict[str, Any],
    sld_inputs: dict[str, Any],
    group_index: int,
) -> SldCanonicalInput:
    """LEGACY compatibility only. Convert old dict-based SLD inputs into SldCanonicalInput."""
    stage13_output = stage13_output or {}
    ac_output = ac_output or {}
    dc_summary = dc_summary or {}
    sld_inputs = sld_inputs or {}

    ac_blocks_total = _safe_int(ac_output.get("num_blocks") or ac_output.get("ac_blocks_total"), 0)
    if ac_blocks_total <= 0:
        total_pcs = _safe_int(ac_output.get("total_pcs"), 0)
        pcs_per_block = _safe_int(ac_output.get("pcs_per_block"), 0)
        if total_pcs > 0 and pcs_per_block > 0:
            ac_blocks_total = max(1, total_pcs // pcs_per_block)
    if ac_blocks_total <= 0:
        ac_blocks_total = 1

    resolved_group_index = _safe_int(group_index, 1)
    if resolved_group_index < 1:
        resolved_group_index = 1
    if resolved_group_index > ac_blocks_total:
        resolved_group_index = ac_blocks_total
    group_idx = resolved_group_index - 1

    pcs_counts = _resolve_pcs_count_by_block(ac_output, ac_blocks_total)
    pcs_count = pcs_counts[group_idx] if group_idx < len(pcs_counts) else _safe_int(ac_output.get("pcs_per_block"), 4)
    if pcs_count <= 0:
        pcs_count = 1

    block_size_mw = _safe_float(ac_output.get("block_size_mw"), 0.0)
    pcs_rating_each_kw = _safe_float(sld_inputs.get("pcs_rating_each_kw"), 0.0)
    if pcs_rating_each_kw <= 0:
        pcs_rating_each_kw = _safe_float(sld_inputs.get("pcs_rating_each_kva"), 0.0)
    if pcs_rating_each_kw <= 0:
        pcs_rating_each_kw = _safe_float(ac_output.get("pcs_power_kw"), 0.0)
    if pcs_rating_each_kw <= 0:
        pcs_rating_each_kw = _safe_float(ac_output.get("pcs_kw"), 0.0)
    if pcs_rating_each_kw <= 0 and block_size_mw > 0 and pcs_count > 0:
        pcs_rating_each_kw = block_size_mw * 1000.0 / pcs_count
    if pcs_rating_each_kw <= 0:
        pcs_rating_each_kw = 1250.0

    pcs_rating_kw_list = sld_inputs.get("pcs_rating_kw_list")
    if not isinstance(pcs_rating_kw_list, list):
        pcs_rating_kw_list = sld_inputs.get("pcs_rating_kva_list")
    if not isinstance(pcs_rating_kw_list, list) or len(pcs_rating_kw_list) != pcs_count:
        pcs_rating_kw_list = [pcs_rating_each_kw for _ in range(pcs_count)]
    else:
        pcs_rating_kw_list = [_safe_float(value, pcs_rating_each_kw) for value in pcs_rating_kw_list]

    mv_voltage_kv = _safe_float(
        sld_inputs.get("mv_nominal_kv_ac")
        or ac_output.get("mv_voltage_kv")
        or ac_output.get("mv_kv")
        or ac_output.get("grid_kv")
        or stage13_output.get("poi_nominal_voltage_kv"),
        33.0,
    )
    lv_voltage_v_ll = _safe_float(
        sld_inputs.get("pcs_lv_voltage_v_ll")
        or ac_output.get("lv_voltage_v")
        or ac_output.get("lv_v")
        or ac_output.get("inverter_lv_v"),
        690.0,
    )

    transformer_rating_mva = _safe_float(sld_inputs.get("transformer_rating_mva"), 0.0)
    if transformer_rating_mva <= 0:
        transformer_rating_mva = _safe_float(ac_output.get("transformer_mva"), 0.0)
    if transformer_rating_mva <= 0:
        transformer_kva = _safe_float(sld_inputs.get("transformer_rating_kva") or ac_output.get("transformer_kva"), 0.0)
        if transformer_kva > 0:
            transformer_rating_mva = transformer_kva / 1000.0
        elif block_size_mw > 0:
            transformer_rating_mva = block_size_mw / 0.9
    if transformer_rating_mva <= 0:
        transformer_rating_mva = 5.0

    dc_block_energy_mwh = _safe_float(sld_inputs.get("dc_block_energy_mwh"), 0.0)
    if dc_block_energy_mwh <= 0:
        dc_block = dc_summary.get("dc_block") if isinstance(dc_summary, dict) else None
        if dc_block is not None:
            dc_block_energy_mwh = _safe_float(getattr(dc_block, "capacity_mwh", 0.0), 0.0)
    if dc_block_energy_mwh <= 0:
        dc_block_energy_mwh = 5.106

    dc_blocks_per_feeder = _normalize_counts(sld_inputs.get("dc_blocks_per_feeder"), pcs_count)
    if not dc_blocks_per_feeder:
        allocation = ac_output.get("dc_block_allocation")
        if isinstance(allocation, dict):
            per_ac_block = allocation.get("per_ac_block")
            if isinstance(per_ac_block, list) and group_idx < len(per_ac_block):
                per_feeder = per_ac_block[group_idx].get("per_feeder")
                if isinstance(per_feeder, dict) and per_feeder:
                    keys = sorted(per_feeder.keys(), key=lambda key: _safe_int(str(key).lstrip("Ff"), 0))
                    dc_blocks_per_feeder = [_safe_int(per_feeder.get(key), 0) for key in keys]
            if not dc_blocks_per_feeder:
                per_feeder = allocation.get("per_feeder")
                if isinstance(per_feeder, dict) and per_feeder:
                    keys = sorted(per_feeder.keys(), key=lambda key: _safe_int(str(key).lstrip("Ff"), 0))
                    dc_blocks_per_feeder = [_safe_int(per_feeder.get(key), 0) for key in keys]
            if not dc_blocks_per_feeder:
                per_pcs_group = allocation.get("per_pcs_group")
                if isinstance(per_pcs_group, list) and per_pcs_group:
                    dc_blocks_per_feeder = [_safe_int(item.get("dc_block_count"), 0) for item in per_pcs_group]

    if not dc_blocks_per_feeder:
        dc_blocks_per_feeder_by_block = ac_output.get("dc_blocks_per_feeder_by_block")
        if isinstance(dc_blocks_per_feeder_by_block, list) and group_idx < len(dc_blocks_per_feeder_by_block):
            candidate = dc_blocks_per_feeder_by_block[group_idx]
            if isinstance(candidate, list) and candidate:
                dc_blocks_per_feeder = _normalize_counts(candidate, pcs_count)

    if not dc_blocks_per_feeder:
        dc_totals_by_block = _resolve_dc_blocks_total_by_block(ac_output, stage13_output, dc_summary, ac_blocks_total)
        dc_total_group = dc_totals_by_block[group_idx] if group_idx < len(dc_totals_by_block) else 0
        dc_blocks_per_feeder = allocate_dc_blocks(dc_total_group, pcs_count)

    if not dc_blocks_per_feeder:
        dc_blocks_per_feeder = [0 for _ in range(pcs_count)]

    labels, equipment_ratings, transformer_vector_group, transformer_uk_percent, dc_block_voltage_v = (
        _merge_legacy_equipment_payload(sld_inputs)
    )

    return SldCanonicalInput(
        run_id=None,
        project_name=str(stage13_output.get("project_name") or ac_output.get("project_name") or "CALB ESS Project"),
        scenario_id=str(sld_inputs.get("scenario_id") or "legacy_sld_group"),
        group_index=resolved_group_index,
        ac_blocks_total=ac_blocks_total,
        project_frequency_hz=_safe_float(stage13_output.get("poi_frequency_hz"), 0.0) or None,
        mv_voltage_kv=mv_voltage_kv,
        lv_voltage_v_ll=lv_voltage_v_ll,
        transformer_rating_mva=transformer_rating_mva,
        transformer_vector_group=transformer_vector_group,
        transformer_uk_percent=transformer_uk_percent,
        pcs_count=pcs_count,
        pcs_rating_kw_list=[float(value) for value in pcs_rating_kw_list],
        dc_block_energy_mwh=dc_block_energy_mwh,
        dc_blocks_total_in_group=sum(dc_blocks_per_feeder),
        dc_blocks_per_feeder=[int(value) for value in dc_blocks_per_feeder],
        dc_block_voltage_v=dc_block_voltage_v,
        equipment_ratings=equipment_ratings,
        labels=labels,
        diagram_mode="one_ac_block_group",
        theme=str(sld_inputs.get("theme") or "light"),
        compact_mode=bool(sld_inputs.get("compact_mode")),
        draw_summary=bool(sld_inputs.get("draw_summary")),
        validation_mode="draft",
        override_mode=False,
        source_trace={
            "A": "legacy compatibility wrapper",
            "B": "legacy ac_output allocation",
            "C": "legacy equipment defaults",
            "D": "legacy manual sld_inputs",
        },
        draft_warnings=[
            "legacy build path uses compatibility canonical input",
        ],
    )


def build_sld_topology(canonical_input: SldCanonicalInput) -> SldTopology:
    group_token = f"G{canonical_input.group_index:02d}"

    equipment: list[SldEquipment] = []
    nodes: list[SldNode] = []
    edges: list[SldEdge] = []

    def add_equipment(item: SldEquipment) -> None:
        equipment.append(item)

    def add_node(item: SldNode) -> None:
        nodes.append(item)

    def add_edge(item: SldEdge) -> None:
        edges.append(item)

    mv_labels = [
        SldLabel(
            label_id=f"{group_token}-LABEL-TO-SWITCHGEAR",
            semantic_key="to_switchgear",
            text=canonical_input.labels.to_switchgear,
            scope="mv",
        ),
        SldLabel(
            label_id=f"{group_token}-LABEL-TO-OTHER-RMU",
            semantic_key="to_other_rmu",
            text=canonical_input.labels.to_other_rmu,
            scope="mv",
        ),
    ]

    add_node(
        SldNode(
            node_id=f"{group_token}-MV-BUS",
            node_type="mv_bus",
            display_name="MV Bus",
            labels=mv_labels,
            attributes={
                "mv_voltage_kv": canonical_input.mv_voltage_kv,
                "group_index": canonical_input.group_index,
            },
        )
    )

    add_equipment(
        SldEquipment(
            equipment_id=f"{group_token}-RMU",
            equipment_type="rmu",
            display_name="RMU",
            attributes=canonical_input.equipment_ratings.rmu.model_dump(mode="python"),
        )
    )
    add_node(
        SldNode(
            node_id=f"{group_token}-RMU-NODE",
            node_type="rmu",
            display_name="RMU",
            equipment_id=f"{group_token}-RMU",
            labels=mv_labels,
            attributes={"mv_voltage_kv": canonical_input.mv_voltage_kv},
        )
    )

    add_equipment(
        SldEquipment(
            equipment_id=f"{group_token}-TX",
            equipment_type="transformer",
            display_name="Transformer",
            attributes={
                "transformer_rating_mva": canonical_input.transformer_rating_mva,
                "transformer_vector_group": canonical_input.transformer_vector_group,
                "transformer_uk_percent": canonical_input.transformer_uk_percent,
                "transformer_tap_range": canonical_input.equipment_ratings.transformer_tap_range,
                "transformer_cooling": canonical_input.equipment_ratings.transformer_cooling,
                "mv_voltage_kv": canonical_input.mv_voltage_kv,
                "lv_voltage_v_ll": canonical_input.lv_voltage_v_ll,
            },
        )
    )
    add_node(
        SldNode(
            node_id=f"{group_token}-TX-NODE",
            node_type="transformer",
            display_name="Transformer",
            equipment_id=f"{group_token}-TX",
            attributes={
                "transformer_rating_mva": canonical_input.transformer_rating_mva,
                "transformer_vector_group": canonical_input.transformer_vector_group,
                "transformer_uk_percent": canonical_input.transformer_uk_percent,
            },
        )
    )

    add_equipment(
        SldEquipment(
            equipment_id=f"{group_token}-LV-BUSBAR",
            equipment_type="lv_busbar",
            display_name="LV Busbar",
            attributes=canonical_input.equipment_ratings.lv_busbar.model_dump(mode="python"),
        )
    )
    add_node(
        SldNode(
            node_id=f"{group_token}-LV-BUSBAR-NODE",
            node_type="lv_busbar",
            display_name="LV Busbar",
            equipment_id=f"{group_token}-LV-BUSBAR",
            attributes={"lv_voltage_v_ll": canonical_input.lv_voltage_v_ll},
        )
    )

    add_edge(
        SldEdge(
            edge_id=f"{group_token}-EDGE-MV-RMU",
            edge_type="mv_link",
            source_node_id=f"{group_token}-MV-BUS",
            target_node_id=f"{group_token}-RMU-NODE",
            labels=mv_labels,
        )
    )
    add_edge(
        SldEdge(
            edge_id=f"{group_token}-EDGE-RMU-TX",
            edge_type="rmu_to_transformer",
            source_node_id=f"{group_token}-RMU-NODE",
            target_node_id=f"{group_token}-TX-NODE",
        )
    )
    add_edge(
        SldEdge(
            edge_id=f"{group_token}-EDGE-TX-LVBUS",
            edge_type="transformer_to_lv_busbar",
            source_node_id=f"{group_token}-TX-NODE",
            target_node_id=f"{group_token}-LV-BUSBAR-NODE",
        )
    )

    dc_block_ordinal = 0
    for feeder_index, (pcs_rating_kw, dc_block_count) in enumerate(
        zip(canonical_input.pcs_rating_kw_list, canonical_input.dc_blocks_per_feeder),
        start=1,
    ):
        feeder_token = f"{group_token}-F{feeder_index:02d}"
        pcs_equipment_id = f"{feeder_token}-PCS"
        dc_busbar_equipment_id = f"{feeder_token}-DC-BUSBAR"

        add_equipment(
            SldEquipment(
                equipment_id=pcs_equipment_id,
                equipment_type="pcs",
                display_name=f"PCS {feeder_index}",
                feeder_index=feeder_index,
                attributes={
                    "pcs_rating_kw": pcs_rating_kw,
                    "lv_voltage_v_ll": canonical_input.lv_voltage_v_ll,
                },
            )
        )
        add_node(
            SldNode(
                node_id=f"{feeder_token}-PCS-NODE",
                node_type="pcs",
                display_name=f"PCS {feeder_index}",
                equipment_id=pcs_equipment_id,
                feeder_index=feeder_index,
                labels=[
                    SldLabel(
                        label_id=f"{feeder_token}-PCS-LABEL",
                        semantic_key="pcs_rating_kw",
                        text=f"{pcs_rating_kw:.0f} kW",
                        scope="pcs",
                    )
                ],
                attributes={"pcs_rating_kw": pcs_rating_kw},
            )
        )

        add_equipment(
            SldEquipment(
                equipment_id=dc_busbar_equipment_id,
                equipment_type="dc_busbar",
                display_name=f"DC Busbar {feeder_index}",
                feeder_index=feeder_index,
                attributes={
                    "dc_block_count": dc_block_count,
                    "dc_block_voltage_v": canonical_input.dc_block_voltage_v,
                },
            )
        )
        add_node(
            SldNode(
                node_id=f"{feeder_token}-DC-BUSBAR-NODE",
                node_type="dc_busbar",
                display_name=f"DC Busbar {feeder_index}",
                equipment_id=dc_busbar_equipment_id,
                feeder_index=feeder_index,
                labels=[
                    SldLabel(
                        label_id=f"{feeder_token}-DC-BUSBAR-LABEL",
                        semantic_key="dc_blocks_per_feeder",
                        text=f"{dc_block_count} DC blocks",
                        scope="dc_busbar",
                    )
                ],
                attributes={"dc_block_count": dc_block_count},
            )
        )

        add_edge(
            SldEdge(
                edge_id=f"{feeder_token}-EDGE-LVBUS-PCS",
                edge_type="lv_busbar_to_pcs",
                source_node_id=f"{group_token}-LV-BUSBAR-NODE",
                target_node_id=f"{feeder_token}-PCS-NODE",
                feeder_index=feeder_index,
            )
        )
        add_edge(
            SldEdge(
                edge_id=f"{feeder_token}-EDGE-PCS-DCBUS",
                edge_type="pcs_to_dc_busbar",
                source_node_id=f"{feeder_token}-PCS-NODE",
                target_node_id=f"{feeder_token}-DC-BUSBAR-NODE",
                feeder_index=feeder_index,
            )
        )

        for local_block_index in range(1, dc_block_count + 1):
            dc_block_ordinal += 1
            dc_block_equipment_id = f"{feeder_token}-DC-BLOCK-{local_block_index:02d}"
            add_equipment(
                SldEquipment(
                    equipment_id=dc_block_equipment_id,
                    equipment_type="dc_block",
                    display_name=f"DC Block {dc_block_ordinal}",
                    feeder_index=feeder_index,
                    dc_block_index=dc_block_ordinal,
                    attributes={
                        "dc_block_energy_mwh": canonical_input.dc_block_energy_mwh,
                        "dc_block_voltage_v": canonical_input.dc_block_voltage_v,
                    },
                )
            )
            add_node(
                SldNode(
                    node_id=f"{dc_block_equipment_id}-NODE",
                    node_type="dc_block",
                    display_name=f"DC Block {dc_block_ordinal}",
                    equipment_id=dc_block_equipment_id,
                    feeder_index=feeder_index,
                    dc_block_index=dc_block_ordinal,
                    labels=[
                        SldLabel(
                            label_id=f"{dc_block_equipment_id}-LABEL",
                            semantic_key="dc_block_energy_mwh",
                            text=f"{canonical_input.dc_block_energy_mwh:.3f} MWh",
                            scope="dc_block",
                        )
                    ],
                    attributes={
                        "dc_block_energy_mwh": canonical_input.dc_block_energy_mwh,
                        "dc_block_voltage_v": canonical_input.dc_block_voltage_v,
                    },
                )
            )
            add_edge(
                SldEdge(
                    edge_id=f"{dc_block_equipment_id}-EDGE",
                    edge_type="dc_busbar_to_dc_block",
                    source_node_id=f"{feeder_token}-DC-BUSBAR-NODE",
                    target_node_id=f"{dc_block_equipment_id}-NODE",
                    feeder_index=feeder_index,
                    attributes={"local_block_index": local_block_index},
                )
            )

    return SldTopology(
        run_id=canonical_input.run_id,
        project_name=canonical_input.project_name,
        scenario_id=canonical_input.scenario_id,
        source_trace=dict(canonical_input.source_trace),
        validation_mode=canonical_input.validation_mode,
        labels=canonical_input.labels,
        equipment_ratings=canonical_input.equipment_ratings,
        summary=SldTopologySummary(
            group_index=canonical_input.group_index,
            ac_blocks_total=canonical_input.ac_blocks_total,
            feeder_count=canonical_input.pcs_count,
            pcs_count=canonical_input.pcs_count,
            dc_blocks_total_in_group=canonical_input.dc_blocks_total_in_group,
            dc_blocks_per_feeder=list(canonical_input.dc_blocks_per_feeder),
            mv_voltage_kv=canonical_input.mv_voltage_kv,
            lv_voltage_v_ll=canonical_input.lv_voltage_v_ll,
            transformer_rating_mva=canonical_input.transformer_rating_mva,
            transformer_vector_group=canonical_input.transformer_vector_group,
            transformer_uk_percent=canonical_input.transformer_uk_percent,
            pcs_rating_kw_list=list(canonical_input.pcs_rating_kw_list),
            dc_block_energy_mwh=canonical_input.dc_block_energy_mwh,
            dc_block_voltage_v=canonical_input.dc_block_voltage_v,
            project_frequency_hz=canonical_input.project_frequency_hz,
            diagram_mode=canonical_input.diagram_mode,
            theme=canonical_input.theme,
            compact_mode=canonical_input.compact_mode,
            draw_summary=canonical_input.draw_summary,
        ),
        nodes=nodes,
        edges=edges,
        equipment=equipment,
    )


def build_legacy_sld_topology(
    stage13_output: dict[str, Any],
    ac_output: dict[str, Any],
    dc_summary: dict[str, Any],
    sld_inputs: dict[str, Any],
    group_index: int,
) -> SldTopology:
    """LEGACY compatibility only. Old dict-based SLD builders must route through this wrapper."""
    canonical_input = build_legacy_sld_canonical_input(
        stage13_output=stage13_output,
        ac_output=ac_output,
        dc_summary=dc_summary,
        sld_inputs=sld_inputs,
        group_index=group_index,
    )
    return build_sld_topology(canonical_input)
