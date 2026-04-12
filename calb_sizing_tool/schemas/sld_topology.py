from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from calb_sizing_tool.schemas.common import CanonicalBaseModel
from calb_sizing_tool.schemas.sld_render_input import SldEquipmentRatings, SldLabels


SldNodeType = Literal["mv_bus", "rmu", "transformer", "lv_busbar", "pcs", "dc_busbar", "dc_block"]
SldEdgeType = Literal[
    "mv_link",
    "rmu_to_transformer",
    "transformer_to_lv_busbar",
    "lv_busbar_to_pcs",
    "pcs_to_dc_busbar",
    "dc_busbar_to_dc_block",
]
SldEquipmentType = Literal["rmu", "transformer", "lv_busbar", "pcs", "dc_busbar", "dc_block"]


class SldLabel(CanonicalBaseModel):
    label_id: str
    semantic_key: str
    text: str
    scope: str


class SldEquipment(CanonicalBaseModel):
    equipment_id: str
    equipment_type: SldEquipmentType
    display_name: str
    feeder_index: int | None = None
    dc_block_index: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SldNode(CanonicalBaseModel):
    node_id: str
    node_type: SldNodeType
    display_name: str
    equipment_id: str | None = None
    feeder_index: int | None = None
    dc_block_index: int | None = None
    labels: list[SldLabel] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SldEdge(CanonicalBaseModel):
    edge_id: str
    edge_type: SldEdgeType
    source_node_id: str
    target_node_id: str
    feeder_index: int | None = None
    labels: list[SldLabel] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SldTopologySummary(CanonicalBaseModel):
    group_index: int
    ac_blocks_total: int
    feeder_count: int
    pcs_count: int
    dc_blocks_total_in_group: int
    dc_blocks_per_feeder: list[int]
    mv_voltage_kv: float
    lv_voltage_v_ll: float
    transformer_rating_mva: float
    transformer_vector_group: str
    transformer_uk_percent: float
    pcs_rating_kw_list: list[float]
    dc_block_energy_mwh: float
    dc_block_voltage_v: float
    project_frequency_hz: float | None = None
    diagram_mode: str
    theme: str
    compact_mode: bool
    draw_summary: bool


class SldTopology(CanonicalBaseModel):
    run_id: str | None = None
    project_name: str
    scenario_id: str
    source_trace: dict[str, str] = Field(default_factory=dict)
    validation_mode: str
    labels: SldLabels
    equipment_ratings: SldEquipmentRatings
    summary: SldTopologySummary
    nodes: list[SldNode] = Field(default_factory=list)
    edges: list[SldEdge] = Field(default_factory=list)
    equipment: list[SldEquipment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> "SldTopology":
        node_ids = {node.node_id for node in self.nodes}
        equipment_ids = {item.equipment_id for item in self.equipment}
        for node in self.nodes:
            if node.equipment_id and node.equipment_id not in equipment_ids:
                raise ValueError(f"node references unknown equipment_id: {node.equipment_id}")
        for edge in self.edges:
            if edge.source_node_id not in node_ids:
                raise ValueError(f"edge source missing from topology: {edge.source_node_id}")
            if edge.target_node_id not in node_ids:
                raise ValueError(f"edge target missing from topology: {edge.target_node_id}")

        pcs_equipment = [item for item in self.equipment if item.equipment_type == "pcs"]
        dc_block_equipment = [item for item in self.equipment if item.equipment_type == "dc_block"]
        if len(pcs_equipment) != self.summary.pcs_count:
            raise ValueError("topology PCS equipment count must match summary.pcs_count")
        if len(dc_block_equipment) != self.summary.dc_blocks_total_in_group:
            raise ValueError("topology DC block equipment count must match summary.dc_blocks_total_in_group")
        if self.summary.feeder_count != self.summary.pcs_count:
            raise ValueError("feeder_count must match pcs_count")
        return self
