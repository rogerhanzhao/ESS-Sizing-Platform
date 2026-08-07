from __future__ import annotations

from dataclasses import asdict

from calb_diagrams.specs import build_sld_group_spec, build_sld_group_spec_from_topology
from calb_sizing_tool.services.sld_topology_builder import build_legacy_sld_topology
import pytest


def _legacy_payload():
    stage13_output = {
        "project_name": "Legacy Builder Test",
        "poi_nominal_voltage_kv": 33.0,
        "poi_frequency_hz": 50.0,
        "dc_block_total_qty": 6,
    }
    ac_output = {
        "num_blocks": 1,
        "pcs_per_block": 4,
        "grid_kv": 33.0,
        "inverter_lv_v": 690.0,
        "block_size_mw": 5.0,
        "pcs_power_kw": 1250.0,
        "pcs_count_by_block": [4],
        "dc_blocks_total_by_block": [6],
        "dc_blocks_per_feeder_by_block": [[2, 1, 2, 1]],
        "dc_allocation_plan": [
            {"ac_block_index": 1, "dc_blocks_total": 6, "feeder_allocations": [2, 1, 2, 1]}
        ],
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
        "lv_busbar": {"rated_a": 6300.0, "short_circuit_ka": 25.0},
        "cables": {"mv_cable_spec": "TBD", "lv_cable_spec": "TBD", "dc_cable_spec": "TBD"},
        "dc_fuse": {"fuse_spec": "DC isolator/fuse"},
    }
    return stage13_output, ac_output, {}, sld_inputs


def test_legacy_builders_route_through_authoritative_topology():
    stage13_output, ac_output, dc_summary, sld_inputs = _legacy_payload()

    topology = build_legacy_sld_topology(stage13_output, ac_output, dc_summary, sld_inputs, group_index=1)
    wrapped_spec = build_sld_group_spec(stage13_output, ac_output, dc_summary, sld_inputs, group_index=1)
    direct_spec = build_sld_group_spec_from_topology(topology)

    # The contract that still matters: the legacy wrapper and the authoritative
    # topology path must produce the SAME spec, so nothing renders differently
    # depending on which door it came through.
    #
    # This also checked build_ac_block_group_spec and build_single_unit_snapshot
    # against the same topology; both belonged to the IIDM stack retired
    # 2026-08-06.
    assert asdict(wrapped_spec) == asdict(direct_spec)


def test_legacy_builders_are_marked_compatibility_only():
    """The two IIDM-stack builders this also checked were retired 2026-08-06.

    build_sld_group_spec is the one that survives, because it is still reachable
    from calb_diagrams; the marking matters so nobody mistakes it for the
    authoritative path.
    """
    assert "LEGACY" in (build_sld_group_spec.__doc__ or "")


def test_legacy_builders_do_not_guess_missing_feeder_allocation():
    stage13_output, ac_output, dc_summary, sld_inputs = _legacy_payload()
    ac_output.pop("dc_blocks_per_feeder_by_block", None)
    ac_output.pop("dc_blocks_total_by_block", None)
    ac_output.pop("dc_allocation_plan", None)
    sld_inputs.pop("dc_blocks_per_feeder", None)

    with pytest.raises(ValueError, match="dc_allocation_plan is required"):
        build_legacy_sld_topology(stage13_output, ac_output, dc_summary, sld_inputs, group_index=1)
