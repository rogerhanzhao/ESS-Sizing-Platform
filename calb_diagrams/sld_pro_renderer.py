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

"""
sld_pro_renderer.py
-------------------
用于渲染“专业版”单线图（SLD）SVG/PNG 的渲染器。
"""

import math
from pathlib import Path
from typing import List, Tuple

try:  # pragma: no cover - optional dependency
    import svgwrite
except Exception:  # pragma: no cover
    svgwrite = None

try:
    import cairosvg
except Exception:  # pragma: no cover - optional dependency
    cairosvg = None

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

# =============================================================================
# 安全转换 / 格式化工具
# =============================================================================


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
    return "TBD" if v <= 0 else f"{v:.1f} MVA"


def format_kv(value) -> str:
    v = _safe_float(value, 0.0)
    return "TBD" if v <= 0 else f"{v:.1f} kV"


def format_v(value) -> str:
    v = _safe_float(value, 0.0)
    return "TBD" if v <= 0 else f"{v:.0f} V"


def format_percent(value) -> str:
    v = _safe_float(value, 0.0)
    return "TBD" if v <= 0 else f"{v:.1f}%"


def format_mwh(value) -> str:
    v = _safe_float(value, 0.0)
    return "TBD" if v <= 0 else f"{v:.3f} MWh"


def format_kv_plain(value) -> str:
    v = _safe_float(value, 0.0)
    if v <= 0:
        return "TBD"
    if abs(v - round(v)) < 1e-3:
        return f"{int(round(v))}kV"
    return f"{v:.1f}kV"


def format_v_plain(value) -> str:
    v = _safe_float(value, 0.0)
    return "TBD" if v <= 0 else f"{v:.0f}V"


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


# =============================================================================
# 通用绘图基础元件（节点/线/符号）
# =============================================================================


def _draw_pcs_dc_ac_symbol(dwg, x: float, y: float, w: float, h: float) -> None:
    if w <= 0 or h <= 0:
        return

    pad = min(w, h) * 0.12
    inner_x = x + pad
    inner_y = y + pad
    inner_w = max(1.0, w - pad * 2)
    inner_h = max(1.0, h - pad * 2)

    dwg.add(
        dwg.line(
            (inner_x, inner_y),
            (inner_x + inner_w, inner_y + inner_h),
            class_="thin",
        )
    )

    dc_len = inner_w * 0.35
    dc_x1 = inner_x
    dc_x2 = inner_x + dc_len
    dc_y_base = inner_y + inner_h - inner_h * 0.18
    dc_gap = inner_h * 0.12
    dwg.add(dwg.line((dc_x1, dc_y_base), (dc_x2, dc_y_base), class_="thin"))
    dwg.add(dwg.line((dc_x1, dc_y_base - dc_gap), (dc_x2, dc_y_base - dc_gap), class_="thin"))

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


def _draw_contact_bar(dwg, x: float, y: float, length: float, line_class: str = "thin") -> None:
    if length <= 0:
        return
    half = length / 2
    dwg.add(dwg.line((x - half, y), (x + half, y), class_=line_class))


def _draw_open_circle(dwg, x: float, y: float, r: float, line_class: str = "thin") -> None:
    if r <= 0:
        return
    dwg.add(dwg.circle(center=(x, y), r=r, class_=line_class))


def _draw_triangle_down(dwg, x: float, y: float, size: float) -> None:
    half = size * 0.6
    points = [(x, y + size), (x - half, y), (x + half, y)]
    dwg.add(dwg.polygon(points=points, class_="thin", fill="none"))


def _draw_triangle_up(dwg, x: float, y: float, size: float) -> None:
    half = size * 0.6
    points = [(x, y - size), (x - half, y), (x + half, y)]
    dwg.add(dwg.polygon(points=points, class_="thin", fill="none"))


def _draw_triangle_pair(dwg, x: float, y_center: float, size: float, gap: float) -> None:
    top_apex = y_center - gap / 2
    bottom_apex = y_center + gap / 2
    _draw_triangle_down(dwg, x, top_apex - size, size)
    _draw_triangle_up(dwg, x, bottom_apex + size, size)
    # Connect the two flow triangles with a center line segment
    if gap > 0:
        _draw_line_anchored(dwg, (x, top_apex), (x, bottom_apex), class_="thin")


def _draw_breaker_circle(dwg, x: float, y: float, r: float) -> None:
    if r <= 0:
        return
    dwg.add(dwg.circle(center=(x, y), r=r, class_="outline"))
    dwg.add(dwg.line((x - r * 0.7, y - r * 0.7), (x + r * 0.7, y + r * 0.7), class_="thin"))
    dwg.add(dwg.line((x - r * 0.7, y + r * 0.7), (x + r * 0.7, y - r * 0.7), class_="thin"))


def _draw_transformer_symbol(dwg, x: float, y: float, r: float) -> tuple[tuple[float, float], tuple[float, float]]:
    gap = r * 0.9
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


def _snap_point(point: tuple[float, float], anchor: tuple[float, float], tol: float = 0.5) -> tuple[float, float]:
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

# =============================================================================
# Helper: Specific Symbols for Picture 1 (RMU) & Cable Termination
# =============================================================================

def _draw_arrow_up(dwg, x: float, y: float, size: float = 10.0) -> None:
    """画一个向上的箭头（用于进出线终端）"""
    points = [(x, y - size), (x - size * 0.5, y), (x + size * 0.5, y)]
    dwg.add(dwg.polygon(points=points, class_="outline", fill="none"))

def _draw_cable_termination_down(dwg, x: float, y: float, size: float = 8.0) -> None:
    """
    画尖端相对的两个三角形 (Cable Sealing End / Plug-in / Direction Arrows)
    用于变压器柜底部，符合图2的样式。
    """
    half = size * 0.6
    height = size
    gap = size  # separate triangles by ~one triangle height
    
    # Top Triangle: Points DOWN (???)
    # Base at y, Tip at y+height
    points_top = [(x - half, y), (x + half, y), (x, y + height)]
    dwg.add(dwg.polygon(points=points_top, class_="thin", fill="none"))
    
    # Bottom Triangle: Points UP (???)
    # Tip at y+height+gap, Base at y+2*height+gap
    points_bot = [(x, y + height + gap), (x - half, y + 2 * height + gap), (x + half, y + 2 * height + gap)]
    dwg.add(dwg.polygon(points=points_bot, class_="thin", fill="none"))

    # Connect the two flow triangles with a line
    dwg.add(dwg.line((x, y + height), (x, y + height + gap), class_="thin"))
    
    # Line continuing down from the base of the bottom triangle
    dwg.add(dwg.line((x, y + 2 * height + gap), (x, y + 2 * height + gap + 4), class_="thin"))

