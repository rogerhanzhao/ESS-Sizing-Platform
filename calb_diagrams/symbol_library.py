from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SldThemePalette:
    background: str
    outline: str
    thin: str
    thick: str
    dash: str
    text: str
    title: str
    busbar: str


def resolve_palette(theme: str) -> SldThemePalette:
    normalized = str(theme or "light").lower()
    if normalized.startswith("dark"):
        return SldThemePalette(
            background="#0b0f13",
            outline="#e5e7eb",
            thin="#cbd5e1",
            thick="#e5e7eb",
            dash="#22d3ee",
            text="#e5e7eb",
            title="#f8fafc",
            busbar="#ef4444",
        )
    return SldThemePalette(
        background="#ffffff",
        outline="#000000",
        thin="#000000",
        thick="#000000",
        dash="#000000",
        text="#000000",
        title="#000000",
        busbar="#000000",
    )


def symbol_registry() -> dict[str, callable]:
    return {
        "section_frame": draw_section_frame,
        "busbar_horizontal": draw_busbar_horizontal,
        "external_feeder_arrow": draw_external_feeder_arrow,
        "mv_switchgear": draw_mv_switchgear_symbol,
        "rmu": draw_rmu_symbol,
        "transformer": draw_transformer_symbol,
        "pcs": draw_pcs_symbol,
        "dc_interface": draw_dc_interface_symbol,
        "dc_busbar_single": draw_dc_busbar_single,
        "dc_busbar_pair": draw_dc_busbar_pair,
        "dc_feeder_label": draw_dc_feeder_label,
        "dc_block": draw_dc_block_symbol,
    }


def draw_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    renderer = symbol_registry().get(symbol.symbol_type)
    if renderer is None:
        raise ValueError(f"Unsupported SLD symbol_type: {symbol.symbol_type}")
    renderer(dwg, symbol, palette)


def draw_section_frame(dwg, symbol, palette: SldThemePalette) -> None:
    dash = symbol.meta.get("frame_style") == "dash"
    class_name = "dash" if dash else "outline"
    dwg.add(dwg.rect(insert=(symbol.x, symbol.y), size=(symbol.width, symbol.height), class_=class_name))
    if symbol.text_lines:
        title_align = symbol.meta.get("title_align")
        title_y = symbol.y + float(symbol.meta.get("title_offset_y", 18.0))
        if title_align == "center":
            dwg.add(
                dwg.text(
                    symbol.text_lines[0],
                    insert=(symbol.x + symbol.width / 2, title_y),
                    class_="label title",
                    text_anchor="middle",
                )
            )
        else:
            dwg.add(dwg.text(symbol.text_lines[0], insert=(symbol.x + 8, title_y), class_="label title"))


def draw_busbar_horizontal(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.line((symbol.x, symbol.y), (symbol.x + symbol.width, symbol.y), class_="busbar"))
    if symbol.text_lines:
        dwg.add(dwg.text(symbol.text_lines[0], insert=(symbol.x, symbol.y - 8), class_="label"))


def draw_external_feeder_arrow(dwg, symbol, palette: SldThemePalette) -> None:
    x = symbol.x
    y = symbol.y
    height = max(16.0, symbol.height)
    dwg.add(dwg.line((x, y + height), (x, y + 8), class_="thin"))
    dwg.add(dwg.polygon(points=[(x, y), (x - 5, y + 8), (x + 5, y + 8)], class_="outline", fill="none"))
    if symbol.text_lines:
        align = "end" if symbol.meta.get("align") == "right" else "start"
        text_x = x + 8 if align == "start" else x - 8
        dwg.add(dwg.text(symbol.text_lines[0], insert=(text_x, y + 4), class_="small", text_anchor=align))


