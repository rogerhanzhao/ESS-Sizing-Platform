from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from calb_sizing_tool.schemas.sld_topology import SldTopology


LayoutProfileId = Literal["engineering_readable", "compact"]


@dataclass(frozen=True)
class SldLayoutPanelRow:
    item: str
    spec: str


@dataclass(frozen=True)
class SldLayoutPanel:
    panel_id: str
    title: str
    x: float
    y: float
    width: float
    height: float
    rows: tuple[SldLayoutPanelRow, ...] = ()


@dataclass(frozen=True)
class SldLayoutSymbol:
    symbol_id: str
    symbol_type: str
    x: float
    y: float
    width: float = 0.0
    height: float = 0.0
    text_lines: tuple[str, ...] = ()
    anchor_node_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SldLayoutConnector:
    connector_id: str
    points: tuple[tuple[float, float], ...]
    style: str = "thin"
    label: str | None = None


@dataclass(frozen=True)
class SldLayoutPlan:
    width: int
    height: int
    theme: str
    layout_profile: LayoutProfileId
    draw_summary: bool
    panels: tuple[SldLayoutPanel, ...] = ()
    symbols: tuple[SldLayoutSymbol, ...] = ()
    connectors: tuple[SldLayoutConnector, ...] = ()
    summary_lines: tuple[str, ...] = ()


def _fmt_float(value: float, suffix: str, digits: int = 1) -> str:
    return f"{float(value):.{digits}f} {suffix}"


def _fmt_int(value: int, suffix: str) -> str:
    return f"{int(value)} {suffix}"


def _equipment_rows(topology: SldTopology) -> tuple[SldLayoutPanelRow, ...]:
    summary = topology.summary
    equipment = topology.equipment_ratings
    allocation = ", ".join(
        f"F{index}={count}" for index, count in enumerate(summary.dc_blocks_per_feeder, start=1)
    ) or "TBD"
    transformer_bits = [
        _fmt_float(summary.transformer_rating_mva, "MVA"),
        f"{summary.transformer_vector_group}",
        f"Uk={summary.transformer_uk_percent:.1f}%",
    ]
    if equipment.transformer_cooling:
        transformer_bits.append(equipment.transformer_cooling)
    return (
        SldLayoutPanelRow("MV System", f"{summary.mv_voltage_kv:.1f} kV"),
        SldLayoutPanelRow(
            "RMU",
            f"{equipment.rmu.rated_kv:.0f} kV, {equipment.rmu.rated_a:.0f} A, {equipment.rmu.short_circuit_ka_3s:.1f} kA/3s",
        ),
        SldLayoutPanelRow("Transformer", ", ".join(transformer_bits)),
        SldLayoutPanelRow(
            "LV Busbar",
            f"{equipment.lv_busbar.rated_a:.0f} A, {equipment.lv_busbar.short_circuit_ka:.1f} kA",
        ),
        SldLayoutPanelRow(
            "PCS",
            f"{summary.pcs_count} x {summary.pcs_rating_kw_list[0]:.0f} kW @ {summary.lv_voltage_v_ll:.0f} V",
        ),
        SldLayoutPanelRow(
            "Battery Storage Bank",
            f"{summary.dc_blocks_total_in_group} x {summary.dc_block_energy_mwh:.3f} MWh",
        ),
        SldLayoutPanelRow("DC Block Allocation", allocation),
    )


def _summary_lines(topology: SldTopology) -> tuple[str, ...]:
    summary = topology.summary
    allocation = ", ".join(
        f"F{index}={count}" for index, count in enumerate(summary.dc_blocks_per_feeder, start=1)
    ) or "TBD"
    return (
        f"Scenario: {topology.scenario_id}",
        f"PCS count: {summary.pcs_count}",
        f"DC blocks: {summary.dc_blocks_total_in_group} x {summary.dc_block_energy_mwh:.3f} MWh",
        f"Allocation: {allocation}",
    )


