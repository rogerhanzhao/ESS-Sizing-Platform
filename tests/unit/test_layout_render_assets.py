from dataclasses import asdict, replace
from types import SimpleNamespace
import hashlib
import io
import json
from copy import deepcopy

from PIL import Image
import pytest
from docx import Document

from calb_diagrams.ac_block_arrangement_v2 import US_NFPA_OIL
from calb_diagrams.typical_ac_block_arrangement import AcBlockShape, render_typical_ac_block
from calb_sizing_tool.reporting import layout_render_assets as assets
from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting import report_v2


def make_assets(root, n=4, pcs=4, power=5):
    arrangement = render_typical_ac_block(AcBlockShape(n, pcs, power))
    views = {}
    for i, view in enumerate(("TOP", *assets.OBLIQUE_VIEWS)):
        stream = io.BytesIO()
        Image.new("RGB", (150, 100), (i * 30, 100, 160)).save(stream, format="PNG")
        data = stream.getvalue()
        (root / f"{view}.png").write_bytes(data)
        views[view] = dict(file=f"{view}.png", sha256=hashlib.sha256(data).hexdigest())
    entry = dict(id="TEST", released=True, dc_count=n, ac_length_m=arrangement.station_length_m,
                 variant=arrangement.layout_variant, block_power_mw=[power],
                 profile=asdict(US_NFPA_OIL), source_placements=assets.placement_signature(arrangement, US_NFPA_OIL),
                 bound_product_codes=[], allow_unbound_concept=True, views=views)
    (root / "manifest.json").write_text(json.dumps(dict(version="test.1", templates=[entry])), encoding="utf-8")
    ctx = SimpleNamespace(scenario_id="container_only", dc_block_unit_mwh=5.016,
                          ac_output={}, configuration_code=None)
    return ctx, arrangement


@pytest.mark.parametrize("n,pcs,power", [(8,8,10),(4,4,5),(2,2,2.5),(4,8,10)])
def test_each_supported_shape_gets_top_and_one_of_four(tmp_path, n, pcs, power):
    ctx, arrangement = make_assets(tmp_path, n, pcs, power)
    selected = set()
    for view in assets.OBLIQUE_VIEWS:
        pair = assets.select_render_pair(ctx, arrangement, US_NFPA_OIL, root=tmp_path, choose=lambda _: view)
        assert pair.top_png == (tmp_path / "TOP.png").read_bytes()
        assert pair.oblique_png == (tmp_path / f"{view}.png").read_bytes()
        selected.add(pair.oblique_view)
    assert selected == set(assets.OBLIQUE_VIEWS)


@pytest.mark.parametrize("change", ["scenario", "vendor", "mixed", "profile", "shape", "corrupt", "missing", "unreleased"])
def test_uncovered_or_damaged_assets_fall_back(tmp_path, change):
    ctx, a = make_assets(tmp_path)
    profile = US_NFPA_OIL
    if change == "scenario": ctx.scenario_id = "cabinet_only"
    if change == "vendor": ctx.ac_output = {"ac_block_product_block_code": "OTHER-VENDOR"}
    if change == "mixed": ctx.ac_output = {"ac_block_mixed": True}
    if change == "profile": profile = replace(profile, dc_pair_gap_m=0.6)
    if change == "shape": a = render_typical_ac_block(AcBlockShape(6,4,5))
    if change == "corrupt": (tmp_path / "NW.png").write_bytes(b"bad")
    if change == "missing": (tmp_path / "NE.png").unlink()
    if change == "unreleased":
        path = tmp_path / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["templates"][0]["released"] = False
        path.write_text(json.dumps(manifest), encoding="utf-8")
    assert assets.select_render_pair(ctx, a, profile, root=tmp_path) is None


@pytest.mark.parametrize("power", [2.0, 4.0, 5.0])
def test_visual_matching_ignores_power_with_same_cabinet_and_layout(tmp_path, power):
    ctx, _ = make_assets(tmp_path, n=2, pcs=2, power=2.5)
    ctx.dc_block_unit_mwh = 6.26  # Capacity is not a visual-template selector.
    arrangement = render_typical_ac_block(AcBlockShape(2, 2, power))
    before_ctx, before_arrangement = deepcopy(ctx), deepcopy(arrangement)
    assert assets.select_render_pair(ctx, arrangement, US_NFPA_OIL, root=tmp_path)
    assert ctx == before_ctx
    assert arrangement == before_arrangement
    longer = render_typical_ac_block(AcBlockShape(2, 8, 10))
    assert assets.select_render_pair(ctx, longer, US_NFPA_OIL, root=tmp_path) is None


def test_report_replaces_typical_only_and_carries_selected_view(tmp_path, monkeypatch):
    make_assets(tmp_path)
    monkeypatch.setattr(assets, "ASSET_ROOT", tmp_path)
    monkeypatch.setattr(assets.secrets, "choice", lambda _: "NE")
    ctx = build_report_context({}, {
        "stage13_output": dict(project_name="Render integration", poi_power_req_mw=10,
            poi_energy_req_mwh=40, project_life_years=20, cycles_per_year=365, poi_guarantee_year=0),
        "stage2": {"container_count":8},
        "ac_output": dict(num_blocks=2, pcs_per_block=4, pcs_kw=1250,
                          block_size_mw=5, dc_blocks_per_ac=4, dc_blocks_total=8,
                          pcs_count_total=8, total_ac_mw=10),
    }, {})
    ctx.dc_block_unit_mwh = 5.016
    doc = Document(io.BytesIO(report_v2.export_report_v2_1(ctx)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Top view" in text and "NE oblique view" in text
    assert "Rule-based typical arrangement" not in text
    assert "9." in text and "Concept Site" in text
    xml = doc._element.xml
    assert "TEST test.1 TOP" in xml and "TEST test.1 NE" in xml
    assert "NOT FOR CONSTRUCTION" in text


@pytest.mark.parametrize("key,n,pcs,power", [
    ("T1", 8, 8, 8), ("T2", 4, 2, 4),
    ("T3", 2, 2, 2), ("T4", 4, 8, 8),
])
def test_packaged_templates_match_resolved_geometry(key, n, pcs, power):
    """Exercise the shipped manifest and all five image hashes, not a fixture library."""
    ctx = SimpleNamespace(scenario_id="container_only", dc_block_unit_mwh=6.26,
                          ac_output={}, configuration_code=None)
    arrangement = render_typical_ac_block(AcBlockShape(n, pcs, power))
    pair = assets.select_render_pair(ctx, arrangement, US_NFPA_OIL, choose=lambda _: "SW")
    assert pair is not None and pair.template_id == key
    assert Image.open(io.BytesIO(pair.top_png)).size == (1536, 1024)
    assert Image.open(io.BytesIO(pair.oblique_png)).size == (1536, 1024)


def test_40ft_eight_dc_linear_layout_does_not_use_central_image(tmp_path):
    ctx, _ = make_assets(tmp_path, n=8, pcs=8, power=10)
    linear = render_typical_ac_block(AcBlockShape(8, 4, 10))
    assert not linear.uses_central_station
    assert assets.select_render_pair(ctx, linear, US_NFPA_OIL, root=tmp_path) is None
