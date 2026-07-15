from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator

from calb_sizing_tool.common.allocation import evenly_distribute
from calb_sizing_tool.schemas.common import CanonicalBaseModel


TransformerTopology = Literal["two_winding", "three_winding"]
DcInternalBusbarMode = Literal["common", "segregated"]
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
                    "internal_dc_busbar_mode": "common",
                }
            )
        return connections

    block_index = 1
    for feeder_index, count in enumerate(evenly_distribute(blocks, feeders), start=1):
        for _ in range(count):
            connections.append(
                {
                    "dc_block_index": block_index,
                    "feeder_indices": [feeder_index],
                    "output_circuit_count": outputs,
                    "internal_dc_busbar_mode": "common",
                }
            )
            block_index += 1
    return connections


class DcBlockConnection(CanonicalBaseModel):
    """Physical DC Block output circuits connected to PCS feeder(s).

    A DC Block may expose one or two protected outputs from one common internal
    DC busbar.  The outputs remain separate once they leave the DC Block.
    """

    dc_block_index: int
    feeder_indices: list[int]
    output_circuit_count: int
    internal_dc_busbar_mode: DcInternalBusbarMode = "common"

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
        return self
