from dataclasses import asdict

from calb_diagrams.sld_engineering_v2_validation import (
    assert_sld_engineering_v2_layout_acceptance,
    validate_sld_engineering_v2_layout,
)
from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
from tests.unit.test_sld_layout_engine import _build_topology
from tests.unit.test_sld_topology_builder import _build_run_bundle


def _build_v2_plan(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)
    return graph, build_sld_engineering_v2_layout_plan(graph)


def _build_v2_plan_with_dc_allocation(sample_excel_path, allocation):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["transformer_vector_group"] = "Dyn11yn11"
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = list(allocation)
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=AcSnapshot(
            inputs={"grid_kv": 33.0, "lv_voltage_v": 690.0},
            output={
                "num_blocks": 1,
                "pcs_per_block": 4,
                "pcs_kw": 1250.0,
                "block_size_mw": 5.0,
                "transformer_mva": 6.0,
                "dc_allocation_plan": [
                    {"ac_block_index": 1, "dc_blocks_total": sum(allocation), "feeder_allocations": list(allocation)}
                ],
            },
            results={},
        ),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )
    topology = build_sld_topology(canonical)
    graph = build_sld_engineering_v2_graph(topology)
    return graph, build_sld_engineering_v2_layout_plan(graph)


def test_engineering_v2_layout_is_stable(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)

    plan_a = build_sld_engineering_v2_layout_plan(graph)
    plan_b = build_sld_engineering_v2_layout_plan(graph)

    assert asdict(plan_a) == asdict(plan_b)
    assert plan_a.width == 2000
    assert plan_a.height == 1160


def test_engineering_v2_layout_carries_equipment_rows_for_renderer(sample_excel_path):
    _, plan = _build_v2_plan(sample_excel_path)

    rows = {row.item: row.spec for row in plan.equipment_rows}
    assert rows["MV System"] == "33.0 kV"
    assert "33 kV" in rows["MV Switchgear / RMU"]
    assert "6.0 MVA" in rows["Transformer"]
    assert rows["PCS"] == "4 x 1250 kW @ AC 690 V, 50 Hz, DC 1500 V"
    assert rows["MV CT"] == "200/1, 5P20, 10 VA"
    assert rows["MV Cable"] == "MISSING: MV cable spec"
    assert rows["LV Cable"] == "MISSING: LV cable spec"
    assert rows["DC Cable"] == "MISSING: DC cable spec"
    assert rows["BESS Cell"] == "MISSING: BESS cell spec"
    assert rows["DC Interface"] == "DC isolator/fuse"


def test_engineering_v2_layout_keeps_boxes_inside_sections(sample_excel_path):
    _, plan = _build_v2_plan(sample_excel_path)
    sections = {section.section_id: section for section in plan.sections}

    for box in plan.boxes:
        section = sections[box.section_id]
        assert box.x >= section.x
        assert box.y >= section.y
        assert box.x + box.width <= section.x + section.width
        assert box.y + box.height <= section.y + section.height


def test_engineering_v2_connectors_are_port_anchored(sample_excel_path):
    graph, plan = _build_v2_plan(sample_excel_path)
    anchors = {(anchor.node_id, anchor.port_id): anchor for anchor in plan.port_anchors}

    assert len(plan.connectors) == len(graph.edges)
    for connector in plan.connectors:
        source = anchors[(connector.source_node_id, connector.source_port_id)]
        target = anchors[(connector.target_node_id, connector.target_port_id)]
        assert connector.points[0] == (source.x, source.y)
        assert connector.points[-1] == (target.x, target.y)
        assert connector.voltage_domain == source.voltage_domain


