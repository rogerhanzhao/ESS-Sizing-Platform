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


def _feeder_groups(graph, feeder_count: int) -> list[list[int]]:
    """Group feeders that share one DC Block into a tight cluster.

    Feeders wired to the same shared DC Block are drawn as an adjacent pair/cluster
    (so the shared container sits compactly beneath them); every other feeder is
    its own singleton group. Order is preserved left-to-right by first feeder.
    """
    assigned: set[int] = set()
    groups: list[list[int]] = []
    for node in _nodes_by_type(graph, "dc_block"):
        span = sorted(
            int(feeder) for feeder in (node.attributes.get("feeder_span") or [])
            if 1 <= int(feeder) <= feeder_count
        )
        if len(span) > 1 and not (set(span) & assigned):
            groups.append(span)
            assigned.update(span)
    for feeder_index in range(1, feeder_count + 1):
        if feeder_index not in assigned:
            groups.append([feeder_index])
            assigned.add(feeder_index)
    groups.sort(key=lambda group: group[0])
    return groups


# The PCS layout box is 120 wide (see the "pcs" boxes below), so two adjacent
# feeders must never be pitched closer than that plus a visible gap — otherwise
# the PCS symbols overlap.
_PCS_BOX_WIDTH = 120.0
_MIN_FEEDER_PITCH = _PCS_BOX_WIDTH + 20.0


def _grouped_feeder_positions(
    groups: list[list[int]],
    *,
    intra_pitch: float = _MIN_FEEDER_PITCH,
    inter_pitch: float = 264.0,
    max_field_width: float = 1180.0,
) -> tuple[dict[int, float], float]:
    """Raw feeder positions (first feeder at 0): ``intra_pitch`` within a group,
    ``inter_pitch`` between groups, the whole field capped to ``max_field_width``
    so a many-feeder 1:1 station never grows without bound. Returns
    ``(positions, field_width)``; the caller anchors the field on the sheet."""
    intra_pitch = max(float(intra_pitch), _MIN_FEEDER_PITCH)
    inter_pitch = max(float(inter_pitch), _MIN_FEEDER_PITCH)
    positions: dict[int, float] = {}
    cursor = 0.0
    for group_index, group in enumerate(groups):
        if group_index > 0:
            cursor += inter_pitch
        for member_index, feeder_index in enumerate(group):
            if member_index > 0:
                cursor += intra_pitch
            positions[feeder_index] = cursor
    field_width = cursor
    if field_width > max_field_width and field_width > 0:
        # Never scale a pitch below the PCS box width + gap: shrinking the field
        # to fit a cap must not make the PCS symbols overlap. The sheet grows
        # instead (the canvas is content-adaptive). The floor is set by the
        # SMALLEST gap actually used, not by the default pitch constants.
        ordered = sorted(positions.values())
        gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b - a > 0]
        scale = max_field_width / field_width
        if gaps:
            scale = max(scale, _MIN_FEEDER_PITCH / min(gaps))
        if scale < 1.0:
            positions = {feeder: value * scale for feeder, value in positions.items()}
            field_width *= scale
    return positions, field_width


_DEFAULT_INTER_FEEDER_PITCH = 264.0
_RENDERED_SINGLE_DC_CONTAINER_WIDTH = 140.0
_RENDERED_MULTI_DC_CONTAINER_WIDTH = 120.0
_RENDERED_MULTI_DC_SPACING_BASE = 130.0
_RENDERED_MULTI_DC_SPACING_MAX = 150.0
_MULTI_DC_CLEAR_GAP = 22.0


def _local_dc_block_counts(graph, feeder_count: int) -> dict[int, int]:
    """Return dedicated DC Block counts by feeder for renderer-safe spacing.

    Shared DC Blocks span more than one feeder and are rendered as their own
    wide multi-port container, so they must not widen the dedicated per-feeder
    DC Block footprint calculated here.
    """
    counts = {feeder_index: 0 for feeder_index in range(1, feeder_count + 1)}
    for node in _nodes_by_type(graph, "dc_block"):
        feeder_span = [
            int(feeder)
            for feeder in (node.attributes.get("feeder_span") or [])
            if 1 <= int(feeder) <= feeder_count
        ]
        if len(feeder_span) > 1:
            continue
        feeder_index = feeder_span[0] if feeder_span else int(node.feeder_index or 0)
        if feeder_index in counts:
            counts[feeder_index] += 1
    return counts