def _draw_lbs_symbol(dwg, x: float, y: float, open_right: bool = True) -> dict:
    """
    绘制 RMU 进出线负荷开关 (LBS) - 修正版:
    - 顶部：无短横线 (已删除刀闸支点位置的短横线)
    - 底部：小圆圈 (Pivot) + 圆圈下方的短切线 (已加回)
    - 刀闸：从顶部连接点延伸，向下断开 (Open state)
    x, y: 底部圆圈中心坐标
    """
    h = 24.0
    # y is the bottom coordinate center
    top_y = y - h
    
    r_pivot = 2.5
    
    # Bottom 1: Circle (Pivot/Contact)
    dwg.add(dwg.circle(center=(x, y), r=r_pivot, class_="outline", fill="none"))
    
    # Bottom 2: Tangent Line (Below Circle) - 已加回
    tangent_y = y + r_pivot
    dwg.add(dwg.line((x - 6, tangent_y), (x + 6, tangent_y), class_="thin"))
    
    # Top: Fixed Contact Bar - 已删除 (Requested: 删除刀闸支点位置的短横线)
    # dwg.add(dwg.line((x - 4, top_y), (x + 4, top_y), class_="thin"))
    
    # Blade: Pivot at Top Contact, ends near Bottom Circle
    dx = 8.0 if open_right else -8.0
    # Draw line from top contact center to a point offset from bottom
    dwg.add(dwg.line((x, top_y), (x + dx, y - r_pivot - 2), class_="thin"))
    
    return {"top": top_y, "bottom": y}

def _draw_earth_switch_feeder(dwg, x: float, y: float, side: str = 'left') -> None:
    """
    画进出线柜的接地开关。
    结构：横向引出线 -> 竖直静触头 -> 下方接地 -> 刀闸（下支点，向上闭合）
    刀闸方向：向左（远离触头）。
    """
    arm_len = 16.0
    direction = -1.0 if side == 'left' else 1.0
    
    # 1. Horizontal arm (from main line)
    end_x = x + direction * arm_len
    dwg.add(dwg.line((x, y), (end_x, y), class_="thin"))
    
    # 2. Fixed contact (small vertical bar) at end_x, y
    dwg.add(dwg.line((end_x, y - 3), (end_x, y + 3), class_="thin"))
    
    # 3. Ground Pivot (Below)
    ground_pivot_y = y + 14.0
    
    # Line from ground pivot up towards contact (but stop short)
    _draw_ground(dwg, end_x, ground_pivot_y + 4)
    dwg.add(dwg.line((end_x, ground_pivot_y), (end_x, ground_pivot_y + 4), class_="thin"))
    
    # 4. Blade (Open state)
    # Pivot at bottom (ground_pivot_y), moves UP towards contact (y).
    # To show open: blade leans LEFT (if direction is left).
    blade_len = 12.0
    dwg.add(dwg.line((end_x, ground_pivot_y), (end_x - direction * 6, ground_pivot_y - blade_len), class_="thin"))


def _draw_vpis_symbol_feeder(dwg, x: float, y: float, side: str = 'right') -> None:
    """
    VPIS for Feeders: Horizontal Tap -> Vertical Down -> Horizontal Cap -> Down -> Indicator -> Ground
    """
    arm_len = 16.0
    direction = 1.0 if side == 'right' else -1.0
    
    # 1. Horizontal arm
    bend_x = x + direction * arm_len
    dwg.add(dwg.line((x, y), (bend_x, y), class_="thin"))
    
    # 2. Vertical Down to Capacitor
    cap_y = y + 8.0
    dwg.add(dwg.line((bend_x, y), (bend_x, cap_y), class_="thin"))
    
    # 3. Horizontal Capacitor
    cap_w = 12.0
    dwg.add(dwg.line((bend_x - cap_w/2, cap_y), (bend_x + cap_w/2, cap_y), class_="thin"))
    dwg.add(dwg.line((bend_x - cap_w/2, cap_y + 4), (bend_x + cap_w/2, cap_y + 4), class_="thin"))
    
    # 4. Vertical Down to Indicator
    ind_y = cap_y + 4 + 14.0
    dwg.add(dwg.line((bend_x, cap_y + 4), (bend_x, ind_y - 6), class_="thin"))
    
    # 5. Indicator (Circle X)
    _draw_breaker_circle(dwg, bend_x, ind_y, 6.0)
    
    # 6. Ground
    _draw_ground(dwg, bend_x, ind_y + 6)
    dwg.add(dwg.line((bend_x, ind_y + 6), (bend_x, ind_y + 10), class_="thin")) # Small extension


def _draw_vpis_symbol(dwg, x: float, y: float, side: str = 'right') -> None:
    """
    VPIS for Center Feeder
    """
    _draw_vpis_symbol_feeder(dwg, x, y, side)


def _draw_surge_arrester_symbol(dwg, x: float, y: float) -> None:
    """
    避雷器: 矩形 + 内部箭头 + 接地
    """
    w = 12.0
    h = 24.0
    
    # Connection line down to box
    dwg.add(dwg.line((x, y), (x, y + 6), class_="thin"))
    box_y = y + 6
    
    # Box
    dwg.add(dwg.rect(insert=(x - w/2, box_y), size=(w, h), class_="outline"))
    
    # Arrow inside (Down)
    # Head
    dwg.add(dwg.line((x, box_y + h - 4), (x - 3, box_y + h - 8), class_="thin"))
    dwg.add(dwg.line((x, box_y + h - 4), (x + 3, box_y + h - 8), class_="thin"))
    # Shaft
    dwg.add(dwg.line((x, box_y + 4), (x, box_y + h - 4), class_="thin"))
    
    # Ground
    dwg.add(dwg.line((x, box_y + h), (x, box_y + h + 4), class_="thin"))
    _draw_ground(dwg, x, box_y + h + 4)