def test_engineering_v2_layout_has_rmu_bays_and_transformer_alignment(sample_excel_path):
    _, plan = _build_v2_plan(sample_excel_path)
    boxes = {box.node_type: box for box in plan.boxes if box.node_type.startswith("rmu_") or box.node_type == "transformer"}
    anchors = {(anchor.node_id, anchor.port_id): anchor for anchor in plan.port_anchors}

    assert boxes["rmu_ring_in_bay"].x < boxes["rmu_transformer_feeder_bay"].x < boxes["rmu_ring_out_bay"].x
    tx_feeder_box = boxes["rmu_transformer_feeder_bay"]
    transformer_box = boxes["transformer"]

    tx_feeder_load = next(
        anchor
        for (node_id, port_id), anchor in anchors.items()
        if node_id == tx_feeder_box.node_id and port_id == "load_port"
    )
    transformer_hv = next(
        anchor
        for (node_id, port_id), anchor in anchors.items()
        if node_id == transformer_box.node_id and port_id == "hv_port"
    )
    assert abs(tx_feeder_load.x - transformer_hv.x) < 1e-6
    assert tx_feeder_load.y < transformer_hv.y


def test_engineering_v2_layout_places_each_feeder_as_lv_to_pcs_to_dc_chain(sample_excel_path):
    graph, plan = _build_v2_plan(sample_excel_path)
    boxes_by_type = {}
    for box in plan.boxes:
        boxes_by_type.setdefault(box.node_type, []).append(box)

    assert len(boxes_by_type["lv_feeder"]) == graph.summary.feeder_count
    assert len(boxes_by_type["pcs"]) == graph.summary.pcs_count
    assert len(boxes_by_type["dc_interface"]) == graph.summary.feeder_count
    assert len(boxes_by_type["dc_block"]) == graph.summary.dc_blocks_total_in_group

    for feeder_index in range(1, graph.summary.feeder_count + 1):
        feeder = next(box for box in boxes_by_type["lv_feeder"] if box.feeder_index == feeder_index)
        pcs = next(box for box in boxes_by_type["pcs"] if box.feeder_index == feeder_index)
        dc_interface = next(box for box in boxes_by_type["dc_interface"] if box.feeder_index == feeder_index)
        dc_block = next(box for box in boxes_by_type["dc_block"] if box.feeder_index == feeder_index)

        feeder_cx = feeder.x + feeder.width / 2
        assert abs((pcs.x + pcs.width / 2) - feeder_cx) < 1e-6
        assert abs((dc_interface.x + dc_interface.width / 2) - feeder_cx) < 1e-6
        assert abs((dc_block.x + dc_block.width / 2) - feeder_cx) < 1e-6
        assert feeder.y < pcs.y < dc_interface.y < dc_block.y


def test_engineering_v2_layout_has_no_node_center_only_connectors(sample_excel_path):
    _, plan = _build_v2_plan(sample_excel_path)

    for connector in plan.connectors:
        assert connector.source_port_id
        assert connector.target_port_id
        assert connector.source_node_id
        assert connector.target_node_id


def test_engineering_v2_layout_distributes_multiple_dc_blocks_per_feeder(sample_excel_path):
    graph, plan = _build_v2_plan_with_dc_allocation(sample_excel_path, [2, 1, 2, 1])
    dc_blocks = [box for box in plan.boxes if box.node_type == "dc_block"]

    assert len(dc_blocks) == graph.summary.dc_blocks_total_in_group == 6

    feeder_1_blocks = [box for box in dc_blocks if box.feeder_index == 1]
    feeder_3_blocks = [box for box in dc_blocks if box.feeder_index == 3]
    assert len(feeder_1_blocks) == 2
    assert len(feeder_3_blocks) == 2
    assert feeder_1_blocks[0].x != feeder_1_blocks[1].x
    assert feeder_3_blocks[0].x != feeder_3_blocks[1].x

    issues = validate_sld_engineering_v2_layout(plan)
    assert not [issue for issue in issues if issue.severity == "error"]


def test_engineering_v2_layout_acceptance_checks_core_readability(sample_excel_path):
    _, plan = _build_v2_plan(sample_excel_path)

    assert_sld_engineering_v2_layout_acceptance(plan)

    transformer = next(box for box in plan.boxes if box.node_type == "transformer")
    joined_transformer_label = " ".join(transformer.text_lines)
    assert "Dyn11" in joined_transformer_label
    assert "Uk=7.0%" in joined_transformer_label
