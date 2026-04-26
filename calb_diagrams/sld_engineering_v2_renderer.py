from __future__ import annotations

from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - optional dependency
    import svgwrite
except Exception:  # pragma: no cover
    svgwrite = None

try:  # pragma: no cover - optional dependency
    import cairosvg
except Exception:  # pragma: no cover
    cairosvg = None

from calb_diagrams.sld_engineering_v2_layout import SldV2LayoutBox, SldV2LayoutPlan
from calb_diagrams.sld_professional_sheet import (
    ProfessionalSldSheet,
    boxes_by_type as _boxes_by_type,
    build_professional_sld_sheet,
    compact_voltage_label as _compact_voltage_label,
    equipment_row_map as _rows,
    first_box as _first_box,
    format_number as _fmt_number,
)
from calb_diagrams.specs import SLD_FONT_FAMILY
from calb_diagrams.symbol_library import resolve_palette


def _write_png(svg_path: Path, png_path: Path) -> None:
    if cairosvg is None:
        raise ImportError("cairosvg is required to export PNG from SVG.")
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


def _build_drawing(plan: SldV2LayoutPlan):
    palette = resolve_palette(plan.theme)
    dwg = svgwrite.Drawing(
        size=(f"{plan.width}px", f"{plan.height}px"),
        viewBox=f"0 0 {plan.width} {plan.height}",
    )
    dwg.add(
        dwg.style(
            f"""
svg {{ font-family: {SLD_FONT_FAMILY}; font-size: 12px; }}
.background {{ fill: {palette.background}; }}
.wire {{ stroke: {palette.thick}; stroke-width: 2.0; fill: none; stroke-linecap: square; stroke-linejoin: miter; }}
.thin {{ stroke: {palette.thin}; stroke-width: 1.4; fill: none; stroke-linecap: square; stroke-linejoin: miter; }}
.busbar {{ stroke: {palette.busbar}; stroke-width: 2.6; fill: none; stroke-linecap: square; }}
.outline {{ stroke: {palette.outline}; stroke-width: 1.8; fill: none; }}
.symbol-fill {{ fill: {palette.background}; stroke: {palette.outline}; stroke-width: 1.6; }}
.text {{ fill: {palette.text}; }}
.title {{ fill: {palette.title}; font-size: 13px; font-weight: bold; }}
.small {{ fill: {palette.text}; font-size: 10px; }}
.notes {{ fill: {palette.text}; font-size: 12px; font-family: Consolas, 'Courier New', monospace; }}
.notes-title {{ fill: {palette.title}; font-size: 13px; font-weight: bold; font-family: Consolas, 'Courier New', monospace; }}
.debug {{ stroke: {palette.dash}; stroke-width: 1.0; fill: none; opacity: 0.55; }}
.port {{ stroke: {palette.outline}; stroke-width: 1.2; fill: {palette.background}; }}
"""
        )
    )
    dwg.add(dwg.rect(insert=(0, 0), size=(plan.width, plan.height), class_="background"))
    return dwg


def _line(dwg, start: tuple[float, float], end: tuple[float, float], class_name: str = "wire", **kwargs) -> None:
    dwg.add(dwg.line(start, end, class_=class_name, **kwargs))


def _polyline(dwg, points: Iterable[tuple[float, float]], class_name: str = "wire", **kwargs) -> None:
    dwg.add(dwg.polyline(points=list(points), class_=class_name, fill="none", **kwargs))


def _open_triangle(dwg, x: float, y: float, size: float = 12.0) -> None:
    dwg.add(
        dwg.polygon(
            points=[(x, y), (x - size / 2.0, y + size), (x + size / 2.0, y + size)],
            class_="outline",
            fill="none",
        )
    )


def _disconnector(dwg, x: float, y: float, *, side: str = "right") -> None:
    _line(dwg, (x, y - 14.0), (x, y - 4.0), "wire")
    _line(dwg, (x, y + 8.0), (x, y + 18.0), "wire")
    offset = 18.0 if side == "right" else -18.0
    _line(dwg, (x, y - 4.0), (x + offset, y + 10.0), "thin")
    dwg.add(dwg.circle(center=(x, y + 8.0), r=2.2, class_="symbol-fill"))


