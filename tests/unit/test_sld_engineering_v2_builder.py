import pytest

from calb_sizing_tool.schemas.sld_engineering_v2 import SldEngineeringV2Graph
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from tests.unit.sld_topology_fixtures import _build_topology


def test_engineering_v2_builder_outputs_port_level_graph(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)

    node_types = {node.node_type for node in graph.nodes}
    assert graph.model_version == "engineering_v2_topology_v1"
    assert graph.source_topology_hash and len(graph.source_topology_hash) == 64
    assert "rmu_ring_in_bay" in node_types
    assert "rmu_transformer_feeder_bay" in node_types
    assert "rmu_ring_out_bay" in node_types
    assert "lv_feeder" in node_types
    assert "dc_interface" in node_types
    assert "dc_busbar" not in node_types

    transformer = next(node for node in graph.nodes if node.node_type == "transformer")
    transformer_ports = {port.port_id: port for port in transformer.ports}
    assert transformer_ports["hv_port"].voltage_domain == "mv_ac"
    assert transformer_ports["lv_winding_01_port"].voltage_domain == "lv_ac"
    assert transformer_ports["lv_winding_02_port"].voltage_domain == "lv_ac"
    assert len([node for node in graph.nodes if node.node_type == "lv_busbar"]) == 2

    assert len([node for node in graph.nodes if node.node_type == "lv_feeder"]) == graph.summary.feeder_count
    assert len([node for node in graph.nodes if node.node_type == "pcs"]) == graph.summary.pcs_count
    assert len([node for node in graph.nodes if node.node_type == "dc_block"]) == graph.summary.dc_blocks_total_in_group

    pcs = next(node for node in graph.nodes if node.node_type == "pcs")
    assert pcs.attributes["project_frequency_hz"] == 50.0
    assert pcs.attributes["dc_block_voltage_v"] == 1500.0


def test_engineering_v2_edges_are_port_to_port(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)

    ports = {(node.node_id, port.port_id): port for node in graph.nodes for port in node.ports}
    for edge in graph.edges:
        source_port = ports[(edge.source_node_id, edge.source_port_id)]
        target_port = ports[(edge.target_node_id, edge.target_port_id)]
        assert source_port.voltage_domain == target_port.voltage_domain

    edge_types = {edge.edge_type for edge in graph.edges}
    assert "transformer_feeder_bay_to_transformer_hv" in edge_types
    assert "transformer_lv_to_lv_busbar" in edge_types
    assert "lv_busbar_to_lv_feeder" in edge_types
    assert "pcs_to_dc_interface" in edge_types
    assert "dc_interface_to_dc_block" in edge_types


def test_engineering_v2_schema_rejects_unknown_edge_port(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)
    payload = graph.model_dump(mode="python")
    payload["edges"][0]["target_port_id"] = "missing_port"

    with pytest.raises(ValueError, match="edge target port missing"):
        SldEngineeringV2Graph.model_validate(payload)


def test_engineering_v2_schema_rejects_cross_voltage_edge(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)
    payload = graph.model_dump(mode="python")
    payload["edges"][0]["target_node_id"] = next(node.node_id for node in graph.nodes if node.node_type == "pcs")
    payload["edges"][0]["target_port_id"] = "dc_port"

    with pytest.raises(ValueError, match="voltage domains do not match"):
        SldEngineeringV2Graph.model_validate(payload)
