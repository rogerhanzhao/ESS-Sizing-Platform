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
"""Report-level regression for the NOT-FOR-CONSTRUCTION watermark rule.

The unit test in ``tests/unit/test_report_not_for_construction.py`` proves the
watermark *helper* stamps and fails closed. This test renders a whole DOCX and
proves the enforcement holds in the actual report: every §7/§8/§9 concept figure
that reaches the document is visibly watermarked, no un-watermarked source image
leaks through, and every §7/§8/§9 caption states NOT FOR CONSTRUCTION.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import _stamp_not_for_construction, export_report_v2_1

# Captions for the three concept engineering sections carry one of these markers;
# the Stage-3 / POI data charts (Figures 1-2) deliberately do NOT — they are data
# plots, not engineering drawings, so they are excluded from the drawing rule.
_CONCEPT_CAPTION_MARKERS = (
    "Single Line Diagram",
    "AC Block Arrangement",
    "Site Arrangement",
    "Site Layout",
)
# The shared 900x500 white-source fixture carries 527 translucent-red stamp
# pixels with the current Pillow/font fallback.  Non-concept report media tops
# out at 275 incidental red pixels, so 400 keeps the test above that noise
# floor while accepting the mandatory visible stamp across supported Pillow
# versions.
_WATERMARK_PIXEL_MIN = 400


def _white_png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def _red_pixels(png: bytes) -> int:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    return sum(
        1 for r, g, b in img.getdata()
        if r > g + 20 and r > b + 20 and r < 250
    )


def _media_images(report_bytes: bytes) -> list[bytes]:
    z = zipfile.ZipFile(io.BytesIO(report_bytes))
    return [z.read(n) for n in z.namelist() if n.startswith("word/media/")]


def _concept_captions(report_bytes: bytes) -> list[str]:
    from docx import Document

    doc = Document(io.BytesIO(report_bytes))
    return [
        p.text
        for p in doc.paragraphs
        if p.text.startswith("Figure")
        and any(m in p.text for m in _CONCEPT_CAPTION_MARKERS)
    ]


def _assert_report_is_fully_watermarked(report_bytes: bytes, *, raw_sources: list[bytes],
                                        min_concept_figures: int) -> None:
    media = _media_images(report_bytes)

    # 1. No un-watermarked source image leaks into the document.
    media_set = set(media)
    for src in raw_sources:
        assert src not in media_set, "an un-watermarked source image leaked into the report"

    # 2. Enough concept figures are present, and each one carries the red mark.
    watermarked = [png for png in media if _red_pixels(png) >= _WATERMARK_PIXEL_MIN]
    assert len(watermarked) >= min_concept_figures, (
        f"expected >= {min_concept_figures} watermarked concept figures, "
        f"got {len(watermarked)} (red-pixel counts: "
        f"{sorted(_red_pixels(p) for p in media)})"
    )

    # 3. Every §7/§8/§9 caption states NOT FOR CONSTRUCTION.
    captions = _concept_captions(report_bytes)
    assert captions, "expected at least one §7/§8/§9 concept-figure caption"
    for cap in captions:
        assert "NOT FOR CONSTRUCTION" in cap, f"caption missing NOT FOR CONSTRUCTION: {cap!r}"


def test_full_report_watermarks_every_concept_figure_nongoverned():
    """Non-governed path: §7 SLD (PNG), §8 rule-based arrangement, §9 site array."""
    from tools.regress_export import run_ac_sizing, run_dc_sizing

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "v1_case01_container_input.json").read_text("utf-8")
    )
    dc = run_dc_sizing(fixture)
    ac = run_ac_sizing(fixture, dc["stage1"], dc["stage2"])

    sld_src = _white_png(900, 500)
    layout_src = _white_png(901, 501)
    ctx = build_report_context(
        session_state={"artifacts": {"sld_png_bytes": sld_src, "layout_png_bytes": layout_src}},
        stage_outputs={
            "stage13_output": dc["stage1"],
            "stage2": dc["stage2"],
            "stage3_df": dc["stage3_df"],
            "stage3_meta": dc["stage3_meta"],
            "ac_output": ac,
        },
        project_inputs={"poi_energy_guarantee_mwh": fixture["poi_energy_req_mwh"]},
        scenario_ids=fixture["scenario_id"],
    )
    report_bytes = export_report_v2_1(ctx)

    # §7/§8/§9 each produce a concept figure on this path.
    _assert_report_is_fully_watermarked(
        report_bytes, raw_sources=[sld_src, layout_src], min_concept_figures=3
    )
    # §7 is byte-exact: the embedded SLD is precisely the stamped source, never raw.
    assert _stamp_not_for_construction(sld_src) in set(_media_images(report_bytes))


def _governed_ctx(container_count: int, *, poi_power_mw: float, poi_energy_mwh: float,
                  sld_src: bytes):
    from calb_sizing_tool.services.governed_ac_block_service import (
        build_governed_primary_ac_output,
    )

    ac = build_governed_primary_ac_output(container_count)
    return build_report_context(
        session_state={"artifacts": {"sld_png_bytes": sld_src}},
        stage_outputs={
            "stage13_output": {
                "project_name": "Gov",
                "poi_power_req_mw": poi_power_mw,
                "poi_energy_req_mwh": poi_energy_mwh,
                "project_life_years": 20,
                "poi_guarantee_year": 0,
                "cycles_per_year": 365,
            },
            "ac_output": ac,
            "stage2": {"container_count": container_count},
        },
        project_inputs={},
    )


def test_full_report_watermarks_every_concept_figure_governed_bilateral():
    """Governed pure-bilateral path: §7 SLD + §8 bilateral 4+4 AC block + §9 site."""
    from calb_sizing_tool.reporting.report_v2 import BILATERAL_LAYOUT_VARIANT

    sld_src = _white_png(900, 500)
    ctx = _governed_ctx(16, poi_power_mw=20.0, poi_energy_mwh=80.0, sld_src=sld_src)  # 2 x 8
    assert ctx.layout_variant == BILATERAL_LAYOUT_VARIANT, "expected the bilateral 4+4 branch"
    report_bytes = export_report_v2_1(ctx)

    # §7 SLD + §8 bilateral arrangement + §9 governed site — three concept figures.
    _assert_report_is_fully_watermarked(
        report_bytes, raw_sources=[sld_src], min_concept_figures=3
    )
    assert _stamp_not_for_construction(sld_src) in set(_media_images(report_bytes))


def test_full_report_watermarks_every_concept_figure_governed_mixed():
    """Governed mixed path (11x8 + 1x4): §7 SLD + §9 governed mixed site layout."""
    sld_src = _white_png(900, 500)
    ctx = _governed_ctx(92, poi_power_mw=115.0, poi_energy_mwh=400.0, sld_src=sld_src)
    report_bytes = export_report_v2_1(ctx)

    # §7 SLD + §9 governed mixed site layout are both concept figures here. (§8's
    # bilateral field is fixed-8, so the mixed 7-DC/AC average legitimately falls
    # back — the report's own guard covers it; still no unmarked figure appears.)
    _assert_report_is_fully_watermarked(
        report_bytes, raw_sources=[sld_src], min_concept_figures=2
    )
    assert _stamp_not_for_construction(sld_src) in set(_media_images(report_bytes))
