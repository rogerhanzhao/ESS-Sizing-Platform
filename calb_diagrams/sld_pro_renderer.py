# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency
    import svgwrite
except Exception:  # pragma: no cover
    svgwrite = None

try:
    import cairosvg
except Exception:  # pragma: no cover - optional dependency
    cairosvg = None

from calb_diagrams.sld_layout_engine import (
    LayoutProfileId,
    SldLayoutPlan,
    build_sld_layout_plan,
)
from calb_diagrams.symbol_library import draw_symbol, resolve_palette
from calb_diagrams.specs import (
    SLD_DASH_ARRAY,
    SLD_FONT_FAMILY,
    SLD_FONT_SIZE,
    SLD_FONT_SIZE_SMALL,
    SLD_FONT_SIZE_TITLE,
    SLD_STROKE_OUTLINE,
    SLD_STROKE_THICK,
    SLD_STROKE_THIN,
    SldGroupSpec,
    build_topology_from_legacy_sld_group_spec,
)
from calb_sizing_tool.schemas.sld_topology import SldTopology


def _write_png(svg_path: Path, png_path: Path) -> None:
    if cairosvg is None:
        raise ImportError("cairosvg is required to export PNG from SVG.")
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


def _draw_panel(dwg, panel) -> None:
    dwg.add(dwg.rect(insert=(panel.x, panel.y), size=(panel.width, panel.height), class_="outline"))
    dwg.add(dwg.text(panel.title, insert=(panel.x + 8, panel.y + 18), class_="label title"))
    split_x = panel.x + panel.width * 0.37
    current_y = panel.y + 36
    dwg.add(dwg.line((split_x, panel.y + 24), (split_x, panel.y + panel.height), class_="thin"))
    for row in panel.rows:
        current_y += 28
        dwg.add(dwg.line((panel.x, current_y - 18), (panel.x + panel.width, current_y - 18), class_="thin"))
        dwg.add(dwg.text(row.item, insert=(panel.x + 8, current_y), class_="small"))
        dwg.add(dwg.text(row.spec, insert=(split_x + 8, current_y), class_="small"))


def _draw_summary_box(dwg, plan: SldLayoutPlan) -> None:
    if not plan.draw_summary or not plan.summary_lines:
        return
    box_width = 420.0
    box_height = 34.0 + len(plan.summary_lines) * 18.0
    box_x = plan.width - box_width - 40.0
    box_y = plan.height - box_height - 28.0
    dwg.add(dwg.rect(insert=(box_x, box_y), size=(box_width, box_height), class_="outline"))
    dwg.add(dwg.text("Allocation Summary", insert=(box_x + 8, box_y + 18), class_="label title"))
    for index, line in enumerate(plan.summary_lines):
        dwg.add(dwg.text(line, insert=(box_x + 8, box_y + 40 + index * 18), class_="small"))


def _draw_connectors(dwg, plan: SldLayoutPlan) -> None:
    for connector in plan.connectors:
        if len(connector.points) < 2:
            continue
        if len(connector.points) == 2:
            dwg.add(dwg.line(connector.points[0], connector.points[1], class_=connector.style))
        else:
            dwg.add(dwg.polyline(points=list(connector.points), class_=connector.style, fill="none"))
        if connector.label:
            label_x, label_y = connector.points[-1]
            dwg.add(dwg.text(connector.label, insert=(label_x + 4, label_y - 4), class_="small"))


def _build_svg_drawing(plan: SldLayoutPlan):
    palette = resolve_palette(plan.theme)
    dwg = svgwrite.Drawing(
        size=(f"{plan.width}px", f"{plan.height}px"),
        viewBox=f"0 0 {plan.width} {plan.height}",
    )
    dwg.add(
        dwg.style(
            f"""
svg {{ font-family: {SLD_FONT_FAMILY}; font-size: {SLD_FONT_SIZE}px; }}
.outline {{ stroke: {palette.outline}; stroke-width: {max(2.0, SLD_STROKE_OUTLINE)}; fill: none; }}
.thin {{ stroke: {palette.thin}; stroke-width: {max(1.4, SLD_STROKE_THIN)}; fill: none; }}
.thick {{ stroke: {palette.thick}; stroke-width: {max(2.0, SLD_STROKE_THICK)}; fill: none; }}
.dash {{ stroke: {palette.dash}; stroke-width: {max(2.0, SLD_STROKE_OUTLINE)}; fill: none; stroke-dasharray: {SLD_DASH_ARRAY}; }}
.busbar {{ stroke: {palette.busbar}; stroke-width: {max(2.2, SLD_STROKE_THICK)}; fill: none; }}
.label {{ fill: {palette.text}; }}
.title {{ font-size: {SLD_FONT_SIZE_TITLE}px; font-weight: bold; fill: {palette.title}; }}
.small {{ font-size: {SLD_FONT_SIZE_SMALL}px; fill: {palette.text}; }}
"""
        )
    )
    dwg.add(dwg.rect(insert=(0, 0), size=(plan.width, plan.height), fill=palette.background))
    return dwg, palette


def render_sld_svg(
    topology: SldTopology,
    layout_profile: LayoutProfileId,
    theme: str,
    out_svg: Path,
    out_png: Path | None = None,
) -> tuple[Path | None, str | None]:
    """Pure renderer entrypoint.

    Consumes only authoritative topology + layout profile + theme and emits SVG/PNG.
    No AC/DC/session/stage dict inference is allowed in this function.
    """
    if svgwrite is None:
        return None, "Missing dependency: svgwrite. Please install: pip install svgwrite"

    plan = build_sld_layout_plan(topology, layout_profile=layout_profile, theme=theme)
    dwg, palette = _build_svg_drawing(plan)

    for panel in plan.panels:
        _draw_panel(dwg, panel)
    _draw_connectors(dwg, plan)
    for symbol in plan.symbols:
        draw_symbol(dwg, symbol, palette)
    _draw_summary_box(dwg, plan)

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


def render_sld_pro_svg(
    spec: SldGroupSpec | SldTopology,
    out_svg: Path,
    out_png: Path | None = None,
) -> tuple[Path | None, str | None]:
    """Compatibility wrapper for older SLD call sites.

    Rendering is delegated to render_sld_svg(topology, ...). This wrapper only adapts the legacy
    SldGroupSpec shape into topology and must not contain engineering allocation logic.
    Formal SLD generation must call render_sld_svg() with authoritative topology instead.
    """
    if isinstance(spec, SldTopology):
        topology = spec
        layout_profile: LayoutProfileId = "compact" if topology.summary.compact_mode else "engineering_readable"
        theme = topology.summary.theme
    else:
        topology = build_topology_from_legacy_sld_group_spec(spec)
        layout_profile = "compact" if topology.summary.compact_mode else "engineering_readable"
        theme = topology.summary.theme
    return render_sld_svg(topology, layout_profile, theme, out_svg, out_png)
