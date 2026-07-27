from __future__ import annotations

from dataclasses import asdict

import pytest

from calb_diagrams.sld_layout_engine import build_sld_layout_plan
from calb_sizing_tool.schemas.diagram_inputs import SldRenderOptions
from calb_sizing_tool.schemas.sld_render_input import SldInputOverride, legacy_sld_override_preset
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
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


def _build_single_winding_topology(sample_excel_path):
    run_bundle = _build_run_bundle(sample_excel_path)
    ac_snapshot = _make_ac_snapshot()
    ac_output = dict(ac_snapshot.output)
    ac_output.update(
        {
            "pcs_per_block": 2,
            "pcs_kw": 2500.0,
            "block_size_mw": 5.0,
            "transformer_mva": 5.0,
            "dc_allocation_plan": [
                {"ac_block_index": 1, "dc_blocks_total": 2, "feeder_allocations": [1, 1]}
            ],
        }
    )
    override_payload = legacy_sld_override_preset()
    override_payload["dc_block_voltage_v"] = 1500.0
    override_payload["dc_blocks_per_feeder"] = [1, 1]
    canonical = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot.model_copy(update={"output": ac_output}),
        options=SldRenderOptions(
            group_index=1,
            override_mode=True,
            overrides=SldInputOverride.model_validate(override_payload),
        ),
        validation_mode="strict",
    )
    return build_sld_topology(canonical)


def test_layout_engine_rejects_split_secondary_topology(sample_excel_path):
    with pytest.raises(ValueError, match="Topology V1 cannot render independent LV transformer windings"):
        build_sld_layout_plan(
            _build_topology(sample_excel_path),
            layout_profile="engineering_readable",
            theme="dark",
        )


def test_layout_engine_is_stable_for_same_topology(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
    plan_a = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")
    plan_b = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    assert asdict(plan_a) == asdict(plan_b)


def test_layout_engine_profiles_are_distinct(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
    engineering = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")
    compact = build_sld_layout_plan(topology, layout_profile="compact", theme="dark")

    assert engineering.layout_profile == "engineering_readable"
    assert compact.layout_profile == "compact"
    assert engineering.width != compact.width
    assert any(symbol.symbol_type == "dc_interface" for symbol in engineering.symbols)
    assert any(symbol.symbol_type == "dc_interface" for symbol in compact.symbols)


def test_layout_engine_keeps_dc_blocks_in_matching_feeder_columns(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
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

    assert sorted(pcs_centers) == [1, 2]
    assert sorted(dc_centers) == [1, 2]
    for feeder_index, pcs_center in pcs_centers.items():
        assert abs(dc_centers[feeder_index] - pcs_center) < 40.0


def test_layout_engine_uses_vertical_feeder_taps(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
    plan = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    lv_to_pcs = [connector for connector in plan.connectors if "EDGE-LVBUS-PCS" in connector.connector_id]
    pcs_to_dc = [connector for connector in plan.connectors if "EDGE-PCS-DCIF" in connector.connector_id]
    dc_to_block = [connector for connector in plan.connectors if "DC-BLOCK-" in connector.connector_id and "-EDGE" in connector.connector_id]

    assert len(lv_to_pcs) == 2
    assert len(pcs_to_dc) == 2
    assert len(dc_to_block) == 2
    assert all(abs(connector.points[0][0] - connector.points[1][0]) < 1e-6 for connector in lv_to_pcs)
    assert all(abs(connector.points[0][0] - connector.points[1][0]) < 1e-6 for connector in pcs_to_dc)
    assert all(abs(connector.points[0][0] - connector.points[-1][0]) < 1e-6 for connector in dc_to_block)


def test_layout_engine_keeps_pcs_inside_ac_frame_and_battery_frame_below(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
    plan = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    ac_frame = next(symbol for symbol in plan.symbols if symbol.symbol_id == "ac-frame")
    battery_frame = next(symbol for symbol in plan.symbols if symbol.symbol_id == "battery-frame")
    pcs_symbols = [symbol for symbol in plan.symbols if symbol.symbol_type == "pcs"]

    assert pcs_symbols
    for pcs in pcs_symbols:
        assert pcs.y >= ac_frame.y
        assert pcs.y + pcs.height <= ac_frame.y + ac_frame.height
        assert pcs.y + pcs.height < battery_frame.y


def test_layout_engine_uses_dc_interface_instead_of_floating_dc_busbars(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
    plan = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    dc_interfaces = [symbol for symbol in plan.symbols if symbol.symbol_type == "dc_interface"]

    assert dc_interfaces
    assert all(symbol.text_lines[0] == "DC Isolator/Fuse" for symbol in dc_interfaces)
    assert not any(symbol.symbol_type == "dc_busbar_single" for symbol in plan.symbols)
    assert not any(symbol.symbol_type == "dc_busbar_pair" for symbol in plan.symbols)


def test_layout_engine_connects_pcs_and_dc_blocks_with_one_dc_line_per_feeder(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
    plan = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    dc_interfaces = {
        int(symbol.meta["feeder_index"]): symbol
        for symbol in plan.symbols
        if symbol.symbol_type == "dc_interface" and symbol.meta.get("feeder_index") is not None
    }
    pcs_to_dc = [connector for connector in plan.connectors if "EDGE-PCS-DCIF" in connector.connector_id]
    dc_to_block = [
        connector
        for connector in plan.connectors
        if "DC-BLOCK-" in connector.connector_id and "-EDGE" in connector.connector_id
    ]

    assert len(pcs_to_dc) == len(dc_interfaces)
    assert len(dc_to_block) == len(dc_interfaces)
    for connector in pcs_to_dc:
        feeder_index = int(connector.connector_id.split("-F")[1].split("-")[0])
        interface = dc_interfaces[feeder_index]
        assert connector.points[-1] == (interface.x + interface.width / 2, interface.y)

    for connector in dc_to_block:
        feeder_index = int(connector.connector_id.split("-F")[1].split("-")[0])
        interface = dc_interfaces[feeder_index]
        assert connector.points[0] == (interface.x + interface.width / 2, interface.y + interface.height)
        assert connector.points[-1][1] > interface.y


def test_layout_engine_uses_engineering_readable_mv_switchgear(sample_excel_path):
    topology = _build_single_winding_topology(sample_excel_path)
    plan = build_sld_layout_plan(topology, layout_profile="engineering_readable", theme="dark")

    switchgear = next(symbol for symbol in plan.symbols if symbol.symbol_id == "mv-switchgear")
    transformer_feeder = next(connector for connector in plan.connectors if connector.connector_id == "mv-transformer-feeder")

    assert switchgear.symbol_type == "mv_switchgear"
    assert switchgear.text_lines[1:4] == ("Ring In", "Transformer Feeder", "Ring Out")
    assert not any(symbol.symbol_id == "mv-busbar" for symbol in plan.symbols)
    assert any(symbol.anchor_node_id and symbol.anchor_node_id.endswith("MV-RING-IN") for symbol in plan.symbols)
    assert any(symbol.anchor_node_id and symbol.anchor_node_id.endswith("MV-RING-OUT") for symbol in plan.symbols)
    assert transformer_feeder.points[0][1] == switchgear.y + switchgear.height
