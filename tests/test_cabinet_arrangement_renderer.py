import copy
import json
import xml.etree.ElementTree as ET

import pytest

from calb_diagrams.cabinet_arrangement import render_cabinet_arrangement
from tests.test_cabinet_sld_renderer import cabinet_output


def _rectangles(svg):
    return [e for e in ET.fromstring(svg).iter() if e.tag.endswith("rect")]


def _box(element):
    return tuple(float(element.attrib[k]) for k in ("x", "y", "width", "height"))


def _within(inner, outer):
    x, y, width, height = _box(inner)
    ox, oy, ow, oh = _box(outer)
    return ox <= x < x + width <= ox + ow and oy <= y < y + height <= oy + oh


def test_48_cabinet_arrangement_preserves_real_membership_and_pcs_labels():
    output = cabinet_output()
    before = copy.deepcopy(output)
    result = render_cabinet_arrangement(output, "Local test")
    schedule = result["schedule"]
    assert len(result["pages"]) == 2
    assert schedule["physical_cabinet_count"] == 48
    assert schedule["total_nameplate_mwh"] == 20.064
    assert schedule["pcs_count_total"] == 4
    assert schedule["site_area_m2"] is None
    assert schedule["equipment_footprints"] is None
    assert not schedule["dimensions_confirmed"]
    assert not schedule["clearances_confirmed"]
    assert not schedule["fire_separation_verified"]
    assert schedule["ac_blocks"][1]["groups"][0]["cabinet_indices"] == list(range(25, 37))
    assert schedule["ac_blocks"][1]["groups"][0]["pcs_label"] == "PCS 02-01"
    assert schedule["ac_blocks"][1]["groups"][1]["pcs_label"] == "PCS 02-02"
    assert schedule["ac_blocks"][1]["nameplate_mwh"] == 10.032
    assert "C048" in result["pages"][1]["svg"]
    assert "C049" not in result["pages"][1]["svg"]
    assert output == before
    json.dumps(result)


def test_41_cabinet_tail_groups_keep_actual_unequal_quantities():
    result = render_cabinet_arrangement(cabinet_output(41))
    groups = [g for b in result["schedule"]["ac_blocks"] for g in b["groups"]]
    assert [g["cabinet_count"] for g in groups] == [11, 10, 10, 10]
    assert [g["nameplate_mwh"] for g in groups] == [4.598, 4.18, 4.18, 4.18]
    assert "C041" in result["pages"][1]["svg"]
    assert "C042" not in result["pages"][1]["svg"]
    assert [b["cabinet_count"] for b in result["schedule"]["ac_blocks"]] == [21, 20]


@pytest.mark.parametrize("count,blocks,pcs", [(1, 1, 1), (12, 1, 1), (24, 1, 2),
                                               (48, 2, 2), (48, 1, 4), (96, 1, 8)])
def test_rendered_equipment_bounds_and_reserves_do_not_overlap(count, blocks, pcs):
    result = render_cabinet_arrangement(cabinet_output(count, blocks, pcs))
    cabinet_ids = []
    for page in result["pages"]:
        rectangles = _rectangles(page["svg"])
        boundaries = {e.attrib["data-group-index"]: e for e in rectangles
                      if e.attrib.get("data-kind") == "group_boundary"}
        equipment = [e for e in rectangles if e.attrib.get("data-kind") in {"cabinet", "pcs_zone"}]
        reserves = [e for e in rectangles if e.attrib.get("data-kind") in {"service_reserve", "cable_reserve"}]
        for element in equipment + reserves:
            group = element.attrib["data-group-index"]
            assert _within(element, boundaries[group])
            x, y, width, height = _box(element)
            assert 55 <= x < x + width <= 1625
            assert 210 <= y < y + height <= 870
            if element.attrib["data-kind"] == "cabinet":
                cabinet_ids.append(element.attrib["id"])
        # Test actual SVG rectangles, not a separate planned geometry model.
        all_symbols = equipment + reserves
        for i, first in enumerate(all_symbols):
            x1, y1, w1, h1 = _box(first)
            for second in all_symbols[i + 1:]:
                x2, y2, w2, h2 = _box(second)
                assert x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1
        root = ET.fromstring(page["svg"])
        assert not any(e.tag.endswith(("line", "polyline", "path")) for e in root.iter())
        for text in [e for e in root.iter() if e.tag.endswith("text")]:
            assert 28 < float(text.attrib["x"]) < 1652
            assert 28 < float(text.attrib["y"]) < 1160
    assert sorted(cabinet_ids) == sorted(f"cabinet-{i}" for i in range(1, count + 1))


