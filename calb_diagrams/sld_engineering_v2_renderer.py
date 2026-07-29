"""BESS Single Line Diagram renderer — ANSI/IEEE 315 compliant symbols.

Rendering conventions:
- Black-on-white monochrome (print-ready).
- All electrical symbols follow ANSI/IEEE Std 315-1975 (R1993).
- Transformer shown as either two-winding interlocked circles or one MV
  primary with separately identified LV-A/LV-B secondary windings.
- Equipment tags follow NEMA/industry convention: T-01, INV-01, BESS-01, RMU-01.
- Title block per ANSI Y14.1 (no company / logo — added at report-generation time).
"""
from __future__ import annotations

import datetime
import math
import re
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
    ProfessionalTitleBlock,
    boxes_by_type as _boxes_by_type,
    build_professional_sld_sheet,
    compact_voltage_label as _compact_voltage_label,
    equipment_row_map as _rows,
    first_box as _first_box,
    format_number as _fmt_number,
)
from calb_diagrams.sld_engineering_v2_validation import validate_rendered_sld_svg
from calb_diagrams.specs import SLD_FONT_FAMILY
from calb_diagrams.symbol_library import resolve_palette
from calb_sizing_tool.sld.transformer_vector_group import (
    TransformerVectorGroupError,
    parse_transformer_vector_group,
)


# ---------------------------------------------------------------------------
# SVG setup
# ---------------------------------------------------------------------------

def _write_png(svg_path: Path, png_path: Path) -> None:
    if cairosvg is None:
        raise ImportError("cairosvg is required to export PNG from SVG.")
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


def _build_drawing(plan: SldV2LayoutPlan):
    dwg = svgwrite.Drawing(
        size=(f"{plan.width}px", f"{plan.height}px"),
        viewBox=f"0 0 {plan.width} {plan.height}",
    )
    dwg.add(dwg.style(f"""
svg {{ font-family: {SLD_FONT_FAMILY}; font-size: 11px; }}
.bg      {{ fill: #ffffff; }}
.wire    {{ stroke: #1a1a1a; stroke-width: 1.8; fill: none;
            stroke-linecap: square; stroke-linejoin: miter; }}
.thin    {{ stroke: #1a1a1a; stroke-width: 1.2; fill: none;
            stroke-linecap: round; stroke-linejoin: round; }}
.busbar  {{ stroke: #1a1a1a; stroke-width: 3.2; fill: none; stroke-linecap: square; }}
.outline {{ stroke: #1a1a1a; stroke-width: 1.6; fill: none; }}
.sfill   {{ stroke: #1a1a1a; stroke-width: 1.6; fill: #ffffff; }}
.text    {{ fill: #1a1a1a; }}
.title   {{ fill: #1a1a1a; font-size: 12px; font-weight: bold; }}
.label   {{ fill: #1a1a1a; font-size: 10px; }}
.tag     {{ fill: #1a1a1a; font-size: 9px; font-style: italic; }}
.notes   {{ fill: #1a1a1a; font-size: 10.5px; font-family: Consolas, 'Courier New', monospace; }}
.ntitle  {{ fill: #1a1a1a; font-size: 11px; font-weight: bold; }}
.tb      {{ fill: #1a1a1a; font-size: 10px; }}
.tbh     {{ fill: #1a1a1a; font-size: 11px; font-weight: bold; }}
.tbtitle {{ fill: #1a1a1a; font-size: 13px; font-weight: bold; }}
.dot     {{ fill: #1a1a1a; stroke: none; }}
.warn    {{ stroke: #b00020; stroke-width: 1.8; fill: none; stroke-dasharray: 6 4; }}
.warntx  {{ fill: #b00020; font-size: 10px; font-weight: bold; }}
.acblock {{ stroke: #1a56b8; stroke-width: 2.0; fill: none; stroke-dasharray: 10 5; }}
.acblocktx {{ fill: #1a56b8; font-size: 12px; font-weight: bold; }}
"""))
    dwg.add(dwg.rect(insert=(0, 0), size=(plan.width, plan.height), class_="bg"))
    return dwg


# ---------------------------------------------------------------------------
# Low-level drawing helpers
# ---------------------------------------------------------------------------

def _line(dwg, start: tuple[float, float], end: tuple[float, float],
          cls: str = "wire", **kw) -> None:
    dwg.add(dwg.line(start, end, class_=cls, **kw))


def _poly(dwg, pts: Iterable[tuple[float, float]], cls: str = "wire", **kw) -> None:
    dwg.add(dwg.polyline(points=list(pts), class_=cls, fill="none", **kw))


def _rect(dwg, x: float, y: float, w: float, h: float, cls: str = "sfill") -> None:
    dwg.add(dwg.rect(insert=(x, y), size=(w, h), class_=cls))


def _text(dwg, s: str, x: float, y: float, cls: str = "text",
          anchor: str = "start", **kw) -> None:
    dwg.add(dwg.text(s, insert=(x, y), class_=cls, text_anchor=anchor, **kw))


def _junction(dwg, x: float, y: float, r: float = 3.5) -> None:
    """Filled dot at a T-junction on a busbar or wire."""
    dwg.add(dwg.circle(center=(x, y), r=r, class_="dot"))


# ---------------------------------------------------------------------------
# ANSI/IEEE 315 electrical symbols
# ---------------------------------------------------------------------------

def _ground(dwg, x: float, y: float) -> None:
    """ANSI ground symbol — three tapered horizontal lines below a stem."""
    _line(dwg, (x, y), (x, y + 8.0), "thin")
    for i, half in enumerate((10.0, 6.5, 3.0)):
        gy = y + 8.0 + i * 5.0
        _line(dwg, (x - half, gy), (x + half, gy), "thin")


def _disconnect_switch(dwg, x: float, y: float, *, blade_right: bool = True) -> None:
    """ANSI disconnect switch (isolator) — open blade symbol.

    IEEE 315 Fig 2.14.1: pivot (moving) contact = filled circle; fixed contact = horizontal bar.
    blade_right=True puts the blade tip to the right of the conductor.
    """
    off = 16.0 if blade_right else -16.0
    pivot_y = y - 8.0
    fixed_y = y + 8.0
    # Pivot / moving contact — small filled circle at hinge
    dwg.add(dwg.circle(center=(x, pivot_y), r=2.5, class_="sfill"))
    # Open blade from pivot toward (but not touching) fixed contact — OPEN position
    _line(dwg, (x, pivot_y), (x + off, fixed_y - 5.0), "thin")
    # Fixed contact — horizontal bar (IEEE 315 standard, not a circle)
    _line(dwg, (x - 6.0, fixed_y), (x + 6.0, fixed_y), "thin")


def _circuit_breaker(dwg, x: float, y: float) -> None:
    """ANSI circuit breaker — rectangle with diagonal slash (IEEE 315 Fig 2.12.1)."""
    hw, hh = 8.0, 12.0
    _rect(dwg, x - hw, y - hh, hw * 2, hh * 2, "sfill")
    # Diagonal slash top-right → bottom-left (ANSI convention for CB open position)
    _line(dwg, (x + hw, y - hh), (x - hw, y + hh), "thin")


def _fuse(dwg, x: float, y: float, height: float = 18.0) -> None:
    """ANSI cartridge fuse — rectangle with center conductor (IEEE 315 Fig 2.30)."""
    hw = 5.0
    _rect(dwg, x - hw, y - height / 2.0, hw * 2, height, "sfill")
    _line(dwg, (x, y - height / 2.0), (x, y + height / 2.0), "thin")


