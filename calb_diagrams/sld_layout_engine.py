from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil
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


def _fmt_lv_kv(value_v: float) -> str:
    return f"{float(value_v) / 1000.0:.3f} kV"


def _equipment_rows(topology: SldTopology) -> tuple[SldLayoutPanelRow, ...]:
    summary = topology.summary
    equipment = topology.equipment_ratings
    allocation = ", ".join(
        f"F{index}={count}" for index, count in enumerate(summary.dc_blocks_per_feeder, start=1)
    ) or "TBD"
    transformer_bits = [
        f"{summary.mv_voltage_kv:.1f}/{_fmt_lv_kv(summary.lv_voltage_v_ll)}",
        _fmt_float(summary.transformer_rating_mva, "MVA"),
        f"{summary.transformer_vector_group}",
        f"Uk={summary.transformer_uk_percent:.1f}%",
    ]
    if equipment.transformer_cooling:
        transformer_bits.append(equipment.transformer_cooling)
    return (
        SldLayoutPanelRow("MV System", f"{summary.mv_voltage_kv:.1f} kV"),
        SldLayoutPanelRow(
            "MV Switchgear / RMU",
            f"{equipment.rmu.rated_kv:.0f} kV, {equipment.rmu.rated_a:.0f} A, {equipment.rmu.short_circuit_ka_3s:.1f} kA/3s",
        ),
        SldLayoutPanelRow("Transformer", ", ".join(transformer_bits)),
        SldLayoutPanelRow(
            "LV Busbar",
            f"{summary.lv_voltage_v_ll:.0f} V, {equipment.lv_busbar.rated_a:.0f} A, {equipment.lv_busbar.short_circuit_ka:.1f} kA",
        ),
        SldLayoutPanelRow(
            "PCS",
            f"{summary.pcs_count} x {summary.pcs_rating_kw_list[0]:.0f} kW @ {summary.lv_voltage_v_ll:.0f} V",
        ),
        SldLayoutPanelRow("DC Interface", equipment.dc_fuse.fuse_spec),
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
            "mv_switchgear_width": 500.0,
            "mv_switchgear_height": 82.0,
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
        "mv_switchgear_width": 620.0,
        "mv_switchgear_height": 88.0,
        "dc_block_width": 126.0,
        "dc_block_height": 56.0,
        "busbar_gap": 72.0,
    }


def _symbol_center_x(symbol: SldLayoutSymbol) -> float:
    if symbol.symbol_type in {"rmu", "transformer"}:
        return symbol.x
    return symbol.x + symbol.width / 2


def _symbol_top_y(symbol: SldLayoutSymbol) -> float:
    return symbol.y


def _symbol_bottom_y(symbol: SldLayoutSymbol) -> float:
    if symbol.symbol_type == "transformer":
        return symbol.y + max(symbol.height, 62.0)
    return symbol.y + symbol.height


