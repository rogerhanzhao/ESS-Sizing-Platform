from __future__ import annotations

from typing import Any

from pydantic import Field

from calb_sizing_tool.schemas.common import CanonicalBaseModel
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


class AcSnapshot(CanonicalBaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)


class TopologySnapshot(CanonicalBaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class LayoutRuleSnapshot(CanonicalBaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class SldRenderOptions(CanonicalBaseModel):
    group_index: int = 1
    theme: str = "dark"
    draw_summary: bool = False
    mv_kv: float | None = None
    lv_v: float | None = None
    transformer_mva: float | None = None
    pcs_rating_each_kw: float | None = None
    dc_block_energy_mwh: float | None = None
    svg_width: int | None = None
    svg_height: int | None = None
    pcs_gap: int | None = None
    busbar_gap: int | None = None
    font_scale: float | None = None
    dc_blocks_per_feeder: list[int] | None = None


class SldRenderInput(CanonicalBaseModel):
    run_id: str
    run_bundle: DcRunBundle
    ac_snapshot: AcSnapshot
    topology_snapshot: TopologySnapshot | None = None
    layout_rules: LayoutRuleSnapshot | None = None
    options: SldRenderOptions


class DiagramArtifactBundle(CanonicalBaseModel):
    plugin_id: str
    plugin_version: str
    run_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
