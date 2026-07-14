from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from calb_sizing_tool.schemas.common import CanonicalBaseModel
from calb_sizing_tool.schemas.sld_render_input import SldEquipmentRatings, SldLabels
from calb_sizing_tool.schemas.sld_topology import SldTopologySummary


SldV2NodeType = Literal[
    "mv_ring_in_terminal",
    "mv_ring_out_terminal",
    "rmu_switchgear",
    "rmu_ring_in_bay",
    "rmu_transformer_feeder_bay",
    "rmu_ring_out_bay",
    "transformer",
    "lv_busbar",
    "lv_feeder",
    "pcs",
    "dc_interface",
    "dc_block",
]
SldV2PortRole = Literal["line", "bus", "load", "hv", "lv", "tap", "ac", "dc", "input", "output"]
SldV2PortSide = Literal["top", "bottom", "left", "right", "center"]
SldV2VoltageDomain = Literal["mv_ac", "lv_ac", "dc"]
SldV2EdgeType = Literal[
    "ring_in_terminal_to_rmu_bay",
    "rmu_bay_to_bus",
    "rmu_bus_to_transformer_feeder_bay",
    "transformer_feeder_bay_to_transformer_hv",
    "rmu_bus_to_ring_out_bay",
    "rmu_ring_out_bay_to_terminal",
    "transformer_lv_to_lv_busbar",
    "lv_busbar_to_lv_feeder",
    "lv_feeder_to_pcs",
    "pcs_to_dc_interface",
    "dc_interface_to_dc_block",
]


