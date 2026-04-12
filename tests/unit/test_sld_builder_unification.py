from __future__ import annotations

from dataclasses import asdict

from calb_diagrams.specs import build_sld_group_spec, build_sld_group_spec_from_topology
from calb_sizing_tool.services.sld_topology_builder import build_legacy_sld_topology
from calb_sizing_tool.sld.ac_block_group import build_ac_block_group_spec
from calb_sizing_tool.sld.snapshot_single_unit import build_single_unit_snapshot


def _legacy_payload():
    stage13_output = {
        "project_name": "Legacy Builder Test",
        "poi_nominal_voltage_kv": 33.0,
        "poi_frequency_hz": 50.0,
        "dc_block_total_qty": 6,
    }
    ac_output = {
        "num_blocks": 1,
        "grid_kv": 33.0,
        "inverter_lv_v": 690.0,
        "block_size_mw": 5.0,
        "pcs_power_kw": 1250.0,
        "pcs_count_by_block": [4],
        "dc_blocks_total_by_block": [6],
        "dc_blocks_per_feeder_by_block": [[2, 1, 2, 1]],
        "transformer_mva": 5.0,
    }
    sld_inputs = {
        "mv_nominal_kv_ac": 33.0,
        "pcs_lv_voltage_v_ll": 690.0,
        "transformer_rating_mva": 5.0,
        "pcs_rating_each_kw": 1250.0,
        "dc_block_energy_mwh": 5.106,
        "dc_blocks_per_feeder": [2, 1, 2, 1],
        "dc_block_voltage_v": 1500.0,
        "mv_labels": {"to_switchgear": "To Switchgear", "to_other_rmu": "To Other RMU"},
        "rmu": {"rated_kv": 36.0, "rated_a": 630.0, "short_circuit_ka_3s": 25.0, "ct_ratio": "200/1", "ct_class": "5P20", "ct_va": 10.0},
        "transformer": {"vector_group": "Dyn11", "uk_percent": 7.0, "cooling": "ONAN"},
        "lv_busbar": {"rated_a": 2500.0, "short_circuit_ka": 25.0},
        "cables": {"mv_cable_spec": "TBD", "lv_cable_spec": "TBD", "dc_cable_spec": "TBD"},
        "dc_fuse": {"fuse_spec": "TBD"},
    }
    return stage13_output, ac_output, {}, sld_inputs


def test_legacy_builders_route_through_authoritative_topology():
    stage13_output, ac_output, dc_summary, sld_inputs = _legacy_payload()

    topology = build_legacy_sld_topology(stage13_output, ac_output, dc_summary, sld_inputs, group_index=1)
    wrapped_spec = build_sld_group_spec(stage13_output, ac_output, dc_summary, sld_inputs, group_index=1)
    direct_spec = build_sld_group_spec_from_topology(topology)

    assert asdict(wrapped_spec) == asdict(direct_spec)

    group_spec = build_ac_block_group_spec(stage13_output, ac_output, dc_summary, sld_inputs, group_index=1)
    assert group_spec.group_index == topology.summary.group_index
    assert group_spec.pcs_count == topology.summary.pcs_count
    assert group_spec.dc_blocks_per_feeder == topology.summary.dc_blocks_per_feeder

    snapshot = build_single_unit_snapshot(stage13_output, ac_output, dc_summary, sld_inputs, scenario_id="legacy")
    assert snapshot["group_index"] == topology.summary.group_index
    assert snapshot["ac_block"]["pcs_count"] == topology.summary.pcs_count
    assert [entry["dc_block_count"] for entry in snapshot["dc_blocks_by_feeder"]] == topology.summary.dc_blocks_per_feeder


def test_legacy_builders_are_marked_compatibility_only():
    assert "LEGACY" in (build_sld_group_spec.__doc__ or "")
    assert "LEGACY" in (build_ac_block_group_spec.__doc__ or "")
    assert "LEGACY" in (build_single_unit_snapshot.__doc__ or "")