def _ct_symbol(dwg, x: float, y: float) -> None:
    """ANSI current transformer — circle with primary conductor through it (IEEE 315 Fig 5.2.1)."""
    r = 7.0
    dwg.add(dwg.circle(center=(x, y), r=r, class_="sfill"))
    # Primary conductor passes through (drawn as part of connecting wire externally;
    # here we add a short emphasising tick on the CT circle)
    _line(dwg, (x - r - 4.0, y), (x + r + 4.0, y), "thin")


def _ct_group_vertical(dwg, x: float, y: float) -> None:
    """Three CTs stacked vertically on the feeder conductor (3-phase indication)."""
    for i in range(3):
        _ct_symbol(dwg, x, y + i * 18.0)


def _cable_3phase(dwg, x: float, y: float) -> None:
    """Three diagonal hash marks indicating a 3-phase cable run (per ANSI practice)."""
    for i in range(3):
        ox = -10.0 + i * 10.0
        _line(dwg, (x + ox - 8.0, y + 8.0), (x + ox + 8.0, y - 8.0), "thin")


def _delta_mark(dwg, x: float, y: float, size: float = 14.0, *, id_prefix: str | None = None) -> None:
    """Delta (Δ) triangle for transformer HV winding annotation."""
    top = (x, y - size * 0.60)
    bl  = (x - size * 0.55, y + size * 0.40)
    br  = (x + size * 0.55, y + size * 0.40)
    for index, (start, end) in enumerate(((top, bl), (bl, br), (br, top)), start=1):
        _line(dwg, start, end, "thin", **({"id": f"{id_prefix}-delta-{index}"} if id_prefix else {}))


def _wye_mark(dwg, x: float, y: float, size: float = 14.0, *, id_prefix: str | None = None) -> None:
    """Wye winding mark — a three-arm star (Y), never an inferred earth connection.

    A star/wye winding symbol is three conductors meeting at one star point, so
    all THREE arms must be drawn (two upper arms plus the lower star-point / neutral
    arm) — they are the symbol itself, not a removable stub. ``y``/``z`` declare a
    winding connection and ``yn``/``zn`` additionally declare an available neutral
    terminal. Neither declaration says the neutral terminal is earthed: grounding is
    a separate protection design (the ANSI earth symbol) and is deliberately never
    drawn here — only the plain three-arm Y.
    """
    arm = size * 0.60
    _line(dwg, (x, y), (x - arm * 0.87, y - arm * 0.50), "thin", **({"id": f"{id_prefix}-wye-left"} if id_prefix else {}))
    _line(dwg, (x, y), (x + arm * 0.87, y - arm * 0.50), "thin", **({"id": f"{id_prefix}-wye-right"} if id_prefix else {}))
    _line(dwg, (x, y), (x, y + arm), "thin", **({"id": f"{id_prefix}-neutral-leg"} if id_prefix else {}))


def _parse_vector_group(vector_group: str, secondary_count: int) -> tuple[str, list[str]]:
    """Split an IEC vector group string into HV token + one token per secondary.

    'Dyn11'   → ('D', ['yn11'])           (2-winding)
    'Dy11y11' → ('D', ['y11', 'y11'])     (3-winding)
    'YNd11y0' → ('YN', ['d11', 'y0'])

    Returns ('', []) when the string cannot be parsed — callers must then fall
    back to a text annotation so the symbol never contradicts the nameplate.
    """
    try:
        parsed = parse_transformer_vector_group(
            vector_group,
            lv_winding_count=secondary_count,
        )
    except TransformerVectorGroupError:
        return "", []
    return parsed.hv_token, list(parsed.lv_tokens)


def _winding_mark(dwg, x: float, y: float, token: str, size: float = 14.0,
                  fallback_text: str = "", id_prefix: str | None = None) -> None:
    """Draw the winding-connection mark matching a vector-group token.

    Symbol selection is driven by the parsed token so the graphic can never
    contradict the nameplate text. Unknown tokens are annotated as text.
    """
    kind = re.sub(r"\d+$", "", str(token or "")).lower()
    if kind == "d":
        _delta_mark(dwg, x, y, size=size, id_prefix=id_prefix)
    elif kind in ("y", "yn", "z", "zn"):
        _wye_mark(dwg, x, y, size=size, id_prefix=id_prefix)
    else:
        _text(dwg, fallback_text or str(token), x, y + 4.0, "label", anchor="middle")


def _transformer_2w(dwg, x: float, y: float,
                    vector_group: str, text_lines: tuple[str, ...]) -> None:
    """ANSI/IEC two-winding transformer: two clearly interlocked equal circles.

    HV (primary) circle on top, LV (secondary) below; winding marks are derived
    from the vector group via _parse_vector_group -> _winding_mark
    (_delta_mark / _wye_mark). Wire entry at top of the HV circle, exit at
    bottom of the LV circle. Vector groups do not authorise earth symbols.
    """
    r = 28.0
    overlap = 16.0     # classic interlocked-circles look (~0.57 r)
    hv_cy = y + r
    lv_cy = hv_cy + 2 * r - overlap

    dwg.add(dwg.circle(center=(x, hv_cy), r=r, class_="sfill", id="tx-hv-winding"))
    dwg.add(dwg.circle(center=(x, lv_cy), r=r, class_="sfill", id="tx-lv-winding-1"))

    vg = str(vector_group or "TBD").strip()
    hv_token, lv_tokens = _parse_vector_group(vg, 1)
    mark = r * 0.62
    # Marks sit in the non-overlapped part of each circle
    _winding_mark(dwg, x, hv_cy - overlap * 0.35, hv_token, size=mark, fallback_text=vg,
                  id_prefix="tx-hv-winding")
    _winding_mark(dwg, x, lv_cy + overlap * 0.35, lv_tokens[0] if lv_tokens else "",
                  size=mark, fallback_text=vg, id_prefix="tx-lv-winding-1")

    # Nameplate lines to the right (vector group already appears in these
    # lines - do not print it a second time)
    for idx, line in enumerate(text_lines):
        _text(dwg, line, x + r + 12.0, hv_cy - 4.0 + idx * 14.0, "label")

    # Return connection y coordinates for caller
    return hv_cy - r, lv_cy + r   # (top connection y, bottom connection y)


