"""The web page and the exported report must draw ONE arrangement.

Owner instruction 2026-08-03: "网页上 TYPICAL AC BLOCK arrangement 时的排布引擎也要
同步调整 … 摆放方式最好还是原来那套引擎的视角，要统一一下."

The page used to run the legacy grid renderer (2x2 / 1x4 / 4x1 presets, free-text
clearances, a fixed station) while the report ran the rule-based engine, so the
same AC Block was published with two different footprints. These tests lock the
page onto the report's engine.
"""
from __future__ import annotations

import pytest

from calb_diagrams.ac_block_bilateral_layout import (
    LAYOUT_VARIANT as BILATERAL_LAYOUT_VARIANT,
    compute_bilateral_layout,
)
from calb_sizing_tool.plugins.layout_arrangement_v2_plugin import LayoutArrangementV2Plugin
from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderInput, LayoutRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


def _render(ac_output: dict, block_index: int = 1) -> dict:
    plugin = LayoutArrangementV2Plugin()
    render_input = LayoutRenderInput.model_construct(
        run_id="run-1",
        run_bundle=DcRunBundle.model_construct(
            run_id="run-1", project_code="P", project_name="Proj",
            case_code="C", case_name="Case",
        ),
        ac_snapshot=AcSnapshot(inputs={}, output=ac_output, results={}),
        topology_snapshot=None,
        layout_rules=None,
        options=LayoutRenderOptions(block_index=block_index),
    )
    assert plugin.validate_input(render_input) == []
    return plugin.render(render_input)


_8PCS_8DC = {
    "num_blocks": 13, "pcs_per_block": 8, "pcs_kw": 1250.0, "block_size_mw": 10.0,
    "dc_allocation_plan": [{"ac_block_index": 1, "dc_blocks_total": 8}],
}
_4PCS_4DC = {
    "num_blocks": 10, "pcs_per_block": 4, "pcs_kw": 1250.0, "block_size_mw": 5.0,
    "dc_allocation_plan": [{"ac_block_index": 1, "dc_blocks_total": 4}],
}


def test_rule_based_plugin_is_the_page_default():
    registry = get_plugin_registry()
    plugins = registry.list_by_artifact("layout_svg")
    assert plugins, "no layout renderer registered"
    # The page offers plugins in registration order and selects index 0.
    assert plugins[0].metadata.plugin_id == "layout_arrangement_v2"
    # The legacy grid renderer stays available, just not as the default.
    assert registry.get("layout_engineering_v1") is not None


def test_layout_service_defaults_to_the_report_engine():
    import inspect

    from calb_sizing_tool.services.layout_service import render_layout_from_run_bundle

    default = inspect.signature(render_layout_from_run_bundle).parameters["plugin_id"].default
    assert default == "layout_arrangement_v2"


def test_eight_pcs_eight_dc_page_render_matches_the_report_geometry():
    out = _render(_8PCS_8DC)
    spec = out["spec"]
    governed = compute_bilateral_layout(8)
    assert spec["layout_variant"] == BILATERAL_LAYOUT_VARIANT
    assert spec["envelope_w_m"] == pytest.approx(governed.envelope_w_m, abs=0.001)
    assert spec["envelope_d_m"] == pytest.approx(governed.envelope_d_m, abs=0.001)
    # 8 PCS / 10 MW is the 40 ft product — never the 20 ft cabin.
    assert spec["station_length_m"] == pytest.approx(12.192, abs=0.001)
    assert len(spec["placements"]) == 9   # 8 DC + 1 station


def test_smaller_block_uses_the_linear_engine_with_its_own_station_class():
    spec = _render(_4PCS_4DC)["spec"]
    assert spec["layout_variant"] == "linear_mirrored_pairs"
    # 4 PCS / 5 MW is the 20 ft integrated cabin.
    assert spec["station_length_m"] == pytest.approx(6.058, abs=0.001)
    # 2 mirrored pairs + 0.9 m plain-end gap + 3.0 m aisle + 6.058 m cabin
    assert spec["envelope_w_m"] == pytest.approx(22.074, abs=0.001)


def test_spacing_is_rule_profile_and_never_page_settable():
    """Every clearance carries a code basis; the page cannot override any of it."""
    spec = _render(_8PCS_8DC)["spec"]
    assert spec["rule_profile_key"] == "us_nfpa_oil"
    clearances = spec["clearances_m"]
    assert clearances["dc_pair_gap"] == pytest.approx(0.30)
    assert clearances["dc_to_mv_aisle"] == pytest.approx(3.0)
    # Owner ruling 2026-08-03: the DC equipment end takes the AC Block aisle.
    assert clearances["dc_equipment_end"] == pytest.approx(3.0)
    assert spec["code_basis"] and all(
        entry["basis"] for entry in spec["code_basis"]
    )


def test_page_render_is_watermarked_and_emits_the_full_artifact_set():
    plugin = LayoutArrangementV2Plugin()
    out = _render(_8PCS_8DC)
    svg = out["svg_bytes"].decode("utf-8")
    assert "CONCEPT ONLY - NOT FOR CONSTRUCTION" in svg
    assert svg.endswith("</svg>")
    assert out["metadata"]["not_for_construction"] is True

    kinds = {a.artifact_kind for a in plugin.emit_artifact(out)}
    assert kinds == {
        "layout_spec_json",
        "layout_svg",
        "layout_png",
        "layout_metadata_json",
        "layout_master_readiness_manifest_json",
    }


def test_tail_block_power_comes_from_its_own_pcs_count_not_the_fleet_nominal():
    """A tail AC Block with fewer PCS is a smaller block and a smaller station."""
    ac_output = {
        "num_blocks": 2,
        "pcs_per_block": 8,
        "pcs_kw": 1250.0,
        "block_size_mw": 10.0,           # fleet nominal — NOT the tail's power
        "pcs_count_by_block": [8, 3],
        "dc_allocation_plan": [
            {"ac_block_index": 1, "dc_blocks_total": 8},
            {"ac_block_index": 2, "dc_blocks_total": 3},
        ],
    }
    tail = _render(ac_output, block_index=2)["spec"]
    assert tail["pcs_count"] == 3
    assert tail["block_power_mw"] == pytest.approx(3.75, abs=0.001)
    assert tail["layout_variant"] == "linear_mirrored_pairs"
    assert tail["station_length_m"] == pytest.approx(6.058, abs=0.001)


def test_missing_dc_count_fails_closed():
    with pytest.raises(RuntimeError, match="no DC Block count"):
        _render({"num_blocks": 1, "pcs_per_block": 4, "pcs_kw": 1250.0})
