"""Firm rule: every concept engineering figure in the exported report carries a
"DRAFT / OVERRIDE - NOT FOR CONSTRUCTION" watermark, unconditionally.
"""
from __future__ import annotations

import io

from PIL import Image

import pytest

from calb_sizing_tool.reporting.report_v2 import (
    NOT_FOR_CONSTRUCTION_STAMP,
    WatermarkError,
    _add_concept_figure,
    _stamp_not_for_construction,
    _watermark_failure_placeholder,
)


def _image_pixels(img):
    """Pillow >= 12 renames getdata() to get_flattened_data(); support both."""
    try:
        return img.get_flattened_data()
    except AttributeError:
        return img.getdata()


def _red_pixel_count(png: bytes) -> int:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    return sum(
        1 for r, g, b in _image_pixels(img)
        if r > g + 20 and r > b + 20 and r < 250
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
    assert _red_pixel_count(stamped) > 200, "expected a visible red watermark"


def test_none_input_passes_through():
    # A missing figure is the caller's concern (it emits a "not generated"
    # message); there is nothing to stamp.
    assert _stamp_not_for_construction(None) is None


def test_stamp_fails_closed_on_bad_input():
    # FAIL-CLOSED: a bad/unstampable image must NEVER be returned unmarked.
    # It is replaced by a visibly-marked red placeholder — not the original.
    out = _stamp_not_for_construction(b"not-a-png")
    assert out != b"not-a-png"
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
    assert _red_pixel_count(out) > 200, "placeholder must carry the red mark"


def test_stamp_stays_visible_without_system_truetype_fonts(monkeypatch):
    """The mark must stay LARGE when no system font file resolves.

    ``ImageFont.load_default()`` without a size is a ~11 px bitmap font, which
    silently shrank the mandatory stamp to near-invisible on hosts with no DejaVu
    fonts. ``_load_stamp_font`` must ask Pillow's embedded fallback for the size
    it needs, so the mark stays comparable to the system-font rendering.
    """
    from PIL import ImageFont

    real_truetype = ImageFont.truetype

    def _no_font_files(font=None, size=10, *args, **kwargs):
        if isinstance(font, str):          # system font FILES unavailable...
            raise OSError("cannot open resource")
        return real_truetype(font, size, *args, **kwargs)  # ...embedded still ok

    monkeypatch.setattr(ImageFont, "truetype", _no_font_files)
    stamped = _stamp_not_for_construction(_white_png())
    assert _red_pixel_count(stamped) > 2000, "stamp must stay visible without system fonts"


def test_placeholder_does_not_echo_source_and_is_marked():
    placeholder = _watermark_failure_placeholder(_white_png(400, 300))
    assert placeholder is not None
    assert placeholder[:8] == b"\x89PNG\r\n\x1a\n"
    assert _red_pixel_count(placeholder) > 200


def test_stamp_raises_when_pillow_unavailable(monkeypatch):
    # If neither a stamp nor a placeholder can be produced, the report must
    # abort rather than embed an unmarked figure.
    import builtins

    real_import = builtins.__import__

    def _no_pil(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("PIL unavailable (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_pil)
    with pytest.raises(WatermarkError):
        _stamp_not_for_construction(_white_png())


def test_add_concept_figure_embeds_a_stamped_picture():
    from docx import Document
    from docx.shared import Inches

    doc = Document()
    _add_concept_figure(doc, _white_png(), width=Inches(6.0))
    # One inline image was added.
    assert len(doc.inline_shapes) == 1