def _local_dc_half_span(block_count: int) -> float:
    """Half-width of the rendered dedicated-DC footprint about its feeder."""
    if block_count <= 1:
        return _RENDERED_SINGLE_DC_CONTAINER_WIDTH / 2.0
    spacing = min(
        _RENDERED_MULTI_DC_SPACING_MAX,
        _RENDERED_MULTI_DC_SPACING_BASE + max(0, block_count - 2) * 18.0,
    )
    return spacing * (block_count - 1) / 2.0 + _RENDERED_MULTI_DC_CONTAINER_WIDTH / 2.0


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
    shared_spans = [
        (
            [int(fi) for fi in (node.attributes.get("feeder_span") or [])],
            int(node.attributes.get("output_circuit_count") or 1),
        )
        for node in graph.nodes
        if node.node_type == "dc_block" and node.attributes.get("feeder_span")
    ]
    if shared_spans:
        # Shared DC blocks: report which PCS feeders each block supplies
        # instead of a per-feeder count that would misread as dangling feeders.
        allocation = ", ".join(
            (
                f"DC{index}→F{span[0]}-F{span[-1]} ({outputs} outputs)"
                if len(span) > 1
                else f"DC{index}→F{span[0]} ({outputs} output)"
            )
            for index, (span, outputs) in enumerate(shared_spans, start=1)
        )
    else:
        allocation = ", ".join(f"F{index}={count}" for index, count in enumerate(summary.dc_blocks_per_feeder, start=1))
    transformer = (
        f"{summary.mv_voltage_kv:.1f}/{summary.lv_voltage_v_ll / 1000.0:.3f} kV, "
        f"{summary.transformer_rating_mva:.1f} MVA, {summary.transformer_vector_group}, "
        f"Uk={summary.transformer_uk_percent:.1f}%"
    )
    if summary.lv_winding_count > 1:
        transformer += (
            f", {summary.lv_winding_count + 1}-winding transformer "
            f"(1 MV primary + {summary.lv_winding_count} independent LV secondaries)"
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
    height = 1160
    theme = theme or graph.summary.theme

    equipment_section = SldV2LayoutSection("equipment_list", "Equipment List", 40.0, 40.0, 424.0, 860.0)
    equipment_right = equipment_section.x + equipment_section.width  # 464

    summary = graph.summary
    feeder_count = summary.feeder_count

    # --- Compact adaptive feeder field + canvas ---------------------------------
    # Feeders that share a DC Block cluster into a tight pair; groups are separated;
    # the whole field is placed just to the right of the equipment list, centred
    # under the transformer, and the sheet is sized to the content (a small station
    # is not padded out to a fixed huge canvas). Geometry only — the electrical
    # topology, feeder spans, ratings and AC sizing are unchanged.
    rmu_w = 620.0
    rmu_h = 96.0
    bay_w = rmu_w / 3.0
    feeder_groups = _feeder_groups(graph, feeder_count)
    local_dc_counts = _local_dc_block_counts(graph, feeder_count)
    max_local_dc_count = max(local_dc_counts.values(), default=0)
    local_dc_half_span = _local_dc_half_span(max_local_dc_count)
    inter_feeder_pitch = max(
        _DEFAULT_INTER_FEEDER_PITCH,
        2.0 * local_dc_half_span + _MULTI_DC_CLEAR_GAP,
    )
    # Preserve the compact, established single-DC layout (including the 8 PCS
    # sheet). Dedicated multi-DC feeders need a wider field so the renderer's
    # two-rack containers cannot be squeezed back into overlap by the cap.
    max_field_width = 1180.0
    if max_local_dc_count > 1:
        max_field_width = max(
            max_field_width,
            inter_feeder_pitch * max(0, len(feeder_groups) - 1)
            + 120.0 * sum(max(0, len(group) - 1) for group in feeder_groups),
        )
    raw_positions, field_width = _grouped_feeder_positions(
        feeder_groups,
        inter_pitch=inter_feeder_pitch,
        max_field_width=max_field_width,
    )
    # tx centre must keep the feeder field (incl. its ±100 LV-busbar overhang),
    # and the RMU (1.5 bays to its left), clear of the equipment-list panel.
    tx_center_x = max(field_width / 2.0 + equipment_right + 150.0,
                      equipment_right + 30.0 + 1.5 * bay_w)
    field_offset = tx_center_x - field_width / 2.0
    feeder_center_by_index = {fi: pos + field_offset for fi, pos in raw_positions.items()}

    # Narrowest gap between adjacent feeders — per-feeder boxes (DC interface,
    # fuse) must stay within it so they never overlap at tight cluster spacing.
    _sorted_centers = sorted(feeder_center_by_index.values())
    min_feeder_gap = min(
        (_sorted_centers[i + 1] - _sorted_centers[i] for i in range(len(_sorted_centers) - 1)),
        default=200.0,
    )

    rmu_x = tx_center_x - 1.5 * bay_w
    rmu_y = 40.0 + 54.0
    bay_y = rmu_y + 28.0
    bay_h = 58.0
    ring_in_x = rmu_x
    tx_bay_x = rmu_x + bay_w
    ring_out_x = rmu_x + bay_w * 2.0

    # Size the canvas to the content. The AC-BLOCK boundary drawn by the renderer
    # reaches max(rightmost feeder, ring-out centre) + ~126 (bus pad 90 + panel 20
    # + boundary 16), so the canvas must clear that or the dashed box gets clipped.
    ring_out_center = ring_out_x + bay_w / 2.0
    max_feeder_x = max(feeder_center_by_index.values(), default=tx_center_x)
    # A multi-DC feeder extends beyond the PCS centre by more than a single
    # container width. Keep the full rendered footprint inside the canvas.
    content_right = max(ring_out_center, max_feeder_x) + max(140.0, local_dc_half_span + 10.0)
    width = int(round(content_right + 24.0))

    ac_left = 470.0
    ac_span = width - ac_left - 12.0
    ac_section = SldV2LayoutSection("ac_block", "PCS&MVT SKID (AC Block)", ac_left, 40.0, ac_span, 570.0)
    battery_section = SldV2LayoutSection("battery_bank", "Battery Storage Bank", ac_left, 630.0, ac_span, 360.0)
    sections = (equipment_section, ac_section, battery_section)
    section_lookup = {section.section_id: section for section in sections}

    ring_in_terminal = _node_by_type(graph, "mv_ring_in_terminal")
    ring_out_terminal = _node_by_type(graph, "mv_ring_out_terminal")
    rmu_switchgear = _node_by_type(graph, "rmu_switchgear")
    ring_in_bay = _node_by_type(graph, "rmu_ring_in_bay")
    tx_feeder_bay = _node_by_type(graph, "rmu_transformer_feeder_bay")
    ring_out_bay = _node_by_type(graph, "rmu_ring_out_bay")
    transformer = _node_by_type(graph, "transformer")
    lv_busbars = _nodes_by_type(graph, "lv_busbar")

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
                *(
                    (
                        f"{summary.lv_winding_count + 1}-winding: 1 MV primary + "
                        f"{summary.lv_winding_count} independent LV secondaries",
                    )
                    if summary.lv_winding_count > 1
                    else ()
                ),
                *((str(graph.equipment_ratings.transformer_cooling),) if graph.equipment_ratings.transformer_cooling else ()),
            ),
            attributes={"lv_winding_count": summary.lv_winding_count},
        ),
    ]

    # Ordered winding spans (sorted by first feeder) so an independent LV
    # secondary busbar never overhangs into its neighbour's span. With a wide
    # feeder count (e.g. 8 PCS split 4+4) the fixed ±100 pad exceeds the
    # inter-feeder gap, so inner edges are clamped to the boundary midpoint.
    lv_busbar_pad = 100.0
    lv_busbar_gap_margin = 8.0
    lv_busbar_spans: list[tuple[SldV2Node, list[int]]] = []
    for lv_busbar in lv_busbars:
        feeder_span = sorted(
            int(feeder_index)
            for feeder_index in (lv_busbar.attributes.get("feeder_span") or [])
            if int(feeder_index) in feeder_center_by_index
        )
        if not feeder_span:
            raise ValueError(f"LV busbar has no assigned PCS feeder span: {lv_busbar.node_id}")
        lv_busbar_spans.append((lv_busbar, feeder_span))
    lv_busbar_spans.sort(key=lambda entry: entry[1][0])

    for span_index, (lv_busbar, feeder_span) in enumerate(lv_busbar_spans):
        left_center = feeder_center_by_index[feeder_span[0]]
        right_center = feeder_center_by_index[feeder_span[-1]]
        x1 = left_center - lv_busbar_pad
        x2 = right_center + lv_busbar_pad
        if span_index > 0:
            prev_right_center = feeder_center_by_index[lv_busbar_spans[span_index - 1][1][-1]]
            x1 = max(x1, (prev_right_center + left_center) / 2.0 + lv_busbar_gap_margin)
        if span_index < len(lv_busbar_spans) - 1:
            next_left_center = feeder_center_by_index[lv_busbar_spans[span_index + 1][1][0]]
            x2 = min(x2, (right_center + next_left_center) / 2.0 - lv_busbar_gap_margin)
        winding_index = int(lv_busbar.attributes.get("winding_index") or 1)
        boxes.append(
            SldV2LayoutBox(
                node_id=lv_busbar.node_id,
                node_type=lv_busbar.node_type,
                section_id="ac_block",
                x=x1,
                y=ac_section.y + 330.0,
                width=x2 - x1,
                height=18.0,
                text_lines=(f"LV-{chr(64 + winding_index)} bus / {summary.lv_voltage_v_ll:.0f} V",),
                attributes=dict(lv_busbar.attributes),
            )
        )

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

    dc_interface_w = min(136.0, max(60.0, min_feeder_gap - 14.0))
    for node in _nodes_by_type(graph, "dc_interface"):
        center_x = feeder_center_by_index[int(node.feeder_index or 0)]
        boxes.append(
            SldV2LayoutBox(
                node_id=node.node_id,
                node_type=node.node_type,
                section_id="battery_bank",
                x=center_x - dc_interface_w / 2.0,
                y=battery_section.y + 60.0,
                width=dc_interface_w,
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
            # A shared DC block (split across several PCS feeders through their
            # own fuses) is centred between the feeders it supplies.
            feeder_span = [int(fi) for fi in (node.attributes.get("feeder_span") or []) if int(fi) in feeder_center_by_index]
            node_center_x = (
                sum(feeder_center_by_index[fi] for fi in feeder_span) / len(feeder_span)
                if feeder_span
                else center_x
            )
            text_lines = [node.display_name, f"{summary.dc_block_energy_mwh:.3f} MWh"]
            if len(feeder_span) > 1:
                text_lines.append(f"Feeds F{feeder_span[0]}-F{feeder_span[-1]}")
            x, y, block_width, block_height = _local_dc_block_position(
                node_center_x,
                local_index,
                local_count,
                battery_section.y + 130.0,
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
                    text_lines=tuple(text_lines),
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
    for lv_busbar in lv_busbars:
        lv_box = box_lookup[lv_busbar.node_id]
        feeder_span = [
            int(feeder_index)
            for feeder_index in (lv_busbar.attributes.get("feeder_span") or [])
            if int(feeder_index) in feeder_center_by_index
        ]
        custom_port_points[(lv_busbar.node_id, "transformer_port")] = (
            lv_box.x + lv_box.width / 2.0,
            lv_box.y,
        )
        for feeder_index in feeder_span:
            custom_port_points[(lv_busbar.node_id, f"feeder_F{feeder_index:02d}_port")] = (
                feeder_center_by_index[feeder_index],
                lv_box.y + lv_box.height,
            )

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