def _breaker_box(dwg, x: float, y: float) -> None:
    dwg.add(dwg.rect(insert=(x - 7.0, y - 12.0), size=(14.0, 24.0), class_="outline"))
    _line(dwg, (x, y - 12.0), (x, y + 12.0), "thin")


def _earth_switch(dwg, x: float, y: float, *, side: str = "left") -> None:
    direction = -1.0 if side == "left" else 1.0
    _line(dwg, (x, y), (x + direction * 26.0, y), "thin")
    dwg.add(dwg.circle(center=(x + direction * 12.0, y), r=4.0, class_="outline"))
    _line(dwg, (x + direction * 28.0, y - 7.0), (x + direction * 28.0, y + 7.0), "thin")
    _line(dwg, (x + direction * 33.0, y - 5.0), (x + direction * 33.0, y + 5.0), "thin")


def _ct_group(dwg, x: float, y: float) -> None:
    for index in range(3):
        dwg.add(dwg.circle(center=(x - 14.0 + index * 14.0, y), r=6.0, class_="outline"))
        dwg.add(dwg.circle(center=(x - 14.0 + index * 14.0, y + 13.0), r=6.0, class_="outline"))


def _cable_slashes(dwg, x: float, y: float) -> None:
    for index in range(3):
        _line(dwg, (x - 13.0, y + index * 7.0), (x + 13.0, y - 8.0 + index * 7.0), "wire")


def _converter_symbol(dwg, x: float, y: float, width: float, height: float, label: str, subtitle: str = "") -> None:
    dwg.add(dwg.rect(insert=(x - width / 2.0, y), size=(width, height), class_="outline"))
    _line(dwg, (x - width * 0.28, y + height * 0.24), (x + width * 0.20, y + height * 0.70), "thin")
    _polyline(
        dwg,
        [
            (x - width * 0.18, y + height * 0.30),
            (x - width * 0.08, y + height * 0.25),
            (x + width * 0.02, y + height * 0.35),
            (x + width * 0.16, y + height * 0.30),
        ],
        "thin",
    )
    _line(dwg, (x - width * 0.22, y + height * 0.76), (x + width * 0.22, y + height * 0.76), "thin")
    _line(dwg, (x - width * 0.16, y + height * 0.86), (x + width * 0.16, y + height * 0.86), "thin")
    label_x = x + width / 2.0 + 10.0
    dwg.add(dwg.text(label, insert=(label_x, y + height * 0.46), class_="small text"))
    if subtitle:
        dwg.add(dwg.text(subtitle, insert=(label_x, y + height * 0.72), class_="small text"))


def _dc_switch_fuse(dwg, x: float, y: float, height: float = 64.0) -> tuple[float, float]:
    """Draw a vertical DC switch-disconnector plus fuse combination."""

    top_y = y - height / 2.0
    bottom_y = y + height / 2.0
    upper_contact_y = top_y + 10.0
    lower_contact_y = top_y + 28.0
    fuse_top_y = top_y + 38.0
    fuse_h = 18.0
    fuse_bottom_y = fuse_top_y + fuse_h

    _line(dwg, (x, top_y), (x, upper_contact_y), "wire")
    dwg.add(dwg.circle(center=(x, upper_contact_y), r=2.2, class_="symbol-fill"))
    dwg.add(dwg.circle(center=(x, lower_contact_y), r=2.2, class_="symbol-fill"))
    _line(dwg, (x, upper_contact_y), (x + 15.0, lower_contact_y - 2.0), "thin")
    _line(dwg, (x, lower_contact_y), (x, fuse_top_y), "wire")

    dwg.add(dwg.rect(insert=(x - 5.0, fuse_top_y), size=(10.0, fuse_h), class_="outline"))
    _line(dwg, (x, fuse_top_y), (x, fuse_bottom_y), "thin")
    _line(dwg, (x, fuse_bottom_y), (x, bottom_y), "wire")
    return top_y, bottom_y


