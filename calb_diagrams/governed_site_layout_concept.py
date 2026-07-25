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

"""Concept whole-site LAYOUT for a governed (Phase A / Phase B) site.

Places EVERY governed AC Block on a scaled plan view at its real equipment
footprint (bilateral 40 ft head vs linear tails), grouped by governed family and
labelled with the bound catalogue product + transformer nameplate. Unlike the
composition overview (band + counts), this is an arranged plan: blocks packed
into rows within a nominal site width, with a site-envelope estimate.

It is still CONCEPT ONLY — NOT FOR CONSTRUCTION: the packing uses each product's
own equipment envelope plus a uniform inter-block aisle, not a real site boundary
with roads / fire access / setbacks (that remains the L3 Master Layout, which
needs a project site-constraint set).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence
from xml.sax.saxutils import escape as _xml_escape

from calb_diagrams.ac_block_arrangement_v2 import US_NFPA_OIL, compute_layout
from calb_diagrams.ac_block_bilateral_layout import LAYOUT_VARIANT as BILATERAL_VARIANT
from calb_diagrams.ac_block_bilateral_layout import compute_bilateral_layout

_INK = "#1f4e79"
_GROUND = "#eef1ee"
_BLOCK = "#dbe6f2"
_BLOCK_EDGE = "#5b83ad"
_TAIL = "#e5eede"
_TAIL_EDGE = "#7fa262"
_MUTED = "#5b6367"
_AISLE = "#c6cac5"

# Plan-view scale and packing constants (metres).
_AISLE_M = 6.0            # nominal drivable aisle between adjacent AC blocks
_SITE_WIDTH_M = 120.0     # nominal usable site width the blocks wrap within
_ROW_GAP_M = 10.0         # gap between packed rows


@dataclass(frozen=True)
class _Footprint:
    w_m: float
    d_m: float


def _footprint(configuration_code: str, layout_variant: str, dc_per_block: int) -> _Footprint:
    """Real equipment footprint (w x d, m) of one AC block of this configuration."""
    if layout_variant == BILATERAL_VARIANT:
        lay = compute_bilateral_layout(8)
        return _Footprint(lay.envelope_w_m, lay.envelope_d_m)
    lay = compute_layout(max(1, int(dc_per_block)), US_NFPA_OIL)
    return _Footprint(lay.envelope_w_m, lay.envelope_d_m)


def _rect(parts, x, y, w, h, fill, stroke=None, sw=1.0, rx=2.0):
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    parts.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'fill="{fill}" rx="{rx}"{extra}/>'
    )


def _text(parts, x, y, s, size=12, anchor="start", weight=700, fill=_INK):
    parts.append(
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
        f'font-family="Consolas, monospace" font-weight="{weight}" '
        f'text-anchor="{anchor}">{_xml_escape(s)}</text>'
    )


def render_governed_site_layout_concept_svg(run, *, title: str = "CONCEPT SITE LAYOUT") -> str:
    """Render a scaled concept plan of every governed AC Block.

    ``run`` is a services.governed_ac_block_service.GovernedSiteRun (duck-typed:
    needs ``dc_blocks_total`` / ``ac_blocks_total`` / ``ac_power_mw_total`` and a
    ``groups`` iterable of items with configuration_code / layout_variant /
    ac_block_count / dc_blocks_per_ac_block / pcs_per_ac_block / bound_product_code
    and an ``ac_output`` dict carrying an optional ``transformer_mva``).
    """
    groups: Sequence = tuple(run.groups)

    # ---- pack blocks (metres) into rows within the nominal site width ----
    @dataclass
    class _Placed:
        x_m: float
        y_m: float
        fp: _Footprint
        is_tail: bool
        label: str

    placed: List[_Placed] = []
    cursor_x = 0.0
    cursor_y = 0.0
    row_max_d = 0.0
    site_w_m = 0.0
    for g in groups:
        fp = _footprint(g.configuration_code, g.layout_variant, g.dc_blocks_per_ac_block)
        is_tail = g.layout_variant != BILATERAL_VARIANT
        mva = None
        try:
            mva = (g.ac_output or {}).get("transformer_mva")
        except AttributeError:
            mva = None
        mva_txt = f"{float(mva):g} MVA" if mva else "MVA TBD"
        prod = getattr(g, "bound_product_code", None) or "no product"
        for i in range(int(g.ac_block_count)):
            if cursor_x > 0.0 and cursor_x + fp.w_m > _SITE_WIDTH_M:
                cursor_x = 0.0
                cursor_y += row_max_d + _ROW_GAP_M
                row_max_d = 0.0
            placed.append(
                _Placed(cursor_x, cursor_y, fp, is_tail, f"{g.pcs_per_ac_block}P/{g.dc_blocks_per_ac_block}D · {mva_txt} · {prod}")
            )
            cursor_x += fp.w_m + _AISLE_M
            row_max_d = max(row_max_d, fp.d_m)
            site_w_m = max(site_w_m, cursor_x - _AISLE_M)
    site_d_m = cursor_y + row_max_d

    # ---- scale metres -> pixels ----
    margin_l, margin_r, margin_t, margin_b = 40.0, 40.0, 96.0, 64.0
    plan_px_w = 1180.0
    scale = plan_px_w / max(site_w_m, 1.0)
    plan_px_h = site_d_m * scale
    width = margin_l + plan_px_w + margin_r
    height = margin_t + plan_px_h + margin_b

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Consolas, monospace">'
    )
    _rect(parts, 0, 0, width, height, _GROUND, rx=0)
    _text(parts, margin_l, 40, title, size=16)
    _text(
        parts, margin_l, 62,
        f"{run.dc_blocks_total} DC Blocks  ·  {run.ac_blocks_total} AC Blocks  ·  "
        f"{run.ac_power_mw_total:.2f} MW  ·  site envelope ~ {site_w_m:.0f} × {site_d_m:.0f} m (concept)",
        size=11.5, weight=600, fill=_MUTED,
    )

    # site ground
    _rect(parts, margin_l, margin_t, plan_px_w, plan_px_h, "#f7f9f6", _AISLE, 1.0, rx=0)

    for p in placed:
        bx = margin_l + p.x_m * scale
        by = margin_t + p.y_m * scale
        bw = p.fp.w_m * scale
        bh = p.fp.d_m * scale
        fill, edge = (_TAIL, _TAIL_EDGE) if p.is_tail else (_BLOCK, _BLOCK_EDGE)
        _rect(parts, bx, by, bw, bh, fill, edge, 1.2, rx=2.0)
        # label only when the block is wide enough to carry text legibly
        if bw >= 90.0:
            _text(parts, bx + 5, by + 15, p.label, size=8.5, weight=600, fill=_INK)

    _text(
        parts, margin_l, height - 24,
        "CONCEPT ONLY — NOT FOR CONSTRUCTION · blocks at real product footprint + nominal "
        f"{_AISLE_M:.0f} m aisle; no site boundary / roads / fire access (L3 Master Layout).",
        size=10.5, weight=600, fill=_MUTED,
    )
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["render_governed_site_layout_concept_svg"]
