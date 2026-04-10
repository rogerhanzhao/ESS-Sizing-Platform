from __future__ import annotations

from typing import Any

from pydantic import Field

from calb_sizing_tool.schemas.common import CanonicalBaseModel
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, LayoutRuleSnapshot, TopologySnapshot
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


class LayoutRenderOptions(CanonicalBaseModel):
    block_index: int = 1
    arrangement: str = "Auto"
    show_skid: bool = True
    dc_to_dc_clearance_m: float = 0.3
    dc_to_ac_clearance_m: float = 2.0
    perimeter_clearance_m: float = 0.0
    dc_block_mirrored: bool = False
    scale: float = 0.04
    left_margin: int = 40
    top_margin: int = 40
    theme: str = "light"
    block_title: str | None = None
    bess_range_text: str | None = None
    skid_text: str | None = None
    skid_subtext: str | None = None


class LayoutRenderInput(CanonicalBaseModel):
    run_id: str
    run_bundle: DcRunBundle
    ac_snapshot: AcSnapshot
    topology_snapshot: TopologySnapshot | None = None
    layout_rules: LayoutRuleSnapshot | None = None
    options: LayoutRenderOptions


class LayoutArtifactBundle(CanonicalBaseModel):
    plugin_id: str
    plugin_version: str
    run_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
