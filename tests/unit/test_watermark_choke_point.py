"""No engineering drawing reaches a document without the mandatory stamp.

The NOT-FOR-CONSTRUCTION mark is fail-closed by design: `_add_concept_figure`
stamps, substitutes a visibly-marked placeholder for a figure it cannot open,
and raises `WatermarkError` only when even that placeholder is impossible. That
design only holds while every drawing goes THROUGH it — and a codebase this old,
written by several hands, had already grown a second report generator that
embedded the SLD and the arrangement with a bare `doc.add_picture`.

It was reachable only from tests, so nothing shipped unmarked. But "currently
unreachable" is not a safety property: wiring that generator to a button would
have issued unmarked engineering figures to a customer, and nothing would have
objected.

So the rule is enforced structurally rather than remembered: every `add_picture`
in the reporting package is either inside the choke point, or named here with a
reason it is not a drawing.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

REPORTING = pathlib.Path("calb_sizing_tool/reporting")

#: Calls that embed DATA, not an engineering drawing. A degradation curve or a
#: capacity chart cannot be mistaken for a construction document, so it carries
#: no stamp. Each entry names the function and what it embeds — adding one is a
#: deliberate act, which is the point.
ALLOWED_UNSTAMPED = {
    ("report_v2.py", "export_report_v2_1"): "POI capacity / degradation charts",
    ("export_docx.py", "add_header_logo"): "the brand logo in the page header",
    ("export_docx.py", "_append_dc_report_sections"): "DC lifetime charts",
}

#: The one function allowed to call add_picture with a drawing.
CHOKE_POINT = "_add_concept_figure"


def _enclosing_function(tree: ast.AST, lineno: int) -> str | None:
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None) or max(
                getattr(n, "lineno", node.lineno) for n in ast.walk(node)
            )
            if node.lineno <= lineno <= end:
                # Innermost wins, so a nested helper is named rather than its parent.
                if best is None or node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1] if best else None


def _picture_calls() -> list[tuple[str, str, int]]:
    found = []
    for path in sorted(REPORTING.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_picture"):
                found.append((path.name, _enclosing_function(tree, node.lineno) or "<module>",
                              node.lineno))
    return found


def test_the_reporting_package_still_embeds_pictures():
    """Guard the guard: a rename would make every assertion below vacuous."""
    assert _picture_calls(), "no add_picture found — has the reporting API changed?"


@pytest.mark.parametrize("call", _picture_calls(), ids=lambda c: f"{c[0]}:{c[2]}")
def test_every_picture_is_stamped_or_declared_data(call):
    module, function, lineno = call
    if function == CHOKE_POINT:
        return
    assert (module, function) in ALLOWED_UNSTAMPED, (
        f"{module}:{lineno} in {function}() embeds a picture without the "
        f"NOT-FOR-CONSTRUCTION stamp. Route it through {CHOKE_POINT}, or add it "
        f"to ALLOWED_UNSTAMPED with the reason it is data rather than a drawing."
    )


def test_an_unstampable_figure_is_replaced_not_passed_through():
    """The real contract, which is stronger than raising.

    A figure that cannot be opened is swapped for a visibly-marked placeholder,
    so the report is still produced and that one figure says plainly that it
    could not be marked. What must never happen is the ORIGINAL bytes coming
    back — that would put an unmarked drawing in a customer document.
    """
    from calb_sizing_tool.reporting.report_v2 import _stamp_not_for_construction

    corrupt = b"this is not a PNG"
    result = _stamp_not_for_construction(corrupt)
    assert result != corrupt, "an un-stampable figure must never pass through clean"
    assert result.startswith(b"\x89PNG"), "the replacement must be a real image"


def test_it_raises_when_even_the_placeholder_cannot_be_built(monkeypatch):
    """Pillow unavailable: abort rather than emit an unmarked figure."""
    from calb_sizing_tool.reporting import report_v2

    monkeypatch.setattr(report_v2, "_watermark_failure_placeholder", lambda _b: None)
    with pytest.raises(report_v2.WatermarkError):
        report_v2._stamp_not_for_construction(b"this is not a PNG")


def test_the_legacy_generator_embeds_no_engineering_drawing_at_all():
    """Stronger than the rule this file was written for.

    export_docx used to embed the SLD and the layout inside
    `create_combined_report`, which made it a second place a drawing could
    reach a document — the hole this file exists to close. That generator had
    no caller and was deleted (owner ruling 2026-08-08); what remains embeds
    the brand logo and the DC lifetime charts, neither of which is an
    engineering drawing.

    So the guarantee is no longer "it stamps its drawings" but "it has none".
    If a drawing is ever embedded here again — stamped or not — this fails, and
    whoever adds it has to route through report_v2._add_concept_figure instead.
    """
    source = (REPORTING / "export_docx.py").read_text(encoding="utf-8-sig")
    for name in ("sld_png", "sld_svg", "layout_png", "layout_svg"):
        assert name not in source, (
            f"export_docx handles {name} again; engineering drawings belong to "
            f"report_v2, behind the {CHOKE_POINT} stamp"
        )
    assert "_add_concept_figure" not in source