def _transformer_split_secondary(
    dwg,
    x: float,
    y: float,
    vector_group: str,
    text_lines: tuple[str, ...],
    winding_count: int,
) -> tuple[float, list[tuple[float, float]]]:
    """Three-winding transformer per IEC 60617 / ANSI 315: three equal circles
    forming one interlocked cluster - HV primary on top, the independent LV
    secondaries below-left and below-right, every pair of circles overlapping.

    Returns (hv connection y, [(x, y) LV terminal per winding]).
    """
    if winding_count != 2:
        raise ValueError(
            f"split-secondary transformer symbol supports exactly 2 LV windings, got {winding_count}"
        )
    r = 26.0
    dx = 24.0          # horizontal half-spread of the LV circles
    dy = 34.0          # vertical drop of LV centres below the HV centre
    hv_cy = y + r      # HV top connection stays exactly at y
    lv_cy = hv_cy + dy
    # Overlap guarantees: HV-LV centre distance = sqrt(24^2 + 34^2) ~ 41.6 < 2r = 52;
    # LV-LV centre distance = 48 < 52. All three circles interlock as one device.

    vg = str(vector_group or "TBD").strip()
    hv_token, lv_tokens = _parse_vector_group(vg, winding_count)
    mark = r * 0.60

    dwg.add(dwg.circle(center=(x, hv_cy), r=r, class_="sfill", id="tx-hv-winding"))
    _winding_mark(dwg, x, hv_cy - r * 0.28, hv_token, size=mark, fallback_text=vg,
                  id_prefix="tx-hv-winding")

    terminals: list[tuple[float, float]] = []
    for winding_index in range(1, winding_count + 1):
        sign = -1.0 if winding_index == 1 else 1.0
        cx = x + sign * dx
        dwg.add(dwg.circle(center=(cx, lv_cy), r=r, class_="sfill",
                           id=f"tx-lv-winding-{winding_index}"))
        lv_token = lv_tokens[winding_index - 1] if lv_tokens else ""
        _winding_mark(dwg, cx + sign * r * 0.20, lv_cy + r * 0.16, lv_token,
                      size=mark, fallback_text=vg,
                      id_prefix=f"tx-lv-winding-{winding_index}")
        # Identify each secondary beside its own outgoing lead, on the outer
        # side, below the symbol: the draft watermark band sits over the
        # transformer and must not hide the LV-A / LV-B distinction.
        terminal = (cx, lv_cy + r)
        terminals.append(terminal)
        label_anchor = "end" if sign < 0 else "start"
        _text(dwg, f"LV-{chr(64 + winding_index)}",
              cx + sign * 10.0, terminal[1] + 12.0, "tag", anchor=label_anchor)

    # Nameplate block to the right, top-aligned with the symbol and clear of
    # both the LV-B circle (right edge x+dx+r) and the LV routing elbows below.
    plate_x = x + dx + r + 28.0
    for idx, line in enumerate(text_lines):
        _text(dwg, line, plate_x, y + 6.0 + idx * 13.0, "label")
    if lv_tokens:
        if len(set(lv_tokens)) == 1:
            secondaries_note = f"Secondaries: {winding_count} x {lv_tokens[0]} (LV-A, LV-B)"
        else:
            secondaries_note = "Secondaries: " + ", ".join(
                f"LV-{chr(65 + i)}: {token}" for i, token in enumerate(lv_tokens)
            )
        _text(dwg, secondaries_note, plate_x, y + 6.0 + len(text_lines) * 13.0, "label")

    return hv_cy - r, terminals


def _transformer_vector_group_confirmed(vector_group: str, winding_count: int) -> bool:
    """True only when the vector group parses into exactly one LV token per
    independent LV winding (e.g. ``Dyn11`` for 1, ``Dyn11yn11`` for 2)."""
    hv_token, lv_tokens = _parse_vector_group(str(vector_group or "").strip(), winding_count)
    return bool(hv_token) and len(lv_tokens) == winding_count


def _default_vector_group(winding_count: int) -> str:
    """Standard MV step-up default used when the OEM value is unconfirmed.

    ``Dyn11`` for a single LV secondary; ``Dyn11yn11`` for a split (two-LV)
    secondary. Every SLD this tool emits is a watermarked concept document, so an
    unconfirmed transformer is drawn with the industry-standard default and
    annotated as assumed rather than suppressed behind a placeholder box
    (owner decision, 2026-07-29).
    """
    if winding_count <= 1:
        return "Dyn11"
    return "Dyn11" + "yn11" * (winding_count - 1)


def _pcs_by_lv_winding(plan: SldV2LayoutPlan) -> dict[int, list[SldV2LayoutBox]]:
    groups: dict[int, list[SldV2LayoutBox]] = {}
    for pcs in _boxes_by_type(plan, "pcs"):
        winding_index = int(pcs.attributes.get("lv_winding_index") or 1)
        groups.setdefault(winding_index, []).append(pcs)
    return {
        winding_index: sorted(boxes, key=lambda box: int(box.feeder_index or 0))
        for winding_index, boxes in sorted(groups.items())
    }


def _feeder_span_text(boxes: list[SldV2LayoutBox]) -> str:
    feeder_indices = sorted(int(box.feeder_index or 0) for box in boxes if box.feeder_index)
    if not feeder_indices:
        return "Feeders TBD"
    if len(feeder_indices) == 1:
        return f"Feeder F{feeder_indices[0]}"
    return f"Feeders F{feeder_indices[0]}–F{feeder_indices[-1]}"


def _pcs_symbol(dwg, x: float, y: float, width: float, height: float,
                label: str, subtitle: str = "", tag: str = "") -> None:
    """PCS bidirectional AC/DC converter — BESS industry SLD convention.

    Top half: AC side (sine-wave arc above centre line).
    Bottom half: DC side (two horizontal parallel bars).
    Bidirectional arrows on the vertical spine show power flow in both modes.
    """
    lx = x - width / 2.0
    _rect(dwg, lx, y, width, height, "sfill")

    mid_y = y + height * 0.50
    # Horizontal centre divider (light)
    _line(dwg, (lx + 4.0, mid_y), (lx + width - 4.0, mid_y), "thin")

    # AC symbol (top half) — single-cycle sine arc
    ac_cy = y + height * 0.26
    ac_w  = width * 0.55
    ac_h  = height * 0.16
    pts = []
    for i in range(17):
        t = i / 16.0
        pts.append((x - ac_w / 2.0 + t * ac_w,
                    ac_cy - ac_h * math.sin(t * math.pi * 2.0)))
    dwg.add(dwg.polyline(points=pts, class_="thin", fill="none"))

    # DC symbol (bottom half) — two horizontal parallel bars
    dc_cy = y + height * 0.76
    for dy, half in ((-4.0, width * 0.25), (4.0, width * 0.18)):
        _line(dwg, (x - half, dc_cy + dy), (x + half, dc_cy + dy), "thin")

    # Bidirectional arrows on right spine — indicate reversible operation
    spine_x = lx + width * 0.82
    # Up arrow (discharge: DC→AC)
    arr_y1 = mid_y - 10.0
    _line(dwg, (spine_x, mid_y - 4.0), (spine_x, arr_y1), "thin")
    _line(dwg, (spine_x - 4.0, arr_y1 + 5.0), (spine_x, arr_y1), "thin")
    _line(dwg, (spine_x + 4.0, arr_y1 + 5.0), (spine_x, arr_y1), "thin")
    # Down arrow (charge: AC→DC)
    arr_y2 = mid_y + 10.0
    _line(dwg, (spine_x, mid_y + 4.0), (spine_x, arr_y2), "thin")
    _line(dwg, (spine_x - 4.0, arr_y2 - 5.0), (spine_x, arr_y2), "thin")
    _line(dwg, (spine_x + 4.0, arr_y2 - 5.0), (spine_x, arr_y2), "thin")

    # Rating label to the right
    rx = x + width / 2.0 + 6.0
    _text(dwg, label,    rx, y + height * 0.38, "label")
    if subtitle:
        _text(dwg, subtitle, rx, y + height * 0.62, "label")
    if tag:
        _text(dwg, tag, x - width / 2.0 - 4.0, y + 8.0, "tag", anchor="end")


def _dc_isolator_fuse(dwg, x: float, y: float, height: float = 72.0,
                      tag: str = "") -> tuple[float, float]:
    """DC isolator-switch + fuse in series (per ANSI 315 Fig 2.14 + 2.30).

    Returns (top_y, bottom_y) for wire connections.
    """
    top_y = y - height / 2.0
    bottom_y = y + height / 2.0
    sw_top = top_y + 4.0
    sw_bot = top_y + 26.0
    fuse_top = top_y + 34.0
    fuse_bot = fuse_top + 20.0

    # Wire stub in
    _line(dwg, (x, top_y), (x, sw_top), "wire")
    # Disconnect switch: upper moving contact (circle) + open blade + lower fixed contact (bar)
    dwg.add(dwg.circle(center=(x, sw_top), r=2.5, class_="sfill"))  # moving contact
    _line(dwg, (x, sw_top), (x + 14.0, sw_bot - 4.0), "thin")      # open blade
    _line(dwg, (x - 6.0, sw_bot), (x + 6.0, sw_bot), "thin")       # fixed contact (horizontal bar)
    # Wire between switch and fuse
    _line(dwg, (x, sw_bot), (x, fuse_top), "wire")
    # Fuse (ANSI rectangle + center line)
    _rect(dwg, x - 5.0, fuse_top, 10.0, fuse_bot - fuse_top, "sfill")
    _line(dwg, (x, fuse_top), (x, fuse_bot), "thin")
    # Wire stub out
    _line(dwg, (x, fuse_bot), (x, bottom_y), "wire")

    if tag:
        _text(dwg, tag, x + 10.0, y + 4.0, "tag")
    return top_y, bottom_y


