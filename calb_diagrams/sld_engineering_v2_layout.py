from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from calb_sizing_tool.schemas.sld_engineering_v2 import SldEngineeringV2Graph, SldV2Node


@dataclass(frozen=True)
class SldV2LayoutSection:
    section_id: str
    title: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SldV2EquipmentRow:
    item: str
    spec: str


@dataclass(frozen=True)
class SldV2LayoutBox:
    node_id: str
    node_type: str
    section_id: str
    x: float
    y: float
    width: float
    height: float
    text_lines: tuple[str, ...] = ()
    feeder_index: int | None = None
    dc_block_index: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SldV2PortAnchor:
    node_id: str
    port_id: str
    x: float
    y: float
    side: str
    voltage_domain: str
    feeder_index: int | None = None
    dc_block_index: int | None = None


@dataclass(frozen=True)
class SldV2LayoutConnector:
    edge_id: str
    edge_type: str
    source_node_id: str
    source_port_id: str
    target_node_id: str
    target_port_id: str
    points: tuple[tuple[float, float], ...]
    voltage_domain: str
    feeder_index: int | None = None
    dc_block_index: int | None = None


@dataclass(frozen=True)
class SldV2LayoutPlan:
    width: int
    height: int
    theme: str
    sections: tuple[SldV2LayoutSection, ...]
    equipment_rows: tuple[SldV2EquipmentRow, ...]
    boxes: tuple[SldV2LayoutBox, ...]
    port_anchors: tuple[SldV2PortAnchor, ...]
    connectors: tuple[SldV2LayoutConnector, ...]


def _node_by_type(graph: SldEngineeringV2Graph, node_type: str) -> SldV2Node:
    nodes = [node for node in graph.nodes if node.node_type == node_type]
    if len(nodes) != 1:
        raise ValueError(f"engineering_v2 layout requires exactly one {node_type} node")
    return nodes[0]


def _nodes_by_type(graph: SldEngineeringV2Graph, node_type: str) -> list[SldV2Node]:
    return sorted(
        [node for node in graph.nodes if node.node_type == node_type],
        key=lambda node: (node.feeder_index or 0, node.dc_block_index or 0, node.node_id),
    )


