"""Shared DC block topology: fewer DC blocks than PCS feeders.

A 5 MW AC block with 4 x 1250 kW PCS and 2 x 5 MWh DC blocks must render each
DC block feeding a span of PCS feeders (through each feeder's own fuse) — not
two PCS feeders dangling with no DC source, which is electrically meaningless.
"""
from __future__ import annotations

from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_engineering_v2_renderer import render_sld_engineering_v2_svg
from calb_diagrams.sld_engineering_v2_validation import validate_sld_engineering_v2_layout
from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
from tests.unit.test_sld_topology_builder import _build_run_bundle, _make_ac_snapshot


def _make_shared_ac_snapshot() -> AcSnapshot:
    # 5 MW AC block: 4 x 1250 kW PCS fed by 2 x DC blocks (authoritative
    # allocation [1, 1, 0, 0] — two feeders share each block's DC combiner).
    return AcSnapshot(
        inputs={"grid_kv": 33.0, "lv_voltage_v": 690.0},
        output={
            "num_blocks": 1,
            "pcs_per_block": 4,
            "pcs_kw": 1250.0,
            "block_size_mw": 5.0,
            "transformer_mva": 6.0,
            "dc_allocation_plan": [
                {"ac_block_index": 1, "dc_blocks_total": 2, "feeder_allocations": [1, 1, 0, 0]}
            ],
        },
        results={},
    )


def _shared_topology(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["dc_block_voltage_v"] = 1500.0
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=_make_shared_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )
    return build_sld_topology(canonical)


def test_every_pcs_feeder_has_a_dc_source(sample_excel_path):
    topology = _shared_topology(sample_excel_path)
    assert topology.summary.lv_winding_count == 2
    graph = build_sld_engineering_v2_graph(topology)

    dc_blocks = [n for n in graph.nodes if n.node_type == "dc_block"]
    assert len(dc_blocks) == 2  # total block count preserved

    # Every dc_interface (one per PCS feeder) must feed into a DC block.
    interfaces = {n.node_id for n in graph.nodes if n.node_type == "dc_interface"}
    sourced = {e.source_node_id for e in graph.edges if e.edge_type == "dc_interface_to_dc_block"}
    assert interfaces == sourced, "a PCS feeder is dangling without a DC source"

    spans = sorted(tuple(n.attributes["feeder_span"]) for n in dc_blocks)
    assert spans == [(1, 2), (3, 4)]

    lv_busbars = sorted(
        (node for node in graph.nodes if node.node_type == "lv_busbar"),
        key=lambda node: int(node.attributes["winding_index"]),
    )
    assert [node.attributes["feeder_span"] for node in lv_busbars] == [[1, 2], [3, 4]]


def test_per_feeder_mode_is_unchanged(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = [1, 1, 1, 1]
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=_make_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )
    graph = build_sld_engineering_v2_graph(build_sld_topology(canonical))
    dc_blocks = [n for n in graph.nodes if n.node_type == "dc_block"]
    assert len(dc_blocks) == 4
    assert sorted(tuple(n.attributes["feeder_span"]) for n in dc_blocks) == [(1,), (2,), (3,), (4,)]


def test_shared_layout_renders_and_passes_acceptance(sample_excel_path):
    graph = build_sld_engineering_v2_graph(_shared_topology(sample_excel_path))
    plan = build_sld_engineering_v2_layout_plan(graph, theme="dark")

    errors = [i for i in validate_sld_engineering_v2_layout(plan) if i.severity == "error"]
    assert not errors, [i.message for i in errors]

    block_boxes = [b for b in plan.boxes if b.node_type == "dc_block"]
    assert len(block_boxes) == 2
    # Shared block sits between its two feeders: strictly between the fuse
    # boxes of F1/F2 (i.e. not centred under a single feeder).
    fuse_boxes = sorted(
        (b for b in plan.boxes if b.node_type == "dc_interface"),
        key=lambda b: b.feeder_index or 0,
    )
    first_block = min(block_boxes, key=lambda b: b.x)
    f1_center = fuse_boxes[0].x + fuse_boxes[0].width / 2.0
    f2_center = fuse_boxes[1].x + fuse_boxes[1].width / 2.0
    block_center = first_block.x + first_block.width / 2.0
    assert f1_center < block_center < f2_center

    # Equipment list reports block->feeder spans, not dangling zero counts.
    allocation_row = next(r for r in plan.equipment_rows if "DC1" in r.spec or "F1=" in r.spec)
    assert "DC1→F1-F2" in allocation_row.spec
    assert "F3=0" not in allocation_row.spec