def _battery_symbol(dwg, cx: float, y: float, sym_w: float, height: float) -> None:
    """ANSI battery glyph (alternating long/short lines) + polarity, centred at cx."""
    batt_top = y + height * 0.18
    batt_bot = y + height * 0.72
    n_cells = 4
    step = (batt_bot - batt_top) / n_cells
    for i in range(n_cells):
        ly = batt_top + i * step
        half = (sym_w * 0.30) if (i % 2 == 0) else (sym_w * 0.18)
        _line(dwg, (cx - half, ly), (cx + half, ly), "thin")
    _text(dwg, "+", cx - sym_w * 0.38, y + height * 0.14, "label")
    _text(dwg, "-", cx - sym_w * 0.38, y + height * 0.80, "label")


def _shared_bess_container(dwg, cx: float, y: float, width: float, height: float,
                           group_xs: list[float], title: str, subtitle: str,
                           tag: str = "") -> None:
    """One DC container holding an INDEPENDENT battery group per PCS output
    circuit: a battery glyph centred under each output terminal, thin dividers
    between groups, drawn compactly (not one stretched glyph)."""
    lx = cx - width / 2.0
    _rect(dwg, lx, y, width, height, "sfill")
    ordered = sorted(group_xs)
    # Pull the battery groups toward the container centre so they sit inside the
    # box rather than hugging the side walls.
    inset = [cx + (gx - cx) * 0.58 for gx in ordered]
    if len(inset) > 1:
        cell = min(inset[i + 1] - inset[i] for i in range(len(inset) - 1))
    else:
        cell = width
    # One consistent battery-glyph size across every DC container (single- or
    # multi-circuit), shrinking only if the cells are genuinely too tight — so all
    # DC Blocks read as the same symbol regardless of PCS:DC ratio.
    sym_w = max(34.0, min(54.0, cell * 0.66))
    for gx in inset:
        _battery_symbol(dwg, gx, y, sym_w, height)
    _text(dwg, title, cx, y + height + 12.0, "label", anchor="middle")
    if subtitle:
        _text(dwg, subtitle, cx, y + height + 24.0, "label", anchor="middle")
    if tag:
        # Bottom-right, below the battery groups (the top edge is occupied by the
        # per-circuit glyphs).
        _text(dwg, tag, cx + width / 2.0 - 5.0, y + height - 6.0, "tag", anchor="end")


def _bess_block(dwg, x: float, y: float, width: float, height: float,
                title: str, subtitle: str, tag: str = "",
                symbol_span: float | None = None) -> None:
    """Single-circuit DC container.

    Delegates to the same drawer as the shared multi-circuit container so EVERY
    DC Block reads identically (same box, battery glyph, tag placement) regardless
    of the PCS:DC ratio — a single-circuit block is just a one-cell container.
    """
    _shared_bess_container(dwg, x, y, width, height, [x], title, subtitle, tag=tag)


def _open_triangle_terminal(dwg, x: float, y: float, size: float = 13.0) -> None:
    """Upward-pointing open triangle = MV feeder terminal (utility supply)."""
    dwg.add(dwg.polygon(
        points=[(x, y), (x - size / 2.0, y + size), (x + size / 2.0, y + size)],
        class_="sfill",
    ))


def _feeder_terminal(dwg, x: float, y_top: float, y_bus: float,
                     label: str, *, blade_right: bool,
                     y_equip_start: float | None = None,
                     tag_ds: str = "", tag_cb: str = "") -> None:
    """MV feeder terminal: triangle (external) → DS → CB → ES → CT → bus.

    y_top     : y-position of the external cable entry triangle (above switchgear box).
    y_equip_start : y-position where the first piece of equipment (DS) is drawn.
                    Defaults to y_top + 40 for backward compatibility.
                    Set explicitly to place equipment below the RMU title-label band.
    y_bus     : y-position of the internal MV bus (bottom of bay).
    """
    if y_equip_start is None:
        y_equip_start = y_top + 40.0

    # External cable entry triangle + feeder label
    _open_triangle_terminal(dwg, x, y_top + 2.0)
    label_x = x - 10.0 if blade_right else x + 10.0
    label_anchor = "end" if blade_right else "start"
    _text(dwg, label, label_x, y_top, "label", anchor=label_anchor)

    # ── Equipment positions ────────────────────────────────────────────────
    ds_y = y_equip_start
    cb_y = y_equip_start + 40.0
    es_y = y_equip_start + 80.0
    ct_y = min(y_equip_start + 116.0, y_bus - 24.0)

    # ── Segmented conductor — wire breaks at DS open gap (ANSI open-contact rule) ──
    # Segment 1: triangle entry → DS moving contact (pivot)
    _line(dwg, (x, y_top + 13.0), (x, ds_y - 8.0), "wire")

    # DS (disconnect switch / isolator)
    _disconnect_switch(dwg, x, ds_y, blade_right=blade_right)
    if tag_ds:
        tag_x = x + (10 if blade_right else -10)
        _text(dwg, tag_ds, tag_x, ds_y - 6.0,
              "tag", anchor="start" if blade_right else "end")

    # Segment 2: DS fixed bar → CB top
    _line(dwg, (x, ds_y + 8.0), (x, cb_y - 12.0), "wire")

    # CB (circuit breaker — sfill rect covers wire through it)
    _circuit_breaker(dwg, x, cb_y)
    if tag_cb:
        _text(dwg, tag_cb, x + 12.0, cb_y + 4.0, "tag")

    # Segment 3: CB bottom → CT top  (passes through ES side-branch junction)
    _line(dwg, (x, cb_y + 12.0), (x, ct_y - 7.0), "wire")

    # Earthing switch — side branch off main conductor (no wire break on main line)
    es_arm = 22.0 if blade_right else -22.0
    arm_tip_x = x + es_arm
    blade_tip_x = arm_tip_x + es_arm * 0.45
    blade_tip_y = es_y + 14.0
    _line(dwg, (x, es_y), (arm_tip_x, es_y), "thin")
    _line(dwg, (arm_tip_x, es_y), (blade_tip_x, blade_tip_y), "thin")
    _ground(dwg, blade_tip_x, blade_tip_y)

    # CT (primary conductor passes through core — no wire break)
    _ct_symbol(dwg, x, ct_y)

    # Segment 4: CT bottom → internal MV bus
    _line(dwg, (x, ct_y + 7.0), (x, y_bus), "wire")


# ---------------------------------------------------------------------------
# Panel: notes / equipment list (left side)
# ---------------------------------------------------------------------------