# =============================================================================
# AC Switch Helper
# =============================================================================
def _draw_arrow_box(dwg, x: float, y: float, w: float, h: float) -> None:
    dwg.add(dwg.rect(insert=(x - w / 2, y), size=(w, h), class_="outline"))
    dwg.add(dwg.line((x, y + 4), (x, y + h - 6), class_="thin"))
    dwg.add(dwg.line((x, y + h - 6), (x - 4, y + h - 10), class_="thin"))
    dwg.add(dwg.line((x, y + h - 6), (x + 4, y + h - 10), class_="thin"))

# =============================================================================
# DC Switch
# =============================================================================
def _draw_dc_switch(
    dwg,
    x: float,
    y: float,
    h: float,
    *,
    lead_end_y: float | None = None,
) -> float:
    if h <= 0:
        return y

    bottom_y = (y + h) if lead_end_y is None else max(lead_end_y, y + h * 0.6)

    contact_y = y + h * 0.18
    pivot_y = y + h * 0.42
    fuse_top = y + h * 0.62
    fuse_h = max(8.0, min(h * 0.20, h * 0.30))
    
    fuse_h = fuse_h * 2.0
    fuse_h = min(fuse_h, h * 0.55)
    fuse_bot = fuse_top + fuse_h

    if fuse_bot > y + h * 0.92:
        fuse_top = y + h * 0.55
        fuse_bot = fuse_top + fuse_h

    contact_w = max(10.0, min(h * 0.42, h * 0.60))
    fuse_w = max(8.0, fuse_h * 0.55)

    blade_dx = h * 0.32 * (2.0 / 3.0)
    blade_dy = h * 0.08
    blade_tip_x = x - blade_dx
    blade_tip_y = contact_y + blade_dy

    _draw_line_anchored(
        dwg,
        (x, y),
        (x, contact_y),
        class_="thin",
        start_anchor=(x, y),
        end_anchor=(x, contact_y),
    )

    dwg.add(dwg.line((x - contact_w / 2, contact_y), (x + contact_w / 2, contact_y), class_="thin"))

    _draw_line_anchored(
        dwg,
        (x, pivot_y),
        (x, fuse_top),
        class_="thin",
        start_anchor=(x, pivot_y),
        end_anchor=(x, fuse_top),
    )

    dwg.add(dwg.line((x, pivot_y), (blade_tip_x, blade_tip_y), class_="thin"))

    dwg.add(dwg.rect(insert=(x - fuse_w / 2, fuse_top), size=(fuse_w, fuse_bot - fuse_top), class_="outline"))

    _draw_line_anchored(
        dwg,
        (x, fuse_bot),
        (x, bottom_y),
        class_="thin",
        start_anchor=(x, fuse_bot),
        end_anchor=(x, bottom_y),
    )

    return bottom_y


# =============================================================================
# 其他组合符号 / 文字排版工具
# =============================================================================


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


def _rmu_class_kv(mv_kv: float) -> float:
    if mv_kv <= 24:
        return 24.0
    if mv_kv <= 36:
        return 36.0
    return round(mv_kv)


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


# =============================================================================
# Dark mode 设备清单
# =============================================================================


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
    transformer = equipment.get("transformer", {}) if isinstance(equipment.get("transformer"), dict) else {}
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

    rated_kv = _safe_float(rmu.get("rated_kv"), 0.0)
    if rated_kv <= 0:
        rated_kv = _rmu_class_kv(spec.mv_voltage_kv)
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
    bess_line = f"1~{dc_blocks_total} BESS" if dc_blocks_total > 0 else "BESS TBD"

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


def _build_equipment_list(spec: SldGroupSpec, compact_mode: bool = False) -> List[Tuple[str, str]]:
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
    rated_kv = _safe_float(rmu.get("rated_kv"), 0.0)
    if rated_kv <= 0:
        rated_kv = _rmu_class_kv(spec.mv_voltage_kv)
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


# =============================================================================
# PNG 导出
# =============================================================================


def _write_png(svg_path: Path, png_path: Path) -> None:
    if cairosvg is None:
        raise ImportError("cairosvg is required to export PNG from SVG.")
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


# =============================================================================
# 主渲染入口：render_sld_pro_svg
# =============================================================================