def test_eight_group_sheet_uses_all_real_groups_and_stays_readable():
    result = render_cabinet_arrangement(cabinet_output(96, 1, 8))
    svg = result["pages"][0]["svg"]
    root = ET.fromstring(svg)
    labels = [e for e in root.iter() if e.tag.endswith("text") and (e.text or "").startswith("C0")]
    assert len(labels) == 96
    assert all(float(e.attrib["font-size"]) >= 11 for e in labels)
    assert len({e.attrib["data-group-index"] for e in _rectangles(svg)
                if e.attrib.get("data-kind") == "group_boundary"}) == 8
    assert svg.count("PCS 01-08") == 2  # group membership title and physical PCS zone


def test_concept_boundary_is_unambiguous_and_container_assumptions_absent():
    result = render_cabinet_arrangement(cabinet_output())
    for page in result["pages"]:
        svg = page["svg"]
        for statement in ["NOT TO SCALE / NO SITE AREA ESTIMATE", "CONCEPT / NOT FOR CONSTRUCTION",
                          "Group outlines show saved electrical membership, not fire compartments",
                          "station type, footprint and equipment separation: TBC"]:
            assert statement in svg
        assert "20ft" not in svg
        assert "40ft" not in svg
        assert "site_area_m2" not in svg
    assert any("Fire separation" in w for w in result["warnings"])


@pytest.mark.parametrize("corruption", ["count", "energy", "pcs", "member", "topology", "marker"])
def test_arrangement_cannot_bypass_existing_cabinet_contract_validation(corruption):
    output = cabinet_output()
    if corruption == "count":
        output["physical_cabinet_count"] = 49
    elif corruption == "energy":
        output["dc_total_mwh"] = 100
    elif corruption == "pcs":
        output["cabinet_group_contract"]["groups"][0]["pcs_index"] = 2
    elif corruption == "member":
        output["cabinet_group_contract"]["groups"][0]["cabinet_indices"][0] = 99
    elif corruption == "topology":
        output["transformer_topology_confirmation"] = None
    else:
        output["dc_unit_kind"] = "container"
    with pytest.raises(ValueError):
        render_cabinet_arrangement(output)


def test_customer_text_is_escaped_and_arrangement_is_deterministic():
    output = cabinet_output()
    first = render_cabinet_arrangement(output, '<Project "A" & B>')
    assert first == render_cabinet_arrangement(output, '<Project "A" & B>')
    assert "<Project" not in first["pages"][0]["svg"]
    assert "&lt;Project" in first["pages"][0]["svg"]
    ET.fromstring(first["pages"][0]["svg"])


@pytest.mark.parametrize("output", [cabinet_output(12, 1, 1), cabinet_output(), cabinet_output(96, 1, 8)])
def test_actual_text_glyphs_fit_inside_equipment_and_page(output):
    from cairosvg.surface import cairo

    context = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
    for page in render_cabinet_arrangement(output)["pages"]:
        root = ET.fromstring(page["svg"])
        for element in [e for e in root.iter() if e.tag.endswith("text")]:
            context.select_font_face("Arial", cairo.FONT_SLANT_NORMAL,
                                     cairo.FONT_WEIGHT_BOLD if element.attrib.get("font-weight") == "bold" else cairo.FONT_WEIGHT_NORMAL)
            context.set_font_size(float(element.attrib["font-size"]))
            xb, yb, width, height, advance, _ = context.text_extents(element.text)
            x, y = float(element.attrib["x"]), float(element.attrib["y"])
            if element.attrib.get("text-anchor") == "middle":
                x -= advance / 2
            assert 28 <= x + xb < x + xb + width <= 1652
            assert 28 <= y + yb < y + yb + height <= 1160
            label = element.text or ""
            if label.startswith("C0") and label[1:].isdigit():
                cabinet = next(e for e in _rectangles(page["svg"]) if e.attrib.get("id") == f"cabinet-{int(label[1:])}")
                cx, cy, cw, ch = _box(cabinet)
                assert cx <= x + xb < x + xb + width <= cx + cw
                assert cy <= y + yb < y + yb + height <= cy + ch


def _documented_basis():
    return dict(status="documented", cabinet_dimensions_mm={"width": 1200, "depth": 1500, "height": 2500},
                dimension_source=dict(source_title="Example cabinet data sheet", page=2, revision="A"),
                clearances=[dict(relation="Cabinet side to side", value_mm=300,
                                 evidence_kind="test_configuration", source_title="Example test document",
                                 page=10, conditions="Example test configuration only")], notes=[])


