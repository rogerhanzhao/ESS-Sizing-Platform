from __future__ import annotations

from typing import Dict, List

from calb_sizing_tool.plugins.base import DiagramPlugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: Dict[str, DiagramPlugin] = {}

    def register(self, plugin: DiagramPlugin) -> None:
        self._plugins[plugin.metadata.plugin_id] = plugin

    def get(self, plugin_id: str) -> DiagramPlugin | None:
        return self._plugins.get(plugin_id)

    def list(self) -> list[DiagramPlugin]:
        return list(self._plugins.values())

    def list_by_artifact(self, artifact_kind: str) -> List[DiagramPlugin]:
        return [
            plugin
            for plugin in self._plugins.values()
            if artifact_kind in plugin.metadata.supported_artifact_kind
        ]


_REGISTRY: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        from calb_sizing_tool.plugins.sld_engineering_plugin import SldEngineeringPlugin
        from calb_sizing_tool.plugins.layout_engineering_plugin import LayoutEngineeringPlugin
        from calb_sizing_tool.plugins.prompt_layout_plugin import PromptLayoutPlugin

        registry = PluginRegistry()
        registry.register(SldEngineeringPlugin())
        registry.register(LayoutEngineeringPlugin())
        registry.register(PromptLayoutPlugin())
        _REGISTRY = registry
    return _REGISTRY
