"""One renderer remains, and the retired names must still be safe to receive.

Owner, 2026-08-06: "legacy_server 不留; topology_v1 不用了". Both renderers were
deleted, so there is nothing left to dispatch to.

The interesting half is what happens to the NAMES. Every SLD artifact ever
generated recorded its renderer_mode in metadata, so a restored run, an external
submission or a hand-edited setting can still hand us "legacy_server" long after
the code is gone. Rejecting it would turn old, valid data into a crash; the mode
resolves to the current renderer instead. An outright unknown string is still an
error, because that is a caller bug rather than a historical record — and losing
that distinction would let a typo silently render something unintended.
"""
import pytest

from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.services.sld_renderer_mode_service import (
    AVAILABLE_SLD_RENDERER_MODES,
    DEFAULT_SLD_RENDERER_MODE,
    PUBLIC_SLD_RENDERER_MODES,
    RETIRED_SLD_RENDERER_MODES,
    is_sld_renderer_mode_available,
    is_sld_renderer_mode_public,
    normalize_sld_renderer_mode,
    sld_renderer_mode_label,
)

RETIRED = ("legacy_server", "topology_v1")


def test_engineering_v2_is_the_only_renderer():
    assert AVAILABLE_SLD_RENDERER_MODES == ("engineering_v2",)
    assert PUBLIC_SLD_RENDERER_MODES == ("engineering_v2",)
    assert DEFAULT_SLD_RENDERER_MODE == "engineering_v2"
    assert SldRenderOptions().renderer_mode == "engineering_v2"
    assert is_sld_renderer_mode_available("engineering_v2") is True
    assert is_sld_renderer_mode_public("engineering_v2") is True
    assert "Engineering V2 Professional SLD" in sld_renderer_mode_label("engineering_v2")


@pytest.mark.parametrize("mode", RETIRED)
def test_a_retired_mode_resolves_instead_of_raising(mode):
    """Old metadata must not become a crash."""
    assert mode in RETIRED_SLD_RENDERER_MODES
    assert normalize_sld_renderer_mode(mode) == DEFAULT_SLD_RENDERER_MODE
    assert is_sld_renderer_mode_available(mode) is True, (
        "it resolves to the available renderer, so it reports as available — the "
        "caller gets a drawing rather than an error"
    )


@pytest.mark.parametrize("mode", RETIRED)
def test_a_retired_mode_is_not_offered_to_anyone(mode):
    assert mode not in AVAILABLE_SLD_RENDERER_MODES
    assert mode not in PUBLIC_SLD_RENDERER_MODES
    assert mode not in sld_renderer_mode_label.__globals__["_MODE_LABELS"]


def test_an_unknown_mode_still_fails_fast():
    """A typo is a caller bug and must not silently render something else."""
    with pytest.raises(ValueError, match="Unsupported SLD renderer mode"):
        normalize_sld_renderer_mode("unknown")


def test_the_retired_renderers_are_gone():
    """The point of the retirement — the modules must not come back quietly."""
    import importlib

    for module in ("calb_diagrams.sld_server_baseline_renderer",
                   "calb_diagrams.sld_pro_renderer"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


def test_nothing_dispatches_on_a_retired_mode():
    """A leftover branch would be dead code pointing at a deleted renderer."""
    import inspect

    from calb_sizing_tool.plugins import sld_engineering_plugin

    source = inspect.getsource(sld_engineering_plugin)
    for mode in RETIRED:
        assert f'renderer_mode == "{mode}"' not in source, (
            f"the plugin still branches on {mode}, whose renderer no longer exists"
        )