def _slot_centers(x1: float, x2: float, count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [(x1 + x2) / 2.0]
    step = (x2 - x1) / float(count - 1)
    return [x1 + index * step for index in range(count)]


def _local_dc_block_position(
    center_x: float,
    local_block_index: int,
    local_block_count: int,
    base_y: float,
) -> tuple[float, float, float, float]:
    """Place multiple DC blocks below one PCS without stacking them on top of each other."""
    if local_block_count > 4:
        raise ValueError("engineering_v2 layout supports up to 4 DC blocks per feeder in explicit block mode")
    width = 128.0 if local_block_count == 1 else 112.0
    height = 58.0 if local_block_count == 1 else 50.0
    gap_x = 20.0
    gap_y = 10.0
    columns = 1 if local_block_count == 1 else 2
    zero_based = local_block_index - 1
    column = zero_based % columns
    row = zero_based // columns
    total_width = columns * width + (columns - 1) * gap_x
    x = center_x - total_width / 2.0 + column * (width + gap_x)
    y = base_y + row * (height + gap_y)
    return x, y, width, height


def _side_anchor(box: SldV2LayoutBox, side: str) -> tuple[float, float]:
    if side == "top":
        return (box.x + box.width / 2.0, box.y)
    if side == "bottom":
        return (box.x + box.width / 2.0, box.y + box.height)
    if side == "left":
        return (box.x, box.y + box.height / 2.0)
    if side == "right":
        return (box.x + box.width, box.y + box.height / 2.0)
    return (box.x + box.width / 2.0, box.y + box.height / 2.0)


def _route(start: tuple[float, float], end: tuple[float, float]) -> tuple[tuple[float, float], ...]:
    if abs(start[0] - end[0]) < 1e-6 or abs(start[1] - end[1]) < 1e-6:
        return (start, end)
    mid_y = (start[1] + end[1]) / 2.0
    return (start, (start[0], mid_y), (end[0], mid_y), end)


def _contains(section: SldV2LayoutSection, box: SldV2LayoutBox) -> bool:
    return (
        box.x >= section.x
        and box.y >= section.y
        and box.x + box.width <= section.x + section.width
        and box.y + box.height <= section.y + section.height
    )


def _equipment_rows(graph: SldEngineeringV2Graph) -> tuple[SldV2EquipmentRow, ...]:
    summary = graph.summary
    ratings = graph.equipment_ratings
    allocation = ", ".join(f"F{index}={count}" for index, count in enumerate(summary.dc_blocks_per_feeder, start=1))
    transformer = (
        f"{summary.mv_voltage_kv:.1f}/{summary.lv_voltage_v_ll / 1000.0:.3f} kV, "
        f"{summary.transformer_rating_mva:.1f} MVA, {summary.transformer_vector_group}, "
        f"Uk={summary.transformer_uk_percent:.1f}%"
    )
    if ratings.transformer_cooling:
        transformer += f", {ratings.transformer_cooling}"

    def required_spec(field_name: str, value: str | None) -> str:
        text = str(value or "").strip()
        if not text or text.lower() in {"tbd", "n/a", "na", "none"}:
            return f"MISSING: {field_name}"
        return text

    pcs_ratings = sorted({round(float(value), 3) for value in summary.pcs_rating_kw_list})
    frequency = f", {summary.project_frequency_hz:.0f} Hz" if summary.project_frequency_hz else ""
    if len(pcs_ratings) == 1:
        pcs_spec = (
            f"{summary.pcs_count} x {pcs_ratings[0]:.0f} kW @ AC {summary.lv_voltage_v_ll:.0f} V"
            f"{frequency}, DC {summary.dc_block_voltage_v:.0f} V"
        )
    else:
        pcs_spec = (
            f"{summary.pcs_count} PCS @ {summary.lv_voltage_v_ll:.0f} V; "
            + ", ".join(f"F{index}={rating:.0f} kW" for index, rating in enumerate(summary.pcs_rating_kw_list, start=1))
        )

    return (
        SldV2EquipmentRow("MV System", f"{summary.mv_voltage_kv:.1f} kV"),
        SldV2EquipmentRow(
            "MV Switchgear / RMU",
            f"{ratings.rmu.rated_kv:.0f} kV, {ratings.rmu.rated_a:.0f} A, {ratings.rmu.short_circuit_ka_3s:.1f} kA/3s",
        ),
        SldV2EquipmentRow(
            "MV CT",
            f"{ratings.rmu.ct_ratio}, {ratings.rmu.ct_class}, {ratings.rmu.ct_va:.0f} VA",
        ),
        SldV2EquipmentRow("MV Cable", required_spec("MV cable spec", ratings.cables.mv_cable_spec)),
        SldV2EquipmentRow("Transformer", transformer),
        SldV2EquipmentRow("LV Cable", required_spec("LV cable spec", ratings.cables.lv_cable_spec)),
        SldV2EquipmentRow(
            "LV Busbar",
            f"{summary.lv_voltage_v_ll:.0f} V, {ratings.lv_busbar.rated_a:.0f} A, {ratings.lv_busbar.short_circuit_ka:.1f} kA",
        ),
        SldV2EquipmentRow("PCS", pcs_spec),
        SldV2EquipmentRow("DC Interface", ratings.dc_fuse.fuse_spec),
        SldV2EquipmentRow("DC Cable", required_spec("DC cable spec", ratings.cables.dc_cable_spec)),
        SldV2EquipmentRow("Battery Storage Bank", f"{summary.dc_blocks_total_in_group} x {summary.dc_block_energy_mwh:.3f} MWh"),
        SldV2EquipmentRow("DC Block Allocation", allocation),
        SldV2EquipmentRow("BESS Cell", required_spec("BESS cell spec", ratings.battery_cell_spec)),
    )


def build_sld_engineering_v2_layout_plan(
    graph: SldEngineeringV2Graph,
    *,
    theme: str | None = None,
) -> SldV2LayoutPlan:
    width = 1780
    height = 900
    theme = theme or graph.summary.theme

    equipment_section = SldV2LayoutSection("equipment_list", "Equipment List", 40.0, 40.0, 420.0, 330.0)
    ac_section = SldV2LayoutSection("ac_block", "PCS&MVT SKID (AC Block)", 495.0, 40.0, 1245.0, 485.0)
    battery_section = SldV2LayoutSection("battery_bank", "Battery Storage Bank", 495.0, 555.0, 1245.0, 285.0)
    sections = (equipment_section, ac_section, battery_section)
    section_lookup = {section.section_id: section for section in sections}

    summary = graph.summary
    feeder_count = summary.feeder_count
    feeder_centers = _slot_centers(ac_section.x + 220.0, ac_section.x + ac_section.width - 220.0, feeder_count)
    feeder_center_by_index = {index: center for index, center in enumerate(feeder_centers, start=1)}

    ring_in_terminal = _node_by_type(graph, "mv_ring_in_terminal")
    ring_out_terminal = _node_by_type(graph, "mv_ring_out_terminal")
    rmu_switchgear = _node_by_type(graph, "rmu_switchgear")
    ring_in_bay = _node_by_type(graph, "rmu_ring_in_bay")
    tx_feeder_bay = _node_by_type(graph, "rmu_transformer_feeder_bay")
    ring_out_bay = _node_by_type(graph, "rmu_ring_out_bay")
    transformer = _node_by_type(graph, "transformer")
    lv_busbar = _node_by_type(graph, "lv_busbar")

    rmu_x = ac_section.x + 312.0
    rmu_y = ac_section.y + 54.0
    rmu_w = 620.0
    rmu_h = 96.0
    bay_w = rmu_w / 3.0
    bay_y = rmu_y + 28.0
    bay_h = 58.0
    ring_in_x = rmu_x
    tx_bay_x = rmu_x + bay_w
    ring_out_x = rmu_x + bay_w * 2.0
    tx_center_x = tx_bay_x + bay_w / 2.0

    boxes: list[SldV2LayoutBox] = [
        SldV2LayoutBox(
            node_id=ring_in_terminal.node_id,
            node_type=ring_in_terminal.node_type,
            section_id="ac_block",
            x=ring_in_x + bay_w / 2.0 - 24.0,
            y=ac_section.y + 18.0,
            width=48.0,
            height=24.0,
            text_lines=("Ring In",),
        ),
        SldV2LayoutBox(
            node_id=ring_out_terminal.node_id,
            node_type=ring_out_terminal.node_type,
            section_id="ac_block",
            x=ring_out_x + bay_w / 2.0 - 24.0,
            y=ac_section.y + 18.0,
            width=48.0,
            height=24.0,
            text_lines=("Ring Out",),
        ),
        SldV2LayoutBox(
            node_id=rmu_switchgear.node_id,
            node_type=rmu_switchgear.node_type,
            section_id="ac_block",
            x=rmu_x,
            y=rmu_y,
            width=rmu_w,
            height=rmu_h,
            text_lines=("RMU / MV Switchgear",),
        ),
        SldV2LayoutBox(
            node_id=ring_in_bay.node_id,
            node_type=ring_in_bay.node_type,
            section_id="ac_block",
            x=ring_in_x + 8.0,
            y=bay_y,
            width=bay_w - 16.0,
            height=bay_h,
            text_lines=("Ring In",),
        ),
        SldV2LayoutBox(
            node_id=tx_feeder_bay.node_id,
            node_type=tx_feeder_bay.node_type,
            section_id="ac_block",
            x=tx_bay_x + 8.0,
            y=bay_y,
            width=bay_w - 16.0,
            height=bay_h,
            text_lines=("Transformer Feeder",),
        ),
        SldV2LayoutBox(
            node_id=ring_out_bay.node_id,
            node_type=ring_out_bay.node_type,
            section_id="ac_block",
            x=ring_out_x + 8.0,
            y=bay_y,
            width=bay_w - 16.0,
            height=bay_h,
            text_lines=("Ring Out",),
        ),
        SldV2LayoutBox(
            node_id=transformer.node_id,
            node_type=transformer.node_type,
            section_id="ac_block",
            x=tx_center_x - 46.0,
            y=ac_section.y + 210.0,
            width=92.0,
            height=92.0,
            text_lines=(
                "Transformer",
                f"{summary.mv_voltage_kv:.1f}/{summary.lv_voltage_v_ll / 1000.0:.3f} kV",
                f"{summary.transformer_rating_mva:.1f} MVA",
                f"{summary.transformer_vector_group}, Uk={summary.transformer_uk_percent:.1f}%",
                *((str(graph.equipment_ratings.transformer_cooling),) if graph.equipment_ratings.transformer_cooling else ()),
            ),
        ),
        SldV2LayoutBox(
            node_id=lv_busbar.node_id,
            node_type=lv_busbar.node_type,
            section_id="ac_block",
            x=ac_section.x + 80.0,
            y=ac_section.y + 330.0,
            width=ac_section.width - 160.0,
            height=18.0,
            text_lines=(f"LV Busbar {summary.lv_voltage_v_ll:.0f} V",),
        ),
    ]

    for node in _nodes_by_type(graph, "lv_feeder"):
        center_x = feeder_center_by_index[int(node.feeder_index or 0)]
        boxes.append(
            SldV2LayoutBox(
                node_id=node.node_id,
                node_type=node.node_type,
                section_id="ac_block",
                x=center_x - 9.0,
                y=ac_section.y + 356.0,
                width=18.0,
                height=42.0,
                text_lines=(f"F{node.feeder_index}",),
                feeder_index=node.feeder_index,
            )
        )

    for node in _nodes_by_type(graph, "pcs"):
        center_x = feeder_center_by_index[int(node.feeder_index or 0)]
        boxes.append(
            SldV2LayoutBox(
                node_id=node.node_id,
                node_type=node.node_type,
                section_id="ac_block",
                x=center_x - 60.0,
                y=ac_section.y + 390.0,
                width=120.0,
                height=72.0,
                text_lines=(node.display_name, f"{node.attributes.get('pcs_rating_kw', 0):.0f} kW"),
                feeder_index=node.feeder_index,
                attributes=dict(node.attributes),
            )
        )

    for node in _nodes_by_type(graph, "dc_interface"):
        center_x = feeder_center_by_index[int(node.feeder_index or 0)]
        boxes.append(
            SldV2LayoutBox(
                node_id=node.node_id,
                node_type=node.node_type,
                section_id="battery_bank",
                x=center_x - 68.0,
                y=battery_section.y + 92.0,
                width=136.0,
                height=42.0,
                text_lines=("DC Isolator/Fuse", f"F{node.feeder_index}"),
                feeder_index=node.feeder_index,
                attributes=dict(node.attributes),
            )
        )

    dc_blocks_by_feeder: dict[int, list[SldV2Node]] = {}
    for node in _nodes_by_type(graph, "dc_block"):
        dc_blocks_by_feeder.setdefault(int(node.feeder_index or 0), []).append(node)

    for feeder_index, nodes in dc_blocks_by_feeder.items():
        nodes = sorted(nodes, key=lambda item: (item.attributes.get("local_block_index", 0), item.dc_block_index or 0))
        center_x = feeder_center_by_index[int(feeder_index)]
        local_count = len(nodes)
        for local_index, node in enumerate(nodes, start=1):
            x, y, block_width, block_height = _local_dc_block_position(
                center_x,
                local_index,
                local_count,
                battery_section.y + 186.0,
            )
            boxes.append(
                SldV2LayoutBox(
                    node_id=node.node_id,
                    node_type=node.node_type,
                    section_id="battery_bank",
                    x=x,
                    y=y,
                    width=block_width,
                    height=block_height,
                    text_lines=(node.display_name, f"{summary.dc_block_energy_mwh:.3f} MWh"),
                    feeder_index=node.feeder_index,
                    dc_block_index=node.dc_block_index,
                    attributes=dict(node.attributes),
                )
            )

    box_lookup = {box.node_id: box for box in boxes}
    for box in boxes:
        if not _contains(section_lookup[box.section_id], box):
            raise ValueError(f"engineering_v2 layout box crosses section boundary: {box.node_id}")

    custom_port_points: dict[tuple[str, str], tuple[float, float]] = {
        (rmu_switchgear.node_id, "ring_in_bus_port"): (ring_in_x + bay_w / 2.0, rmu_y + rmu_h * 0.62),
        (rmu_switchgear.node_id, "transformer_feeder_bus_port"): (tx_center_x, rmu_y + rmu_h * 0.62),
        (rmu_switchgear.node_id, "ring_out_bus_port"): (ring_out_x + bay_w / 2.0, rmu_y + rmu_h * 0.62),
    }
    lv_box = box_lookup[lv_busbar.node_id]
    tx_box = box_lookup[transformer.node_id]
    custom_port_points[(lv_busbar.node_id, "transformer_port")] = (tx_box.x + tx_box.width / 2.0, lv_box.y)
    for feeder_index, center_x in feeder_center_by_index.items():
        custom_port_points[(lv_busbar.node_id, f"feeder_F{feeder_index:02d}_port")] = (center_x, lv_box.y + lv_box.height)

    anchors: list[SldV2PortAnchor] = []
    for node in graph.nodes:
        box = box_lookup[node.node_id]
        for port in node.ports:
            point = custom_port_points.get((node.node_id, port.port_id))
            if point is None:
                point = _side_anchor(box, port.side)
            anchors.append(
                SldV2PortAnchor(
                    node_id=node.node_id,
                    port_id=port.port_id,
                    x=point[0],
                    y=point[1],
                    side=port.side,
                    voltage_domain=port.voltage_domain,
                    feeder_index=port.feeder_index,
                    dc_block_index=port.dc_block_index,
                )
            )

    anchor_lookup = {(anchor.node_id, anchor.port_id): anchor for anchor in anchors}
    connectors: list[SldV2LayoutConnector] = []
    for edge in graph.edges:
        source = anchor_lookup[(edge.source_node_id, edge.source_port_id)]
        target = anchor_lookup[(edge.target_node_id, edge.target_port_id)]
        connectors.append(
            SldV2LayoutConnector(
                edge_id=edge.edge_id,
                edge_type=edge.edge_type,
                source_node_id=edge.source_node_id,
                source_port_id=edge.source_port_id,
                target_node_id=edge.target_node_id,
                target_port_id=edge.target_port_id,
                points=_route((source.x, source.y), (target.x, target.y)),
                voltage_domain=source.voltage_domain,
                feeder_index=edge.feeder_index,
                dc_block_index=edge.dc_block_index,
            )
        )

    return SldV2LayoutPlan(
        width=width,
        height=height,
        theme=theme,
        sections=sections,
        equipment_rows=_equipment_rows(graph),
        boxes=tuple(boxes),
        port_anchors=tuple(anchors),
        connectors=tuple(connectors),
    )
