import copy
import json
import xml.etree.ElementTree as ET

import pytest

from calb_diagrams.cabinet_sld import render_cabinet_sld
from calb_sizing_tool.services.ac_sizing_service import build_dc_allocation_plan
from calb_sizing_tool.services.cabinet_ac_preview_service import attach_cabinet_allocation, build_cabinet_groups


def cabinet_output(count=48, blocks=2, per_block=2, topology="two_winding"):
    plan = build_cabinet_groups(count, round(count * .418, 3), ["CALB_0.418MWh_CAB_8P"])
    allocation = build_dc_allocation_plan(len(plan["groups"]), blocks, per_block, dc_block_output_circuits=1)
    plan = attach_cabinet_allocation(plan, allocation)
    counts = [r["dc_blocks_total"] for r in allocation]
    return dict(dc_unit_kind="independent_cabinet_group", cabinet_group_contract=plan,
                physical_cabinet_count=count, dc_total_mwh=round(count * .418, 3),
                dc_blocks_total=len(plan["groups"]), num_blocks=blocks,
                ac_block_rows=[dict(pcs_count=per_block, pcs_kw=2000, dc_blocks=n) for n in counts],
                pcs_count_by_block=[per_block] * blocks, dc_blocks_per_ac=counts,
                dc_blocks_total_by_block=counts, pcs_count_total=blocks * per_block,
                total_ac_mw=blocks * per_block * 2, dc_allocation_plan=allocation,
                transformer_topology=topology, transformer_topology_confirmation="confirmed_by_user",
                lv_winding_count=1 if topology == "two_winding" else 2,
                lv_busbar_topology="common_single_lv_busbar" if topology == "two_winding" else "independent_lv_busbars",
                dc_block_output_circuits=1, grid_kv=33, lv_v=690)


def test_saved_48_cabinet_membership_is_rendered_once_and_keeps_real_power():
    result = render_cabinet_sld(cabinet_output())
    graph = result["topology"]
    assert len(result["pages"]) == 2
    assert [b["cabinet_count"] for b in graph["ac_blocks"]] == [24, 24]
    assert [b["nameplate_mwh"] for b in graph["ac_blocks"]] == [10.032, 10.032]
    assert [b["pcs_nameplate_mw"] for b in graph["ac_blocks"]] == [4, 4]
    assert graph["physical_cabinet_count"] == 48
    assert graph["total_nameplate_mwh"] == 20.064
    assert len([n for n in graph["nodes"] if n["kind"] == "cabinet"]) == 48
    assert len([n for n in graph["nodes"] if n["kind"] == "pcs"]) == 4
    drawn = [e.attrib["id"] for p in result["pages"] for e in ET.fromstring(p["svg"]).iter()
             if e.tag.endswith("rect") and e.attrib.get("id", "").startswith("cabinet-")]
    assert sorted(drawn) == sorted(f"cabinet-{i}" for i in range(1, 49))
    assert all("20ft" not in p["svg"] for p in result["pages"])
    json.dumps(result)


def test_uneven_41_cabinets_preserve_actual_group_energy_and_ids():
    output = cabinet_output(41)
    result = render_cabinet_sld(output)
    buses = [n for n in result["topology"]["nodes"] if n["kind"] == "independent_dc_bus"]
    assert [b["nameplate_mwh"] for b in buses] == [4.598, 4.18, 4.18, 4.18]
    assert [b["cabinet_count"] for b in result["topology"]["ac_blocks"]] == [21, 20]
    assert "C041" in result["pages"][1]["svg"]
    assert "C042" not in result["pages"][1]["svg"]