def _draw_notes_panel(dwg, sheet: ProfessionalSldSheet) -> None:
    notes = sheet.notes
    panel_h = notes.height + 26.0   # 26 = title band; no stray empty band below
    _rect(dwg, notes.x, notes.y, notes.width, panel_h, "sfill")
    dwg.add(dwg.rect(insert=(notes.x, notes.y), size=(notes.width, panel_h), class_="outline"))

    _text(dwg, notes.title,
          notes.x + notes.width / 2.0, notes.y + 18.0, "ntitle", anchor="middle")
    _line(dwg, (notes.x, notes.y + 26.0), (notes.x + notes.width, notes.y + 26.0), "thin")

    cur_y = notes.y + 26.0
    for sec in notes.sections:
        sec_bot = cur_y + sec.height
        _rect(dwg, notes.x, cur_y, notes.width, sec.height, "sfill")
        dwg.add(dwg.rect(insert=(notes.x, cur_y), size=(notes.width, sec.height), class_="outline"))
        _text(dwg, sec.title, notes.x + 8.0, cur_y + 18.0, "ntitle")
        for i, line in enumerate(sec.lines):
            _text(dwg, line, notes.x + 10.0, cur_y + 34.0 + i * 16.0, "notes")
        cur_y = sec_bot


# ---------------------------------------------------------------------------
# MV section: RMU + transformer
# ---------------------------------------------------------------------------

def _draw_mv_rmu_and_transformer(
    dwg, plan: SldV2LayoutPlan, sheet: ProfessionalSldSheet
) -> tuple[float, float]:
    rows = _rows(plan)
    transformer = _first_box(plan, "transformer")
    pcs_by_winding = _pcs_by_lv_winding(plan)
    winding_count = len(pcs_by_winding)
    mv = sheet.mv

    mv_sys = _compact_voltage_label(rows.get("MV System", "MV"))
    vg = rows.get("Transformer", "")
    # Extract vector group from transformer spec string (first field)
    vg_token = ""
    for part in vg.split(","):
        token = part.strip()
        if any(c in token for c in ("D", "Y", "d", "y", "Z", "z")):
            vg_token = token
            break

    # Section heading
    _text(dwg, "PCS & MVT SKID (AC BLOCK)", mv.center_x, 44.0, "title", anchor="middle")

    # ── RMU enclosure box ──────────────────────────────────────────────────
    # Box spans from top_y+28 down to bus_y+16 so it contains all bay equipment.
    # Inside: title band (top 50 px) separated by a horizontal rule from the
    # equipment band (where DS, CB, ES, CT are drawn, starting at y_equip_start).
    rmu_box_x  = mv.ring_in_x - 110.0
    rmu_box_w  = mv.ring_out_x - mv.ring_in_x + 220.0
    rmu_box_y  = mv.top_y + 28.0
    bus_y_internal  = mv.bus_y
    rmu_box_h  = bus_y_internal - rmu_box_y + 16.0
    rmu_title_h = 50.0                           # height of title-label band
    y_equip_start = rmu_box_y + rmu_title_h + 22.0  # DS pivot must clear rule (pivot=y-8)

    _rect(dwg, rmu_box_x, rmu_box_y, rmu_box_w, rmu_box_h, "sfill")
    dwg.add(dwg.rect(insert=(rmu_box_x, rmu_box_y), size=(rmu_box_w, rmu_box_h), class_="outline"))

    # Title band content
    _text(dwg, "RMU-01  /  MV Switchgear",
          mv.center_x, rmu_box_y + 14.0, "title", anchor="middle")
    _text(dwg, mv_sys,
          mv.center_x, rmu_box_y + 28.0, "label", anchor="middle")
    # Bay labels — Ring In/Out offset away from the feeder wire that runs through
    # the title band; 42 keeps a clear gap below the "33kV" system label above.
    _text(dwg, "Ring In",          mv.ring_in_x  - 14.0, rmu_box_y + 42.0, "label", anchor="end")
    _text(dwg, "Transformer Feeder", mv.center_x, rmu_box_y + 42.0, "label", anchor="middle")
    _text(dwg, "Ring Out",         mv.ring_out_x + 14.0, rmu_box_y + 42.0, "label", anchor="start")

    # Horizontal rule separating title band from equipment band
    rule_y = rmu_box_y + rmu_title_h
    _line(dwg, (rmu_box_x, rule_y), (rmu_box_x + rmu_box_w, rule_y), "thin")

    # Bay dividers (vertical, equipment-band only — start at the rule)
    for bx in (mv.ring_in_x + 105.0, mv.ring_out_x - 105.0):
        _line(dwg, (bx, rule_y), (bx, rmu_box_y + rmu_box_h), "thin")

    # Internal MV bus at mv.bus_y
    _line(dwg, (mv.ring_in_x - 90.0, bus_y_internal),
               (mv.ring_out_x + 90.0, bus_y_internal), "busbar")

    # Ring In feeder terminal
    _feeder_terminal(dwg, mv.ring_in_x, mv.top_y,
                     bus_y_internal, f"To {mv_sys} Switchgear",
                     blade_right=False, y_equip_start=y_equip_start,
                     tag_ds="DS-01", tag_cb="52-01")
    _junction(dwg, mv.ring_in_x, bus_y_internal)

    # Ring Out feeder terminal
    _feeder_terminal(dwg, mv.ring_out_x, mv.top_y,
                     bus_y_internal, "To Other RMU",
                     blade_right=True, y_equip_start=y_equip_start,
                     tag_ds="DS-02", tag_cb="52-02")
    _junction(dwg, mv.ring_out_x, bus_y_internal)

    # ── Transformer feeder branch ──────────────────────────────────────────
    # ── Transformer feeder — segmented conductor, DS open gap visible ─────────
    _junction(dwg, mv.center_x, bus_y_internal)

    # Equipment positions (DS-TX pushed 12px lower so pivot clears RMU box bottom)
    ds_y = bus_y_internal + 40.0   # pivot at bus_y+32, RMU box bottom at bus_y+16 → 16px clear
    cb_y = bus_y_internal + 80.0
    ct_y = bus_y_internal + 120.0

    # Segment 1: bus → DS moving contact
    _line(dwg, (mv.center_x, bus_y_internal), (mv.center_x, ds_y - 8.0), "wire")
    _disconnect_switch(dwg, mv.center_x, ds_y, blade_right=True)
    _text(dwg, "DS-TX", mv.center_x + 12.0, ds_y - 6.0, "tag")

    # Segment 2: DS fixed bar → CB top
    _line(dwg, (mv.center_x, ds_y + 8.0), (mv.center_x, cb_y - 12.0), "wire")
    _circuit_breaker(dwg, mv.center_x, cb_y)
    _text(dwg, "52-TX", mv.center_x - 12.0, cb_y + 4.0, "tag", anchor="end")

    # Segment 3: CB bottom → CT top
    _line(dwg, (mv.center_x, cb_y + 12.0), (mv.center_x, ct_y - 7.0), "wire")
    _ct_symbol(dwg, mv.center_x, ct_y)
    _text(dwg, "CT-TX", mv.center_x + 12.0, ct_y + 4.0, "tag")

    # Segment 4: CT bottom → cable hash / HV terminal area
    _line(dwg, (mv.center_x, ct_y + 7.0), (mv.center_x, mv.transformer_y - 32.0), "wire")

    # MV cable hash marks (above HV terminal)
    _cable_3phase(dwg, mv.center_x, mv.transformer_y - 40.0)

    # ── Transformer ────────────────────────────────────────────────────────
    # Defensive gate: a transformer that declares N LV windings must resolve to
    # exactly N PCS groups, otherwise the drawing would silently show fewer
    # secondaries than the equipment list promises.
    declared_windings = int((transformer.attributes if transformer else {}).get("lv_winding_count") or 0)
    if declared_windings > 1 and declared_windings != winding_count:
        raise ValueError(
            f"transformer declares {declared_windings} LV windings but PCS groups "
            f"resolve to {winding_count} — refusing to draw an incomplete secondary"
        )

    # Filter standalone vector-group token from text lines (already drawn as winding marks)
    raw_lines = transformer.text_lines[1:] if transformer else ()
    filtered_lines = tuple(ln for ln in raw_lines if ln.strip() != (vg_token or "TBD"))
    # Concept SLD rule (owner decision, 2026-07-29): an unconfirmed vector group
    # no longer suppresses the winding symbol. Draw the real interlocked-circle
    # transformer with the standard default (Dyn11 / Dyn11yn11) and annotate the
    # nameplate as an assumed default. The formal-readiness gate independently
    # keeps the sheet a watermarked concept until a real vector group is
    # confirmed, so the drawing stays readable without over-claiming.
    if _transformer_vector_group_confirmed(vg_token, winding_count):
        vg_effective = vg_token
        tx_lines = filtered_lines
    else:
        vg_effective = _default_vector_group(winding_count)
        tx_lines = filtered_lines + (
            f"Vector group {vg_effective} assumed (standard default - to be confirmed)",
        )

    if winding_count > 1:
        tx_top, tx_lv_terminals = _transformer_split_secondary(
            dwg,
            mv.center_x,
            mv.transformer_y,
            vg_effective,
            tx_lines,
            winding_count,
        )
    else:
        tx_top, tx_bot = _transformer_2w(
            dwg, mv.center_x, mv.transformer_y,
            vg_effective, tx_lines,
        )
        tx_lv_terminals = [(mv.center_x, tx_bot)]
    _text(dwg, "T-01", mv.center_x - 62.0, mv.transformer_y + 18.0, "tag", anchor="end")

    # Short wire connecting feeder branch to HV terminal
    _line(dwg, (mv.center_x, mv.transformer_y - 32.0), (mv.center_x, tx_top), "wire")
    # Separate secondaries are routed independently to their corresponding LV
    # winding busbars. There is deliberately no common LV conductor between
    # these paths. Elbows run below the LV-A/LV-B lead labels so the wires
    # never cross the transformer nameplate text.
    for (winding_index, pcs_boxes), terminal in zip(sorted(pcs_by_winding.items()), tx_lv_terminals):
        target_x = sum(box.x + box.width / 2.0 for box in pcs_boxes) / len(pcs_boxes)
        elbow_y = terminal[1] + 24.0
        _poly(
            dwg,
            [terminal, (terminal[0], elbow_y), (target_x, elbow_y), (target_x, mv.lv_bus_y)],
            "wire",
            id=f"transformer-lv-winding-{winding_index}",
        )
        # Junction dot only where the secondary lands on a real busbar (≥2 PCS);
        # a single-PCS winding continues straight into the one feeder.
        if len(pcs_boxes) > 1:
            _junction(dwg, target_x, mv.lv_bus_y)

    return mv.center_x, mv.lv_bus_y


