from __future__ import annotations

from dataclasses import asdict

from calb_diagrams.sld_layout_engine import build_sld_layout_plan
from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology
from tests.unit.test_sld_topology_builder import _build_run_bundle, _make_ac_snapshot


def _build_topology(sample_excel_path):
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
    return build_sld_topology(canonical)


def test_layout_engine_is_stable_for_same_topology(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    plan_a = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")
    plan_b = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    assert asdict(plan_a) == asdict(plan_b)


def test_layout_engine_profiles_are_distinct(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    engineering = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")
    compact = build_sld_layout_plan(topology, layout_profile="compact", theme="dark")

    assert engineering.layout_profile == "engineering_readable"
    assert compact.layout_profile == "compact"
    assert engineering.width != compact.width
    assert any(symbol.symbol_type == "dc_busbar_pair" for symbol in engineering.symbols)
    assert any(symbol.symbol_type == "dc_busbar_single" for symbol in compact.symbols)
