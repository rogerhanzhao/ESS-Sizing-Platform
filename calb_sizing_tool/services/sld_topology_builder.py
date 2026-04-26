from __future__ import annotations

from typing import Any, Sequence

from calb_sizing_tool.adapters.ac_to_sld_adapter import AcToSldAdapterError, normalize_ac_output_for_sld
from calb_sizing_tool.schemas.sld_render_input import (
    SldCanonicalInput,
    SldEquipmentRatings,
    SldLabels,
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


def _merge_legacy_equipment_payload(sld_inputs: dict[str, Any]) -> tuple[SldLabels, SldEquipmentRatings, str, float, float]:
    payload = {
        "labels": {},
        "equipment_ratings": {},
    }

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
                payload["equipment_ratings"].setdefault(key, {})
                payload["equipment_ratings"][key].update({name: value for name, value in candidate.items() if value not in (None, "")})
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
            payload["equipment_ratings"].setdefault(key, {})
            payload["equipment_ratings"][key].update({name: value for name, value in candidate.items() if value not in (None, "")})

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

    missing_fields: list[str] = []
    label_to_switchgear = str(payload["labels"].get("to_switchgear") or "").strip()
    label_to_other_rmu = str(payload["labels"].get("to_other_rmu") or "").strip()
    if not label_to_switchgear:
        missing_fields.append("mv_labels.to_switchgear")
    if not label_to_other_rmu:
        missing_fields.append("mv_labels.to_other_rmu")
    if "rmu" not in payload["equipment_ratings"]:
        missing_fields.append("rmu")
    if "lv_busbar" not in payload["equipment_ratings"]:
        missing_fields.append("lv_busbar")
    if "cables" not in payload["equipment_ratings"]:
        missing_fields.append("cables")
    if "dc_fuse" not in payload["equipment_ratings"]:
        missing_fields.append("dc_fuse")
    if not str(payload.get("transformer_vector_group") or "").strip():
        missing_fields.append("transformer.vector_group")
    if _safe_float(payload.get("transformer_uk_percent"), 0.0) <= 0:
        missing_fields.append("transformer.uk_percent")
    if _safe_float(payload.get("dc_block_voltage_v"), 0.0) <= 0:
        missing_fields.append("dc_block_voltage_v")
    if missing_fields:
        raise ValueError(
            "legacy compatibility inputs are missing required engineering fields: "
            + ", ".join(missing_fields)
        )

    return (
        SldLabels.model_validate(
            {
                "to_switchgear": label_to_switchgear,
                "to_other_rmu": label_to_other_rmu,
            }
        ),
        SldEquipmentRatings.model_validate(payload["equipment_ratings"]),
        str(payload["transformer_vector_group"]),
        float(payload["transformer_uk_percent"]),
        float(payload["dc_block_voltage_v"]),
    )


def build_legacy_sld_canonical_input(
    stage13_output: dict[str, Any],
    ac_output: dict[str, Any],
    dc_summary: dict[str, Any],
    sld_inputs: dict[str, Any],
    group_index: int,
) -> SldCanonicalInput:
    """LEGACY compatibility only.

    Old dict-based callers are adapted into SldCanonicalInput, but this path is
    now strict about feeder allocation and transformer sizing. It no longer
    fabricates PCS counts, transformer MVA, or DC feeder splits.
    """
    stage13_output = stage13_output or {}
    ac_output = ac_output or {}
    dc_summary = dc_summary or {}
    sld_inputs = sld_inputs or {}

    try:
        authoritative_ac = normalize_ac_output_for_sld(ac_output)
    except AcToSldAdapterError as exc:
        raise ValueError(
            "legacy compatibility path requires an AC output that satisfies the AC->SLD contract: "
            + "; ".join(exc.errors)
        ) from exc

    ac_blocks_total = authoritative_ac.num_blocks

    resolved_group_index = _safe_int(group_index, 1)
    if resolved_group_index < 1 or resolved_group_index > ac_blocks_total:
        raise ValueError(
            f"group_index={resolved_group_index} is outside the authoritative AC block range 1..{ac_blocks_total}."
        )
    group_idx = resolved_group_index - 1

    pcs_count = authoritative_ac.pcs_count_by_block[group_idx]
    pcs_rating_kw_list = list(authoritative_ac.pcs_rating_kw_list_by_block[group_idx])

    mv_voltage_kv = _safe_float(
        sld_inputs.get("mv_nominal_kv_ac")
        or authoritative_ac.mv_voltage_kv
        or stage13_output.get("poi_nominal_voltage_kv"),
        0.0,
    )
    if mv_voltage_kv <= 0:
        raise ValueError("legacy compatibility path requires mv_nominal_kv_ac or authoritative MV voltage.")
    lv_voltage_v_ll = _safe_float(
        sld_inputs.get("pcs_lv_voltage_v_ll")
        or authoritative_ac.lv_voltage_v,
        0.0,
    )
    if lv_voltage_v_ll <= 0:
        raise ValueError("legacy compatibility path requires pcs_lv_voltage_v_ll or authoritative LV voltage.")

    transformer_rating_mva = _safe_float(
        sld_inputs.get("transformer_rating_mva") or authoritative_ac.transformer_mva,
        0.0,
    )
    if transformer_rating_mva <= 0:
        raise ValueError("legacy compatibility path requires transformer_rating_mva or authoritative transformer_mva.")

    dc_block_energy_mwh = _safe_float(sld_inputs.get("dc_block_energy_mwh"), 0.0)
    if dc_block_energy_mwh <= 0:
        dc_block = dc_summary.get("dc_block") if isinstance(dc_summary, dict) else None
        if dc_block is not None:
            dc_block_energy_mwh = _safe_float(getattr(dc_block, "capacity_mwh", 0.0), 0.0)
    if dc_block_energy_mwh <= 0:
        raise ValueError("legacy compatibility path requires dc_block_energy_mwh or dc_summary.dc_block.capacity_mwh.")

    dc_blocks_per_feeder = _normalize_counts(sld_inputs.get("dc_blocks_per_feeder"), pcs_count)
    if not dc_blocks_per_feeder:
        dc_blocks_per_feeder = list(authoritative_ac.dc_blocks_per_feeder_by_block[group_idx])
    if len(dc_blocks_per_feeder) != pcs_count:
        raise ValueError("legacy compatibility path requires dc_blocks_per_feeder to match authoritative PCS count.")
    expected_dc_blocks_total = authoritative_ac.dc_blocks_total_by_block[group_idx]
    if sum(dc_blocks_per_feeder) != expected_dc_blocks_total:
        raise ValueError(
            "legacy compatibility path requires dc_blocks_per_feeder to match the authoritative AC allocation total."
        )

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
            node_id=f"{group_token}-MV-RING-IN",
            node_type="mv_ring_in",
            display_name="Ring In",
            labels=[mv_labels[0]],
            attributes={"mv_voltage_kv": canonical_input.mv_voltage_kv},
        )
    )

    add_equipment(
        SldEquipment(
            equipment_id=f"{group_token}-RMU",
            equipment_type="rmu",
            display_name="RMU / MV Switchgear",
            attributes=canonical_input.equipment_ratings.rmu.model_dump(mode="python"),
        )
    )
    add_node(
        SldNode(
            node_id=f"{group_token}-RMU-NODE",
            node_type="mv_switchgear",
            display_name="RMU / MV Switchgear",
            equipment_id=f"{group_token}-RMU",
            labels=mv_labels,
            attributes={"mv_voltage_kv": canonical_input.mv_voltage_kv},
        )
    )
    add_node(
        SldNode(
            node_id=f"{group_token}-MV-TX-FEEDER",
            node_type="mv_transformer_feeder",
            display_name="Transformer Feeder",
            equipment_id=f"{group_token}-RMU",
            attributes={"mv_voltage_kv": canonical_input.mv_voltage_kv},
        )
    )
    add_node(
        SldNode(
            node_id=f"{group_token}-MV-RING-OUT",
            node_type="mv_ring_out",
            display_name="Ring Out",
            labels=[mv_labels[1]],
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
            edge_id=f"{group_token}-EDGE-RINGIN-RMU",
            edge_type="ring_in_to_switchgear",
            source_node_id=f"{group_token}-MV-RING-IN",
            target_node_id=f"{group_token}-RMU-NODE",
            labels=mv_labels,
        )
    )
    add_edge(
        SldEdge(
            edge_id=f"{group_token}-EDGE-RMU-TXFEEDER",
            edge_type="switchgear_to_transformer_feeder",
            source_node_id=f"{group_token}-RMU-NODE",
            target_node_id=f"{group_token}-MV-TX-FEEDER",
        )
    )
    add_edge(
        SldEdge(
            edge_id=f"{group_token}-EDGE-TXFEEDER-TX",
            edge_type="transformer_feeder_to_transformer",
            source_node_id=f"{group_token}-MV-TX-FEEDER",
            target_node_id=f"{group_token}-TX-NODE",
        )
    )
    add_edge(
        SldEdge(
            edge_id=f"{group_token}-EDGE-RMU-RINGOUT",
            edge_type="switchgear_to_ring_out",
            source_node_id=f"{group_token}-RMU-NODE",
            target_node_id=f"{group_token}-MV-RING-OUT",
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
        dc_interface_equipment_id = f"{feeder_token}-DC-INTERFACE"

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
                equipment_id=dc_interface_equipment_id,
                equipment_type="dc_interface",
                display_name=f"DC Interface {feeder_index}",
                feeder_index=feeder_index,
                attributes={
                    "dc_block_count": dc_block_count,
                    "dc_block_voltage_v": canonical_input.dc_block_voltage_v,
                    "fuse_spec": canonical_input.equipment_ratings.dc_fuse.fuse_spec,
                },
            )
        )
        add_node(
            SldNode(
                node_id=f"{feeder_token}-DC-INTERFACE-NODE",
                node_type="dc_interface",
                display_name=f"DC Interface {feeder_index}",
                equipment_id=dc_interface_equipment_id,
                feeder_index=feeder_index,
                labels=[
                    SldLabel(
                        label_id=f"{feeder_token}-DC-INTERFACE-LABEL",
                        semantic_key="dc_blocks_per_feeder",
                        text=f"{dc_block_count} DC blocks",
                        scope="dc_interface",
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
                edge_id=f"{feeder_token}-EDGE-PCS-DCIF",
                edge_type="pcs_to_dc_interface",
                source_node_id=f"{feeder_token}-PCS-NODE",
                target_node_id=f"{feeder_token}-DC-INTERFACE-NODE",
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
                    edge_type="dc_interface_to_dc_block",
                    source_node_id=f"{feeder_token}-DC-INTERFACE-NODE",
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