def test_shared_dc_svg_draws_both_outputs_and_split_lv_windings(sample_excel_path, tmp_path):
    graph = build_sld_engineering_v2_graph(_shared_topology(sample_excel_path))
    plan = build_sld_engineering_v2_layout_plan(graph, theme="light")
    svg_path = tmp_path / "shared_dc_split_lv.svg"

    rendered_path, warning = render_sld_engineering_v2_svg(plan, svg_path)

    assert rendered_path == svg_path
    assert warning is None
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "LV-A DISTRIBUTION SECTION" in svg_text
    assert "LV-B DISTRIBUTION SECTION" in svg_text
    assert "NO LV BUS TIE" in svg_text
    assert "LV-A BUS / 690 V" in svg_text
    assert "LV-B BUS / 690 V" in svg_text
    assert "3-winding: 1 MV primary + 2 independent LV secondaries" in svg_text
    assert 'id="transformer-lv-winding-1"' in svg_text
    assert 'id="transformer-lv-winding-2"' in svg_text
    assert 'id="shared-dc-G01-DC-BLOCK-01-F01"' in svg_text
    assert 'id="shared-dc-G01-DC-BLOCK-01-F02"' in svg_text
    assert 'id="shared-dc-G01-DC-BLOCK-02-F03"' in svg_text
    assert 'id="shared-dc-G01-DC-BLOCK-02-F04"' in svg_text


def _shared_branch_points(svg_text: str, poly_id: str) -> list[tuple[float, float]]:
    import re

    match = re.search(rf'<polyline[^>]*id="{poly_id}"[^>]*>', svg_text)
    assert match, f"polyline {poly_id} not found"
    points_attr = re.search(r'points="([^"]+)"', match.group(0)).group(1)
    return [
        (float(pair.split(",")[0]), float(pair.split(",")[1]))
        for pair in points_attr.replace(", ", ",").split()
    ]


def test_pcs_dc_sides_never_share_a_dc_busbar(sample_excel_path, tmp_path):
    """ELECTRICAL RULE (owner, 2026-07-13): a PCS DC input must never share a
    DC busbar with another PCS. A shared DC Block connects each PCS through its
    own independent output circuit — the drawing must not contain a common
    conductor joining two PCS DC sides outside the block."""
    graph = build_sld_engineering_v2_graph(_shared_topology(sample_excel_path))
    plan = build_sld_engineering_v2_layout_plan(graph, theme="light")
    svg_path = tmp_path / "shared_dc_rule.svg"
    render_sld_engineering_v2_svg(plan, svg_path)
    svg_text = svg_path.read_text(encoding="utf-8")

    # The old (electrically wrong) drawing joined the feeders with a horizontal
    # "branch" bus and a block riser tapping it. Neither may exist any more.
    assert "-branch" not in svg_text
    assert "shared-dc-G01-DC-BLOCK-01-block" not in svg_text

    f01 = _shared_branch_points(svg_text, "shared-dc-G01-DC-BLOCK-01-F01")
    f02 = _shared_branch_points(svg_text, "shared-dc-G01-DC-BLOCK-01-F02")

    # Each branch lands on its own discrete terminal on the block top.
    assert f01[-1][1] == f02[-1][1]              # both reach the block top edge
    assert f01[-1][0] != f02[-1][0]              # ...at different terminals
    # The two branches never touch: no shared vertex between the polylines.
    assert not (set(f01) & set(f02)), "PCS DC branches must not share any conductor point"
    # Discrete output circuits are labelled.
    assert ">OUT-1<" in svg_text
    assert ">OUT-2<" in svg_text