def _battery_block(dwg, x: float, y: float, width: float, height: float, title: str, subtitle: str) -> None:
    dwg.add(dwg.text(f"{title} {subtitle}".strip(), insert=(x, y), style="display:none"))
    dwg.add(dwg.rect(insert=(x - width / 2.0, y), size=(width, height), class_="outline"))
    stack_top_y = y + 14.0
    stack_bottom_y = y + height - 14.0
    _line(dwg, (x, stack_top_y - 4.0), (x, stack_bottom_y + 4.0), "thin")
    dwg.add(dwg.text("+", insert=(x + width * 0.28, y + 15.0), class_="small text"))
    dwg.add(dwg.text("-", insert=(x + width * 0.28, y + height - 7.0), class_="small text"))
    for row in range(5):
        row_y = stack_top_y + row * ((stack_bottom_y - stack_top_y) / 4.0)
        _line(dwg, (x - 15.0, row_y), (x + 15.0, row_y), "thin")
        _line(dwg, (x - 9.0, row_y + 5.0), (x + 9.0, row_y + 5.0), "thin")
    dwg.add(dwg.text(title, insert=(x, y + height + 12.0), class_="small text", text_anchor="middle"))
    if subtitle:
        dwg.add(dwg.text(subtitle, insert=(x, y + height + 25.0), class_="small text", text_anchor="middle"))


def _delta_symbol(dwg, x: float, y: float, size: float) -> None:
    top = (x, y - size * 0.48)
    left = (x - size * 0.50, y + size * 0.40)
    right = (x + size * 0.50, y + size * 0.40)
    _line(dwg, top, left, "thin")
    _line(dwg, left, right, "thin")
    _line(dwg, right, top, "thin")


def _wye_symbol(dwg, x: float, y: float, size: float) -> None:
    center = (x, y)
    _line(dwg, center, (x, y - size * 0.52), "thin")
    _line(dwg, center, (x - size * 0.48, y + size * 0.40), "thin")
    _line(dwg, center, (x + size * 0.48, y + size * 0.40), "thin")


def _transformer_symbol(dwg, x: float, y: float, text_lines: tuple[str, ...]) -> None:
    radius = 30.0
    upper = (x, y)
    lower_left = (x - 28.0, y + 42.0)
    lower_right = (x + 28.0, y + 42.0)
    for center in (upper, lower_left, lower_right):
        dwg.add(dwg.circle(center=center, r=radius, class_="outline"))
    _delta_symbol(dwg, upper[0], upper[1], 24.0)
    _wye_symbol(dwg, lower_left[0], lower_left[1], 24.0)
    _wye_symbol(dwg, lower_right[0], lower_right[1], 24.0)
    for index, line in enumerate(text_lines):
        dwg.add(dwg.text(line, insert=(x + 88.0, y - 10.0 + index * 14.0), class_="small text"))


def _feeder_terminal(dwg, x: float, y_top: float, y_bus: float, label: str, *, align: str) -> None:
    _line(dwg, (x, y_top + 18.0), (x, y_bus), "wire")
    _open_triangle(dwg, x, y_top + 5.0, 14.0)
    text_x = x - 10.0 if align == "right" else x + 10.0
    text_anchor = "end" if align == "right" else "start"
    dwg.add(dwg.text(label, insert=(text_x, y_top), class_="small text", text_anchor=text_anchor))
    _breaker_box(dwg, x, y_top + 70.0)
    _earth_switch(dwg, x, y_top + 120.0, side="left" if align == "left" else "right")
    _disconnector(dwg, x, y_top + 158.0, side="right" if align == "left" else "left")


def _draw_notes_panel(dwg, sheet: ProfessionalSldSheet) -> None:
    notes = sheet.notes
    dwg.add(dwg.rect(insert=(notes.x, notes.y), size=(notes.width, notes.height), class_="outline"))
    dwg.add(dwg.text(notes.title, insert=(notes.x + 10.0, notes.y + 18.0), class_="notes-title"))
    current_y = notes.y
    for section in notes.sections:
        current_y += section.height
        _line(dwg, (notes.x, current_y), (notes.x + notes.width, current_y), "thin")
        text_y = current_y - section.height + 30.0
        dwg.add(dwg.text(section.title, insert=(notes.x + 8.0, text_y), class_="notes-title"))
        for index, line in enumerate(section.lines):
            dwg.add(dwg.text(line, insert=(notes.x + 8.0, text_y + 24.0 + index * 17.0), class_="notes"))


