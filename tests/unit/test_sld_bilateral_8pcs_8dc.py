"""SLD regression for the governed ACBLK-10MW-8PCS-8DC-40FT-BILATERAL unit.

Drives the governed configuration through the real AC->SLD contract path and
asserts the exact topology the handoff (§7) requires:
- one AC Block;
- eight 1,250 kW PCS feeders;
- two LV secondary groups, four feeders per group (4+4);
- eight DC Block nodes, each mapped DC-i -> PCS-i;
- every PCS feeder has a DC source (no dangling PCS);
- no symbol/label/wire collision (layout + rendered-SVG validators);
- exact equipment counts.
"""
from __future__ import annotations

from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_engineering_v2_renderer import render_sld_engineering_v2_svg
from calb_diagrams.sld_engineering_v2_validation import (
    validate_rendered_sld_svg,
    validate_sld_engineering_v2_layout,
)
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.governed_ac_block_config import (
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as CFG,
)
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
from tests.unit.test_sld_topology_builder import _build_run_bundle


# PROVISIONAL engineering values injected only to make the drawing renderable.
# They are NOT owner-approved product data: 10 MW / 0.9 = 11.11 MVA is supplied
# here as an explicit Engineering Setting, exactly what the governed config
# refuses to invent on its own.
_PROVISIONAL_TRANSFORMER_MVA = 11.11
_PROVISIONAL_LV_VOLTAGE_V = 690.0


def _governed_ac_snapshot() -> AcSnapshot:
    output = CFG.to_ac_sld_output(
        engineering_overrides={
            "transformer_mva": _PROVISIONAL_TRANSFORMER_MVA,
            "lv_voltage_v": _PROVISIONAL_LV_VOLTAGE_V,
        }
    )
    # The governed configuration intentionally leaves vector group provisional
    # until it is bound to product/engineering data.  Carry the selected
    # product-style value on the AC-to-SLD output contract for this 8-PCS test.
    output["transformer_vector_group"] = "Dy11y11"
    return AcSnapshot(
        inputs={"grid_kv": 33.0, "lv_voltage_v": _PROVISIONAL_LV_VOLTAGE_V},
        output=output,
        results={},
    )


def _governed_topology(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["transformer_vector_group"] = "Dy11y11"
    override_payload["dc_block_voltage_v"] = 1500.0
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=_governed_ac_snapshot(),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )
    return build_sld_topology(canonical)


def test_topology_has_one_block_eight_pcs_two_lv_windings(sample_excel_path):
    topology = _governed_topology(sample_excel_path)
    assert topology.summary.ac_blocks_total == 1
    assert topology.summary.pcs_count == 8
    assert topology.summary.feeder_count == 8
    assert topology.summary.lv_winding_count == 2
    assert topology.summary.transformer_topology == "three_winding"


def test_two_lv_secondaries_split_four_plus_four(sample_excel_path):
    topology = _governed_topology(sample_excel_path)
    lv_busbars = sorted(
        (node for node in topology.nodes if node.node_type == "lv_busbar"),
        key=lambda node: int(node.attributes["winding_index"]),
    )
    assert len(lv_busbars) == 2
    assert [node.attributes["feeder_span"] for node in lv_busbars] == [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
    ]


def test_exact_equipment_counts(sample_excel_path):
    topology = _governed_topology(sample_excel_path)

    def count(node_type: str) -> int:
        return sum(1 for node in topology.nodes if node.node_type == node_type)

    assert count("pcs") == 8
    assert count("dc_interface") == 8
    assert count("dc_block") == 8
    assert count("lv_busbar") == 2
    assert count("transformer") == 1
    assert count("mv_switchgear") == 1


def test_eight_dc_nodes_mapped_one_to_one(sample_excel_path):
    topology = _governed_topology(sample_excel_path)
    dc_blocks = sorted(
        (node for node in topology.nodes if node.node_type == "dc_block"),
        key=lambda node: int(node.dc_block_index or 0),
    )
    assert [node.dc_block_index for node in dc_blocks] == list(range(1, 9))
    # DC-i -> PCS-i dedicated links (single-feeder span each).
    assert [tuple(node.attributes["feeder_span"]) for node in dc_blocks] == [
        (i,) for i in range(1, 9)
    ]


def test_no_dangling_pcs_feeder(sample_excel_path):
    """Every PCS feeder must trace to a DC source (handoff §7)."""
    topology = _governed_topology(sample_excel_path)
    graph = build_sld_engineering_v2_graph(topology)
    interfaces = {n.node_id for n in graph.nodes if n.node_type == "dc_interface"}
    sourced = {
        e.source_node_id for e in graph.edges if e.edge_type == "dc_interface_to_dc_block"
    }
    assert interfaces == sourced


def test_layout_and_rendered_svg_have_no_collisions(sample_excel_path, tmp_path):
    graph = build_sld_engineering_v2_graph(_governed_topology(sample_excel_path))
    plan = build_sld_engineering_v2_layout_plan(graph, theme="light")

    layout_errors = [i for i in validate_sld_engineering_v2_layout(plan) if i.severity == "error"]
    assert not layout_errors, [i.message for i in layout_errors]

    svg_path = tmp_path / "bilateral_8pcs_8dc.svg"
    rendered_path, warning = render_sld_engineering_v2_svg(plan, svg_path)
    assert rendered_path == svg_path
    assert warning is None

    svg_text = svg_path.read_text(encoding="utf-8")
    svg_errors = [i for i in validate_rendered_sld_svg(svg_text) if i.severity == "error"]
    assert not svg_errors, [i.message for i in svg_errors]

    # Both independent LV secondaries are drawn.
    assert "LV-A DISTRIBUTION SECTION" in svg_text
    assert "LV-B DISTRIBUTION SECTION" in svg_text
    assert "NO LV BUS TIE" in svg_text
    assert "3-winding: 1 MV primary + 2 independent LV secondaries" in svg_text
    for winding in (1, 2):
        prefix = f'tx-lv-winding-{winding}'
        assert f'id="{prefix}-wye-left"' in svg_text
        assert f'id="{prefix}-wye-right"' in svg_text
        assert f'id="{prefix}-earth-bar-1"' not in svg_text
