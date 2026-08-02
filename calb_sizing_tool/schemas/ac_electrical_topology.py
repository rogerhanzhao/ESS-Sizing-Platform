from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator

from calb_sizing_tool.common.allocation import evenly_distribute
from calb_sizing_tool.schemas.common import CanonicalBaseModel


TransformerTopology = Literal["two_winding", "three_winding"]

# ELECTRICAL RULE (owner correction, 2026-08-02): different PCS must NEVER share a
# DC busbar. A DC Block is by design built with TWO INDEPENDENT DC circuits
# ("segregated"); those two circuits may feed two different PCS, but only PCS
# inside the SAME AC Block. "common" therefore means one internal DC busbar and is
# only admissible when the block serves a single PCS.
#
# The "common busbar" wording never described the DC Block: it describes the DC
# BUSBAR UNDER ONE PCS, which has several ports so that ONE PCS can take SEVERAL
# DC Blocks. That is a PCS-side busbar, not a DC-Block-side one.
DcInternalBusbarMode = Literal["common", "segregated"]
DEFAULT_DC_BLOCK_INTERNAL_MODE: DcInternalBusbarMode = "segregated"
DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS = 2


def build_dc_block_connection_plan(
    dc_blocks_total: int,
    pcs_count: int,
    *,
    output_circuit_count: int = DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS,
) -> list[dict]:
    """Build the physical DC Block output-circuit to PCS-feeder mapping.

    This remains deliberately independent of the AC sizing service, so the
    adapter and SLD layers can consume the same topology contract without
    importing service-package side effects.

    The plan is built for ONE AC Block, and ``pcs_count`` is that AC Block's own
    feeder count — so every connection returned here necessarily references only
    PCS inside this AC Block. That is the rule a DC Block's two independent DC
    circuits must respect: they may feed two different PCS, but never PCS in a
    different AC Block, and never through a shared DC busbar.
    """
    blocks = int(dc_blocks_total or 0)
    feeders = int(pcs_count or 0)
    outputs = int(output_circuit_count or 0)
    if blocks <= 0 or feeders <= 0:
        return []
    if outputs not in (1, 2):
        raise ValueError("DC Block output_circuit_count must be 1 or 2")
    if blocks * outputs < feeders:
        raise ValueError(
            f"{blocks} DC Block(s) with {outputs} output circuit(s) each cannot supply "
            f"all {feeders} PCS feeders"
        )

    def _guard_same_ac_block(built: list[dict]) -> list[dict]:
        """Every referenced feeder must belong to THIS AC Block's feeder range."""
        for connection in built:
            outside = [f for f in connection["feeder_indices"] if not 1 <= int(f) <= feeders]
            if outside:
                raise ValueError(
                    f"DC Block {connection['dc_block_index']} feeds PCS feeder(s) {outside} "
                    f"outside this AC Block (1..{feeders}); a DC Block may only feed PCS "
                    f"within the same AC Block"
                )
        return built

    connections: list[dict] = []
    if blocks <= feeders:
        cursor = 1
        for block_index, span_size in enumerate(evenly_distribute(feeders, blocks), start=1):
            feeder_indices = list(range(cursor, cursor + span_size))
            cursor += span_size
            connections.append(
                {
                    "dc_block_index": block_index,
                    "feeder_indices": feeder_indices,
                    "output_circuit_count": outputs,
                    "internal_dc_busbar_mode": DEFAULT_DC_BLOCK_INTERNAL_MODE,
                }
            )
        return _guard_same_ac_block(connections)

    block_index = 1
    for feeder_index, count in enumerate(evenly_distribute(blocks, feeders), start=1):
        for _ in range(count):
            connections.append(
                {
                    "dc_block_index": block_index,
                    "feeder_indices": [feeder_index],
                    "output_circuit_count": outputs,
                    "internal_dc_busbar_mode": DEFAULT_DC_BLOCK_INTERNAL_MODE,
                }
            )
            block_index += 1
    return _guard_same_ac_block(connections)


class DcBlockConnection(CanonicalBaseModel):
    """Physical DC Block output circuits connected to PCS feeder(s).

    A DC Block is built with TWO INDEPENDENT DC circuits ("segregated"). Those two
    circuits may feed two different PCS — but only PCS inside the SAME AC Block,
    and never through a shared DC busbar: different PCS must never be tied
    together on the DC side. A "common" internal busbar is therefore only
    admissible when the block serves a single PCS.
    """

    dc_block_index: int
    feeder_indices: list[int]
    output_circuit_count: int
    internal_dc_busbar_mode: DcInternalBusbarMode = DEFAULT_DC_BLOCK_INTERNAL_MODE

    @field_validator("dc_block_index", "output_circuit_count")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("value must be > 0")
        return int(value)

    @field_validator("feeder_indices")
    @classmethod
    def _positive_unique_feeders(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("feeder_indices must be non-empty")
        normalized = [int(item) for item in value]
        if any(item <= 0 for item in normalized):
            raise ValueError("feeder_indices must be > 0")
        if len(set(normalized)) != len(normalized):
            raise ValueError("feeder_indices must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_output_capacity(self) -> "DcBlockConnection":
        if len(self.feeder_indices) > self.output_circuit_count:
            raise ValueError("connected PCS feeders exceed DC Block output_circuit_count")
        # Different PCS must NEVER share a DC busbar. A block that feeds more than
        # one PCS must therefore keep its DC circuits segregated.
        if len(self.feeder_indices) > 1 and self.internal_dc_busbar_mode == "common":
            raise ValueError(
                "a DC Block feeding several PCS must be 'segregated': different PCS "
                "must never share a DC busbar"
            )
        return self