class SldV2Port(CanonicalBaseModel):
    port_id: str
    display_name: str
    port_role: SldV2PortRole
    side: SldV2PortSide
    voltage_domain: SldV2VoltageDomain
    feeder_index: int | None = None
    dc_block_index: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SldV2Node(CanonicalBaseModel):
    node_id: str
    node_type: SldV2NodeType
    display_name: str
    equipment_id: str | None = None
    feeder_index: int | None = None
    dc_block_index: int | None = None
    ports: list[SldV2Port] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SldV2Edge(CanonicalBaseModel):
    edge_id: str
    edge_type: SldV2EdgeType
    source_node_id: str
    source_port_id: str
    target_node_id: str
    target_port_id: str
    feeder_index: int | None = None
    dc_block_index: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SldEngineeringV2Graph(CanonicalBaseModel):
    model_version: str = "engineering_v2_topology_v1"
    run_id: str | None = None
    project_name: str
    scenario_id: str
    validation_mode: str
    source_topology_hash: str | None = None
    labels: SldLabels
    equipment_ratings: SldEquipmentRatings
    summary: SldTopologySummary
    nodes: list[SldV2Node] = Field(default_factory=list)
    edges: list[SldV2Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_engineering_graph(self) -> "SldEngineeringV2Graph":
        node_ids: set[str] = set()
        port_lookup: dict[tuple[str, str], SldV2Port] = {}
        node_lookup: dict[str, SldV2Node] = {}

        for node in self.nodes:
            if node.node_id in node_ids:
                raise ValueError(f"duplicate engineering_v2 node_id: {node.node_id}")
            node_ids.add(node.node_id)
            node_lookup[node.node_id] = node

            local_port_ids: set[str] = set()
            for port in node.ports:
                if port.port_id in local_port_ids:
                    raise ValueError(f"duplicate port_id on node {node.node_id}: {port.port_id}")
                local_port_ids.add(port.port_id)
                port_lookup[(node.node_id, port.port_id)] = port

        self._validate_required_nodes(node_lookup)
        self._validate_required_ports(node_lookup)
        self._validate_edges(node_lookup, port_lookup)
        self._validate_counts(node_lookup)
        return self

    def _validate_required_nodes(self, node_lookup: dict[str, SldV2Node]) -> None:
        present_types = {node.node_type for node in node_lookup.values()}
        required_types = {
            "mv_ring_in_terminal",
            "mv_ring_out_terminal",
            "rmu_switchgear",
            "rmu_ring_in_bay",
            "rmu_transformer_feeder_bay",
            "rmu_ring_out_bay",
            "transformer",
            "lv_busbar",
            "pcs",
            "dc_interface",
            "dc_block",
        }
        missing = sorted(required_types - present_types)
        if missing:
            raise ValueError("engineering_v2 graph is missing required node types: " + ", ".join(missing))

    def _validate_required_ports(self, node_lookup: dict[str, SldV2Node]) -> None:
        required_ports_by_type: dict[str, set[str]] = {
            "mv_ring_in_terminal": {"line_port"},
            "mv_ring_out_terminal": {"line_port"},
            "rmu_switchgear": {"ring_in_bus_port", "transformer_feeder_bus_port", "ring_out_bus_port"},
            "rmu_ring_in_bay": {"line_port", "bus_port"},
            "rmu_transformer_feeder_bay": {"bus_port", "load_port"},
            "rmu_ring_out_bay": {"bus_port", "line_port"},
            "transformer": {"hv_port"},
            "lv_busbar": {"transformer_port"},
            "lv_feeder": {"busbar_port", "pcs_port"},
            "pcs": {"ac_port", "dc_port"},
            "dc_interface": {"pcs_port", "block_port"},
            "dc_block": {"input_port"},
        }
        for node in node_lookup.values():
            port_ids = {port.port_id for port in node.ports}
            missing = required_ports_by_type[str(node.node_type)] - port_ids
            if missing:
                raise ValueError(
                    f"engineering_v2 node {node.node_id} is missing required ports: "
                    + ", ".join(sorted(missing))
                )

        transformer = next(node for node in node_lookup.values() if node.node_type == "transformer")
        transformer_port_ids = {port.port_id for port in transformer.ports}
        if self.summary.lv_winding_count == 1:
            expected_transformer_ports = {"lv_port"}
        else:
            expected_transformer_ports = {
                f"lv_winding_{winding_index:02d}_port"
                for winding_index in range(1, self.summary.lv_winding_count + 1)
            }
        missing_transformer_ports = expected_transformer_ports - transformer_port_ids
        if missing_transformer_ports:
            raise ValueError(
                "transformer is missing LV winding port(s): " + ", ".join(sorted(missing_transformer_ports))
            )

        lv_busbars = [node for node in node_lookup.values() if node.node_type == "lv_busbar"]
        if len(lv_busbars) != self.summary.lv_winding_count:
            raise ValueError("engineering_v2 LV busbar count must match summary.lv_winding_count")
        feeder_winding_count: dict[int, int] = {}
        for busbar in lv_busbars:
            port_ids = {port.port_id for port in busbar.ports}
            if "transformer_port" not in port_ids:
                raise ValueError(f"lv_busbar is missing transformer port: {busbar.node_id}")
            for port in busbar.ports:
                if port.feeder_index is not None:
                    feeder_winding_count[port.feeder_index] = feeder_winding_count.get(port.feeder_index, 0) + 1
        for feeder_index in range(1, self.summary.feeder_count + 1):
            if feeder_winding_count.get(feeder_index) != 1:
                raise ValueError(
                    f"feeder F{feeder_index} must connect to exactly one independent LV winding"
                )

    def _validate_edges(
        self,
        node_lookup: dict[str, SldV2Node],
        port_lookup: dict[tuple[str, str], SldV2Port],
    ) -> None:
        edge_ids: set[str] = set()
        for edge in self.edges:
            if edge.edge_id in edge_ids:
                raise ValueError(f"duplicate engineering_v2 edge_id: {edge.edge_id}")
            edge_ids.add(edge.edge_id)
            if edge.source_node_id not in node_lookup:
                raise ValueError(f"engineering_v2 edge source node missing: {edge.source_node_id}")
            if edge.target_node_id not in node_lookup:
                raise ValueError(f"engineering_v2 edge target node missing: {edge.target_node_id}")
            source_port = port_lookup.get((edge.source_node_id, edge.source_port_id))
            if source_port is None:
                raise ValueError(f"engineering_v2 edge source port missing: {edge.source_node_id}.{edge.source_port_id}")
            target_port = port_lookup.get((edge.target_node_id, edge.target_port_id))
            if target_port is None:
                raise ValueError(f"engineering_v2 edge target port missing: {edge.target_node_id}.{edge.target_port_id}")
            if source_port.voltage_domain != target_port.voltage_domain:
                raise ValueError(
                    "engineering_v2 edge voltage domains do not match: "
                    f"{edge.source_node_id}.{edge.source_port_id}={source_port.voltage_domain} -> "
                    f"{edge.target_node_id}.{edge.target_port_id}={target_port.voltage_domain}"
                )

    def _validate_counts(self, node_lookup: dict[str, SldV2Node]) -> None:
        nodes_by_type: dict[str, list[SldV2Node]] = {}
        for node in node_lookup.values():
            nodes_by_type.setdefault(str(node.node_type), []).append(node)

        if len(nodes_by_type.get("pcs", [])) != self.summary.pcs_count:
            raise ValueError("engineering_v2 PCS node count must match summary.pcs_count")
        if len(nodes_by_type.get("lv_feeder", [])) != self.summary.feeder_count:
            raise ValueError("engineering_v2 LV feeder node count must match summary.feeder_count")
        if len(nodes_by_type.get("dc_interface", [])) != self.summary.feeder_count:
            raise ValueError("engineering_v2 DC interface node count must match summary.feeder_count")
        if len(nodes_by_type.get("dc_block", [])) != self.summary.dc_blocks_total_in_group:
            raise ValueError("engineering_v2 DC block node count must match summary.dc_blocks_total_in_group")
