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
        "rmu": draw_rmu_symbol,
        "transformer": draw_transformer_symbol,
        "pcs": draw_pcs_symbol,
        "dc_busbar_single": draw_dc_busbar_single,
        "dc_busbar_pair": draw_dc_busbar_pair,
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
    for idx, line in enumerate(symbol.text_lines):
        dwg.add(dwg.text(line, insert=(center_x + symbol.width * 0.2, top_y + 12 + idx * 14), class_="small"))


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


def draw_dc_busbar_single(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.line((symbol.x, symbol.y), (symbol.x + symbol.width, symbol.y), class_="busbar"))
    label = symbol.text_lines[0] if symbol.text_lines else "DC BUSBAR"
    dwg.add(dwg.text(label, insert=(symbol.x, symbol.y - 8), class_="small"))


def draw_dc_busbar_pair(dwg, symbol, palette: SldThemePalette) -> None:
    gap = symbol.height or 22.0
    dwg.add(dwg.line((symbol.x, symbol.y), (symbol.x + symbol.width, symbol.y), class_="busbar"))
    dwg.add(dwg.line((symbol.x, symbol.y + gap), (symbol.x + symbol.width, symbol.y + gap), class_="busbar"))
    label_a = symbol.text_lines[0] if len(symbol.text_lines) >= 1 else "DC BUSBAR A"
    label_b = symbol.text_lines[1] if len(symbol.text_lines) >= 2 else "DC BUSBAR B"
    dwg.add(dwg.text(label_a, insert=(symbol.x, symbol.y - 8), class_="small"))
    dwg.add(dwg.text(label_b, insert=(symbol.x, symbol.y + gap - 8), class_="small"))


def draw_dc_block_symbol(dwg, symbol, palette: SldThemePalette) -> None:
    dwg.add(dwg.rect(insert=(symbol.x, symbol.y), size=(symbol.width, symbol.height), class_="outline"))
    mid_x = symbol.x + symbol.width / 2
    top_y = symbol.y + 10
    dwg.add(dwg.line((mid_x, top_y), (mid_x, symbol.y + symbol.height - 10), class_="thin"))
    for row in range(6):
        row_y = symbol.y + 12 + row * max(6.0, symbol.height / 8.0)
        dwg.add(dwg.line((mid_x - 14, row_y), (mid_x + 14, row_y), class_="thin"))
    for idx, line in enumerate(symbol.text_lines):
        dwg.add(dwg.text(line, insert=(symbol.x + 8, symbol.y + 18 + idx * 14), class_="small"))
