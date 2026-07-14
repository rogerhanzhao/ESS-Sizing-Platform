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

import math
from pathlib import Path
from typing import List, Tuple
try:  # pragma: no cover - optional dependency
    import svgwrite
except Exception:  # pragma: no cover
    svgwrite = None

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
)

try:
    import cairosvg
except Exception:  # pragma: no cover - optional dependency
    cairosvg = None
def _draw_triangle_up_tip(dwg, tip_x: float, tip_y: float, size: float) -> None:
    """Up-pointing triangle where (tip_x, tip_y) is the tip point."""
    half = size * 0.6
    base_y = tip_y + size
    points = [(tip_x, tip_y), (tip_x - half, base_y), (tip_x + half, base_y)]
    dwg.add(dwg.polygon(points=points, class_="thin", fill="none"))


def _draw_arrow_head_right(dwg, x: float, y: float, size: float) -> None:
    """Simple open arrow head pointing right, tip at (x, y)."""
    half = size * 0.6
    points = [(x, y), (x - size, y - half), (x - size, y + half)]
    dwg.add(dwg.polygon(points=points, class_="thin", fill="none"))

def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def format_mva(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    return f"{v:.1f} MVA"


def format_kv(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    return f"{v:.1f} kV"


def format_v(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    return f"{v:.0f} V"


def format_percent(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    return f"{v:.1f}%"


def format_mwh(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    return f"{v:.3f} MWh"


def format_kv_plain(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    if abs(v - round(v)) < 1e-3:
        return f"{int(round(v))}kV"
    return f"{v:.1f}kV"


def format_v_plain(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    if v >= 1000:
        return f"{v:.0f}V"
    return f"{v:.0f}V"


def _estimate_current_a(power_kw: float, voltage_v: float) -> float:
    if power_kw <= 0 or voltage_v <= 0:
        return 0.0
    return power_kw * 1000.0 / (math.sqrt(3) * voltage_v)


def _estimate_dc_current_a(power_kw: float, voltage_v: float) -> float:
    if power_kw <= 0 or voltage_v <= 0:
        return 0.0
    return power_kw * 1000.0 / voltage_v


def _pick_pcs_rating_kw(spec: SldGroupSpec) -> float:
    for rating in spec.pcs_rating_kw_list:
        if rating:
            return rating
    return 0.0


def _draw_pcs_dc_ac_symbol(dwg, x: float, y: float, w: float, h: float) -> None:
    if w <= 0 or h <= 0:
        return
    pad = min(w, h) * 0.18
    inner_x = x + pad
    inner_y = y + pad
    inner_w = max(1.0, w - pad * 2)
    inner_h = max(1.0, h - pad * 2)

    # Diagonal conversion slash (IEC-style orientation).
    dwg.add(
        dwg.line(
            (inner_x, inner_y),
            (inner_x + inner_w, inner_y + inner_h),
            class_="thin",
        )
    )

    # DC lines (bottom-left).
    dc_len = inner_w * 0.35
    dc_x1 = inner_x
    dc_x2 = inner_x + dc_len
    dc_y_base = inner_y + inner_h - inner_h * 0.18
    dc_gap = inner_h * 0.12
    dwg.add(dwg.line((dc_x1, dc_y_base), (dc_x2, dc_y_base), class_="thin"))
    dwg.add(dwg.line((dc_x1, dc_y_base - dc_gap), (dc_x2, dc_y_base - dc_gap), class_="thin"))

    # AC sine (top-right).
    ac_x1 = inner_x + inner_w * 0.65
    ac_x2 = inner_x + inner_w
    wave_w = max(1.0, ac_x2 - ac_x1)
    wave_amp = inner_h * 0.12
    wave_mid_y = inner_y + inner_h * 0.18
    points = []
    steps = 6
    for idx in range(steps + 1):
        t = idx / steps
        px = ac_x1 + t * wave_w
        py = wave_mid_y + math.sin(t * math.pi * 2) * wave_amp
        points.append((px, py))
    dwg.add(dwg.polyline(points=points, class_="thin", fill="none"))


def _draw_breaker_x(dwg, x: float, y: float, size: float) -> None:
    half = size * 0.5
    dwg.add(dwg.line((x - half, y - half), (x + half, y + half), class_="thin"))
    dwg.add(dwg.line((x - half, y + half), (x + half, y - half), class_="thin"))


def _draw_dc_switch(dwg, x: float, y: float, h: float) -> None:
    blade_dx = h * 0.45
    blade_dy = h * 0.45
    contact_w = h * 0.4
    dwg.add(dwg.line((x, y), (x + blade_dx, y + blade_dy), class_="thin"))
    dwg.add(
        dwg.line(
            (x - contact_w / 2, y + h),
            (x + contact_w / 2, y + h),
            class_="thin",
        )
    )


def _draw_fuse(dwg, x: float, y: float, w: float, h: float) -> None:
    dwg.add(
        dwg.rect(
            insert=(x - w / 2, y),
            size=(w, h),
            class_="thin",
        )
    )


def _draw_battery_column(dwg, x: float, y: float, h: float, rows: int) -> None:
    if rows <= 0 or h <= 0:
        return
    cell_pitch = h / rows
    long_w = max(8.0, min(16.0, cell_pitch * 0.9))
    short_w = long_w * 0.6
    plate_gap = min(4.0, max(2.0, cell_pitch * 0.2))
    dwg.add(dwg.line((x, y - 2), (x, y + h + 2), class_="thin"))
    for row in range(rows):
        y_center = y + cell_pitch * (row + 0.5)
        y_long = y_center - plate_gap / 2
        y_short = y_center + plate_gap / 2
        dwg.add(dwg.line((x - long_w / 2, y_long), (x + long_w / 2, y_long), class_="thin"))
        dwg.add(dwg.line((x - short_w / 2, y_short), (x + short_w / 2, y_short), class_="thin"))
    dot_gap = min(6.0, max(3.0, cell_pitch * 0.3))
    mid_y = y + h * 0.5
    for offset in (-dot_gap, 0.0, dot_gap):
        dwg.add(dwg.line((x - 1.5, mid_y + offset), (x + 1.5, mid_y + offset), class_="thin"))


def _draw_triangle_up(dwg, x: float, y: float, size: float) -> None:
    half = size * 0.6
    points = [(x, y - size), (x - half, y), (x + half, y)]
    dwg.add(dwg.polygon(points=points, class_="thin", fill="none"))


def _draw_breaker_circle(dwg, x: float, y: float, r: float) -> None:
    if r <= 0:
        return
    dwg.add(dwg.circle(center=(x, y), r=r, class_="outline"))
    dwg.add(dwg.line((x - r * 0.7, y - r * 0.7), (x + r * 0.7, y + r * 0.7), class_="thin"))
    dwg.add(dwg.line((x - r * 0.7, y + r * 0.7), (x + r * 0.7, y - r * 0.7), class_="thin"))


def _draw_transformer_symbol(dwg, x: float, y: float, r: float) -> tuple[tuple[float, float], tuple[float, float]]:
    gap = r * 1.4
    top_center = (x, y)
    left_center = (x - gap, y + gap)
    right_center = (x + gap, y + gap)
    for cx, cy in (top_center, left_center, right_center):
        dwg.add(dwg.circle(center=(cx, cy), r=r, class_="outline"))

    tri = [
        (top_center[0], top_center[1] - r * 0.55),
        (top_center[0] - r * 0.5, top_center[1] + r * 0.35),
        (top_center[0] + r * 0.5, top_center[1] + r * 0.35),
    ]
    dwg.add(dwg.polygon(points=tri, class_="thin", fill="none"))

    for cx, cy in (left_center, right_center):
        dwg.add(dwg.line((cx, cy), (cx, cy - r * 0.6), class_="thin"))
        dwg.add(dwg.line((cx, cy), (cx - r * 0.5, cy + r * 0.35), class_="thin"))
        dwg.add(dwg.line((cx, cy), (cx + r * 0.5, cy + r * 0.35), class_="thin"))

    return left_center, right_center


def _draw_node(dwg, x: float, y: float, r: float, fill: str) -> None:
    dwg.add(dwg.circle(center=(x, y), r=r, class_="outline", fill=fill))


def _draw_solid_node(dwg, x: float, y: float, r: float, fill: str) -> None:
    dwg.add(dwg.circle(center=(x, y), r=r, fill=fill, stroke=fill, stroke_width=0.6))


def _snap_point(
    point: tuple[float, float], anchor: tuple[float, float], tol: float = 0.5
) -> tuple[float, float]:
    if abs(point[0] - anchor[0]) > tol or abs(point[1] - anchor[1]) > tol:
        return anchor
    return point


def _draw_line_anchored(
    dwg,
    start: tuple[float, float],
    end: tuple[float, float],
    class_: str = "thin",
    start_anchor: tuple[float, float] | None = None,
    end_anchor: tuple[float, float] | None = None,
    tol: float = 0.5,
) -> None:
    if start_anchor is not None:
        start = _snap_point(start, start_anchor, tol)
    if end_anchor is not None:
        end = _snap_point(end, end_anchor, tol)
    dwg.add(dwg.line(start, end, class_=class_))


def _draw_ground(dwg, x: float, y: float) -> None:
    dwg.add(dwg.line((x, y), (x, y + 6), class_="thin"))
    dwg.add(dwg.line((x - 6, y + 6), (x + 6, y + 6), class_="thin"))
    dwg.add(dwg.line((x - 4, y + 9), (x + 4, y + 9), class_="thin"))
    dwg.add(dwg.line((x - 2, y + 12), (x + 2, y + 12), class_="thin"))


def _draw_capacitor(dwg, x: float, y: float, w: float, gap: float) -> None:
    dwg.add(dwg.line((x - w / 2, y), (x + w / 2, y), class_="thin"))
    dwg.add(dwg.line((x - w / 2, y + gap), (x + w / 2, y + gap), class_="thin"))


def _draw_triangle_down(dwg, x: float, y: float, size: float) -> None:
    half = size * 0.6
    points = [(x, y + size), (x - half, y), (x + half, y)]
    dwg.add(dwg.polygon(points=points, class_="thin", fill="none"))


def _draw_arrow_box(dwg, x: float, y: float, w: float, h: float) -> None:
    dwg.add(dwg.rect(insert=(x - w / 2, y), size=(w, h), class_="outline"))
    dwg.add(dwg.line((x, y + 4), (x, y + h - 6), class_="thin"))
    dwg.add(dwg.line((x, y + h - 6), (x - 4, y + h - 10), class_="thin"))
    dwg.add(dwg.line((x, y + h - 6), (x + 4, y + h - 10), class_="thin"))


def _wrap_text(text: str, max_chars: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _approx_chars(width_px: float) -> int:
    return max(6, int(width_px / 7))


def _table_row_lines(text: str, max_chars: int) -> List[str]:
    value = str(text or "TBD")
    lines = _wrap_text(value, max_chars)
    return lines if lines else ["TBD"]


def _require_rmu_class_kv(spec: SldGroupSpec, rmu_payload: dict) -> float:
    rated_kv = _safe_float(rmu_payload.get("rated_kv"), 0.0)
    if rated_kv <= 0:
        raise ValueError(
            f"Legacy SLD spec for group {spec.group_index} is missing rmu.rated_kv. "
            "Renderer will not infer RMU equipment class from mv_voltage_kv."
        )
    return rated_kv


def _range_text(values: List[float], unit: str) -> str:
    if not values:
        return "TBD"
    minimum = min(values)
    maximum = max(values)
    if abs(maximum - minimum) < 1e-6:
        return f"{minimum:.0f} {unit}"
    return f"{minimum:.0f}-{maximum:.0f} {unit}"


def _split_pcs_groups(pcs_count: int) -> tuple[list[int], list[int]]:
    if pcs_count <= 0:
        return [], []
    split = int(math.ceil(pcs_count / 2))
    return list(range(1, split + 1)), list(range(split + 1, pcs_count + 1))


def _build_compact_equipment_list(spec: SldGroupSpec) -> List[Tuple[str, str]]:
    equipment = spec.equipment_list or {}
    hz_value = _safe_float(equipment.get("project_hz"), 0.0) if isinstance(equipment, dict) else 0.0
    hz_text = f"{hz_value:.0f}Hz" if hz_value > 0 else "50/60Hz"

    mv_spec = f"{format_kv(spec.mv_voltage_kv)}, 3-phase, {hz_text}"

    tr_parts = [
        format_mva(spec.transformer_mva),
        f"{format_kv(spec.mv_voltage_kv)}/{format_v(spec.lv_voltage_v_ll)}",
    ]
    if spec.transformer_vector_group:
        tr_parts.append(str(spec.transformer_vector_group))
    tr_spec = ", ".join([part for part in tr_parts if part and part != "TBD"]) or "TBD"

    pcs_text = _range_text(spec.pcs_rating_kw_list, "kW")
    pcs_spec = "TBD"
    if spec.pcs_count > 0 and pcs_text != "TBD":
        pcs_spec = f"{spec.pcs_count} x {pcs_text}"

    dc_total = _safe_int(spec.dc_blocks_total_in_group, 0)
    dc_spec = "TBD"
    if dc_total > 0:
        energy_text = format_mwh(spec.dc_block_energy_mwh)
        dc_spec = f"{dc_total} x {energy_text}" if energy_text != "TBD" else f"{dc_total} x TBD"

    return [
        ("MV Switchgear", mv_spec),
        ("Transformer", tr_spec),
        ("PCS", pcs_spec),
        ("DC Block", dc_spec),
    ]


def _build_dark_equipment_sections(spec: SldGroupSpec) -> list[tuple[str, list[str]]]:
    equipment = spec.equipment_list or {}
    rmu = equipment.get("rmu", {}) if isinstance(equipment.get("rmu"), dict) else {}
    transformer = (
        equipment.get("transformer", {}) if isinstance(equipment.get("transformer"), dict) else {}
    )
    lv_bus = equipment.get("lv_busbar", {}) if isinstance(equipment.get("lv_busbar"), dict) else {}
    cables = equipment.get("cables", {}) if isinstance(equipment.get("cables"), dict) else {}
    dc_fuse = equipment.get("dc_fuse", {}) if isinstance(equipment.get("dc_fuse"), dict) else {}

    hz_value = _safe_float(equipment.get("project_hz"), 0.0)
    hz_text = f"{hz_value:.0f}Hz" if hz_value > 0 else "50/60Hz"

    mv_cable_spec = cables.get("mv_cable_spec")
    if not mv_cable_spec:
        mv_kv_text = format_kv_plain(spec.mv_voltage_kv)
        mv_cable_spec = f"XLPE/Cu-{mv_kv_text}" if mv_kv_text != "TBD" else "TBD"

    lv_cable_spec = cables.get("lv_cable_spec") or "TBD"

    dc_voltage_v = _safe_float(equipment.get("dc_block_voltage_v"), 0.0)
    dc_voltage_text = f"{dc_voltage_v:.0f}V" if dc_voltage_v > 0 else "TBD"
    dc_cable_spec = cables.get("dc_cable_spec")
    if not dc_cable_spec:
        if dc_voltage_v > 0:
            dc_cable_spec = f"XLPE/Cu-DC-{dc_voltage_v / 1000.0:.1f}kV"
        else:
            dc_cable_spec = "TBD"

    rated_kv = _require_rmu_class_kv(spec, rmu)
    rated_a = _safe_float(rmu.get("rated_a"), 0.0)
    short_ka = _safe_float(rmu.get("short_circuit_ka_3s"), 0.0)
    ct_ratio = rmu.get("ct_ratio") or "TBD"
    ct_class = rmu.get("ct_class") or "TBD"
    ct_va = _safe_float(rmu.get("ct_va"), 0.0)
    ct_va_text = f"{ct_va:.0f}VA" if ct_va > 0 else "TBD VA"

    kv_text = f"{rated_kv:.0f}kV" if rated_kv > 0 else "TBD kV"
    a_text = f"{rated_a:.0f}A" if rated_a > 0 else "TBD A"
    ka_text = f"{short_ka:.1f}kA/3s" if short_ka > 0 else "TBD kA/3s"
    rmu_lines = [
        f"LBS: {kv_text}, {a_text}, {ka_text}",
        f"CB: {kv_text}, {a_text}, {ka_text}",
        f"CT: {ct_ratio}, {ct_class}, {ct_va_text}",
        "With DS, ES, & Live Display",
    ]

    tr_lines = []
    tr_kva = spec.transformer_mva * 1000.0 if spec.transformer_mva > 0 else 0.0
    tr_line1 = f"{tr_kva:.0f} kVA" if tr_kva > 0 else "TBD kVA"
    vector = transformer.get("vector_group") or spec.transformer_vector_group
    if vector:
        tr_line1 = f"{tr_line1}, {vector}"
    tr_lines.append(tr_line1)

    tap_range = transformer.get("tap_range")
    mv_lv_text = f"{format_kv_plain(spec.mv_voltage_kv)}/{format_v_plain(spec.lv_voltage_v_ll)}"
    if tap_range:
        mv_lv_text = f"{format_kv_plain(spec.mv_voltage_kv)}{tap_range}/{format_v_plain(spec.lv_voltage_v_ll)}"
    tr_lines.append(mv_lv_text)

    uk = transformer.get("uk_percent")
    if uk is None:
        uk = spec.transformer_uk_percent
    cooling = transformer.get("cooling")
    tr_tail = []
    if uk:
        tr_tail.append(f"Ud={format_percent(uk)}")
    if cooling:
        tr_tail.append(str(cooling))
    tr_lines.append(", ".join(tr_tail) if tr_tail else "TBD")

    lv_rated_a = _safe_float(lv_bus.get("rated_a"), 0.0)
    if lv_rated_a <= 0 and spec.transformer_mva > 0:
        lv_rated_a = _estimate_current_a(spec.transformer_mva * 1000.0, spec.lv_voltage_v_ll)
    lv_rated_a = round(lv_rated_a / 10.0) * 10 if lv_rated_a > 0 else 0.0
    lv_ka = _safe_float(lv_bus.get("short_circuit_ka"), 0.0)
    lv_rated_text = f"{lv_rated_a:.0f}A" if lv_rated_a > 0 else "TBD A"
    lv_ka_text = f"{lv_ka:.1f}kA" if lv_ka > 0 else "TBD kA"
    copper_line = f"AC{format_v_plain(spec.lv_voltage_v_ll)}, {lv_rated_text}, {lv_ka_text}"

    pcs_rating_kw = _pick_pcs_rating_kw(spec)
    pcs_rating_text = f"{pcs_rating_kw:.0f}kW" if pcs_rating_kw > 0 else "TBD"
    pcs_count = max(1, _safe_int(spec.pcs_count, 1))

    cb_current = _estimate_current_a(pcs_rating_kw, spec.lv_voltage_v_ll)
    cb_current = round(cb_current / 10.0) * 10 if cb_current > 0 else 0.0
    cb_current_text = f"{cb_current:.0f}A" if cb_current > 0 else "TBD A"
    cb_ka_text = lv_ka_text if lv_ka > 0 else "TBD kA"
    pcs_lines = [
        f"CB: AC{format_v_plain(spec.lv_voltage_v_ll)}, {cb_current_text}, {cb_ka_text}",
        f"PCS-{pcs_rating_text} x {pcs_count}",
        f"AC{format_v_plain(spec.lv_voltage_v_ll)}/{hz_text}, DC{dc_voltage_text}",
    ]

    dc_current = _estimate_dc_current_a(pcs_rating_kw, dc_voltage_v)
    if dc_voltage_v > 0 and dc_current > 0:
        pcs_lines.append(f"DS: DC{dc_voltage_text}, {dc_current:.0f}A")
    else:
        pcs_lines.append("DS: TBD")

    fuse_spec = dc_fuse.get("fuse_spec") or ""
    if fuse_spec:
        pcs_lines.append(f"FUSE: {fuse_spec}")
    elif dc_voltage_v > 0:
        pcs_lines.append(f"FUSE: DC{dc_voltage_text}, TBD")
    else:
        pcs_lines.append("FUSE: TBD")

    dc_blocks_total = _safe_int(spec.dc_blocks_total_in_group, 0)
    if dc_blocks_total > 0:
        bess_line = f"{dc_blocks_total} BESS"
    else:
        bess_line = "BESS TBD"

    sections = [
        ("Power Cable", [mv_cable_spec]),
        ("Ring Main Unit (SF6)", rmu_lines),
        ("Power Cable", [lv_cable_spec]),
        ("Step-up Transformer (OIL)", tr_lines),
        ("Connecting Copper Tape", [copper_line]),
        ("Power Converter System (PCS)", pcs_lines),
        ("Power Cable", [dc_cable_spec]),
        ("Battery Storage Bank (BAT)", [bess_line]),
    ]

    return sections


def _build_equipment_list(
    spec: SldGroupSpec, compact_mode: bool = False
) -> List[Tuple[str, str]]:
    if compact_mode:
        return _build_compact_equipment_list(spec)
    eq = spec.equipment_list or {}
    rmu = eq.get("rmu", {}) if isinstance(eq.get("rmu"), dict) else {}
    transformer = eq.get("transformer", {}) if isinstance(eq.get("transformer"), dict) else {}
    lv_bus = eq.get("lv_busbar", {}) if isinstance(eq.get("lv_busbar"), dict) else {}
    cables = eq.get("cables", {}) if isinstance(eq.get("cables"), dict) else {}
    dc_fuse = eq.get("dc_fuse", {}) if isinstance(eq.get("dc_fuse"), dict) else {}

    items = []
    items.append(("MV Cable", cables.get("mv_cable_spec") or "TBD"))

    rmu_parts = []
    rated_kv = _require_rmu_class_kv(spec, rmu)
    rmu_parts.append(f"{rated_kv:.0f} kV class")
    rated_a = _safe_float(rmu.get("rated_a"), 0.0)
    if rated_a > 0:
        rmu_parts.append(f"{rated_a:.0f} A")
    short_ka = _safe_float(rmu.get("short_circuit_ka_3s"), 0.0)
    if short_ka > 0:
        rmu_parts.append(f"{short_ka:.1f} kA/3s")
    if rmu.get("ct_ratio"):
        rmu_parts.append(f"CT {rmu.get('ct_ratio')}")
    if rmu.get("ct_class"):
        rmu_parts.append(str(rmu.get("ct_class")))
    ct_va = _safe_float(rmu.get("ct_va"), 0.0)
    if ct_va > 0:
        rmu_parts.append(f"{ct_va:.0f} VA")
    items.append(("Ring Main Unit (RMU)", ", ".join(rmu_parts) if rmu_parts else "TBD"))

    tr_parts = [
        format_mva(spec.transformer_mva),
        f"{format_kv(spec.mv_voltage_kv)}/{format_v(spec.lv_voltage_v_ll)}",
    ]
    vector = transformer.get("vector_group") or spec.transformer_vector_group
    if vector:
        tr_parts.append(str(vector))
    uk = transformer.get("uk_percent")
    if uk is None:
        uk = spec.transformer_uk_percent
    if uk:
        tr_parts.append(f"Uk={format_percent(uk)}")
    cooling = transformer.get("cooling")
    if cooling:
        tr_parts.append(str(cooling))
    items.append(("Transformer", ", ".join(tr_parts) if tr_parts else "TBD"))

    lv_parts = []
    lv_a = _safe_float(lv_bus.get("rated_a"), 0.0)
    if lv_a > 0:
        lv_parts.append(f"{lv_a:.0f} A")
    lv_ka = _safe_float(lv_bus.get("short_circuit_ka"), 0.0)
    if lv_ka > 0:
        lv_parts.append(f"{lv_ka:.1f} kA")
    items.append(("LV Busbar", ", ".join(lv_parts) if lv_parts else "TBD"))

    pcs_text = _range_text(spec.pcs_rating_kw_list, "kW")
    pcs_spec = f"{pcs_text} x {spec.pcs_count}"
    if spec.lv_voltage_v_ll:
        pcs_spec = f"{pcs_spec}, LV {format_v(spec.lv_voltage_v_ll)}"
    items.append(("PCS", pcs_spec))

    items.append(("LV Cable", cables.get("lv_cable_spec") or "TBD"))
    items.append(("DC Cable", cables.get("dc_cable_spec") or "TBD"))
    items.append(("DC Fuse", dc_fuse.get("fuse_spec") or "TBD"))

    battery_parts = [f"{format_mwh(spec.dc_block_energy_mwh)} each"]
    if spec.dc_blocks_total_in_group:
        battery_parts.append(f"x {_safe_int(spec.dc_blocks_total_in_group, 0)}")
    items.append(("Battery Storage Bank", " ".join(battery_parts) if battery_parts else "TBD"))

    allocation_parts = [
        f"F{idx + 1}={spec.dc_blocks_per_feeder[idx] if idx < len(spec.dc_blocks_per_feeder) else 0}"
        for idx in range(spec.pcs_count)
    ]
    allocation_text = ", ".join(allocation_parts) if allocation_parts else "TBD"
    items.append(("DC Block Allocation", allocation_text))

    return items


def _write_png(svg_path: Path, png_path: Path) -> None:
    if cairosvg is None:
        raise ImportError("cairosvg is required to export PNG from SVG.")
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


def render_sld_pro_svg(
    spec: SldGroupSpec, out_svg: Path, out_png: Path | None = None
) -> tuple[Path | None, str | None]:
    if svgwrite is None:
        return None, "Missing dependency: svgwrite. Please install: pip install svgwrite"
    out_svg = Path(out_svg)

    layout_params = spec.layout_params if isinstance(spec.layout_params, dict) else {}
    compact_mode = bool(layout_params.get("compact_mode"))
    theme = str(layout_params.get("theme") or "light").lower()
    dark_mode = theme.startswith("dark")
    if "draw_summary" in layout_params:
        draw_summary = bool(layout_params.get("draw_summary"))
    else:
        draw_summary = not dark_mode

    width = int(_safe_float(layout_params.get("svg_width"), 1750))
    width = max(1200, width)
    left_margin = _safe_float(layout_params.get("left_margin"), 40)
    left_col_width = _safe_float(layout_params.get("column_width"), 360 if dark_mode else 420)
    table_x = left_margin
    table_y = 40
    table_w = left_col_width
    diagram_left = left_margin + left_col_width + 40
    diagram_right = width - 40
    diagram_width = diagram_right - diagram_left

    row_h = int(_safe_float(layout_params.get("row_height"), 16))
    title_h = 20
    header_h = 18

    item_col_w = 150
    spec_col_w = table_w - item_col_w
    rows = []
    dark_sections = []
    dark_section_gap = 0
    dark_list_pad_y = 0
    dark_detail_indent = 0
    if dark_mode:
        max_chars = _approx_chars(table_w - 28)
        dark_section_gap = 6
        dark_list_pad_y = 12
        dark_detail_indent = 12
        for title, lines in _build_dark_equipment_sections(spec):
            wrapped_lines = []
            for line in lines:
                wrapped_lines.extend(_wrap_text(line, max_chars))
            dark_sections.append({"title": title, "lines": wrapped_lines})
        if not dark_sections:
            dark_sections = [{"title": "Equipment List", "lines": ["TBD"]}]
        total_lines = sum(1 + len(section["lines"]) for section in dark_sections)
        table_h = (
            dark_list_pad_y * 2
            + total_lines * row_h
            + (len(dark_sections) - 1) * dark_section_gap
        )
    else:
        items = _build_equipment_list(spec, compact_mode)
        item_chars = _approx_chars(item_col_w)
        spec_chars = _approx_chars(spec_col_w)
        for item, spec_text in items:
            item_lines = _table_row_lines(item, item_chars)
            spec_lines = _table_row_lines(spec_text, spec_chars)
            rows.append(
                {
                    "item_lines": item_lines,
                    "spec_lines": spec_lines,
                    "lines": max(len(item_lines), len(spec_lines)),
                }
            )
        table_h = title_h + header_h + sum(row["lines"] * row_h for row in rows)

    skid_x = diagram_left
    skid_y = table_y
    skid_pad = _safe_float(layout_params.get("skid_pad"), 60.0)
    battery_pad = _safe_float(layout_params.get("battery_pad"), 40.0)
    pcs_count = max(1, int(spec.pcs_count))
    group_a, group_b = _split_pcs_groups(pcs_count)
    group_split = len(group_a)
    pcs_box_h = 54
    pcs_pad = skid_pad
    pcs_span = max(240.0, diagram_width - pcs_pad * 2)
    slot_w = pcs_span / pcs_count
    if compact_mode:
        pcs_box_w = min(80.0, max(58.0, slot_w - 20.0))
        pcs_box_h = max(78.0, pcs_box_w)
    else:
        pcs_box_w = min(160.0, max(110.0, slot_w - 10.0))
    pcs_centers = [
        skid_x + pcs_pad + (idx + 0.5) * slot_w for idx in range(pcs_count)
    ]
    mv_center_x = skid_x + diagram_width / 2
    gap_center = mv_center_x

    mv_bus_y = skid_y + 120
    mv_breaker_offset = 16.0
    mv_switch_gap = 14.0
    mv_switch_h = 12.0
    mv_chain_gap = 18.0
    mv_to_tr_gap = 46.0
    tr_radius = 14.0

    breaker_y = mv_bus_y + mv_breaker_offset
    switch_y = breaker_y + mv_switch_gap
    equip_y = switch_y + mv_switch_h + mv_chain_gap
    tr_top_y = equip_y + mv_to_tr_gap

    bus_y = tr_top_y + tr_radius * 2 + 80.0
    pcs_y = bus_y + 24.0
    dc_blocks_total = _safe_int(spec.dc_blocks_total_in_group, 0)
    battery_x = skid_x + battery_pad
    battery_w = diagram_width - battery_pad * 2

    if compact_mode:
        dc_bus_y = pcs_y + pcs_box_h + 30
        skid_h = max(360.0, dc_bus_y - skid_y + 50)

        battery_y = skid_y + skid_h + 40
        battery_title_h = 20
        dc_block_h = max(140.0, pcs_box_h * 1.5)
        dc_block_gap_y = 18.0
        per_feeder_counts = (
            [max(1, _safe_int(v, 1)) for v in spec.dc_blocks_per_feeder]
            if isinstance(spec.dc_blocks_per_feeder, list)
            else []
        )
        max_blocks = max(per_feeder_counts) if per_feeder_counts else 1
        max_blocks = max(1, min(max_blocks, 2))
        dc_stack_h = dc_block_h * max_blocks + dc_block_gap_y * (max_blocks - 1)
        dc_box_y = battery_y + battery_title_h + 30
        battery_h = battery_title_h + 30 + dc_stack_h + 40

        allocation_parts = [
            f"F{idx + 1}={spec.dc_blocks_per_feeder[idx] if idx < len(spec.dc_blocks_per_feeder) else 0}"
            for idx in range(pcs_count)
        ]
        allocation_text = ", ".join(allocation_parts) if allocation_parts else "TBD"
        summary_lines = [
            f"Battery Storage Bank: {dc_blocks_total} blocks @ {format_mwh(spec.dc_block_energy_mwh)} each",
            f"PCS count: {pcs_count}, LV {format_v(spec.lv_voltage_v_ll)}",
            f"Allocation: {allocation_text}",
        ]
    else:
        dc_bus_a_y = pcs_y + pcs_box_h + 28
        dc_bus_gap = 22
        dc_bus_b_y = dc_bus_a_y + dc_bus_gap
        skid_h = max(380.0, dc_bus_b_y - skid_y + 60)

        battery_y = skid_y + skid_h + 40
        battery_title_h = 20
        circuit_pad = 18
        circuit_gap = 18
        dc_circuit_a_y = battery_y + battery_title_h + circuit_pad
        dc_circuit_b_y = dc_circuit_a_y + circuit_gap
        dc_box_h = 54

        show_individual_blocks = 0 < dc_blocks_total <= 6
        blocks_to_draw = dc_blocks_total if show_individual_blocks else 1
        block_cols = min(3, blocks_to_draw) if show_individual_blocks else 1
        block_rows = int(math.ceil(blocks_to_draw / block_cols)) if show_individual_blocks else 1
        block_gap_x = 20.0
        block_gap_y = 16.0
        block_area_w = max(220.0, battery_w - 80.0)
        dc_box_w = min(
            160.0,
            max(110.0, (block_area_w - (block_cols - 1) * block_gap_x) / block_cols),
        )
        block_grid_w = block_cols * dc_box_w + max(0, block_cols - 1) * block_gap_x
        block_grid_h = block_rows * dc_box_h + max(0, block_rows - 1) * block_gap_y
        dc_box_x_start = battery_x + (battery_w - block_grid_w) / 2
        dc_box_y = dc_circuit_b_y + 24
        battery_note_y = dc_box_y + block_grid_h + 18
        battery_h = max(battery_title_h + 80.0, battery_note_y - battery_y + 24)

        allocation_parts = [
            f"F{idx + 1}={spec.dc_blocks_per_feeder[idx] if idx < len(spec.dc_blocks_per_feeder) else 0}"
            for idx in range(pcs_count)
        ]
        allocation_text = ", ".join(allocation_parts) if allocation_parts else "TBD"
        group_a_counts = [
            spec.dc_blocks_per_feeder[idx - 1] if idx - 1 < len(spec.dc_blocks_per_feeder) else 0
            for idx in group_a
        ]
        group_b_counts = [
            spec.dc_blocks_per_feeder[idx - 1] if idx - 1 < len(spec.dc_blocks_per_feeder) else 0
            for idx in group_b
        ]
        group_a_text = ", ".join(
            [f"F{idx}={group_a_counts[i]}" for i, idx in enumerate(group_a)]
        ) or "None"
        group_b_text = ", ".join(
            [f"F{idx}={group_b_counts[i]}" for i, idx in enumerate(group_b)]
        ) or "None"
        summary_lines = [
            f"Battery Storage Bank: {dc_blocks_total} blocks @ {format_mwh(spec.dc_block_energy_mwh)} each",
            f"PCS count: {pcs_count}, LV {format_v(spec.lv_voltage_v_ll)}",
            f"Group A feeders: {group_a_text} (total {sum(group_a_counts)})",
            f"Group B feeders: {group_b_text} (total {sum(group_b_counts)})",
            f"Allocation: {allocation_text}",
            "Counts indicate allocation for sizing/configuration; detailed DC wiring is not represented.",
        ]

    wrapped_lines = []
    note_w = 0.0
    note_h = 0.0
    note_x = 0.0
    note_y = 0.0
    if draw_summary:
        for line in summary_lines:
            wrapped_lines.extend(_wrap_text(line, 64))

        note_w = min(480.0, diagram_width * 0.9)
        note_h = 24 + len(wrapped_lines) * 18
        note_x = diagram_right - note_w
        note_y = battery_y + battery_h + 24

    diagram_bottom = battery_y + battery_h + 40
    height = max(table_y + table_h + 40, diagram_bottom)
    if draw_summary:
        height = max(height, note_y + note_h + 40)

    dwg = svgwrite.Drawing(
        filename=str(out_svg),
        size=(f"{width}px", f"{height}px"),
        viewBox=f"0 0 {width} {height}",
    )
    outline_color = "#e5e7eb" if dark_mode else "#000000"
    thin_color = "#cbd5e1" if dark_mode else "#000000"
    thick_color = "#e5e7eb" if dark_mode else "#000000"
    dash_color = "#22d3ee" if dark_mode else "#000000"
    busbar_color = "#ef4444" if dark_mode else "#000000"
    label_color = "#e5e7eb" if dark_mode else "#000000"
    title_color = "#f8fafc" if dark_mode else "#000000"
    bg_color = "#0b0f13" if dark_mode else "#ffffff"

    thin_width = max(1.5, SLD_STROKE_THIN)
    outline_width = max(2.0, SLD_STROKE_OUTLINE)
    thick_width = max(2.0, SLD_STROKE_THICK)
    dash_width = outline_width
    busbar_width = max(2.0, SLD_STROKE_THICK)

    dwg.add(
        dwg.style(
            f"""
svg {{ font-family: {SLD_FONT_FAMILY}; font-size: {SLD_FONT_SIZE}px; }}
.outline {{ stroke: {outline_color}; stroke-width: {outline_width}; fill: none; }}
.thin {{ stroke: {thin_color}; stroke-width: {thin_width}; fill: none; }}
.thick {{ stroke: {thick_color}; stroke-width: {thick_width}; fill: none; }}
.dash {{ stroke: {dash_color}; stroke-width: {dash_width}; fill: none; stroke-dasharray: {SLD_DASH_ARRAY}; }}
.busbar {{ stroke: {busbar_color}; stroke-width: {busbar_width}; fill: none; }}
.label {{ fill: {label_color}; }}
.title {{ font-size: {SLD_FONT_SIZE_TITLE}px; font-weight: bold; fill: {title_color}; }}
.small {{ font-size: {SLD_FONT_SIZE_SMALL}px; fill: {label_color}; }}
"""
        )
    )
    dwg.add(dwg.rect(insert=(0, 0), size=(width, height), fill=bg_color))

    if dark_mode:
        list_pad_x = 10
        dwg.add(dwg.rect(insert=(table_x, table_y), size=(table_w, table_h), class_="outline"))
        current_y = table_y + dark_list_pad_y
        for idx, section in enumerate(dark_sections):
            current_y += row_h
            dwg.add(
                dwg.text(
                    section["title"],
                    insert=(table_x + list_pad_x, current_y - 3),
                    class_="label title",
                )
            )
            for line in section["lines"]:
                current_y += row_h
                dwg.add(
                    dwg.text(
                        line,
                        insert=(table_x + list_pad_x + dark_detail_indent, current_y - 3),
                        class_="label small",
                    )
                )
            if idx < len(dark_sections) - 1:
                current_y += dark_section_gap
                sep_y = current_y - dark_section_gap / 2
                dwg.add(
                    dwg.line(
                        (table_x, sep_y),
                        (table_x + table_w, sep_y),
                        class_="thin",
                    )
                )
    else:
        dwg.add(dwg.rect(insert=(table_x, table_y), size=(table_w, table_h), class_="outline"))
        col_split = table_x + item_col_w
        dwg.add(dwg.line((col_split, table_y), (col_split, table_y + table_h), class_="thin"))
        dwg.add(
            dwg.line(
                (table_x, table_y + title_h),
                (table_x + table_w, table_y + title_h),
                class_="thin",
            )
        )
        dwg.add(
            dwg.line(
                (table_x, table_y + title_h + header_h),
                (table_x + table_w, table_y + title_h + header_h),
                class_="thin",
            )
        )
        dwg.add(dwg.text("Equipment List", insert=(table_x + 6, table_y + 14), class_="label title"))
        dwg.add(dwg.text("Item", insert=(table_x + 6, table_y + title_h + 13), class_="label"))
        dwg.add(dwg.text("Spec", insert=(col_split + 6, table_y + title_h + 13), class_="label"))

        current_y = table_y + title_h + header_h
        for row in rows:
            for line_idx, line in enumerate(row["item_lines"]):
                y = current_y + row_h * (line_idx + 1) - 3
                dwg.add(dwg.text(line, insert=(table_x + 6, y), class_="label"))
            for line_idx, line in enumerate(row["spec_lines"]):
                y = current_y + row_h * (line_idx + 1) - 3
                dwg.add(dwg.text(line, insert=(col_split + 6, y), class_="label"))
            current_y += row_h * row["lines"]
            dwg.add(dwg.line((table_x, current_y), (table_x + table_w, current_y), class_="thin"))

    dwg.add(dwg.rect(insert=(skid_x, skid_y), size=(diagram_width, skid_h), class_="dash"))
    if dark_mode:
        dwg.add(
            dwg.text(
                "AC Block (PCS&MV SKID)",
                insert=(skid_x + diagram_width - 8, skid_y + 18),
                class_="label title",
                text_anchor="end",
            )
        )
    else:
        dwg.add(
            dwg.text(
                "PCS&MVT SKID (AC Block)",
                insert=(skid_x + 8, skid_y + 18),
                class_="label title",
            )
        )

    mv_labels = spec.equipment_list.get("mv_labels") if isinstance(spec.equipment_list, dict) else {}
    to_switchgear = mv_labels.get("to_switchgear") if isinstance(mv_labels, dict) else None
    to_other_rmu = mv_labels.get("to_other_rmu") if isinstance(mv_labels, dict) else None
    if not to_switchgear:
        if dark_mode:
            to_switchgear = f"To {format_kv_plain(spec.mv_voltage_kv)} Switchgear"
        else:
            to_switchgear = f"To {format_kv(spec.mv_voltage_kv)} Switchgear"
    if not to_other_rmu:
        to_other_rmu = "To Other RMU"

    # --- MV: match PDF: short internal bus, not full-width
    terminal_y = skid_y + max(56.0, skid_pad)
    mv_bus_half = min(300.0, max(180.0, diagram_width * 0.22))
    terminal_left_x = mv_center_x - mv_bus_half
    terminal_right_x = mv_center_x + mv_bus_half

    dwg.add(dwg.text(to_switchgear, insert=(terminal_left_x - 10, terminal_y - 18), class_="label"))
    dwg.add(
        dwg.text(
            to_other_rmu,
            insert=(terminal_right_x + 10, terminal_y - 18),
            class_="label",
            text_anchor="end",
        )
    )

    node_fill = label_color
    busbar_left_x = terminal_left_x
    busbar_right_x = terminal_right_x
    dwg.add(dwg.line((busbar_left_x, mv_bus_y), (busbar_right_x, mv_bus_y), class_="thin"))

    node_r = 3.0
    _draw_node(dwg, terminal_left_x, mv_bus_y, node_r, node_fill)
    _draw_node(dwg, terminal_right_x, mv_bus_y, node_r, node_fill)
    _draw_node(dwg, mv_center_x, mv_bus_y, node_r, node_fill)

    # RMU taps
    rmu_tap_h = 26.0
    for tap_x in (terminal_left_x, terminal_right_x):
        _draw_line_anchored(
            dwg,
            (tap_x, mv_bus_y),
            (tap_x, mv_bus_y - rmu_tap_h),
            class_="thin",
            start_anchor=(tap_x, mv_bus_y),
        )
    dwg.add(dwg.text("RMU", insert=(terminal_left_x - 26, terminal_y + 10), class_="label"))

    # MV center chain
    branch_top = (mv_center_x, mv_bus_y)
    branch_bottom = (mv_center_x, equip_y)
    _draw_line_anchored(
        dwg,
        branch_top,
        branch_bottom,
        class_="thin",
        start_anchor=branch_top,
        end_anchor=branch_bottom,
    )
    _draw_breaker_x(dwg, mv_center_x, breaker_y, 9.0)
    _draw_dc_switch(dwg, mv_center_x, switch_y, mv_switch_h)

    equip_span = 60.0
    dwg.add(
        dwg.line(
            (mv_center_x - equip_span, equip_y),
            (mv_center_x + equip_span, equip_y),
            class_="thin",
        )
    )
    # Left arrester box
    left_box_x = mv_center_x - equip_span
    _draw_arrow_box(dwg, left_box_x, equip_y + 6, 14.0, 22.0)
    _draw_ground(dwg, left_box_x, equip_y + 30)

    # CT circles
    ct_y = equip_y + 10
    for offset in (-12, 0, 12):
        dwg.add(dwg.circle(center=(mv_center_x + offset, ct_y), r=3.5, class_="outline"))

    # Right breaker + capacitor
    right_x = mv_center_x + equip_span
    _draw_capacitor(dwg, right_x, equip_y + 4, 14.0, 5.0)
    _draw_breaker_circle(dwg, right_x, equip_y + 16, 6.0)
    _draw_ground(dwg, right_x, equip_y + 26)

    tr_center_x = gap_center
    dwg.add(dwg.line((mv_center_x, equip_y), (mv_center_x, tr_top_y - tr_radius), class_="thin"))
    _draw_triangle_down(dwg, mv_center_x, tr_top_y - tr_radius - 8, 8.0)
    left_center, right_center = _draw_transformer_symbol(dwg, tr_center_x, tr_top_y, tr_radius)

    # Transformer LV double down-leads to LV busbar (match PDF)
    tx_lv_spacing = _safe_float(layout_params.get("tx_lv_spacing"), 14.0)
    tx_lv_spacing = min(18.0, max(12.0, tx_lv_spacing))
    tx_lv_start_y = left_center[1] + tr_radius
    tx_lv_left_start = (tr_center_x - tx_lv_spacing, tx_lv_start_y)
    tx_lv_right_start = (tr_center_x + tx_lv_spacing, tx_lv_start_y)
    tx_lv_left = (tr_center_x - tx_lv_spacing, bus_y)
    tx_lv_right = (tr_center_x + tx_lv_spacing, bus_y)
    _draw_line_anchored(
        dwg,
        tx_lv_left_start,
        tx_lv_left,
        class_="thick",
        start_anchor=tx_lv_left_start,
        end_anchor=tx_lv_left,
    )
    _draw_line_anchored(
        dwg,
        tx_lv_right_start,
        tx_lv_right,
        class_="thick",
        start_anchor=tx_lv_right_start,
        end_anchor=tx_lv_right,
    )

    tr_text_x = tr_center_x + tr_radius * 2 + 90
    tr_text_y = max(tr_top_y - tr_radius - 6, equip_y + 8)
    tr_lines = [
        "Transformer",
        f"{format_kv(spec.mv_voltage_kv)}/{format_v(spec.lv_voltage_v_ll)}",
        format_mva(spec.transformer_mva),
    ]
    if spec.transformer_vector_group:
        tr_lines.append(str(spec.transformer_vector_group))
    if spec.transformer_uk_percent:
        tr_lines.append(f"Uk={format_percent(spec.transformer_uk_percent)}")
    cooling = (
        spec.equipment_list.get("transformer", {}).get("cooling")
        if isinstance(spec.equipment_list, dict)
        else None
    )
    if cooling:
        tr_lines.append(str(cooling))
    for idx, line in enumerate(tr_lines):
        dwg.add(dwg.text(line, insert=(tr_text_x, tr_text_y + idx * 16), class_="label"))

    bus_x1 = skid_x + skid_pad
    bus_x2 = skid_x + diagram_width - skid_pad
    busbar_class = "busbar" if dark_mode else "thick"
    dwg.add(dwg.line((bus_x1, bus_y), (bus_x2, bus_y), class_=busbar_class))
    dwg.add(dwg.text("LV Busbar", insert=(bus_x1, bus_y - 8), class_="label"))

    pcs_label_offset = _safe_float(layout_params.get("pcs_label_offset"), 10.0)
    pcs_switch_offset = _safe_float(layout_params.get("pcs_switch_offset"), 8.0)
    pcs_breaker_size = _safe_float(layout_params.get("pcs_breaker_size"), 6.0)
    lv_tap_nodes = bool(layout_params.get("lv_tap_nodes", False))
    lv_node_r = 3.0

    # transformer connection nodes + X on LV busbar (match PDF)
    _draw_solid_node(dwg, tx_lv_left[0], tx_lv_left[1], lv_node_r, node_fill)
    _draw_solid_node(dwg, tx_lv_right[0], tx_lv_right[1], lv_node_r, node_fill)
    _draw_breaker_x(dwg, tx_lv_left[0], bus_y, pcs_breaker_size)
    _draw_breaker_x(dwg, tx_lv_right[0], bus_y, pcs_breaker_size)

    # --- Aux power input branch (match PDF right-side arrow)
    aux_enable = bool(layout_params.get("aux_power_input", True))
    if aux_enable:
        aux_bus_len = 70.0
        aux_bus_y = bus_y - 90.0
        aux_bus_x2 = bus_x2 - 30.0
        aux_bus_x1 = aux_bus_x2 - aux_bus_len

        dwg.add(dwg.line((aux_bus_x1, aux_bus_y), (aux_bus_x2, aux_bus_y), class_="thin"))

        aux_drop_x = aux_bus_x1 + aux_bus_len * 0.35
        _draw_line_anchored(
            dwg,
            (aux_drop_x, aux_bus_y),
            (aux_drop_x, bus_y),
            class_="thin",
            start_anchor=(aux_drop_x, aux_bus_y),
            end_anchor=(aux_drop_x, bus_y),
        )
        _draw_breaker_x(dwg, aux_drop_x, bus_y, pcs_breaker_size)
        _draw_dc_switch(dwg, aux_drop_x, (aux_bus_y + bus_y) / 2 - 6.0, 12.0)

        arrow_tip_x = min(diagram_right - 6.0, aux_bus_x2 + 30.0)
        _draw_arrow_head_right(dwg, arrow_tip_x, aux_bus_y, 10.0)
        dwg.add(
            dwg.text(
                "Power input from Auxiliary transformer for station",
                insert=(arrow_tip_x + 8.0, aux_bus_y + 4.0),
                class_="label",
            )
        )

    for idx in range(pcs_count):
        pcs_center_x = pcs_centers[idx]
        pcs_left_x = pcs_center_x - pcs_box_w / 2
        dwg.add(dwg.rect(insert=(pcs_left_x, pcs_y), size=(pcs_box_w, pcs_box_h), class_="outline"))
        if compact_mode:
            label_y = bus_y + pcs_label_offset
            label_x = pcs_center_x + 6
            dwg.add(
                dwg.text(
                    f"PCS-{idx + 1}",
                    insert=(label_x, label_y),
                    class_="label",
                    text_anchor="start",
                )
            )
            _draw_pcs_dc_ac_symbol(
                dwg,
                pcs_left_x + pcs_box_w * 0.12,
                pcs_y + pcs_box_h * 0.26,
                pcs_box_w * 0.76,
                pcs_box_h * 0.68,
            )
        else:
            dwg.add(
                dwg.text(
                    f"PCS-{idx + 1}",
                    insert=(pcs_center_x + 6, pcs_y + 20),
                    class_="label",
                    text_anchor="start",
                )
            )
            rating = spec.pcs_rating_kw_list[idx] if idx < len(spec.pcs_rating_kw_list) else 0.0
            rating_text = f"{rating:.0f} kW" if rating else "TBD"
            dwg.add(
                dwg.text(
                    rating_text,
                    insert=(pcs_center_x + 6, pcs_y + 38),
                    class_="label",
                    text_anchor="start",
                )
            )

        tap = (pcs_center_x, bus_y)
        pcs_in = (pcs_center_x, pcs_y)
        _draw_line_anchored(
            dwg,
            tap,
            pcs_in,
            class_="thin",
            start_anchor=tap,
            end_anchor=pcs_in,
        )

        # match PDF: X marker sits ON LV busbar
        _draw_breaker_x(dwg, pcs_center_x, bus_y, pcs_breaker_size)

        if compact_mode:
            # match PDF: switch symbol on the down-lead just below LV bus
            switch_h = 12.0
            switch_y_local = bus_y + 6.0
            _draw_dc_switch(dwg, pcs_center_x, switch_y_local, switch_h)

        if lv_tap_nodes:
            _draw_node(dwg, tap[0], tap[1], lv_node_r, node_fill)

    if compact_mode:
        dwg.add(dwg.rect(insert=(battery_x, battery_y), size=(battery_w, battery_h), class_="dash"))
        if dark_mode:
            dwg.add(
                dwg.text(
                    "DC Block (BESS)",
                    insert=(battery_x + battery_w - 8, battery_y + 16),
                    class_="label title",
                    text_anchor="end",
                )
            )
        else:
            dwg.add(
                dwg.text(
                    "Battery Storage Bank",
                    insert=(battery_x + 8, battery_y + 16),
                    class_="label title",
                )
            )

        dc_node_r = 2.5
        for idx in range(pcs_count):
            line_x = pcs_centers[idx]
            dc_top = pcs_y + pcs_box_h
            per_feeder = (
                per_feeder_counts[idx] if idx < len(per_feeder_counts) else 1
            )
            block_count = max(1, min(per_feeder, max_blocks))
            stack_h = dc_block_h * block_count + dc_block_gap_y * (block_count - 1)
            stack_top_y = dc_box_y + (dc_stack_h - stack_h) / 2
            branch_bus_y = stack_top_y - 10
            available = max(8.0, branch_bus_y - dc_top)

            # spacing for: switch + fuse + switch (match PDF 2-level switching)
            switch_h = 14.0
            fuse_h = 10.0
            gap_before = 6.0
            gap_between = 8.0
            gap_after = 8.0
            total = gap_before + switch_h + gap_between + fuse_h + gap_between + switch_h + gap_after
            if total > available:
                scale = max(0.55, available / total)
                switch_h *= scale
                fuse_h *= scale
                gap_before *= scale
                gap_between *= scale
                gap_after *= scale

            # positions
            switch1_y = dc_top + gap_before
            fuse_top = switch1_y + switch_h + gap_between
            fuse_center_y = fuse_top + fuse_h / 2
            switch2_y = fuse_top + fuse_h + gap_between

            pcs_out = (line_x, dc_top)
            prot_center = (line_x, fuse_center_y)
            branch_bus = (line_x, branch_bus_y)

            _draw_line_anchored(
                dwg,
                pcs_out,
                prot_center,
                class_="thin",
                start_anchor=pcs_out,
                end_anchor=prot_center,
            )
            _draw_dc_switch(dwg, line_x, switch1_y, switch_h)
            _draw_fuse(dwg, line_x, fuse_top, max(6.0, pcs_box_w * 0.1), fuse_h)
            _draw_dc_switch(dwg, line_x, switch2_y, switch_h)

            _draw_line_anchored(
                dwg,
                prot_center,
                branch_bus,
                class_="thin",
                start_anchor=prot_center,
                end_anchor=branch_bus,
            )
            _draw_node(dwg, branch_bus[0], branch_bus[1], dc_node_r, node_fill)

            block_positions = []
            if block_count > 1:
                bus_half = min(16.0, slot_w * 0.18)
                dwg.add(
                    dwg.line(
                        (line_x - bus_half, branch_bus_y),
                        (line_x + bus_half, branch_bus_y),
                        class_="thin",
                    )
                )
            for b in range(block_count):
                block_y = stack_top_y + b * (dc_block_h + dc_block_gap_y)
                block_positions.append((line_x, block_y))

            for center_x, block_y in block_positions:
                dc_in = (center_x, block_y)
                _draw_line_anchored(
                    dwg,
                    (center_x, branch_bus_y),
                    dc_in,
                    class_="thin",
                    start_anchor=(center_x, branch_bus_y),
                    end_anchor=dc_in,
                )

                # match PDF: triangle terminal at DC block input
                _draw_triangle_up_tip(dwg, dc_in[0], dc_in[1], 6.0)

                dwg.add(
                    dwg.rect(
                        insert=(center_x - pcs_box_w * 0.4, block_y),
                        size=(pcs_box_w * 0.8, dc_block_h),
                        class_="outline",
                    )
                )
                inner_pad = max(10.0, dc_block_h * 0.12)
                usable_h = max(1.0, dc_block_h - inner_pad * 2)
                _draw_battery_column(
                    dwg,
                    center_x,
                    block_y + inner_pad,
                    usable_h,
                    6,
                )
    else:
        dwg.add(dwg.line((bus_x1, dc_bus_a_y), (bus_x2, dc_bus_a_y), class_=busbar_class))
        dwg.add(dwg.text("DC BUSBAR A", insert=(bus_x1, dc_bus_a_y - 8), class_="label"))
        dwg.add(dwg.line((bus_x1, dc_bus_b_y), (bus_x2, dc_bus_b_y), class_=busbar_class))
        dwg.add(dwg.text("DC BUSBAR B", insert=(bus_x1, dc_bus_b_y - 8), class_="label"))

        dc_node_r = 2.5
        for idx in range(pcs_count):
            line_x = pcs_centers[idx]
            target_bus_y = dc_bus_a_y if idx < group_split else dc_bus_b_y
            pcs_out = (line_x, pcs_y + pcs_box_h)
            target = (line_x, target_bus_y)
            _draw_line_anchored(
                dwg,
                pcs_out,
                target,
                class_="thin",
                start_anchor=pcs_out,
                end_anchor=target,
            )
            _draw_node(dwg, target[0], target[1], dc_node_r, node_fill)

        dwg.add(dwg.rect(insert=(battery_x, battery_y), size=(battery_w, battery_h), class_="dash"))
        if dark_mode:
            dwg.add(
                dwg.text(
                    "DC Block (BESS)",
                    insert=(battery_x + battery_w - 8, battery_y + 16),
                    class_="label title",
                    text_anchor="end",
                )
            )
        else:
            dwg.add(
                dwg.text(
                    "Battery Storage Bank",
                    insert=(battery_x + 8, battery_y + 16),
                    class_="label title",
                )
            )

        circuit_x1 = battery_x + 60
        circuit_x2 = battery_x + battery_w - 60
        dwg.add(dwg.line((circuit_x1, dc_circuit_a_y), (circuit_x2, dc_circuit_a_y), class_="thin"))
        dwg.add(dwg.text("Circuit A", insert=(circuit_x1, dc_circuit_a_y - 6), class_="small"))
        dwg.add(dwg.line((circuit_x1, dc_circuit_b_y), (circuit_x2, dc_circuit_b_y), class_="thin"))
        dwg.add(dwg.text("Circuit B", insert=(circuit_x1, dc_circuit_b_y - 6), class_="small"))

        link_x = bus_x2 - 40
        dwg.add(dwg.line((link_x, dc_bus_a_y), (link_x, dc_circuit_a_y), class_="thin"))
        dwg.add(dwg.line((link_x, dc_bus_b_y), (link_x, dc_circuit_b_y), class_="thin"))

        block_index = 0
        for row in range(block_rows):
            for col in range(block_cols):
                if show_individual_blocks and block_index >= dc_blocks_total:
                    break
                cell_x = dc_box_x_start + col * (dc_box_w + block_gap_x)
                cell_y = dc_box_y + row * (dc_box_h + block_gap_y)
                dwg.add(dwg.rect(insert=(cell_x, cell_y), size=(dc_box_w, dc_box_h), class_="outline"))

                if show_individual_blocks:
                    label = f"DC Block #{block_index + 1} ({format_mwh(spec.dc_block_energy_mwh)})"
                else:
                    label = f"DC Block ({format_mwh(spec.dc_block_energy_mwh)}) x {dc_blocks_total}"
                dwg.add(dwg.text(label, insert=(cell_x + 6, cell_y + 20), class_="small"))
                dwg.add(dwg.text("2 circuits (A/B)", insert=(cell_x + 6, cell_y + 38), class_="small"))

                line_x_a = cell_x + dc_box_w * 0.4
                line_x_b = cell_x + dc_box_w * 0.6
                dwg.add(dwg.line((line_x_a, cell_y), (line_x_a, dc_circuit_a_y), class_="thin"))
                dwg.add(dwg.line((line_x_b, cell_y), (line_x_b, dc_circuit_b_y), class_="thin"))

                block_index += 1
            if show_individual_blocks and block_index >= dc_blocks_total:
                break

        if not dark_mode:
            dwg.add(
                dwg.text(
                    "Each DC block provides Circuit A and Circuit B.",
                    insert=(battery_x + 8, battery_note_y),
                    class_="small",
                )
            )

    if draw_summary:
        dwg.add(dwg.rect(insert=(note_x, note_y), size=(note_w, note_h), class_="outline"))
        dwg.add(
            dwg.text(
                "Allocation Summary (AC Block group)",
                insert=(note_x + 8, note_y + 18),
                class_="label title",
            )
        )
        for idx, line in enumerate(wrapped_lines):
            dwg.add(
                dwg.text(
                    line,
                    insert=(note_x + 8, note_y + 36 + idx * 18),
                    class_="label",
                )
            )

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    dwg.save()

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