def _draw_mv_rmu_and_transformer(dwg, plan: SldV2LayoutPlan, sheet: ProfessionalSldSheet) -> tuple[float, float]:
    rows = _rows(plan)
    transformer = _first_box(plan, "transformer")
    transformer_lines = transformer.text_lines if transformer else ("Transformer",)
    mv = sheet.mv

    mv_system = _compact_voltage_label(rows.get("MV System", "MV"))
    dwg.add(dwg.text("PCS&MVT SKID (AC Block)", insert=(mv.center_x, 54.0), class_="title text", text_anchor="middle"))
    dwg.add(dwg.text("RMU / MV Switchgear", insert=(mv.center_x, 98.0), class_="title text", text_anchor="middle"))

    _feeder_terminal(dwg, mv.ring_in_x, mv.top_y, mv.bus_y, f"To {mv_system} Switchgear", align="left")
    _feeder_terminal(dwg, mv.ring_out_x, mv.top_y, mv.bus_y, "To Other RMU", align="right")
    _line(dwg, (mv.ring_in_x, mv.bus_y), (mv.ring_out_x, mv.bus_y), "wire")
    dwg.add(dwg.text("Ring In", insert=(mv.ring_in_x - 28.0, mv.bus_y - 112.0), class_="small text", text_anchor="end"))
    dwg.add(dwg.text("Ring Out", insert=(mv.ring_out_x + 28.0, mv.bus_y - 112.0), class_="small text", text_anchor="start"))
    dwg.add(dwg.text(f"{mv_system} RMU", insert=(mv.ring_out_x - 4.0, mv.bus_y - 10.0), class_="small text", text_anchor="end"))

    _line(dwg, (mv.center_x, mv.bus_y), (mv.center_x, mv.transformer_y - 92.0), "wire")
    _disconnector(dwg, mv.center_x, mv.bus_y + 28.0, side="right")
    _breaker_box(dwg, mv.center_x, mv.bus_y + 66.0)
    _earth_switch(dwg, mv.center_x, mv.bus_y + 100.0, side="left")
    _ct_group(dwg, mv.center_x, mv.bus_y + 116.0)
    _cable_slashes(dwg, mv.center_x, mv.transformer_y - 32.0)
    dwg.add(dwg.text("Transformer Feeder", insert=(mv.center_x + 26.0, mv.bus_y + 46.0), class_="small text"))

    _line(dwg, (mv.center_x, mv.transformer_y - 20.0), (mv.center_x, mv.transformer_y - 32.0), "wire")
    _transformer_symbol(dwg, mv.center_x, mv.transformer_y, transformer_lines)
    _line(dwg, (mv.center_x, mv.transformer_y + 72.0), (mv.center_x, mv.lv_bus_y), "wire")
    return mv.center_x, mv.lv_bus_y