# ---------------------------------------------------------------------------
# LV busbar + PCS + DC section
# ---------------------------------------------------------------------------

def _draw_lv_pcs_dc(dwg, plan: SldV2LayoutPlan, sheet: ProfessionalSldSheet) -> None:
    pcs_boxes = _boxes_by_type(plan, "pcs")
    dc_boxes  = _boxes_by_type(plan, "dc_block")

    if not pcs_boxes:
        return

    lvdc = sheet.lvdc
    mv   = sheet.mv
    pcs_by_winding = _pcs_by_lv_winding(plan)
    shared_dc_boxes = [
        block
        for block in dc_boxes
        if len([int(feeder) for feeder in (block.attributes.get("feeder_span") or [])]) > 1
    ]
    local_dc_by_feeder: dict[int, list[SldV2LayoutBox]] = {}
    for block in dc_boxes:
        if block in shared_dc_boxes:
            continue
        local_dc_by_feeder.setdefault(int(block.feeder_index or 0), []).append(block)

    lv_v = _fmt_number(
        (pcs_boxes[0].attributes if pcs_boxes else {}).get("lv_voltage_v_ll"), decimals=0
    )
    bus_y_by_winding: dict[int, float] = {}
    winding_bus_extents: list[tuple[int, float, float]] = []
    split_secondary = len(pcs_by_winding) > 1

    # Independent LV secondary busbars must never overhang into each other. With
    # a wide feeder count (e.g. 8 PCS split 4+4) the fixed ±90 pad exceeds the
    # inter-winding gap, so each secondary's inner edge is clamped to the
    # boundary midpoint — keeping the two secondaries visibly separate (and the
    # "NO LV BUS TIE" tag correct) without changing the common-bus case.
    _bus_pad = 90.0
    _bus_gap_margin = 8.0
    _winding_center_span = {
        winding_index: (
            min(pcs.x + pcs.width / 2.0 for pcs in winding_pcs),
            max(pcs.x + pcs.width / 2.0 for pcs in winding_pcs),
        )
        for winding_index, winding_pcs in pcs_by_winding.items()
    }
    _ordered_windings = sorted(_winding_center_span, key=lambda idx: _winding_center_span[idx][0])
    _clamped_bus_extents: dict[int, tuple[float, float]] = {}
    for _pos, _wi in enumerate(_ordered_windings):
        _left_center, _right_center = _winding_center_span[_wi]
        _bx1 = _left_center - _bus_pad
        _bx2 = _right_center + _bus_pad
        if _pos > 0:
            _prev_right = _winding_center_span[_ordered_windings[_pos - 1]][1]
            _bx1 = max(_bx1, (_prev_right + _left_center) / 2.0 + _bus_gap_margin)
        if _pos < len(_ordered_windings) - 1:
            _next_left = _winding_center_span[_ordered_windings[_pos + 1]][0]
            _bx2 = min(_bx2, (_right_center + _next_left) / 2.0 - _bus_gap_margin)
        _clamped_bus_extents[_wi] = (_bx1, _bx2)

    # AC Block boundary — the RMU/MV switchgear, the step-up transformer and the
    # PCS all belong to ONE AC Block; draw an explicit boundary around them (down
    # to just above the DC Blocks, which are separate) so the single-line reads
    # as a physical AC Block skid, not loose symbols.
    _panel_lefts = [bx1 - 20.0 for bx1, _bx2 in _clamped_bus_extents.values()]
    _panel_rights = [bx2 + 20.0 for _bx1, bx2 in _clamped_bus_extents.values()]
    ac_x1 = min(min(_panel_lefts), mv.ring_in_x - 110.0) - 16.0
    ac_x2 = max(max(_panel_rights), mv.ring_out_x + 110.0) + 16.0
    ac_y1 = 30.0
    ac_y2 = lvdc.pcs_y + lvdc.converter_height + 34.0
    dwg.add(dwg.rect(insert=(ac_x1, ac_y1), size=(ac_x2 - ac_x1, ac_y2 - ac_y1),
                     class_="acblock", id="ac-block-boundary"))
    _text(dwg, "AC BLOCK BOUNDARY", ac_x1 + 12.0, ac_y1 + 20.0, "acblocktx", anchor="start")

    for winding_index, winding_pcs in pcs_by_winding.items():
        bus_x1, bus_x2 = _clamped_bus_extents[winding_index]
        bus_y = mv.lv_bus_y
        bus_y_by_winding[winding_index] = bus_y
        winding_bus_extents.append((winding_index, bus_x1, bus_x2))

        # A three-winding transformer has two independent LV secondary
        # distribution sections.  Give each one a visible boundary and a
        # feeder range so it cannot be mistaken for a single common busbar.
        panel_y = bus_y - 40.0
        panel_bottom = lvdc.pcs_y + lvdc.converter_height + 22.0
        panel_x = bus_x1 - 20.0
        panel_width = bus_x2 - bus_x1 + 40.0
        _rect(dwg, panel_x, panel_y, panel_width, panel_bottom - panel_y, "outline")
        section_label = (
            f"LV-{chr(64 + winding_index)} DISTRIBUTION SECTION"
            if split_secondary
            else "LV DISTRIBUTION SECTION — COMMON BUS"
        )
        secondary_label = (
            f"Secondary LV-{chr(64 + winding_index)}  •  {_feeder_span_text(winding_pcs)}"
            if split_secondary
            else _feeder_span_text(winding_pcs)
        )
        _text(dwg, section_label, panel_x + 12.0, bus_y - 20.0, "title")
        _text(dwg, secondary_label, panel_x + 12.0, bus_y - 6.0, "label")
        # A busbar is only meaningful when it collects more than one feeder. When
        # an LV winding serves a single PCS there is nothing to bus together, so
        # the transformer secondary connects straight to that one PCS feeder — no
        # redundant LV busbar line (and no "LV BUS" label) is drawn.
        if len(winding_pcs) > 1:
            _line(
                dwg,
                (bus_x1, bus_y),
                (bus_x2, bus_y),
                "busbar",
                id=f"lv-winding-{winding_index}-busbar",
            )
            label = f"LV-{chr(64 + winding_index)} BUS / {lv_v} V" if split_secondary else f"LV BUS / {lv_v} V"
            _text(dwg, label, bus_x2 - 8.0, bus_y - 6.0, "label", anchor="end")

    if split_secondary and len(winding_bus_extents) == 2:
        _, left_x1, left_x2 = winding_bus_extents[0]
        _, right_x1, right_x2 = winding_bus_extents[1]
        if left_x2 < right_x1:
            # The horizontal gap between the two busbars is too narrow for a
            # horizontal note without hitting the LV-B / DS-F05 labels, so draw
            # the tie note VERTICALLY in the empty inter-winding column (between
            # the last LV-A feeder and the first LV-B feeder).
            tie_x = (left_x2 + right_x1) / 2.0
            tie_y = mv.lv_bus_y + 60.0
            _text(dwg, "NO LV BUS TIE", tie_x, tie_y, "tag", anchor="middle",
                  transform=f"rotate(-90 {tie_x:.1f} {tie_y:.1f})")

    # (No floating "BATTERY STORAGE BANK" heading: the battery band is fully
    # occupied by vertical feeder drops at every feeder_x, so a centred title
    # unavoidably lands on a conductor. The section is already identified by the
    # equipment list and each block's "DC Block #N / BESS-0N" label.)

    dc_bottom_by_feeder: dict[int, float] = {}
    pcs_x_by_feeder: dict[int, float] = {}
    for fi, pcs in enumerate(pcs_boxes, start=1):
        fi = int(pcs.feeder_index or fi)
        px = pcs.x + pcs.width / 2.0
        winding_index = int(pcs.attributes.get("lv_winding_index") or 1)
        bus_y = bus_y_by_winding[winding_index]
        pcs_label = pcs.text_lines[0] if pcs.text_lines else f"PCS {fi}"
        pcs_sub   = pcs.text_lines[1] if len(pcs.text_lines) > 1 else ""

        # ── LV feeder — segmented conductor, DS open gap visible ─────────────
        # Tap dot only where the feeder taps a real busbar (≥2 PCS on the
        # winding); a single-PCS winding connects straight through, no tap.
        if len(pcs_by_winding.get(winding_index, [])) > 1:
            _junction(dwg, px, bus_y)
        ds_y = bus_y + 28.0
        cb_y = bus_y + 56.0

        # Segment 1: LV bus → DS moving contact (pivot)
        _line(dwg, (px, bus_y), (px, ds_y - 8.0), "wire")
        _disconnect_switch(dwg, px, ds_y, blade_right=True)
        _text(dwg, f"DS-F{fi:02d}", px - 10.0, ds_y - 6.0, "tag", anchor="end")

        # Segment 2: DS fixed bar → CB top
        _line(dwg, (px, ds_y + 8.0), (px, cb_y - 12.0), "wire")
        _circuit_breaker(dwg, px, cb_y)
        _text(dwg, f"52-F{fi:02d}", px + 12.0, cb_y + 4.0, "tag")

        # Segment 3: CB bottom → PCS top
        _line(dwg, (px, cb_y + 12.0), (px, lvdc.pcs_y), "wire")

        # PCS box
        _pcs_symbol(dwg, px, lvdc.pcs_y,
                    lvdc.converter_width, lvdc.converter_height,
                    pcs_label, pcs_sub, tag=f"INV-{fi:02d}")

        # Wire: PCS bottom → DC isolator/fuse
        _line(dwg, (px, lvdc.pcs_y + lvdc.converter_height),
                   (px, lvdc.dc_device_y - lvdc.converter_height * 0.5), "wire")

        dc_top, dc_bot = _dc_isolator_fuse(
            dwg, px, lvdc.dc_device_y, tag=f"F-{fi:02d}"
        )
        dc_bottom_by_feeder[fi] = dc_bot
        pcs_x_by_feeder[fi] = px

        # Per-feeder DC blocks retain the previous 1:1 / multi-block drawing.
        blocks = sorted(local_dc_by_feeder.get(fi, []),
                        key=lambda b: b.dc_block_index or 0)
        if not blocks:
            continue

        multi = len(blocks) > 1
        # The horizontal branch must sit BELOW the fuse outlet (dc_bot),
        # otherwise the drop wire would double back up across the fuse stub.
        branch_y = max(lvdc.block_y - (30.0 if multi else 10.0), dc_bot + 8.0)

        if multi:
            spc = min(lvdc.multi_block_spacing_max,
                      lvdc.multi_block_spacing_base + max(0, len(blocks) - 2) * 18.0)
            start = px - spc * (len(blocks) - 1) / 2.0
            bx_list = [start + spc * i for i in range(len(blocks))]
            # Horizontal branch bus + T-junction at feeder centre
            _line(dwg, (min(bx_list), branch_y), (max(bx_list), branch_y), "wire")
            _junction(dwg, px, branch_y)
        else:
            bx_list = [px]

        # Wire: DC fuse bottom → branch point
        _line(dwg, (px, dc_bot), (px, branch_y), "wire")

        for blk, bx in zip(blocks, bx_list):
            _line(dwg, (bx, branch_y), (bx, lvdc.block_y), "wire")
            # Junction only where a vertical drop meets the horizontal branch bus
            if multi:
                _junction(dwg, bx, branch_y)
            b_title = blk.text_lines[0] if blk.text_lines else "BESS"
            b_sub   = blk.text_lines[1] if len(blk.text_lines) > 1 else ""
            gi      = int(blk.dc_block_index or 0)
            _bess_block(dwg, bx, lvdc.block_y,
                        lvdc.battery_width, lvdc.battery_height,
                        b_title, b_sub, tag=f"BESS-{gi:02d}")

    # ELECTRICAL RULE (owner decision, 2026-07-13 session): a PCS DC input must
    # NEVER share a DC busbar with another PCS. A shared DC Block exposes one
    # INDEPENDENT output circuit per PCS (its common bus lives INSIDE the block),
    # so each PCS feeder is routed as its own branch to its own output terminal on
    # the block — no common conductor, junction dot or horizontal "branch bus"
    # joining two PCS DC sides outside the block.
    #
    # LAYOUT (owner decision, 2026-07-29): do NOT converge the feeders left/right
    # onto a small centred block — that reads as one block fed from both sides.
    # Instead draw ONE WIDE multi-port container that spans under the feeders it
    # serves, and drop each PCS STRAIGHT DOWN into its own output terminal
    # directly beneath that PCS. No horizontal elbows.
    for block in sorted(shared_dc_boxes, key=lambda item: int(item.dc_block_index or 0)):
        feeder_span = [int(feeder) for feeder in (block.attributes.get("feeder_span") or [])]
        if not feeder_span or any(feeder not in dc_bottom_by_feeder for feeder in feeder_span):
            raise ValueError(f"shared DC block has unresolved feeder connection(s): {block.node_id}")
        output_circuits = int(block.attributes.get("output_circuit_count") or len(feeder_span))
        if len(feeder_span) > output_circuits:
            raise ValueError(
                f"DC block {block.node_id} feeds {len(feeder_span)} PCS but exposes "
                f"only {output_circuits} output circuit(s)"
            )
        prefix = f"shared-dc-{block.node_id}"
        # The container spans just under the feeders it serves (compact — not a
        # full-width slab), with one INDEPENDENT battery group per PCS output
        # circuit drawn inside, directly beneath its own straight-drop terminal.
        feeder_xs = [pcs_x_by_feeder[feeder] for feeder in feeder_span]
        left_x, right_x = min(feeder_xs), max(feeder_xs)
        block_cx = (left_x + right_x) / 2.0
        edge_pad = 26.0
        block_w = (right_x - left_x) + 2 * edge_pad
        for circuit_index, feeder_index in enumerate(feeder_span, start=1):
            terminal_x = pcs_x_by_feeder[feeder_index]
            # Straight vertical drop: fuse outlet → its own terminal on block top.
            _poly(
                dwg,
                [
                    (terminal_x, dc_bottom_by_feeder[feeder_index]),
                    (terminal_x, lvdc.block_y),
                ],
                "wire",
                id=f"{prefix}-F{feeder_index:02d}",
            )
            _text(dwg, f"OUT-{circuit_index}", terminal_x + 8.0, lvdc.block_y - 6.0,
                  "tag", anchor="start")
        b_title = block.text_lines[0] if block.text_lines else "BESS"
        b_sub = block.text_lines[1] if len(block.text_lines) > 1 else ""
        dc_block_index = int(block.dc_block_index or 0)
        _shared_bess_container(
            dwg,
            block_cx,
            lvdc.block_y,
            block_w,
            lvdc.battery_height,
            feeder_xs,
            b_title,
            b_sub,
            tag=f"BESS-{dc_block_index:02d}",
        )


