"""The DC page's private helpers must keep agreeing with the frozen service.

`ui/dc_view.py` carries its own copies of six helpers that
`services/stage1_service.py` also defines — `to_float`, `to_int`, `to_frac`,
`clamp01`, `safe_div`, `calc_sc_loss_pct`. The service is FROZEN CANON, hash
pinned by tests/test_frozen_canon_guard.py; the page's copies are not pinned by
anything.

Measured 2026-08-06: all six agree today, exercised across their edge cases —
so this is a drift risk, not a live defect. But the freeze protects one copy
while the page a user actually looks at reads from the other, and nothing keeps
them in step. `calc_sc_loss_pct` in particular is a sizing number: if the two
diverged, the page would show one storage-loss percentage while the canon
computed another, and the frozen file would still pass its hash check.

The honest fix is for the page to call the service (as `dc_view.run_stage1`
already does — it is a two-line delegation, so the canon really is what users
get). Until someone does that, this test is what notices.
"""
from __future__ import annotations

import math

import pytest

from calb_sizing_tool.services import stage1_service as canon
from calb_sizing_tool.ui import dc_view as page

DUPLICATED = ("to_float", "to_int", "to_frac", "clamp01", "safe_div", "calc_sc_loss_pct")

#: Values chosen to hit the coercion helpers' failure modes, not just their
#: happy path — a silent divergence lives in how each one handles junk.
AWKWARD = [0, 1, -1, 0.5, 2.5, 100, "3.14", "abc", "", None, True, [], "1e3", " 7 "]


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-12) or (math.isnan(a) and math.isnan(b))
    return a == b


def _call(func, *args):
    try:
        return func(*args)
    except Exception as exc:               # a raised type is part of the behaviour
        return f"{type(exc).__name__}"


@pytest.mark.parametrize("name", DUPLICATED)
def test_the_page_still_defines_its_own_copy(name):
    """If the duplication is ever removed, delete this file rather than weaken it."""
    assert hasattr(page, name) and hasattr(canon, name), (
        f"{name} no longer exists in both places — if the page now calls the "
        f"service, this whole test file has served its purpose and can go"
    )


@pytest.mark.parametrize("name", ("to_float", "to_int", "to_frac"))
def test_the_coercion_helpers_agree(name):
    page_fn, canon_fn = getattr(page, name), getattr(canon, name)
    default = {"to_float": 9.9, "to_int": 7, "to_frac": 0.5}[name]
    for value in AWKWARD:
        assert _same(_call(page_fn, value), _call(canon_fn, value)), value
        assert _same(_call(page_fn, value, default), _call(canon_fn, value, default)), value


def test_clamp01_agrees():
    for value in (0, 1, -0.2, 1.4, 0.5, "0.3", None, "abc"):
        assert _same(_call(page.clamp01, value), _call(canon.clamp01, value)), value


def test_safe_div_agrees():
    for numerator in (1, 0, -3, 2.5):
        for denominator in (1, 0, 0.0, -2, None):
            assert _same(_call(page.safe_div, numerator, denominator),
                         _call(canon.safe_div, numerator, denominator)), (numerator, denominator)


def test_the_storage_loss_curve_agrees():
    """The one that is a SIZING number rather than a coercion detail.

    Covers the whole mapping, the >12-month extrapolation and the boundary
    between them, because that is where two hand-copied curves drift apart.
    """
    for months in list(range(-3, 40)) + [0.5, 12.9, 13.0, 1000, "6", "abc", None, True]:
        assert _same(_call(page.calc_sc_loss_pct, months),
                     _call(canon.calc_sc_loss_pct, months)), months


def test_the_page_delegates_the_stage_1_calculation_itself():
    """The helpers are copied; the CALCULATION must not be.

    dc_view.run_stage1 is a two-line delegation to the frozen service. If it
    ever grew its own arithmetic, the freeze would be decorative: the pinned
    file would still hash correctly while users saw different numbers.
    """
    import inspect

    source = inspect.getsource(page.run_stage1)
    assert "service_run_stage1" in source, (
        "the DC page must not compute Stage 1 itself — that is frozen canon"
    )
    assert len(source.strip().splitlines()) <= 4, (
        "run_stage1 on the page has grown a body; it must stay a delegation"
    )
