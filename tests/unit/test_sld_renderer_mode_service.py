import pytest

from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.services.sld_renderer_mode_service import (
    AVAILABLE_SLD_RENDERER_MODES,
    PRODUCTION_BASELINE_SLD_RENDERER_MODE,
    RESERVED_SLD_RENDERER_MODES,
    is_sld_renderer_mode_available,
    normalize_sld_renderer_mode,
    sld_renderer_mode_label,
)


def test_sld_render_options_default_is_engineering_v2_professional_candidate():
    assert SldRenderOptions().renderer_mode == "engineering_v2"
    assert normalize_sld_renderer_mode(None) == "engineering_v2"


def test_production_baseline_mode_is_available():
    assert PRODUCTION_BASELINE_SLD_RENDERER_MODE == "legacy_server"
    assert "legacy_server" in AVAILABLE_SLD_RENDERER_MODES
    assert is_sld_renderer_mode_available("legacy_server") is True
    assert sld_renderer_mode_label("legacy_server").startswith("Legacy Compatibility")


def test_engineering_v2_is_available_for_manual_preview():
    assert normalize_sld_renderer_mode("engineering_v2") == "engineering_v2"
    assert is_sld_renderer_mode_available("engineering_v2") is True
    assert "engineering_v2" in AVAILABLE_SLD_RENDERER_MODES
    assert "Engineering V2 Professional SLD" in sld_renderer_mode_label("engineering_v2")


def test_topology_v1_is_retired_from_public_mode_list_but_reserved_for_compatibility():
    assert "topology_v1" not in AVAILABLE_SLD_RENDERER_MODES
    assert "topology_v1" in RESERVED_SLD_RENDERER_MODES
    assert normalize_sld_renderer_mode("topology_v1") == "topology_v1"
    assert is_sld_renderer_mode_available("topology_v1") is False


def test_unknown_renderer_mode_fails_fast():
    with pytest.raises(ValueError, match="Unsupported SLD renderer mode"):
        normalize_sld_renderer_mode("unknown")