# ---------------------------------------------------------------------------
# Title block (ANSI Y14.1 style, no company/logo)
# ---------------------------------------------------------------------------

def _clip_text(text: str, avail_px: float, char_px: float) -> str:
    """Truncate *text* with an ellipsis so its estimated width fits *avail_px*."""
    if avail_px <= 0 or not text:
        return text
    max_chars = int(avail_px / max(1.0, char_px))
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip() + "…"


def _draw_title_block(dwg, tb: ProfessionalTitleBlock, plan: SldV2LayoutPlan) -> None:
    x, y, w, h = tb.x, tb.y, tb.width, tb.height

    # Outer border
    dwg.add(dwg.rect(insert=(x, y), size=(w, h), class_="outline"))

    # Column dividers
    for cx in (tb.desc_col_right, tb.drg_col_right, tb.rev_col_right):
        _line(dwg, (cx, y), (cx, y + h), "thin")

    # Horizontal mid-line
    mid_y = y + h / 2.0
    _line(dwg, (x, mid_y), (x + w, mid_y), "thin")

    # --- Main description column (left) ---
    # Defensive clip so neither line can overrun into the DRG-NO column on a
    # compact sheet (title is 13 px bold, subtitle 10 px).
    desc_avail = tb.desc_col_right - (x + 10.0) - 10.0
    _text(dwg, _clip_text(tb.drawing_title, desc_avail, 8.0),
          x + 10.0, y + h * 0.30, "tbtitle")
    _text(dwg, _clip_text(tb.drawing_subtitle, desc_avail, 5.9),
          x + 10.0, y + h * 0.65, "tb")

    # --- DRG No column ---
    drg_x = tb.desc_col_right + 8.0
    _text(dwg, "DRG NO.", drg_x, y + 14.0, "tb")
    _text(dwg, tb.drg_number, drg_x, mid_y - 6.0, "tbh")
    _text(dwg, "DATE", drg_x, mid_y + 14.0, "tb")
    date_str = tb.date or datetime.date.today().isoformat()
    _text(dwg, date_str, drg_x, y + h - 8.0, "tb")

    # --- REV column ---
    rev_x = tb.drg_col_right + 8.0
    _text(dwg, "REV", rev_x, y + 14.0, "tb")
    _text(dwg, tb.revision, rev_x, mid_y - 6.0, "tbh")

    # --- Scale / info column ---
    inf_x = tb.rev_col_right + 8.0
    _text(dwg, "SCALE", inf_x, y + 14.0, "tb")
    _text(dwg, tb.scale, inf_x, mid_y - 6.0, "tbh")
    _text(dwg, "UNITS: mm", inf_x, mid_y + 14.0, "tb")
    _text(dwg, "ANSI / IEEE 315", inf_x, y + h - 8.0, "tb")


