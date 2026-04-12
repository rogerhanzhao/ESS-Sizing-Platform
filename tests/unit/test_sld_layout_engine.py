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


def test_layout_engine_keeps_dc_blocks_in_matching_feeder_columns(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    plan = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    pcs_centers = {
        int(symbol.meta["feeder_index"]): symbol.x + symbol.width / 2
        for symbol in plan.symbols
        if symbol.symbol_type == "pcs" and symbol.meta.get("feeder_index") is not None
    }
    dc_centers = {
        int(symbol.meta["feeder_index"]): symbol.x + symbol.width / 2
        for symbol in plan.symbols
        if symbol.symbol_type == "dc_block" and symbol.meta.get("feeder_index") is not None
    }

    assert sorted(pcs_centers) == [1, 2, 3, 4]
    assert sorted(dc_centers) == [1, 2, 3, 4]
    for feeder_index, pcs_center in pcs_centers.items():
        assert abs(dc_centers[feeder_index] - pcs_center) < 40.0


def test_layout_engine_uses_vertical_feeder_taps(sample_excel_path):
    topology = _build_topology(sample_excel_path)
    plan = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    lv_to_pcs = [connector for connector in plan.connectors if "EDGE-LVBUS-PCS" in connector.connector_id]
    pcs_to_dc = [connector for connector in plan.connectors if "EDGE-PCS-DCBUS" in connector.connector_id]
    dc_to_block = [connector for connector in plan.connectors if "DC-BLOCK-" in connector.connector_id and connector.connector_id.endswith("-EDGE")]

    assert len(lv_to_pcs) == 4
    assert len(pcs_to_dc) == 4
    assert len(dc_to_block) == 4
    assert all(abs(connector.points[0][0] - connector.points[1][0]) < 1e-6 for connector in lv_to_pcs)
    assert all(abs(connector.points[0][0] - connector.points[1][0]) < 1e-6 for connector in pcs_to_dc)
    assert all(abs(connector.points[0][0] - connector.points[1][0]) < 1e-6 for connector in dc_to_block)