def test_dc_graph_never_ties_independent_groups_or_shares_a_pcs():
    graph = render_cabinet_sld(cabinet_output())["topology"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    dc_edges = [e for e in graph["edges"] if e["domain"] == "dc"]
    for edge in dc_edges:
        assert nodes[edge["source"]]["group_index"] == nodes[edge["target"]]["group_index"]
    for pcs in [n for n in graph["nodes"] if n["kind"] == "pcs"]:
        incoming = [e for e in dc_edges if e["target"] == pcs["id"]]
        assert len(incoming) == 1
        assert nodes[incoming[0]["source"]]["kind"] == "independent_dc_bus"


def test_three_winding_keeps_lv_buses_separate_and_explicitly_provisional():
    result = render_cabinet_sld(cabinet_output(topology="three_winding"))
    graph = result["topology"]
    assert graph["lv_allocation_basis"] == "concept_balanced_split_pending_oem"
    assert any("pending OEM" in warning for warning in result["warnings"])
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert not any(nodes[e["source"]]["kind"] == nodes[e["target"]]["kind"] == "lv_bus" for e in graph["edges"])
    for index in (1, 2):
        buses = [n for n in graph["nodes"] if n["kind"] == "lv_bus" and n["ac_block_index"] == index]
        assert {b["winding"] for b in buses} == {"A", "B"}
        assignments = [n for n in graph["nodes"] if n["kind"] == "pcs" and n["ac_block_index"] == index]
        assert {p["lv_winding"] for p in assignments} == {"A", "B"}
        assert all(not p["lv_allocation_confirmed"] for p in assignments)
    assert all("Vector / grounding: TBC" in p["svg"] for p in result["pages"])
    assert all("Dyn" not in p["svg"] for p in result["pages"])


@pytest.mark.parametrize("field,value", [
    ("dc_unit_kind", "container"), ("physical_cabinet_count", 49),
    ("dc_total_mwh", 99), ("dc_blocks_total", 48), ("num_blocks", 3),
    ("pcs_count_by_block", [3, 1]), ("pcs_count_total", 99), ("total_ac_mw", 99),
    ("transformer_topology", "automatic"), ("transformer_topology_confirmation", None),
    ("lv_winding_count", 2), ("lv_busbar_topology", "independent_lv_busbars"),
    ("dc_block_output_circuits", 2), ("lv_v", float("nan")),
    ("lv_winding_count", True), ("dc_block_output_circuits", True),
    ("pcs_count_by_block", [2.0, 2]), ("pcs_count_total", 4.0),
])
def test_conflicting_or_unconfirmed_snapshot_fails_before_rendering(field, value):
    output = cabinet_output()
    output[field] = value
    with pytest.raises(ValueError):
        render_cabinet_sld(output)


@pytest.mark.parametrize("corruption", ["member", "energy", "local_pcs", "ac_block", "row_count", "connection", "swapped_pcs", "float_id"])
def test_corrupted_physical_schedule_or_allocation_is_rejected(corruption):
    output = cabinet_output()
    if corruption == "member":
        output["cabinet_group_contract"]["groups"][1]["cabinet_indices"][0] = 1
    elif corruption == "energy":
        output["cabinet_group_contract"]["groups"][0]["nameplate_mwh"] = 9
    elif corruption == "local_pcs":
        output["cabinet_group_contract"]["groups"][1]["pcs_index"] = 3
    elif corruption == "ac_block":
        output["cabinet_group_contract"]["groups"][0]["ac_block_index"] = 3
    elif corruption == "row_count":
        output["ac_block_rows"][0]["pcs_count"] = 3
    elif corruption == "swapped_pcs":
        output["cabinet_group_contract"]["groups"][0]["pcs_index"] = 2
        output["cabinet_group_contract"]["groups"][1]["pcs_index"] = 1
    elif corruption == "float_id":
        output["cabinet_group_contract"]["groups"][0]["group_index"] = 1.0
    else:
        output["dc_allocation_plan"][0]["dc_block_connections"][0]["feeder_indices"] = [2]
    with pytest.raises(ValueError):
        render_cabinet_sld(output)


def test_three_winding_rejects_an_unsubstantiated_second_lv_connection():
    output = cabinet_output(12, blocks=1, per_block=1, topology="three_winding")
    with pytest.raises(ValueError, match="both independent LV"):
        render_cabinet_sld(output)


def test_renderer_is_deterministic_escapes_customer_text_and_does_not_mutate_input():
    output = cabinet_output()
    before = copy.deepcopy(output)
    result = render_cabinet_sld(output, '<script>"A & B"</script>')
    assert result == render_cabinet_sld(output, '<script>"A & B"</script>')
    assert output == before
    assert "<script>" not in result["pages"][0]["svg"]
    assert "&lt;script&gt;" in result["pages"][0]["svg"]
    assert ET.fromstring(result["pages"][0]["svg"]) is not None


def test_maximum_eight_group_sheet_has_in_frame_non_overlapping_cabinets():
    output = cabinet_output(96, blocks=1, per_block=8, topology="three_winding")
    root = ET.fromstring(render_cabinet_sld(output)["pages"][0]["svg"])
    rectangles = [e for e in root.iter() if e.tag.endswith("rect") and e.attrib.get("id", "").startswith("cabinet-")]
    assert len(rectangles) == 96
    boxes = [(float(e.attrib["x"]), float(e.attrib["y"]), float(e.attrib["width"]), float(e.attrib["height"])) for e in rectangles]
    for x, y, width, height in boxes:
        assert 28 <= x < x + width <= 1652
        assert 185 < y < y + height < 985
    for i, first in enumerate(boxes):
        x1, y1, w1, h1 = first
        for x2, y2, w2, h2 in boxes[i + 1:]:
            assert x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1
    # DC feeders are horizontal + vertical, with no diagonal fan or cross-group bus.
    for e in root.iter():
        if e.tag.endswith("polyline"):
            points = [tuple(map(float, pair.split(","))) for pair in e.attrib["points"].split()]
            assert all(x1 == x2 or y1 == y2 for (x1, y1), (x2, y2) in zip(points, points[1:]))


def test_small_block_transformer_and_lv_labels_do_not_intrude_into_header():
    root = ET.fromstring(render_cabinet_sld(cabinet_output(12, 1, 1))["pages"][0]["svg"])
    transformer = next(e for e in root.iter() if e.attrib.get("id") == "concept-transformer")
    assert float(transformer.attrib["y"]) >= 225
    lv_labels = [e for e in root.iter() if e.tag.endswith("text") and e.text == "LV-A"]
    assert all(float(e.attrib["y"]) > 225 for e in lv_labels)


def test_summed_group_energy_must_reconcile_not_only_individual_rounding():
    output = cabinet_output()
    for group in output["cabinet_group_contract"]["groups"]:
        group["nameplate_mwh"] += .0004
    with pytest.raises(ValueError, match="Summed independent group energy"):
        render_cabinet_sld(output)


def test_two_pcs_transformer_port_label_has_actual_text_clearance_from_title():
    # Use the same Cairo font backend as the exported drawing. Checking only
    # label origins missed this defect: the two strings occupied the same line.
    from cairosvg.surface import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    context = cairo.Context(surface)
    context.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)

    def text_bounds(element):
        context.set_font_size(float(element.attrib["font-size"]))
        x_bearing, y_bearing, width, height, advance, _ = context.text_extents(element.text)
        origin_x = float(element.attrib["x"])
        anchor = element.attrib.get("text-anchor", "start")
        if anchor == "middle":
            origin_x -= advance / 2
        elif anchor == "end":
            origin_x -= advance
        return (origin_x + x_bearing, float(element.attrib["y"]) + y_bearing,
                origin_x + x_bearing + width, float(element.attrib["y"]) + y_bearing + height)

    for page in render_cabinet_sld(cabinet_output())["pages"]:
        root = ET.fromstring(page["svg"])
        port = next(e for e in root.iter() if e.attrib.get("id") == "transformer-lv-A-label")
        title = next(e for e in root.iter() if e.tag.endswith("text") and e.text == "TRANSFORMER")
        port_box, title_box = text_bounds(port), text_bounds(title)
        # This is the actual problematic 2-PCS geometry: vertical glyph bounds
        # overlap, so adequate horizontal glyph clearance is essential.
        assert max(port_box[1], title_box[1]) < min(port_box[3], title_box[3])
        assert title_box[0] - port_box[2] >= 12

        # Prove that returning to the previous position would fail this same
        # clearance check, even though both SVG text origins remain in frame.
        transformer = next(e for e in root.iter() if e.attrib.get("id") == "concept-transformer")
        port.set("x", str(float(transformer.attrib["x"]) + 8))
        port.attrib.pop("text-anchor")
        assert title_box[0] - text_bounds(port)[2] < 12