# ---------------------------------------------------------------------------
# Debug overlays (port anchors + connector paths)
# ---------------------------------------------------------------------------

def _draw_debug_connectors(dwg, plan: SldV2LayoutPlan) -> None:
    for connector in plan.connectors:
        if len(connector.points) == 2:
            _line(dwg, connector.points[0], connector.points[1],
                  "thin", opacity="0.4", id=f"edge-{connector.edge_id}")
        else:
            _poly(dwg, connector.points, "thin",
                  opacity="0.4", id=f"edge-{connector.edge_id}")


def _draw_port_anchors(dwg, plan: SldV2LayoutPlan) -> None:
    for anchor in plan.port_anchors:
        dwg.add(dwg.circle(
            center=(anchor.x, anchor.y), r=2.4,
            class_="sfill",
            id=f"port-{anchor.node_id}-{anchor.port_id}",
        ))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_sld_engineering_v2_svg(
    plan: SldV2LayoutPlan,
    out_svg: Path,
    out_png: Path | None = None,
    *,
    show_port_anchors: bool = False,
) -> tuple[Path | None, str | None]:
    """Render a professional ANSI/IEEE 315 BESS single-line diagram.

    Consumes only the resolved V2 layout plan. Does not read topology,
    AC output dicts, DC snapshots, or Streamlit session state.
    """
    if svgwrite is None:
        return None, "Missing dependency: svgwrite. Install: pip install svgwrite"

    sheet = build_professional_sld_sheet(plan)
    dwg   = _build_drawing(plan)

    # Drawing border (outermost frame)
    dwg.add(dwg.rect(
        insert=(20, 20), size=(plan.width - 40, plan.height - 40),
        class_="outline",
    ))

    _draw_notes_panel(dwg, sheet)
    _draw_mv_rmu_and_transformer(dwg, plan, sheet)
    _draw_lv_pcs_dc(dwg, plan, sheet)
    _draw_title_block(dwg, sheet.title_block, plan)

    if show_port_anchors:
        _draw_debug_connectors(dwg, plan)
        _draw_port_anchors(dwg, plan)

    out_svg = Path(out_svg)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    dwg.saveas(str(out_svg))

    # Rendered-output quality gate: geometric defects (winding circles that do
    # not interlock, text intruding into the title block) surface as a warning
    # so callers and tests see them even when the layout plan validated clean.
    gate_issues = [
        issue for issue in validate_rendered_sld_svg(dwg.tostring())
        if issue.severity == "error"
    ]
    warnings: list[str] = []
    if gate_issues:
        warnings.append(
            "Rendered-SVG quality gate: " + "; ".join(issue.message for issue in gate_issues)
        )
    if out_png is not None:
        out_png = Path(out_png)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        try:
            _write_png(out_svg, out_png)
        except ImportError:
            warnings.append("Missing dependency: cairosvg. PNG export skipped.")
        except Exception:
            warnings.append("PNG export failed.")

    return out_svg, ("; ".join(warnings) if warnings else None)