def draw_mv_switchgear_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.rect(insert=(symbol.x, symbol.y), size=(symbol.width, symbol.height), class_="outline"))
    title = symbol.text_lines[0] if symbol.text_lines else "RMU / MV Switchgear"
    dwg.add(
        dwg.text(
            title,
            insert=(symbol.x + symbol.width / 2, symbol.y + 16),
            class_="small",
            text_anchor="middle",
        )
    )

    cubicle_labels = list(symbol.text_lines[1:4]) or ["Ring In", "Transformer Feeder", "Ring Out"]
    cell_width = symbol.width / 3.0
    cell_top = symbol.y + 24.0
    bus_y = symbol.y + symbol.height * 0.58
    top_port_y = symbol.y
    bottom_port_y = symbol.y + symbol.height
    dwg.add(dwg.line((symbol.x + 12.0, bus_y), (symbol.x + symbol.width - 12.0, bus_y), class_="busbar"))
    for index, label in enumerate(cubicle_labels):
        cell_x = symbol.x + cell_width * index
        center_x = cell_x + cell_width / 2.0
        if index > 0:
            dwg.add(dwg.line((cell_x, cell_top), (cell_x, symbol.y + symbol.height), class_="thin"))
        dwg.add(dwg.text(label, insert=(center_x, symbol.y + 38), class_="small", text_anchor="middle"))
        if index == 1:
            dwg.add(dwg.line((center_x, bus_y), (center_x, bottom_port_y), class_="thin"))
            switch_y = bus_y + 16.0
            dwg.add(dwg.line((center_x - 10.0, switch_y - 8.0), (center_x + 10.0, switch_y + 8.0), class_="thin"))
        else:
            dwg.add(dwg.line((center_x, top_port_y), (center_x, bus_y), class_="thin"))
            switch_y = bus_y - 16.0
            dwg.add(dwg.line((center_x - 10.0, switch_y - 8.0), (center_x + 10.0, switch_y + 8.0), class_="thin"))

    if len(symbol.text_lines) >= 5:
        dwg.add(
            dwg.text(
                symbol.text_lines[4],
                insert=(symbol.x + symbol.width - 8.0, symbol.y + symbol.height - 8.0),
                class_="small",
                text_anchor="end",
            )
        )


def draw_rmu_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.rect(insert=(symbol.x - symbol.width / 2, symbol.y), size=(symbol.width, symbol.height), class_="outline"))
    switch_y = symbol.y + symbol.height * 0.4
    dwg.add(dwg.line((symbol.x - symbol.width * 0.28, switch_y), (symbol.x + symbol.width * 0.28, switch_y), class_="thin"))
    dwg.add(dwg.line((symbol.x - symbol.width * 0.18, switch_y - 10), (symbol.x - symbol.width * 0.04, switch_y + 8), class_="thin"))
    dwg.add(dwg.line((symbol.x + symbol.width * 0.18, switch_y - 10), (symbol.x + symbol.width * 0.04, switch_y + 8), class_="thin"))
    for idx, line in enumerate(symbol.text_lines):
        dwg.add(dwg.text(line, insert=(symbol.x, symbol.y + symbol.height + 14 + idx * 14), class_="small", text_anchor="middle"))


def draw_transformer_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    center_x = symbol.x
    top_y = symbol.y
    radius = min(symbol.width * 0.12, 14.0)
    centers = [
        (center_x, top_y + radius),
        (center_x - radius * 1.6, top_y + radius * 2.8),
        (center_x + radius * 1.6, top_y + radius * 2.8),
    ]
    for cx, cy in centers:
        dwg.add(dwg.circle(center=(cx, cy), r=radius, class_="outline"))
    label_x = center_x + max(50.0, symbol.width * 0.38)
    for idx, line in enumerate(symbol.text_lines):
        dwg.add(dwg.text(line, insert=(label_x, top_y + 12 + idx * 14), class_="small"))


def draw_pcs_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.rect(insert=(symbol.x, symbol.y), size=(symbol.width, symbol.height), class_="outline"))
    icon_x = symbol.x + symbol.width * 0.18
    icon_y = symbol.y + symbol.height * 0.25
    dwg.add(dwg.line((icon_x, icon_y), (icon_x + symbol.width * 0.22, icon_y + symbol.height * 0.42), class_="thin"))
    dc_y = symbol.y + symbol.height * 0.72
    dwg.add(dwg.line((icon_x, dc_y), (icon_x + symbol.width * 0.22, dc_y), class_="thin"))
    dwg.add(dwg.line((icon_x, dc_y - 6), (icon_x + symbol.width * 0.22, dc_y - 6), class_="thin"))
    ac_x1 = symbol.x + symbol.width * 0.62
    ac_x2 = symbol.x + symbol.width * 0.86
    mid_y = symbol.y + symbol.height * 0.34
    dwg.add(dwg.polyline(points=[(ac_x1, mid_y), (ac_x1 + 6, mid_y - 3), (ac_x1 + 12, mid_y + 3), (ac_x2, mid_y)], class_="thin", fill="none"))
    for idx, line in enumerate(symbol.text_lines):
        dwg.add(dwg.text(line, insert=(symbol.x + symbol.width * 0.55, symbol.y + 18 + idx * 16), class_="small"))