def render_sld_pro_svg(
    spec: SldGroupSpec, out_svg: Path, out_png: Path | None = None
) -> tuple[Path | None, str | None]:
    """
    渲染 SLD Pro SVG（可选输出 PNG）。
    返回：(out_svg_path, png_warning_message)
    """
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
        table_h = dark_list_pad_y * 2 + total_lines * row_h + (len(dark_sections) - 1) * dark_section_gap
    else:
        items = _build_equipment_list(spec, compact_mode)
        item_chars = _approx_chars(item_col_w)
        spec_chars = _approx_chars(spec_col_w)
        for item, spec_text in items:
            item_lines = _table_row_lines(item, item_chars)
            spec_lines = _table_row_lines(spec_text, spec_chars)
            rows.append({"item_lines": item_lines, "spec_lines": spec_lines, "lines": max(len(item_lines), len(spec_lines))})
        table_h = title_h + header_h + sum(row["lines"] * row_h for row in rows)

    skid_x = diagram_left
    skid_y = table_y
    dash_offset_y = _safe_float(layout_params.get("dash_offset_y"), 12.0)
    skid_pad = _safe_float(layout_params.get("skid_pad"), 60.0)
    battery_pad = _safe_float(layout_params.get("battery_pad"), 40.0)

    pcs_count = max(1, int(spec.pcs_count))
    group_a, group_b = _split_pcs_groups(pcs_count)
    group_split = len(group_a)

    pcs_box_h = 50
    pcs_pad = skid_pad
    pcs_span = max(240.0, diagram_width - pcs_pad * 2)
    slot_w = pcs_span / pcs_count

    if compact_mode:
        pcs_box_w = min(80.0, max(58.0, slot_w - 20.0))
        pcs_box_h = max(66.0, pcs_box_w * 0.9)
    else:
        pcs_box_w = min(160.0, max(110.0, slot_w - 10.0))

    pcs_centers = [skid_x + pcs_pad + (idx + 0.5) * slot_w for idx in range(pcs_count)]
    mv_center_x = skid_x + diagram_width / 2
    gap_center = mv_center_x

    # -------------------------------------------------------------------------
    # MV / RMU Layout Constants
    # -------------------------------------------------------------------------
    # MV Busbar sits here
    mv_bus_y = skid_y + 150 # Moved down to give more space for Feeders
    
    # Feeder (Upwards) dimensions
    feeder_top_y = skid_y + 40.0 # Where arrows are
    
    # Center (Downwards) dimensions
    # Need significant space for: Iso, Earth1, Breaker, Earth2, CT, Surge/VPIS, Cable
    tr_top_y = mv_bus_y + 220.0
    tr_radius = 14.0

    # LV Busbar
    bus_y = tr_top_y + tr_radius * 2 + 50.0
    
    # PCS
    pcs_bus_gap = _safe_float(layout_params.get("pcs_bus_gap"), 75.0)
    pcs_y = bus_y + pcs_bus_gap

    dc_blocks_total = _safe_int(spec.dc_blocks_total_in_group, 0)
    battery_x = skid_x + battery_pad
    battery_w = diagram_width - battery_pad * 2

    # -------------------------------------------------------------------------
    # Layout DC Block / Summary
    # -------------------------------------------------------------------------
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
        dc_box_w = min(160.0, max(110.0, (block_area_w - (block_cols - 1) * block_gap_x) / block_cols))
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
        group_a_text = ", ".join([f"F{idx}={group_a_counts[i]}" for i, idx in enumerate(group_a)]) or "None"
        group_b_text = ", ".join([f"F{idx}={group_b_counts[i]}" for i, idx in enumerate(group_b)]) or "None"
        summary_lines = [
            f"Battery Storage Bank: {dc_blocks_total} blocks @ {format_mwh(spec.dc_block_energy_mwh)} each",
            f"PCS count: {pcs_count}, LV {format_v(spec.lv_voltage_v_ll)}",
            f"Group A feeders: {group_a_text} (total {sum(group_a_counts)})",
            f"Group B feeders: {group_b_text} (total {sum(group_b_counts)})",
            f"Allocation: {allocation_text}",
            "Counts indicate allocation for sizing/configuration; detailed DC wiring is not represented.",
        ]

    wrapped_lines = []
    note_w = note_h = note_x = note_y = 0.0
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
        current_y = table_y + 12
        for idx, section in enumerate(dark_sections):
            current_y += row_h
            dwg.add(dwg.text(section["title"], insert=(table_x + list_pad_x, current_y - 3), class_="label title"))
            for line in section["lines"]:
                current_y += row_h
                dwg.add(
                    dwg.text(
                        line,
                        insert=(table_x + list_pad_x + 12, current_y - 3),
                        class_="label small",
                    )
                )
            if idx < len(dark_sections) - 1:
                current_y += 6
                sep_y = current_y - 3
                dwg.add(dwg.line((table_x, sep_y), (table_x + table_w, sep_y), class_="thin"))
    else:
        dwg.add(dwg.rect(insert=(table_x, table_y), size=(table_w, table_h), class_="outline"))
        col_split = table_x + item_col_w
        dwg.add(dwg.line((col_split, table_y), (col_split, table_y + table_h), class_="thin"))
        dwg.add(dwg.line((table_x, table_y + title_h), (table_x + table_w, table_y + title_h), class_="thin"))
        dwg.add(dwg.line((table_x, table_y + title_h + header_h), (table_x + table_w, table_y + title_h + header_h), class_="thin"))
        dwg.add(dwg.text("Equipment List", insert=(table_x + 6, table_y + 14), class_="label title"))
        dwg.add(dwg.text("Item", insert=(table_x + 6, table_y + title_h + 13), class_="label"))
        dwg.add(dwg.text("Spec", insert=(col_split + 6, table_y + title_h + 13), class_="label"))

        current_y = table_y + title_h + header_h
        for row in rows:
            for line_idx, line in enumerate(row["item_lines"]):
                ytxt = current_y + row_h * (line_idx + 1) - 3
                dwg.add(dwg.text(line, insert=(table_x + 6, ytxt), class_="label"))
            for line_idx, line in enumerate(row["spec_lines"]):
                ytxt = current_y + row_h * (line_idx + 1) - 3
                dwg.add(dwg.text(line, insert=(col_split + 6, ytxt), class_="label"))
            current_y += row_h * row["lines"]
            dwg.add(dwg.line((table_x, current_y), (table_x + table_w, current_y), class_="thin"))

    ac_dash_y = skid_y - dash_offset_y
    ac_dash_h = skid_h + dash_offset_y
    dwg.add(dwg.rect(insert=(skid_x, ac_dash_y), size=(diagram_width, ac_dash_h), class_="dash"))
    if dark_mode:
        dwg.add(dwg.text("AC Block (PCS&MV SKID)", insert=(skid_x + diagram_width - 8, ac_dash_y + 18), class_="label title", text_anchor="end"))
    else:
        dwg.add(dwg.text("PCS&MVT SKID (AC Block)", insert=(skid_x + 8, ac_dash_y + 18), class_="label title"))

    mv_labels = spec.equipment_list.get("mv_labels") if isinstance(spec.equipment_list, dict) else {}
    to_switchgear = mv_labels.get("to_switchgear") if isinstance(mv_labels, dict) else None
    to_other_rmu = mv_labels.get("to_other_rmu") if isinstance(mv_labels, dict) else None
    if not to_switchgear:
        to_switchgear = f"To {format_kv_plain(spec.mv_voltage_kv)} Switchgear" if dark_mode else f"To {format_kv(spec.mv_voltage_kv)} Switchgear"
    if not to_other_rmu:
        to_other_rmu = "To Other RMU"

    hv_bus_span = _safe_float(layout_params.get("hv_bus_span"), diagram_width * 0.45)
    hv_bus_span = max(220.0, min(hv_bus_span, diagram_width - skid_pad * 2))
    hv_bus_left = mv_center_x - hv_bus_span / 2
    hv_bus_right = mv_center_x + hv_bus_span / 2

    # Draw MV Busbar
    dwg.add(dwg.line((hv_bus_left, mv_bus_y), (hv_bus_right, mv_bus_y), class_="thick"))

    node_fill = label_color
    switch_contact_r = _safe_float(layout_params.get("switch_contact_r"), 2.4)
    mv_bus_node_r = _safe_float(layout_params.get("mv_bus_node_r"), 3.0)
    
    # -------------------------------------------------------------------------
    # FEEDERS (Left / Right) - UPWARD - Ref: Image 4
    # -------------------------------------------------------------------------
    # Topology: Bus -> Switch (LBS) -> Node -> (Left: Earth, Right: VPIS) -> Arrow
    
    feeder_xs = [hv_bus_left, hv_bus_right]
    feeder_labels = [to_switchgear, to_other_rmu]
    
    for i, x_pos in enumerate(feeder_xs):
        # 1. Bus Connection
        _draw_solid_node(dwg, x_pos, mv_bus_y, mv_bus_node_r, node_fill)
        
        # 2. Line Up to Switch Base
        switch_base_y = mv_bus_y - 20
        _draw_line_anchored(dwg, (x_pos, mv_bus_y), (x_pos, switch_base_y), class_="thin")
        
        # 3. LBS Switch (Blade opens to right)
        # Call new LBS drawer
        lbs_coords = _draw_lbs_symbol(dwg, x_pos, switch_base_y)
        switch_top_y = lbs_coords["top"]
        
        # 4. Node for Earth/VPIS
        node_y = switch_top_y - 15
        _draw_line_anchored(dwg, (x_pos, switch_top_y), (x_pos, node_y), class_="thin")
        _draw_solid_node(dwg, x_pos, node_y, 2.0, node_fill)
        
        # 5. Earth Switch (Left) - Lateral
        _draw_earth_switch_feeder(dwg, x_pos, node_y, side='left')
        
        # 6. VPIS (Right) - L Shape
        _draw_vpis_symbol_feeder(dwg, x_pos, node_y, side='right')
        
        # 7. Line Up to Arrow
        arrow_y = feeder_top_y
        _draw_line_anchored(dwg, (x_pos, node_y), (x_pos, arrow_y), class_="thin")
        _draw_arrow_up(dwg, x_pos, arrow_y)
        
        # Label
        align = "start" if i == 0 else "end"
        label_x = x_pos - 10 if i == 0 else x_pos + 10
        dwg.add(dwg.text(feeder_labels[i], insert=(label_x, arrow_y - 10), class_="label", text_anchor=align))

    # -------------------------------------------------------------------------
    # CENTER FEEDER (Transformer) - DOWNWARD - Ref: Compact SPDT (No Circles)
    # -------------------------------------------------------------------------
    
    cx = mv_center_x
    
    # 1. Bus Connection node
    _draw_solid_node(dwg, cx, mv_bus_y, mv_bus_node_r, node_fill)
    
    # 2. Circuit Breaker Schema
    # Structure: Bus -> Line -> X Mark -> Blade (Open) -> Connection Point (No Circle)
    
    cb_x_y = mv_bus_y + 20.0       
    cb_pivot_y = cb_x_y + 22.0     
    cb_size = 8.0
    
    # 2.1 Connection: Bus -> X Mark Top
    _draw_line_anchored(dwg, (cx, mv_bus_y), (cx, cb_x_y - cb_size/2), class_="thin")
    
    # 2.2 X Mark
    _draw_breaker_x(dwg, cx, cb_x_y, cb_size)
    
    # 2.3 CB Blade (Open to Left, No Pivot Circle)
    # Blade draws from the bottom connection point UPWARDS to near X
    blade_dx = -7.0
    cb_blade_tip_y = cb_x_y + cb_size/2 + 2.0
    
    # Draw Blade Line directly from pivot coordinate (clean connection)
    dwg.add(dwg.line(
        (cx, cb_pivot_y),             
        (cx + blade_dx, cb_blade_tip_y),    
        class_="thin"
    ))
    
    # 3. SPDT Disconnector / Selector Switch (COMPACT VERSION)
    # Located below the CB connection point
    
    # Distance from CB connection to Switch Top Contact
    switch_top_y = cb_pivot_y + 14.0 
    
    # Draw line connecting CB bottom to SPDT top
    _draw_line_anchored(dwg, (cx, cb_pivot_y), (cx, switch_top_y), class_="thin")
    
    # DISTANCE: Top Contact to Pivot
    spdt_height = 16.0 
    spdt_pivot_y = switch_top_y + spdt_height
    
    # 3.1 Top Static Contact (Horizontal Bar)
    dwg.add(dwg.line((cx - 4, switch_top_y), (cx + 4, switch_top_y), class_="thin"))
    
    # 3.2 Earth Static Contact (Left Side) - Compact
    earth_gap_x = 11.0 
    earth_contact_x = cx - earth_gap_x
    earth_contact_y = switch_top_y + spdt_height * 0.4 
    
    # Vertical static contact bar for Earth
    dwg.add(dwg.line((earth_contact_x, earth_contact_y - 3), (earth_contact_x, earth_contact_y + 3), class_="thin"))
    # Line to Ground symbol
    dwg.add(dwg.line((earth_contact_x, earth_contact_y), (earth_contact_x - 4, earth_contact_y), class_="thin"))
    _draw_ground(dwg, earth_contact_x - 4, earth_contact_y)
    
    # 3.3 SPDT Blade (Angled Left, Compact, No Pivot Circle)
    # Blade draws from the bottom connection point UPWARDS
    spdt_blade_end_x = cx - 7.0
    spdt_blade_end_y = spdt_pivot_y - 12.0
    
    dwg.add(dwg.line((cx, spdt_pivot_y), (spdt_blade_end_x, spdt_blade_end_y), class_="thin"))

    # 4. Branch Node & Symmetrical Layout (Surge / VPIS)
    sv_node_y = spdt_pivot_y + 24.0 
    
    # Line from SPDT connection point down to Branch Node
    _draw_line_anchored(dwg, (cx, spdt_pivot_y), (cx, sv_node_y), class_="thin")
    _draw_solid_node(dwg, cx, sv_node_y, 2.0, node_fill)
    
    sym_offset = 24.0
    
    # --- Left Side: Surge Arrester ---
    surge_x = cx - sym_offset
    dwg.add(dwg.line((cx, sv_node_y), (surge_x, sv_node_y), class_="thin"))
    dwg.add(dwg.line((surge_x, sv_node_y), (surge_x, sv_node_y + 6), class_="thin"))
    _draw_surge_arrester_symbol(dwg, surge_x, sv_node_y + 6)
    
    # --- Right Side: VPIS ---
    vpis_x = cx + sym_offset
    # Horizontal arm
    dwg.add(dwg.line((cx, sv_node_y), (vpis_x, sv_node_y), class_="thin"))
    # Vertical Down to Capacitor
    cap_y = sv_node_y + 8.0
    dwg.add(dwg.line((vpis_x, sv_node_y), (vpis_x, cap_y), class_="thin"))
    # Capacitor
    cap_w = 12.0
    dwg.add(dwg.line((vpis_x - cap_w/2, cap_y), (vpis_x + cap_w/2, cap_y), class_="thin"))
    dwg.add(dwg.line((vpis_x - cap_w/2, cap_y + 4), (vpis_x + cap_w/2, cap_y + 4), class_="thin"))
    # Down to Indicator
    ind_y = cap_y + 4 + 14.0
    dwg.add(dwg.line((vpis_x, cap_y + 4), (vpis_x, ind_y - 6), class_="thin"))
    # Indicator
    _draw_breaker_circle(dwg, vpis_x, ind_y, 6.0)
    # Ground
    _draw_ground(dwg, vpis_x, ind_y + 6)
    dwg.add(dwg.line((vpis_x, ind_y + 6), (vpis_x, ind_y + 10), class_="thin"))

    # 5. CTs
    ct_y = max(sv_node_y + 35.0, ind_y + 15.0)
    _draw_line_anchored(dwg, (cx, sv_node_y), (cx, ct_y + 8), class_="thin") 
    for offset in [-6, 0, 6]:
        dwg.add(dwg.circle(center=(cx + offset, ct_y), r=2.5, class_="outline"))
    
    # 6. Cable Termination
    term_y = ct_y + 20
    _draw_line_anchored(dwg, (cx, ct_y + 8), (cx, term_y), class_="thin")
    _draw_cable_termination_down(dwg, cx, term_y)
    
    # 7. To Transformer
    term_end_y = term_y + 16.0 + 4.0 
    _draw_line_anchored(dwg, (cx, term_end_y), (cx, tr_top_y - tr_radius), class_="thin")
    # -------------------------------------------------------------------------
    # Transformer & Below
    # -------------------------------------------------------------------------
    left_center, right_center = _draw_transformer_symbol(dwg, cx, tr_top_y, tr_radius)

    tx_lv_spacing = _safe_float(layout_params.get("tx_lv_spacing"), 14.0)
    requested_gap = _safe_float(layout_params.get("lv_bus_gap"), 0.0)
    if requested_gap <= 0:
        requested_gap = _safe_float(layout_params.get("lv_bus_coupler_r"), 0.0) * 2
    if requested_gap > 0:
        tx_lv_spacing = requested_gap / 2
    tx_lv_spacing = min(18.0, max(12.0, tx_lv_spacing))

    tx_lv_start_y = left_center[1] + tr_radius
    tx_lv_left_start = (cx - tx_lv_spacing, tx_lv_start_y)
    tx_lv_right_start = (cx + tx_lv_spacing, tx_lv_start_y)
    tx_lv_left = (cx - tx_lv_spacing, bus_y)
    tx_lv_right = (cx + tx_lv_spacing, bus_y)

    _draw_line_anchored(dwg, tx_lv_left_start, tx_lv_left, class_="thick", start_anchor=tx_lv_left_start, end_anchor=tx_lv_left)
    _draw_line_anchored(dwg, tx_lv_right_start, tx_lv_right, class_="thick", start_anchor=tx_lv_right_start, end_anchor=tx_lv_right)

    # Transformer Text
    tr_text_x = cx + tr_radius * 2 + 60
    tr_text_y = tr_top_y - 20
    tr_lines = [
        "Transformer",
        f"{format_kv(spec.mv_voltage_kv)}/{format_v(spec.lv_voltage_v_ll)}",
        format_mva(spec.transformer_mva),
    ]
    if spec.transformer_vector_group:
        tr_lines.append(str(spec.transformer_vector_group))
    if spec.transformer_uk_percent:
        tr_lines.append(f"Uk={format_percent(spec.transformer_uk_percent)}")
    cooling = spec.equipment_list.get("transformer", {}).get("cooling") if isinstance(spec.equipment_list, dict) else None
    if cooling:
        tr_lines.append(str(cooling))
    for idx, line in enumerate(tr_lines):
        dwg.add(dwg.text(line, insert=(tr_text_x, tr_text_y + idx * 16), class_="label"))

    bus_x1 = skid_x + skid_pad
    bus_x2 = skid_x + diagram_width - skid_pad
    busbar_class = "busbar" if dark_mode else "thick"

    lv_bus_split = bool(layout_params.get("lv_bus_split", True))
    if lv_bus_split:
        dwg.add(dwg.line((bus_x1, bus_y), (tx_lv_left[0], bus_y), class_=busbar_class))
        dwg.add(dwg.line((tx_lv_right[0], bus_y), (bus_x2, bus_y), class_=busbar_class))
    else:
        dwg.add(dwg.line((bus_x1, bus_y), (bus_x2, bus_y), class_=busbar_class))
    dwg.add(dwg.text("LV Busbar", insert=(bus_x1, bus_y - 8), class_="label"))

    # ---------------------------
    # PCS box + AC tap
    # ---------------------------
    pcs_label_offset = _safe_float(layout_params.get("pcs_label_offset"), 10.0)
    lv_tap_nodes = bool(layout_params.get("lv_tap_nodes", False))
    lv_node_r = 3.0
    pcs_tap_node_r = _safe_float(layout_params.get("pcs_tap_node_r"), 2.6)
    pcs_ac_x_size = _safe_float(layout_params.get("pcs_ac_x_size"), 6.0)

    _draw_solid_node(dwg, tx_lv_left[0], tx_lv_left[1], lv_node_r, node_fill)
    _draw_solid_node(dwg, tx_lv_right[0], tx_lv_right[1], lv_node_r, node_fill)

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

        _draw_pcs_dc_ac_symbol(
            dwg,
            pcs_left_x + pcs_box_w * 0.08,
            pcs_y + pcs_box_h * 0.18,
            pcs_box_w * 0.84,
            pcs_box_h * 0.74,
        )

        tap = (pcs_center_x, bus_y)
        _draw_solid_node(dwg, tap[0], tap[1], pcs_tap_node_r, node_fill)

        # REVISED AC SWITCH LOGIC
        y_x_mark = bus_y + 35.0  
        y_switch_pivot = y_x_mark + 22.0
        
        if y_switch_pivot > pcs_y - 2:
             y_switch_pivot = pcs_y - 10
             y_x_mark = y_switch_pivot - 22.0

        _draw_line_anchored(
            dwg,
            tap,
            (pcs_center_x, y_x_mark - pcs_ac_x_size/2), 
            class_="thin",
            start_anchor=tap,
            end_anchor=(pcs_center_x, y_x_mark - pcs_ac_x_size/2)
        )

        _draw_breaker_x(dwg, pcs_center_x, y_x_mark, pcs_ac_x_size)

        gap_top_y = y_x_mark + pcs_ac_x_size/2
        blade_dx = -7.0 if pcs_center_x < mv_center_x else 7.0
        dwg.add(dwg.line(
            (pcs_center_x, y_switch_pivot),
            (pcs_center_x + blade_dx, gap_top_y + 2.0),
            class_="thin"
        ))

        _draw_line_anchored(
            dwg,
            (pcs_center_x, y_switch_pivot),
            (pcs_center_x, pcs_y),
            class_="thin",
            start_anchor=(pcs_center_x, y_switch_pivot),
            end_anchor=(pcs_center_x, pcs_y)
        )

    # =============================================================================
    # 下方：Battery Storage Bank（compact_mode vs full）
    # =============================================================================
    if compact_mode:
        battery_dash_y = battery_y - dash_offset_y
        battery_dash_h = battery_h + dash_offset_y
        dwg.add(dwg.rect(insert=(battery_x, battery_dash_y), size=(battery_w, battery_dash_h), class_="dash"))
        if dark_mode:
            dwg.add(dwg.text("DC Block (BESS)", insert=(battery_x + battery_w - 8, battery_dash_y + 16), class_="label title", text_anchor="end"))
        else:
            dwg.add(dwg.text("Battery Storage Bank", insert=(battery_x + 8, battery_dash_y + 16), class_="label title"))

        dc_node_r = 2.5
        dc_triangle_size = _safe_float(layout_params.get("dc_triangle_size"), 8.0)
        dc_triangle_gap = _safe_float(layout_params.get("dc_triangle_gap"), 4.0)

        forced_symbol_h = _safe_float(layout_params.get("dc_switch_symbol_h"), 0.0)
        
        skid_bottom_y = skid_y + skid_h

        for idx in range(pcs_count):
            line_x = pcs_centers[idx]
            dc_top = pcs_y + pcs_box_h

            per_feeder = per_feeder_counts[idx] if idx < len(per_feeder_counts) else 1
            block_count = max(1, min(per_feeder, max_blocks))

            block_w = pcs_box_w * 0.8
            if block_count > 1:
                stack_h = dc_block_h
            else:
                stack_h = dc_block_h * block_count + dc_block_gap_y * (block_count - 1)
            stack_top_y = dc_box_y + (dc_stack_h - stack_h) / 2

            min_busbar_y = dc_top + 26.0 - dc_triangle_size
            branch_bus_y = max(min_busbar_y, stack_top_y - 30.0)
            branch_bus_y = min(branch_bus_y, stack_top_y - 6.0)
            gap_to_block = max(6.0, stack_top_y - branch_bus_y)
            branch_bus_y = stack_top_y - gap_to_block * 3.0
            branch_bus_y = max(min_busbar_y, branch_bus_y)
            branch_bus_y = min(branch_bus_y, stack_top_y - 6.0)
            if block_count > 1:
                branch_bus_y = min(branch_bus_y, skid_bottom_y - 6.0)


            _draw_line_anchored(dwg, (line_x, dc_top), (line_x, branch_bus_y), class_="thin", start_anchor=(line_x, dc_top), end_anchor=(line_x, branch_bus_y))

            flow_gap = dc_triangle_gap + dc_triangle_size * 0.6
            min_clearance = dc_triangle_size + flow_gap * 0.5 + 2.0
            flow_center_y = branch_bus_y - min_clearance - dc_triangle_size * 2.0
            _draw_triangle_pair(dwg, line_x, flow_center_y, dc_triangle_size, flow_gap)

            # Local DC busbar per PCS (independent)
            block_gap_x = max(14.0, block_w * 0.15) if block_count > 1 else 0.0
            total_w = block_count * block_w + max(0.0, (block_count - 1) * block_gap_x)
            if total_w <= 0:
                total_w = block_w
            bus_half = min(slot_w * 0.35, total_w / 2 + 8.0)
            dwg.add(dwg.line((line_x - bus_half, branch_bus_y), (line_x + bus_half, branch_bus_y), class_="thin"))
            _draw_node(dwg, line_x, branch_bus_y, dc_node_r, node_fill)

            if block_count > 1:
                start_x = line_x - total_w / 2 + block_w / 2
                block_centers = [start_x + i * (block_w + block_gap_x) for i in range(block_count)]
            else:
                block_centers = [line_x]

            for center_x in block_centers:
                block_y = stack_top_y

                switch_top_y = max(battery_dash_y + 6.0, block_y - 60.0)
                switch_gap = max(0.0, block_y - switch_top_y)
                block_switch_h = min(60.0, max(28.0, switch_gap * 0.9))
                block_switch_h = min(block_switch_h, switch_gap)
                switch_top_y = max(battery_dash_y + 6.0, switch_top_y - block_switch_h)
                _draw_line_anchored(dwg, (center_x, branch_bus_y), (center_x, switch_top_y), class_="thin", start_anchor=(center_x, branch_bus_y), end_anchor=(center_x, switch_top_y))
                _draw_dc_switch(dwg, center_x, switch_top_y, block_switch_h, lead_end_y=block_y)

                dwg.add(dwg.rect(insert=(center_x - block_w * 0.5, block_y), size=(block_w, dc_block_h), class_="outline"))

                inner_pad = max(10.0, dc_block_h * 0.12)
                usable_h = max(1.0, dc_block_h - inner_pad * 2)
                _draw_battery_column(dwg, center_x, block_y + inner_pad, usable_h, 6)
    else:
        busbar_class = "busbar" if dark_mode else "thick"

        dc_bus_a_y = pcs_y + pcs_box_h + 28
        dc_bus_b_y = dc_bus_a_y + 22

        dc_node_r = 2.5
        
        # Build map of block_index -> pcs_index for connection routing
        block_to_pcs = {}
        current_block = 0
        for p_i, count in enumerate(spec.dc_blocks_per_feeder):
            if p_i >= pcs_count: break
            for _ in range(count):
                block_to_pcs[current_block] = p_i
                current_block += 1

        # Draw Per-PCS Independent Busbars
        local_bus_w = min(120.0, slot_w * 0.8)

        for idx in range(pcs_count):
            cx = pcs_centers[idx]
            bx1 = cx - local_bus_w / 2
            bx2 = cx + local_bus_w / 2

            # Busbar A & B (Local)
            dwg.add(dwg.line((bx1, dc_bus_a_y), (bx2, dc_bus_a_y), class_=busbar_class))
            dwg.add(dwg.text(f"DC BUSBAR A (Ckt A)", insert=(bx1, dc_bus_a_y - 8), class_="small"))
            dwg.add(dwg.line((bx1, dc_bus_b_y), (bx2, dc_bus_b_y), class_=busbar_class))
            dwg.add(dwg.text(f"DC BUSBAR B (Ckt B)", insert=(bx1, dc_bus_b_y - 8), class_="small"))

            # Connect PCS to both Busbars (Internal DC link)
            _draw_line_anchored(dwg, (cx, pcs_y + pcs_box_h), (cx, dc_bus_b_y), class_="thin")
            _draw_node(dwg, cx, dc_bus_a_y, dc_node_r, node_fill)
            _draw_node(dwg, cx, dc_bus_b_y, dc_node_r, node_fill)

        battery_dash_y = battery_y - dash_offset_y
        battery_dash_h = battery_h + dash_offset_y
        dwg.add(dwg.rect(insert=(battery_x, battery_dash_y), size=(battery_w, battery_dash_h), class_="dash"))
        if dark_mode:
            dwg.add(dwg.text("DC Block (BESS)", insert=(battery_x + battery_w - 8, battery_dash_y + 16), class_="label title", text_anchor="end"))
        else:
            dwg.add(dwg.text("Battery Storage Bank", insert=(battery_x + 8, battery_dash_y + 16), class_="label title"))

        dc_circuit_a_y = battery_y + battery_title_h + 18
        dc_circuit_b_y = dc_circuit_a_y + 18

        show_individual_blocks = 0 < dc_blocks_total <= 6
        blocks_to_draw = dc_blocks_total if show_individual_blocks else 1
        block_cols = min(3, blocks_to_draw) if show_individual_blocks else 1
        block_rows = int(math.ceil(blocks_to_draw / block_cols)) if show_individual_blocks else 1
        block_gap_x = 20.0
        block_gap_y = 16.0
        block_area_w = max(220.0, battery_w - 80.0)
        dc_box_w = min(160.0, max(110.0, (block_area_w - (block_cols - 1) * block_gap_x) / block_cols))
        block_grid_w = block_cols * dc_box_w + max(0, block_cols - 1) * block_gap_x
        block_grid_h = block_rows * dc_box_h + max(0, block_rows - 1) * block_gap_y
        dc_box_x_start = battery_x + (battery_w - block_grid_w) / 2
        dc_box_y = dc_circuit_b_y + 24

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

                # Connect Block to assigned PCS (Parallel Logic)
                if block_index in block_to_pcs:
                    p_idx = block_to_pcs[block_index]
                    pcs_cx = pcs_centers[p_idx]

                    # Calculate offset to ensure parallel visual (separate lines hitting busbar)
                    siblings = [b for b, p in block_to_pcs.items() if p == p_idx]
                    try:
                        sib_idx = siblings.index(block_index)
                        sib_count = len(siblings)
                    except ValueError:
                        sib_idx = 0
                        sib_count = 1
                    
                    safe_w = local_bus_w * 0.8
                    if sib_count > 1:
                        step = safe_w / (sib_count - 1)
                        offset = -safe_w/2 + step * sib_idx
                    else:
                        offset = 0
                    target_x = pcs_cx + offset

                    # Route Circuit A
                    dwg.add(dwg.line((line_x_a, cell_y), (line_x_a, dc_circuit_a_y), class_="thin"))
                    dwg.add(dwg.line((line_x_a, dc_circuit_a_y), (target_x, dc_circuit_a_y), class_="thin"))
                    dwg.add(dwg.line((target_x, dc_circuit_a_y), (target_x, dc_bus_a_y), class_="thin"))
                    _draw_node(dwg, target_x, dc_bus_a_y, 2.0, node_fill)

                    # Route Circuit B
                    dwg.add(dwg.line((line_x_b, cell_y), (line_x_b, dc_circuit_b_y), class_="thin"))
                    dwg.add(dwg.line((line_x_b, dc_circuit_b_y), (target_x, dc_circuit_b_y), class_="thin"))
                    dwg.add(dwg.line((target_x, dc_circuit_b_y), (target_x, dc_bus_b_y), class_="thin"))
                    _draw_node(dwg, target_x, dc_bus_b_y, 2.0, node_fill)

                block_index += 1
            if show_individual_blocks and block_index >= dc_blocks_total:
                break

    if draw_summary:
        dwg.add(dwg.rect(insert=(note_x, note_y), size=(note_w, note_h), class_="outline"))
        dwg.add(dwg.text("Allocation Summary (AC Block group)", insert=(note_x + 8, note_y + 18), class_="label title"))
        for idx, line in enumerate(wrapped_lines):
            dwg.add(dwg.text(line, insert=(note_x + 8, note_y + 36 + idx * 18), class_="label"))

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


# =============================================================================
# Battery column（保持你原图风格的“电芯列”）
# =============================================================================


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
