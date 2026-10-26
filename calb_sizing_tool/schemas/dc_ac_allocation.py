"""Explicit, comparison-only DC-to-AC connectivity declarations.

Capability references identify supplied records. They do not certify those
records, approve equipment, or extend the existing AC sizing/diagram contract.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


MAX_ALLOCATION_ITEMS = 10_000  # Memory guard, not an engineering grouping limit.


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must contain a non-whitespace character")
    return value


StableId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,95}$"),
]
Sha256 = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-fA-F0-9]{64}$"),
]
NonEmptyText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1),
    AfterValidator(_nonblank),
]


class _AllocationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class AllocationSource(_AllocationModel):
    dc_manifest_sha256: Sha256
    candidate_comparison_sha256: Sha256


class CapabilityReference(_AllocationModel):
    """Unverified package identity; mere presence never grants approval."""

    package_code: NonEmptyText
    revision: NonEmptyText
    sha256: Sha256
    evidence_ref: NonEmptyText


class AcBlock(_AllocationModel):
    ac_block_id: StableId


class PcsInstance(_AllocationModel):
    pcs_id: StableId
    ac_block_id: StableId
    capability_ref: CapabilityReference | None = None
    parallel_applicability_ref: NonEmptyText | None = None


class PcsInputPort(_AllocationModel):
    pcs_id: StableId
    port_id: StableId
    dc_bus_id: StableId


class TransformerInstance(_AllocationModel):
    transformer_id: StableId
    ac_block_id: StableId
    capability_ref: CapabilityReference | None = None


class LvWinding(_AllocationModel):
    transformer_id: StableId
    winding_id: StableId
    lv_bus_id: StableId


class PhysicalUnitAssignment(_AllocationModel):
    unit_id: StableId
    ac_block_id: StableId


class DcDomainConnection(_AllocationModel):
    domain_id: StableId
    pcs_id: StableId
    port_id: StableId


class PcsLvConnection(_AllocationModel):
    pcs_id: StableId
    transformer_id: StableId
    winding_id: StableId


class DcAcAllocation(_AllocationModel):
    """Declared identities and connections; no inferred ratios or ratings."""

    contract_type: Literal["dc_ac_allocation_v1"] = "dc_ac_allocation_v1"
    schema_version: Literal[1] = 1
    source: AllocationSource
    ac_blocks: list[AcBlock] = Field(max_length=MAX_ALLOCATION_ITEMS)
    pcs_instances: list[PcsInstance] = Field(max_length=MAX_ALLOCATION_ITEMS)
    input_ports: list[PcsInputPort] = Field(max_length=MAX_ALLOCATION_ITEMS)
    transformer_instances: list[TransformerInstance] = Field(max_length=MAX_ALLOCATION_ITEMS)
    lv_windings: list[LvWinding] = Field(max_length=MAX_ALLOCATION_ITEMS)
    unit_assignments: list[PhysicalUnitAssignment] = Field(max_length=MAX_ALLOCATION_ITEMS)
    dc_connections: list[DcDomainConnection] = Field(max_length=MAX_ALLOCATION_ITEMS)
    lv_connections: list[PcsLvConnection] = Field(max_length=MAX_ALLOCATION_ITEMS)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_version(cls, value: object) -> object:
        # Literal[1] alone also accepts True and 1.0 in Pydantic.
        if type(value) is not int:
            raise ValueError("schema_version must be the integer 1")
        return value


__all__ = [
    "MAX_ALLOCATION_ITEMS",
    "AcBlock",
    "AllocationSource",
    "CapabilityReference",
    "DcAcAllocation",
    "DcDomainConnection",
    "LvWinding",
    "PcsInputPort",
    "PcsInstance",
    "PcsLvConnection",
    "PhysicalUnitAssignment",
    "TransformerInstance",
]