def draw_dc_interface_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    center_x = symbol.x + symbol.width / 2
    top_y = symbol.y
    bottom_y = symbol.y + symbol.height
    center_y = top_y + symbol.height / 2
    # Conductor
    dwg.add(dwg.line((center_x, top_y), (center_x, bottom_y), class_="thin"))
    # Fuse (rectangle) above the switch
    dwg.add(dwg.rect(insert=(center_x - 5, center_y - 15), size=(10, 8), class_="outline"))
    # Disconnect switch: moving contact (upper circle) + open blade + fixed contact (lower bar)
    upper_y = center_y - 3
    lower_y = center_y + 9
    dwg.add(dwg.circle(center=(center_x, upper_y), r=2.5, class_="outline"))
    dwg.add(dwg.line((center_x, upper_y), (center_x + 12, lower_y), class_="thin"))
    dwg.add(dwg.line((center_x - 7, lower_y), (center_x + 7, lower_y), class_="thin"))
    for idx, line in enumerate(symbol.text_lines):
        dwg.add(
            dwg.text(
                line,
                insert=(center_x + 14.0, center_y - 2 + idx * 12),
                class_="small",
                text_anchor="start",
            )
        )


def draw_dc_busbar_single(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.line((symbol.x, symbol.y), (symbol.x + symbol.width, symbol.y), class_="busbar"))
    label = symbol.text_lines[0] if symbol.text_lines else "DC BUSBAR"
    dwg.add(dwg.text(label, insert=(symbol.x, symbol.y - 8), class_="small"))


def draw_dc_busbar_pair(dwg, symbol, palette: SldThemePalette) -> None:
    height = max(symbol.height or 72.0, 44.0)
    center_x = symbol.x + symbol.width / 2
    rail_offset = min(14.0, max(10.0, symbol.width * 0.18))
    positive_x = center_x - rail_offset
    negative_x = center_x + rail_offset
    y1 = symbol.y
    y2 = symbol.y + height

    dwg.add(dwg.line((positive_x, y1), (positive_x, y2), class_="busbar"))
    dwg.add(dwg.line((negative_x, y1), (negative_x, y2), class_="busbar"))
    label_a = symbol.text_lines[0] if len(symbol.text_lines) >= 1 else "DC+"
    label_b = symbol.text_lines[1] if len(symbol.text_lines) >= 2 else "DC-"
    dwg.add(dwg.text(label_a, insert=(positive_x - 4, y1 - 8), class_="small", text_anchor="end"))
    dwg.add(dwg.text(label_b, insert=(negative_x + 4, y1 - 8), class_="small", text_anchor="start"))


def draw_dc_feeder_label(dwg, symbol, palette: SldThemePalette) -> None:
    if not symbol.text_lines:
        return
    dwg.add(
        dwg.text(
            symbol.text_lines[0],
            insert=(symbol.x + 6, symbol.y + 4),
            class_="small",
            text_anchor="start",
        )
    )


def draw_dc_block_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.rect(insert=(symbol.x, symbol.y), size=(symbol.width, symbol.height), class_="outline"))
    battery_x = symbol.x + symbol.width - max(24.0, symbol.width * 0.22)
    top_y = symbol.y + 13
    dwg.add(dwg.line((battery_x, top_y), (battery_x, symbol.y + symbol.height - 8), class_="thin"))
    for row in range(6):
        row_y = symbol.y + 12 + row * max(6.0, symbol.height / 8.0)
        dwg.add(dwg.line((battery_x - 10, row_y), (battery_x + 10, row_y), class_="thin"))
    for idx, line in enumerate(symbol.text_lines):
        dwg.add(dwg.text(line, insert=(symbol.x + 8, symbol.y + 18 + idx * 14), class_="small"))
