from __future__ import annotations

from typing import Any

from pydantic import Field

from calb_sizing_tool.schemas.common import CanonicalBaseModel
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_render_input import SldCanonicalInput, SldInputOverride


class AcSnapshot(CanonicalBaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)


class TopologySnapshot(CanonicalBaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class LayoutRuleSnapshot(CanonicalBaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class SldRenderOptions(CanonicalBaseModel):
    group_index: int | None = None
    theme: str = "dark"
    draw_summary: bool = False
    compact_mode: bool = False
    override_mode: bool = False
    overrides: SldInputOverride | None = None


class SldRenderInput(CanonicalBaseModel):
    run_id: str
    run_bundle: DcRunBundle
    ac_snapshot: AcSnapshot
    topology_snapshot: TopologySnapshot | None = None
    layout_rules: LayoutRuleSnapshot | None = None
    options: SldRenderOptions
    canonical_input: SldCanonicalInput


class DiagramArtifactBundle(CanonicalBaseModel):
    plugin_id: str
    plugin_version: str
    run_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
