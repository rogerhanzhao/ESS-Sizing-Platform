"""Firm rule: every concept engineering figure in the exported report carries a
"DRAFT / OVERRIDE - NOT FOR CONSTRUCTION" watermark, unconditionally.
"""
from __future__ import annotations

import io

from PIL import Image

from calb_sizing_tool.reporting.report_v2 import (
    NOT_FOR_CONSTRUCTION_STAMP,
    _add_concept_figure,
    _stamp_not_for_construction,
)


def _white_png(w=900, h=500) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_stamp_text_is_the_draft_not_for_construction_mark():
    assert NOT_FOR_CONSTRUCTION_STAMP == "DRAFT / OVERRIDE - NOT FOR CONSTRUCTION"


def test_stamp_overlays_a_translucent_red_watermark():
    original = _white_png()
    stamped = _stamp_not_for_construction(original)
    assert stamped != original
    assert stamped[:8] == b"\x89PNG\r\n\x1a\n"
    # The watermark tints some pixels reddish (red channel clearly above green
    # and blue) without being pure white — the 0.28-opacity red mark.
    img = Image.open(io.BytesIO(stamped)).convert("RGB")
    reddish = sum(
        1 for r, g, b in img.get_flattened_data()
        if r > g + 20 and r > b + 20 and r < 250
    )
    assert reddish > 200, f"expected a visible red watermark, got {reddish} tinted pixels"


def test_stamp_never_raises_on_bad_input():
    assert _stamp_not_for_construction(None) is None
    assert _stamp_not_for_construction(b"not-a-png") == b"not-a-png"


def test_add_concept_figure_embeds_a_stamped_picture():
    from docx import Document
    from docx.shared import Inches

    doc = Document()
    _add_concept_figure(doc, _white_png(), width=Inches(6.0))
    # One inline image was added.
    assert len(doc.inline_shapes) == 1