def _orthogonal_points(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    bend_y: float,
) -> tuple[tuple[float, float], ...]:
    if abs(start[0] - end[0]) < 1e-6:
        return (start, end)
    return (start, (start[0], bend_y), (end[0], bend_y), end)


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

    mv_switchgear_width = min(config["mv_switchgear_width"], ac_frame_width - 180.0)
    mv_switchgear_height = config["mv_switchgear_height"]
    mv_switchgear_x = ac_frame_x + ac_frame_width / 2 - mv_switchgear_width / 2
    mv_switchgear_y = ac_frame_y + 54.0
    ring_in_x = mv_switchgear_x + mv_switchgear_width / 6.0
    transformer_feeder_x = mv_switchgear_x + mv_switchgear_width / 2.0
    ring_out_x = mv_switchgear_x + mv_switchgear_width * 5.0 / 6.0
    tx_x = transformer_feeder_x
    tx_y = mv_switchgear_y + mv_switchgear_height + 70.0
    lv_bus_y = tx_y + 104.0
    lv_bus_x1 = ac_frame_x + 80.0
    lv_bus_x2 = ac_frame_x + ac_frame_width - 80.0
    pcs_y = lv_bus_y + 54.0
    pcs_bottom_y = pcs_y + config["pcs_height"]

    ac_frame_height = max(config["ac_height"], pcs_bottom_y - ac_frame_y + 34.0)
    battery_frame_x = diagram_x
    battery_frame_y = ac_frame_y + ac_frame_height + 32.0
    battery_frame_width = diagram_width
    max_blocks_per_feeder = max(summary.dc_blocks_per_feeder or [1])
    max_grid_cols = 1 if max_blocks_per_feeder <= 4 else 2
    max_grid_rows = max(1, ceil(max_blocks_per_feeder / max_grid_cols))
    block_stack_height = (
        max_grid_rows * config["dc_block_height"]
        + max(0, max_grid_rows - 1) * 18.0
    )
    battery_frame_height = max(config["battery_height"], 132.0 + block_stack_height)

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
            meta={"frame_style": "dash", "title_align": "center"},
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

    ring_in_node = next(node for node in topology.nodes if node.node_type == "mv_ring_in")
    rmu_node = next(node for node in topology.nodes if node.node_type == "mv_switchgear")
    transformer_feeder_node = next(node for node in topology.nodes if node.node_type == "mv_transformer_feeder")
    ring_out_node = next(node for node in topology.nodes if node.node_type == "mv_ring_out")
    tx_node = next(node for node in topology.nodes if node.node_type == "transformer")
    lv_node = next(node for node in topology.nodes if node.node_type == "lv_busbar")

    symbols.append(
        SldLayoutSymbol(
            symbol_id="mv-switchgear",
            symbol_type="mv_switchgear",
            x=mv_switchgear_x,
            y=mv_switchgear_y,
            width=mv_switchgear_width,
            height=mv_switchgear_height,
            text_lines=(
                "RMU / MV Switchgear",
                "Ring In",
                "Transformer Feeder",
                "Ring Out",
                f"{topology.equipment_ratings.rmu.rated_kv:.0f} kV",
            ),
            anchor_node_id=rmu_node.node_id,
            meta={
                "ring_in_x": ring_in_x,
                "transformer_feeder_x": transformer_feeder_x,
                "ring_out_x": ring_out_x,
            },
        )
    )

    feeder_arrow_y = ac_frame_y + 18.0
    feeder_arrow_height = max(28.0, mv_switchgear_y - feeder_arrow_y - 6.0)
    symbols.append(
        SldLayoutSymbol(
            symbol_id="ring-in-feeder",
            symbol_type="external_feeder_arrow",
            x=ring_in_x,
            y=feeder_arrow_y,
            height=feeder_arrow_height + 6.0,
            text_lines=(topology.labels.to_switchgear,),
            anchor_node_id=ring_in_node.node_id,
        )
    )
    symbols.append(
        SldLayoutSymbol(
            symbol_id="ring-out-feeder",
            symbol_type="external_feeder_arrow",
            x=ring_out_x,
            y=feeder_arrow_y,
            height=feeder_arrow_height + 6.0,
            text_lines=(topology.labels.to_other_rmu,),
            anchor_node_id=ring_out_node.node_id,
            meta={"align": "right"},
        )
    )

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
                f"{summary.mv_voltage_kv:.1f}/{_fmt_lv_kv(summary.lv_voltage_v_ll)}",
                f"{summary.transformer_rating_mva:.1f} MVA",
                f"{summary.transformer_vector_group}, Uk={summary.transformer_uk_percent:.1f}%",
                *((topology.equipment_ratings.transformer_cooling,) if topology.equipment_ratings.transformer_cooling else ()),
            ),
            anchor_node_id=tx_node.node_id,
        )
    )

    symbols.append(
        SldLayoutSymbol(
            symbol_id="lv-busbar",
            symbol_type="busbar_horizontal",
            x=lv_bus_x1,
            y=lv_bus_y,
            width=lv_bus_x2 - lv_bus_x1,
            text_lines=(f"LV Busbar {summary.lv_voltage_v_ll:.0f} V",),
            anchor_node_id=lv_node.node_id,
        )
    )

    pcs_nodes = sorted([node for node in topology.nodes if node.node_type == "pcs"], key=lambda item: item.feeder_index or 0)
    dc_interface_nodes = sorted(
        [node for node in topology.nodes if node.node_type == "dc_interface"],
        key=lambda item: item.feeder_index or 0,
    )
    dc_block_nodes = sorted(
        [node for node in topology.nodes if node.node_type == "dc_block"],
        key=lambda item: (item.feeder_index or 0, item.dc_block_index or 0),
    )

    pcs_count = max(1, len(pcs_nodes))
    slot_width = (lv_bus_x2 - lv_bus_x1) / pcs_count

    interface_block_gap = config["busbar_gap"]
    dc_interface_y = battery_frame_y + 84.0
    feeder_column_gap = min(28.0, slot_width * 0.16)
    dc_blocks_by_feeder: dict[int, list] = {}
    for dc_block in dc_block_nodes:
        feeder_key = int(dc_block.feeder_index or 0)
        dc_blocks_by_feeder.setdefault(feeder_key, []).append(dc_block)
    for feeder_key in dc_blocks_by_feeder:
        dc_blocks_by_feeder[feeder_key] = sorted(
            dc_blocks_by_feeder[feeder_key],
            key=lambda item: (item.dc_block_index or 0),
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
                    f"F{index + 1}",
                    f"{summary.pcs_rating_kw_list[index]:.0f} kW",
                ),
                anchor_node_id=pcs_node.node_id,
                meta={"feeder_index": pcs_node.feeder_index},
            )
        )

        feeder_left = lv_bus_x1 + slot_width * index + feeder_column_gap / 2
        feeder_right = lv_bus_x1 + slot_width * (index + 1) - feeder_column_gap / 2
        feeder_width = max(140.0, feeder_right - feeder_left)
        dc_interface_node = dc_interface_nodes[index]
        feeder_index = int(dc_interface_node.feeder_index or (index + 1))
        interface_width = min(96.0, max(76.0, feeder_width * 0.46))
        symbols.append(
            SldLayoutSymbol(
                symbol_id=f"dc-interface-{index + 1}",
                symbol_type="dc_interface",
                x=center_x - interface_width / 2,
                y=dc_interface_y,
                width=interface_width,
                height=42.0,
                text_lines=("DC Isolator/Fuse", f"F{feeder_index}"),
                anchor_node_id=dc_interface_node.node_id,
                meta={"feeder_index": feeder_index},
            )
        )

        feeder_blocks = dc_blocks_by_feeder.get(feeder_index, [])
        local_count = len(feeder_blocks)
        if not feeder_blocks:
            continue

        grid_cols = 1 if local_count <= 4 else 2
        grid_rows = max(1, ceil(local_count / grid_cols))
        col_gap = 18.0
        row_gap = 18.0
        inner_padding = 10.0
        if grid_cols == 1:
            block_width = min(config["dc_block_width"], feeder_width - inner_padding * 2)
        else:
            block_width = min(
                config["dc_block_width"],
                (feeder_width - inner_padding * 2 - col_gap) / 2,
            )
        block_width = max(84.0, block_width)
        total_grid_width = grid_cols * block_width + max(0, grid_cols - 1) * col_gap
        grid_left = max(feeder_left + inner_padding, center_x - total_grid_width / 2)
        grid_right_limit = feeder_right - inner_padding
        if grid_left + total_grid_width > grid_right_limit:
            grid_left = max(feeder_left + inner_padding, grid_right_limit - total_grid_width)

        block_top = dc_interface_y + 42.0 + interface_block_gap + 18.0
        for local_index, dc_block in enumerate(feeder_blocks):
            row = local_index // grid_cols
            col = local_index % grid_cols
            block_x = grid_left + col * (block_width + col_gap)
            block_y = block_top + row * (config["dc_block_height"] + row_gap)
            symbols.append(
                SldLayoutSymbol(
                    symbol_id=f"dc-block-{dc_block.node_id}",
                    symbol_type="dc_block",
                    x=block_x,
                    y=block_y,
                    width=block_width,
                    height=config["dc_block_height"],
                    text_lines=(
                        f"DC Block #{dc_block.dc_block_index}",
                        f"{summary.dc_block_energy_mwh:.3f} MWh",
                    ),
                    anchor_node_id=dc_block.node_id,
                    meta={"feeder_index": feeder_index},
                )
            )

    symbol_anchor = {symbol.anchor_node_id: symbol for symbol in symbols if symbol.anchor_node_id}

    connectors.append(
        SldLayoutConnector(
            connector_id="mv-transformer-feeder",
            points=((transformer_feeder_x, mv_switchgear_y + mv_switchgear_height), (tx_x, tx_y)),
            style="thick",
            label=transformer_feeder_node.display_name,
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
                        (_symbol_center_x(target_symbol), _symbol_top_y(source_symbol)),
                        (_symbol_center_x(target_symbol), _symbol_top_y(target_symbol)),
                    ),
                    label=f"F{edge.feeder_index}",
                )
            )
        elif edge.edge_type == "pcs_to_dc_interface":
            connectors.append(
                SldLayoutConnector(
                    connector_id=edge.edge_id,
                    points=(
                        (_symbol_center_x(source_symbol), _symbol_bottom_y(source_symbol)),
                        (_symbol_center_x(target_symbol), _symbol_top_y(target_symbol)),
                    ),
                )
            )
        elif edge.edge_type == "dc_interface_to_dc_block":
            source_y = _symbol_bottom_y(source_symbol) if source_symbol.symbol_type == "dc_interface" else _symbol_top_y(source_symbol)
            connectors.append(
                SldLayoutConnector(
                    connector_id=edge.edge_id,
                    points=_orthogonal_points(
                        (_symbol_center_x(source_symbol), source_y),
                        (_symbol_center_x(target_symbol), _symbol_top_y(target_symbol)),
                        bend_y=_symbol_top_y(target_symbol) - 18.0,
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
