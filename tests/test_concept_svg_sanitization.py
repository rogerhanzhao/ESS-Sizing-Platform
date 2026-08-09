"""Concept SLGs must never leak a raw 'MISSING: <label>' marker.

A concept drawing carries a NOT-FOR-CONSTRUCTION status, and unsupplied
engineering values must render as a neutral placeholder — not the internal
MISSING marker — regardless of marker casing/spacing drift in the renderer.
"""
from calb_sizing_tool.services.sld_pipeline_service import _concept_safe_svg


def _svg(body: str) -> bytes:
    return f'<svg xmlns="http://www.w3.org/2000/svg">{body}</svg>'.encode("utf-8")


def test_official_svg_is_untouched():
    raw = _svg("<text>MISSING: Transformer MVA</text>")
    assert _concept_safe_svg(raw, "official") == raw


def test_concept_replaces_missing_marker():
    out = _concept_safe_svg(_svg("<text>MISSING: Transformer MVA</text>"), "concept").decode()
    assert "MISSING" not in out
    assert "Not specified - concept only" in out
    assert "CONCEPT ONLY - NOT FOR CONSTRUCTION" in out


def test_concept_marker_case_and_spacing_variants_are_scrubbed():
    for marker in ("MISSING: X", "missing: X", "Missing : X", "MISSING:X"):
        out = _concept_safe_svg(_svg(f"<text>{marker}</text>"), "concept").decode()
        assert "MISSING" not in out.upper() or "NOT FOR CONSTRUCTION" in out
        # the marker label itself must be gone
        assert "missing:" not in out.lower()


def test_concept_handles_multiple_markers():
    body = "<text>MISSING: A</text><text>MISSING: B</text>"
    out = _concept_safe_svg(_svg(body), "concept").decode()
    assert "missing:" not in out.lower()
    assert out.count("Not specified - concept only") == 2


def test_draft_override_adds_watermark_and_scrubs_missing_marker():
    out = _concept_safe_svg(_svg("<text>MISSING: Transformer MVA</text>"), "draft_override").decode()
    assert "DRAFT / OVERRIDE - NOT FOR CONSTRUCTION" in out
    assert "missing:" not in out.lower()
    assert "Not specified - concept only" in out


def test_malformed_svg_raises():
    import pytest

    with pytest.raises(ValueError):
        _concept_safe_svg(b"<svg>no closing tag", "concept")
