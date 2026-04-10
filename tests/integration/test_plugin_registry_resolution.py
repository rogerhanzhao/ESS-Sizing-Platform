from __future__ import annotations

from calb_sizing_tool.plugins.registry import get_plugin_registry


def test_plugin_registry_resolution():
    registry = get_plugin_registry()
    sld_plugin = registry.get("sld_engineering_v1")
    layout_plugin = registry.get("layout_engineering_v1")

    assert sld_plugin is not None
    assert layout_plugin is not None
    assert "sld_svg" in sld_plugin.metadata.supported_artifact_kind
    assert "layout_svg" in layout_plugin.metadata.supported_artifact_kind