def _profile_config(layout_profile: LayoutProfileId) -> dict[str, float]:
    if layout_profile == "compact":
        return {
            "width": 1680,
            "panel_width": 360.0,
            "ac_height": 320.0,
            "battery_height": 220.0,
            "pcs_width": 92.0,
            "pcs_height": 68.0,
            "dc_block_width": 92.0,
            "dc_block_height": 92.0,
            "busbar_gap": 56.0,
        }
    return {
        "width": 1780,
        "panel_width": 420.0,
        "ac_height": 380.0,
        "battery_height": 260.0,
        "pcs_width": 118.0,
        "pcs_height": 74.0,
        "dc_block_width": 126.0,
        "dc_block_height": 56.0,
        "busbar_gap": 72.0,
    }


def build_sld_layout_plan(
    topology: SldTopology,
    *,
    layout_profile: LayoutProfileId,
    theme: str,
) -> SldLayoutPlan:
    summary = topology.summary
    config = _profile_config(layout_profile)
    panel_rows = _equipment_rows(topology)
    summary_lines = _summary_lines(topology)

    width = int(config["width"])
    margin = 40.0
    panel_x = margin
    panel_y = 40.0
    panel_width = config["panel_width"]
    panel_row_height = 34.0
    panel_height = 58.0 + panel_row_height * len(panel_rows)

    diagram_x = panel_x + panel_width + 36.0
    diagram_width = width - diagram_x - margin
    ac_frame_x = diagram_x
    ac_frame_y = 40.0
    ac_frame_width = diagram_width
    ac_frame_height = config["ac_height"]

    battery_frame_x = diagram_x
    battery_frame_y = ac_frame_y + ac_frame_height + 48.0
    battery_frame_width = diagram_width
    battery_frame_height = config["battery_height"]

    summary_box_height = 120.0 if summary.draw_summary else 0.0
    height = int(battery_frame_y + battery_frame_height + summary_box_height + 80.0)

    symbols: list[SldLayoutSymbol] = [
        SldLayoutSymbol(
            symbol_id="ac-frame",
            symbol_type="section_frame",
            x=ac_frame_x,
            y=ac_frame_y,
            width=ac_frame_width,
            height=ac_frame_height,
            text_lines=("PCS&MVT SKID (AC Block)",),
            meta={"frame_style": "dash"},
        ),
        SldLayoutSymbol(
            symbol_id="battery-frame",
            symbol_type="section_frame",
            x=battery_frame_x,
            y=battery_frame_y,
            width=battery_frame_width,
            height=battery_frame_height,
            text_lines=("Battery Storage Bank",),
            meta={"frame_style": "dash"},
        ),
    ]
    connectors: list[SldLayoutConnector] = []

    mv_bus_y = ac_frame_y + 72.0
    mv_bus_x1 = ac_frame_x + 110.0
    mv_bus_x2 = ac_frame_x + ac_frame_width - 110.0
    symbols.append(
        SldLayoutSymbol(
            symbol_id="mv-busbar",
            symbol_type="busbar_horizontal",
            x=mv_bus_x1,
            y=mv_bus_y,
            width=mv_bus_x2 - mv_bus_x1,
            text_lines=("MV BUS",),
            anchor_node_id=next(node.node_id for node in topology.nodes if node.node_type == "mv_bus"),
        )
    )

    symbols.append(
        SldLayoutSymbol(
            symbol_id="mv-feeder-left",
            symbol_type="external_feeder_arrow",
            x=mv_bus_x1,
            y=ac_frame_y + 18.0,
            height=44.0,
            text_lines=(topology.labels.to_switchgear,),
        )
    )
    symbols.append(
        SldLayoutSymbol(
            symbol_id="mv-feeder-right",
            symbol_type="external_feeder_arrow",
            x=mv_bus_x2,
            y=ac_frame_y + 18.0,
            height=44.0,
            text_lines=(topology.labels.to_other_rmu,),
            meta={"align": "right"},
        )
    )

    rmu_node = next(node for node in topology.nodes if node.node_type == "rmu")
    tx_node = next(node for node in topology.nodes if node.node_type == "transformer")
    lv_node = next(node for node in topology.nodes if node.node_type == "lv_busbar")

    rmu_x = ac_frame_x + ac_frame_width / 2
    rmu_y = mv_bus_y + 36.0
    symbols.append(
        SldLayoutSymbol(
            symbol_id="rmu",
            symbol_type="rmu",
            x=rmu_x,
            y=rmu_y,
            width=92.0,
            height=58.0,
            text_lines=("RMU", f"{topology.equipment_ratings.rmu.rated_kv:.0f} kV"),
            anchor_node_id=rmu_node.node_id,
        )
    )

    tx_x = ac_frame_x + ac_frame_width / 2
    tx_y = rmu_y + 122.0
    symbols.append(
        SldLayoutSymbol(
            symbol_id="transformer",
            symbol_type="transformer",
            x=tx_x,
            y=tx_y,
            width=128.0,
            height=62.0,
            text_lines=(
                "Transformer",
                f"{summary.transformer_rating_mva:.1f} MVA",
                f"{summary.transformer_vector_group}, Uk={summary.transformer_uk_percent:.1f}%",
            ),
            anchor_node_id=tx_node.node_id,
        )
    )

    lv_bus_y = tx_y + 94.0
    lv_bus_x1 = ac_frame_x + 80.0
    lv_bus_x2 = ac_frame_x + ac_frame_width - 80.0
    symbols.append(
        SldLayoutSymbol(
            symbol_id="lv-busbar",
            symbol_type="busbar_horizontal",
            x=lv_bus_x1,
            y=lv_bus_y,
            width=lv_bus_x2 - lv_bus_x1,
            text_lines=("LV Busbar",),
            anchor_node_id=lv_node.node_id,
        )
    )

    pcs_nodes = sorted([node for node in topology.nodes if node.node_type == "pcs"], key=lambda item: item.feeder_index or 0)
    dc_bus_nodes = sorted(
        [node for node in topology.nodes if node.node_type == "dc_busbar"],
        key=lambda item: item.feeder_index or 0,
    )
    dc_block_nodes = sorted(
        [node for node in topology.nodes if node.node_type == "dc_block"],
        key=lambda item: (item.feeder_index or 0, item.dc_block_index or 0),
    )

    pcs_count = max(1, len(pcs_nodes))
    slot_width = (lv_bus_x2 - lv_bus_x1) / pcs_count
    pcs_y = lv_bus_y + 54.0

    busbar_pair_gap = config["busbar_gap"]
    battery_grid_top = battery_frame_y + 72.0
    battery_slots = max(summary.dc_blocks_total_in_group, 1)
    battery_slot_width = battery_frame_width / max(battery_slots, 3)

    dc_block_positions: dict[str, tuple[float, float]] = {}
    for index, dc_block in enumerate(dc_block_nodes):
        block_x = battery_frame_x + 30.0 + (index % max(1, min(3, battery_slots))) * (
            config["dc_block_width"] + 24.0
        )
        block_y = battery_grid_top + (index // max(1, min(3, battery_slots))) * (
            config["dc_block_height"] + 18.0
        )
        dc_block_positions[dc_block.node_id] = (block_x, block_y)
        symbols.append(
            SldLayoutSymbol(
                symbol_id=f"dc-block-{index + 1}",
                symbol_type="dc_block",
                x=block_x,
                y=block_y,
                width=config["dc_block_width"],
                height=config["dc_block_height"],
                text_lines=(
                    f"DC Block #{index + 1}",
                    f"{summary.dc_block_energy_mwh:.3f} MWh",
                ),
                anchor_node_id=dc_block.node_id,
                meta={"feeder_index": dc_block.feeder_index},
            )
        )

    for index, pcs_node in enumerate(pcs_nodes):
        center_x = lv_bus_x1 + slot_width * (index + 0.5)
        pcs_x = center_x - config["pcs_width"] / 2
        symbols.append(
            SldLayoutSymbol(
                symbol_id=f"pcs-{index + 1}",
                symbol_type="pcs",
                x=pcs_x,
                y=pcs_y,
                width=config["pcs_width"],
                height=config["pcs_height"],
                text_lines=(
                    f"PCS-{index + 1}",
                    f"{summary.pcs_rating_kw_list[index]:.0f} kW",
                ),
                anchor_node_id=pcs_node.node_id,
                meta={"feeder_index": pcs_node.feeder_index},
            )
        )

        dc_bus_y = pcs_y + config["pcs_height"] + 36.0
        dc_bus_node = dc_bus_nodes[index]
        if layout_profile == "compact":
            symbols.append(
                SldLayoutSymbol(
                    symbol_id=f"dc-busbar-{index + 1}",
                    symbol_type="dc_busbar_single",
                    x=center_x - slot_width * 0.26,
                    y=dc_bus_y,
                    width=slot_width * 0.52,
                    text_lines=("DC BUSBAR",),
                    anchor_node_id=dc_bus_node.node_id,
                    meta={"feeder_index": dc_bus_node.feeder_index},
                )
            )
        else:
            symbols.append(
                SldLayoutSymbol(
                    symbol_id=f"dc-busbar-{index + 1}",
                    symbol_type="dc_busbar_pair",
                    x=center_x - slot_width * 0.30,
                    y=dc_bus_y,
                    width=slot_width * 0.60,
                    height=busbar_pair_gap,
                    text_lines=("DC BUSBAR A", "DC BUSBAR B"),
                    anchor_node_id=dc_bus_node.node_id,
                    meta={"feeder_index": dc_bus_node.feeder_index},
                )
            )

    symbol_anchor = {symbol.anchor_node_id: symbol for symbol in symbols if symbol.anchor_node_id}

    connectors.append(
        SldLayoutConnector(
            connector_id="mv-to-rmu",
            points=((rmu_x, mv_bus_y), (rmu_x, rmu_y)),
        )
    )
    connectors.append(
        SldLayoutConnector(
            connector_id="rmu-to-transformer",
            points=((rmu_x, rmu_y + 58.0), (tx_x, tx_y)),
        )
    )
    connectors.append(
        SldLayoutConnector(
            connector_id="transformer-to-lv",
            points=((tx_x, tx_y + 62.0), (tx_x, lv_bus_y)),
            style="thick",
        )
    )

    for edge in topology.edges:
        source_symbol = symbol_anchor.get(edge.source_node_id)
        target_symbol = symbol_anchor.get(edge.target_node_id)
        if source_symbol is None or target_symbol is None:
            continue

        if edge.edge_type == "lv_busbar_to_pcs":
            connectors.append(
                SldLayoutConnector(
                    connector_id=edge.edge_id,
                    points=(
                        (source_symbol.x + source_symbol.width / 2, source_symbol.y),
                        (target_symbol.x + target_symbol.width / 2, target_symbol.y),
                    ),
                )
            )
        elif edge.edge_type == "pcs_to_dc_busbar":
            connectors.append(
                SldLayoutConnector(
                    connector_id=edge.edge_id,
                    points=(
                        (source_symbol.x + source_symbol.width / 2, source_symbol.y + source_symbol.height),
                        (target_symbol.x + target_symbol.width / 2, target_symbol.y),
                    ),
                )
            )
        elif edge.edge_type == "dc_busbar_to_dc_block":
            connectors.append(
                SldLayoutConnector(
                    connector_id=edge.edge_id,
                    points=(
                        (source_symbol.x + source_symbol.width / 2, source_symbol.y + max(2.0, source_symbol.height)),
                        (target_symbol.x + target_symbol.width / 2, target_symbol.y),
                    ),
                )
            )

    panel = SldLayoutPanel(
        panel_id="equipment-panel",
        title="Equipment List",
        x=panel_x,
        y=panel_y,
        width=panel_width,
        height=panel_height,
        rows=panel_rows,
    )

    return SldLayoutPlan(
        width=width,
        height=height,
        theme=theme,
        layout_profile=layout_profile,
        draw_summary=summary.draw_summary,
        panels=(panel,),
        symbols=tuple(symbols),
        connectors=tuple(connectors),
        summary_lines=summary_lines,
    )
