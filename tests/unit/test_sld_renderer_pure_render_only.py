from __future__ import annotations

import inspect

import pytest

pytest.importorskip("svgwrite")

from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_engineering_v2_renderer import render_sld_engineering_v2_svg
from calb_diagrams.sld_pro_renderer import render_sld_pro_svg
from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
from tests.unit.test_sld_topology_builder import _build_run_bundle, _make_ac_snapshot


def _build_topology(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    override_payload = legacy_sld_override_preset()
    override_payload["transformer_vector_group"] = "Dyn11yn11"
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
    return build_sld_topology(canonical)


def test_renderer_only_consumes_topology_contract(sample_excel_path, tmp_path):
    topology = _build_topology(sample_excel_path)
    svg_path = tmp_path / "pure_topology.svg"

    plan = build_sld_engineering_v2_layout_plan(build_sld_engineering_v2_graph(topology), theme="dark")
    result_path, warning = render_sld_engineering_v2_svg(plan, svg_path)

    assert result_path == svg_path
    assert warning is None
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "PCS &amp; MVT SKID (AC BLOCK)" in svg_text
    assert "BESS-01" in svg_text  # battery bank identified by per-block tags
    assert "RMU-01  /  MV Switchgear" in svg_text
    assert "Transformer Feeder" in svg_text
    assert "F-01" in svg_text
    assert "DC BUSBAR" not in svg_text


def test_renderer_source_does_not_reference_legacy_runtime_inputs():
    source = inspect.getsource(render_sld_engineering_v2_svg)
    assert "ac_output" not in source
    assert "stage13_output" not in source
    assert "session_state" not in source
    assert "st.session_state" not in source

    compat_source = inspect.getsource(render_sld_pro_svg)
    assert "render_sld_svg" in compat_source