def test_optional_documented_basis_is_retained_without_claiming_scaled_geometry():
    basis = _documented_basis()
    original = copy.deepcopy(basis)
    result = render_cabinet_arrangement(cabinet_output(), installation_basis=basis)
    assert result["schedule"]["installation_basis"] == basis
    assert result["schedule"]["installation_basis"] is not basis
    assert result["schedule"]["site_area_m2"] is None
    assert not result["schedule"]["dimensions_confirmed"]
    assert basis == original
    assert result["schedule"]["cabinet_dimensions_documented"]
    assert "Documented cabinet W x D x H: 1200 x 1500 x 2500 mm" in result["pages"][0]["svg"]
    assert "Dimension source: Example cabinet data sheet, p. 2, rev. A" in result["pages"][0]["svg"]
    assert result["schedule"]["dimension_source"] == basis["dimension_source"]
    assert "TEST SETUP / NOT INSTALLATION MINIMUM" in result["pages"][0]["svg"]
    assert any("TEST SETUP / NOT INSTALLATION MINIMUM" in warning for warning in result["warnings"])


@pytest.mark.parametrize("basis", [dict(status="draft", cabinet_dimensions_mm=None, clearances=[], notes=[]),
                                     dict(status="documented", cabinet_dimensions_mm=None, clearances=[], notes=[]),
                                     dict(status="documented", cabinet_dimensions_mm=[], clearances=[], notes=[]),
                                     dict(status="documented", cabinet_dimensions_mm={"width": float("nan"), "depth": 1, "height": 1}, clearances=[], notes=[])])
def test_malformed_installation_basis_is_rejected(basis):
    with pytest.raises(ValueError, match="Installation basis"):
        render_cabinet_arrangement(cabinet_output(), installation_basis=basis)


def test_unverified_basis_cannot_promote_dimensions_or_test_values_to_drawing_claims():
    basis = _documented_basis()
    basis["status"] = "unverified"
    result = render_cabinet_arrangement(cabinet_output(), installation_basis=basis)
    assert not result["schedule"]["cabinet_dimensions_documented"]
    assert "1200 x 1500 x 2500 mm" not in result["pages"][0]["svg"]
    assert "Dimension source:" not in result["pages"][0]["svg"]
    assert "Footprints, access sides and all clearances: TBC" in result["pages"][0]["svg"]
    assert result["schedule"]["installation_basis"]["status"] == "unverified"


def test_manufacturer_requirement_is_distinguished_from_a_test_configuration():
    basis = _documented_basis()
    basis["clearances"][0]["evidence_kind"] = "manufacturer_requirement"
    result = render_cabinet_arrangement(cabinet_output(), installation_basis=basis)
    assert "TEST SETUP / NOT INSTALLATION MINIMUM" not in result["pages"][0]["svg"]
    assert result["schedule"]["installation_basis"]["clearances"][0]["evidence_kind"] == "manufacturer_requirement"


@pytest.mark.parametrize("source", [None, {}, {"source_title": "Data sheet"},
                                      {"source_title": "Data sheet", "page": 0},
                                      {"source_title": "Data sheet", "page": True},
                                      {"source_title": "", "page": 2},
                                      {"source_title": "D:/private/data.pdf", "page": 2},
                                      {"source_title": "/private/data.pdf", "page": 2}])
def test_documented_dimension_claims_require_a_complete_non_path_source_reference(source):
    basis = _documented_basis()
    if source is None:
        basis.pop("dimension_source")
    else:
        basis["dimension_source"] = source
    with pytest.raises(ValueError, match="dimension_source"):
        render_cabinet_arrangement(cabinet_output(), installation_basis=basis)


def test_unverified_dimensions_may_retain_partial_provenance_without_a_drawing_claim():
    basis = _documented_basis()
    basis["status"] = "unverified"
    basis["dimension_source"] = {"source_title": "Pending data sheet"}
    result = render_cabinet_arrangement(cabinet_output(), installation_basis=basis)
    assert not result["schedule"]["cabinet_dimensions_documented"]
    assert result["schedule"]["dimension_source"] == basis["dimension_source"]
    assert "Documented cabinet W x D x H" not in result["pages"][0]["svg"]
    assert "Dimension source:" not in result["pages"][0]["svg"]