def _draw_lv_pcs_dc(dwg, plan: SldV2LayoutPlan, sheet: ProfessionalSldSheet) -> None:
    pcs_boxes = _boxes_by_type(plan, "pcs")
    dc_boxes = _boxes_by_type(plan, "dc_block")
    by_feeder: dict[int, list[SldV2LayoutBox]] = {}
    for block in dc_boxes:
        by_feeder.setdefault(int(block.feeder_index or 0), []).append(block)

    if not pcs_boxes:
        return
    lvdc = sheet.lvdc
    dwg.add(dwg.text("DC Interface", insert=(lvdc.bus_x1, lvdc.dc_device_y), style="display:none"))
    _line(dwg, (lvdc.bus_x1, sheet.mv.lv_bus_y), (lvdc.bus_x2, sheet.mv.lv_bus_y), "busbar")
    first_pcs = pcs_boxes[0]
    lv_voltage = _fmt_number(first_pcs.attributes.get("lv_voltage_v_ll"), decimals=0)
    dwg.add(
        dwg.text(
            f"LV Busbar={lv_voltage}V",
            insert=(lvdc.bus_x2 - 4.0, sheet.mv.lv_bus_y - 8.0),
            class_="text",
            text_anchor="end",
        )
    )

    for pcs in pcs_boxes:
        feeder_index = int(pcs.feeder_index or 0)
        x = pcs.x + pcs.width / 2.0
        label = pcs.text_lines[0] if pcs.text_lines else f"PCS-{feeder_index}"
        subtitle = pcs.text_lines[1] if len(pcs.text_lines) > 1 else ""
        _line(dwg, (x, sheet.mv.lv_bus_y), (x, lvdc.pcs_y), "wire")
        _disconnector(dwg, x, sheet.mv.lv_bus_y + 22.0, side="right")
        dwg.add(dwg.text(f"F{feeder_index}", insert=(x + 8.0, sheet.mv.lv_bus_y + 28.0), class_="small text"))
        _converter_symbol(dwg, x, lvdc.pcs_y, lvdc.converter_width, lvdc.converter_height, label, subtitle)
        dc_device_top_y, dc_device_bottom_y = _dc_switch_fuse(dwg, x, lvdc.dc_device_y)
        _line(dwg, (x, lvdc.pcs_y + lvdc.converter_height), (x, dc_device_top_y), "wire")
        _line(dwg, (x, dc_device_bottom_y), (x, lvdc.block_y - 20.0), "wire")
        dwg.add(dwg.text("DC Isolator/Fuse", insert=(x + 16.0, lvdc.dc_device_y + 5.0), style="display:none"))
        dwg.add(dwg.text(f"F{feeder_index}", insert=(x + 10.0, lvdc.dc_device_y + 5.0), class_="small text"))

        blocks = sorted(by_feeder.get(feeder_index, []), key=lambda item: item.dc_block_index or 0)
        if len(blocks) <= 1:
            block_centers = [x]
        else:
            spacing = min(lvdc.multi_block_spacing_max, lvdc.multi_block_spacing_base + max(0, len(blocks) - 2) * 16.0)
            start = x - spacing * (len(blocks) - 1) / 2.0
            block_centers = [start + spacing * index for index in range(len(blocks))]
            branch_y = lvdc.block_y - 26.0
            _line(dwg, (min(block_centers), branch_y), (max(block_centers), branch_y), "wire")
            _line(dwg, (x, lvdc.block_y - 20.0), (x, branch_y), "wire")

        for block, block_x in zip(blocks, block_centers):
            _line(dwg, (block_x, lvdc.block_y - 26.0), (block_x, lvdc.block_y), "wire")
            title = block.text_lines[0] if block.text_lines else "DC Block"
            subtitle = block.text_lines[1] if len(block.text_lines) > 1 else ""
            _battery_block(dwg, block_x, lvdc.block_y, lvdc.battery_width, lvdc.battery_height, title, subtitle)


def _draw_debug_connectors(dwg, plan: SldV2LayoutPlan) -> None:
    for connector in plan.connectors:
        if len(connector.points) == 2:
            _line(dwg, connector.points[0], connector.points[1], "debug", id=f"edge-{connector.edge_id}")
        else:
            _polyline(dwg, connector.points, "debug", id=f"edge-{connector.edge_id}")


def _draw_port_anchors(dwg, plan: SldV2LayoutPlan) -> None:
    for anchor in plan.port_anchors:
        dwg.add(dwg.circle(center=(anchor.x, anchor.y), r=2.4, class_="port", id=f"port-{anchor.node_id}-{anchor.port_id}"))


def render_sld_engineering_v2_svg(
    plan: SldV2LayoutPlan,
    out_svg: Path,
    out_png: Path | None = None,
    *,
    show_port_anchors: bool = False,
) -> tuple[Path | None, str | None]:
    """Render a professional electrical single-line diagram from a V2 layout plan.

    This renderer consumes only the resolved V2 layout plan. It does not read
    topology, AC output dictionaries, DC snapshots, or Streamlit session state.
    """
    if svgwrite is None:
        return None, "Missing dependency: svgwrite. Please install: pip install svgwrite"

    sheet = build_professional_sld_sheet(plan)
    dwg = _build_drawing(plan)
    _draw_notes_panel(dwg, sheet)
    _draw_mv_rmu_and_transformer(dwg, plan, sheet)
    _draw_lv_pcs_dc(dwg, plan, sheet)
    if show_port_anchors:
        _draw_debug_connectors(dwg, plan)
        _draw_port_anchors(dwg, plan)

    out_svg = Path(out_svg)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    dwg.saveas(str(out_svg))

    png_warning = None
    if out_png is not None:
        out_png = Path(out_png)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        try:
            _write_png(out_svg, out_png)
        except ImportError:
            png_warning = "Missing dependency: cairosvg. PNG export skipped."
        except Exception:
            png_warning = "PNG export failed."
    return out_svg, png_warning
