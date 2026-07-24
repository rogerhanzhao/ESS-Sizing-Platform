"""Regression: the old "4 PCS / 2 DC -> [1,1,0,0] with dangling PCS" defect.

Re-verified in THIS repository (not carried over from any QR2CARD session): an
AC Block with fewer DC Blocks than PCS feeders once produced a per-feeder count
of ``[1, 1, 0, 0]`` where two PCS feeders had no DC source, which is
electrically meaningless.

The fix lives entirely in the SLD contract/topology layer (physical DC Block
output-circuit mapping). No frozen DC/AC sizing formula is touched: a DC Block
with fewer units than feeders now spreads its protected output circuits across a
contiguous span of feeders so every PCS is sourced. This test locks that
behaviour at the contract layer, independent of the full render path covered by
``test_sld_shared_dc_blocks.py``.
"""
from __future__ import annotations

from calb_sizing_tool.adapters.ac_to_sld_adapter import normalize_ac_output_for_sld
from calb_sizing_tool.common.allocation import evenly_distribute
from calb_sizing_tool.schemas.ac_electrical_topology import build_dc_block_connection_plan


def test_legacy_even_distribution_still_produces_the_dangling_pattern():
    """Guard the root cause: the naive per-feeder split IS [1,1,0,0]."""
    # This is the historic (wrong) allocation the SLD must never render as-is.
    assert evenly_distribute(2, 4) == [1, 1, 0, 0]


def test_physical_connection_plan_sources_every_feeder():
    connections = build_dc_block_connection_plan(2, 4, output_circuit_count=2)
    # Two DC Blocks, each spreading across two contiguous feeders.
    assert [(c["dc_block_index"], c["feeder_indices"]) for c in connections] == [
        (1, [1, 2]),
        (2, [3, 4]),
    ]
    feeder_allocations = [
        sum(1 for c in connections if feeder_index in c["feeder_indices"])
        for feeder_index in range(1, 5)
    ]
    assert feeder_allocations == [1, 1, 1, 1]
    assert 0 not in feeder_allocations  # no dangling PCS feeder


def test_ac_to_sld_adapter_repairs_legacy_dangling_allocation():
    """A legacy payload carrying [1,1,0,0] is normalized to a fully sourced map."""
    ac_output = {
        "num_blocks": 1,
        "pcs_per_block": 4,
        "pcs_kw": 1250.0,
        "block_size_mw": 5.0,
        "transformer_mva": 6.0,
        "dc_allocation_plan": [
            {"ac_block_index": 1, "dc_blocks_total": 2, "feeder_allocations": [1, 1, 0, 0]}
        ],
    }
    normalized = normalize_ac_output_for_sld(ac_output)
    # The authoritative per-feeder mirror no longer contains dangling zeros.
    assert normalized.dc_blocks_per_feeder_by_block == [[1, 1, 1, 1]]
    connections = normalized.dc_block_connections_by_block[0]
    assert [(c.dc_block_index, c.feeder_indices) for c in connections] == [
        (1, [1, 2]),
        (2, [3, 4]),
    ]
    # Every PCS feeder is referenced by exactly one DC Block output branch.
    referenced = sorted(
        feeder_index
        for connection in connections
        for feeder_index in connection.feeder_indices
    )
    assert referenced == [1, 2, 3, 4]


def test_output_circuit_capacity_is_respected():
    """A DC Block cannot supply more feeders than it has output circuits."""
    import pytest

    # 1 DC Block with a single output circuit cannot feed 4 PCS.
    with pytest.raises(ValueError):
        build_dc_block_connection_plan(1, 4, output_circuit_count=1)
