"""Typed equipment declarations for local DC-to-AC capability comparison.

These records preserve supplied values and explicit unknowns. They do not grant
approval, infer ratings, or replace the frozen AC sizing/electrical contract.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from typing_extensions import Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)


MAX_CAPABILITY_ITEMS = 10_000  # A memory guard, not a grouping design limit.


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must contain a non-whitespace character")
    return value


def _finite_number(value: object) -> object:
    # Reject strings, bools and numeric coercions before Pydantic's conversion.
    if type(value) not in (int, float):
        raise ValueError("A finite integer or floating-point number is required")
    try:
        finite = math.isfinite(value)
    except (OverflowError, ValueError):
        finite = False
    if not finite:
        raise ValueError("A finite, representable number is required")
    return value


StableId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,95}$"),
]
Sha256 = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$"),
]
NonEmptyText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=2_000),
    AfterValidator(_nonblank),
]
PackageCode = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=128),
    AfterValidator(_nonblank),
]
PackageRevision = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=64),
    AfterValidator(_nonblank),
]
FiniteFloat = Annotated[float, BeforeValidator(_finite_number)]
PositiveFloat = Annotated[FiniteFloat, Field(gt=0)]
PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]


class _CapabilityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, allow_inf_nan=False, validate_default=True
    )


def _ordered_range(
    lower: float | None, upper: float | None, *, name: str, exclusive: bool = False
) -> None:
    if lower is not None and upper is not None:
        if lower > upper or (exclusive and lower == upper):
            operator = "less than" if exclusive else "less than or equal to"
            raise ValueError(f"{name} minimum must be {operator} its maximum")


def _require_unique(values: list[str], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")


class CapabilityConditions(_CapabilityModel):
    temperature_min_c: FiniteFloat | None = None
    temperature_max_c: FiniteFloat | None = None
    frequency_hz: PositiveFloat | None = None

    @model_validator(mode="after")
    def _temperature_order(self) -> Self:
        _ordered_range(
            self.temperature_min_c, self.temperature_max_c, name="Temperature"
        )
        return self


class DischargeDutyBasis(_CapabilityModel):
    """One declared discharge condition; no default unity power factor."""

    ambient_temperature_c: FiniteFloat | None = None
    power_factor_abs: Annotated[PositiveFloat, Field(le=1)] | None = None
    mv_bus_voltage_kv: PositiveFloat | None = None
    passive_dc_path_confirmed: StrictBool = False
    evidence_ref: NonEmptyText | None = None


class PcsPortCapability(_CapabilityModel):
    port_id: StableId
    dc_bus_group: StableId
    voltage_min_v: PositiveFloat | None = None
    voltage_max_v: PositiveFloat | None = None
    continuous_current_a: PositiveFloat | None = None
    discharge_power_kw: PositiveFloat | None = None

    @model_validator(mode="after")
    def _voltage_order(self) -> Self:
        _ordered_range(
            self.voltage_min_v, self.voltage_max_v, name="Port voltage", exclusive=True
        )
        return self


class PcsBusCapability(_CapabilityModel):
    dc_bus_group: StableId
    max_parallel_domains: PositiveStrictInt | None = None
    compatible_revision_sha256: list[Sha256] = Field(
        default_factory=list, max_length=MAX_CAPABILITY_ITEMS
    )
    compatible_output_partition_sha256: list[Sha256] = Field(
        default_factory=list, max_length=MAX_CAPABILITY_ITEMS
    )
    parallel_evidence_ref: NonEmptyText | None = None

    @field_validator("max_parallel_domains", mode="before")
    @classmethod
    def _representable_parallel_count(cls, value: object) -> object:
        if value is not None:
            # Keep the public strict integer type; reject unrepresentable JSON
            # counts with a ValidationError instead of leaking OverflowError.
            _finite_number(value)
        return value

    @field_validator("compatible_revision_sha256", "compatible_output_partition_sha256")
    @classmethod
    def _unique_revisions(cls, value: list[str]) -> list[str]:
        _require_unique(value, "Compatible revision hashes")
        return value


class PcsCapability(_CapabilityModel):
    dc_voltage_min_v: PositiveFloat | None = None
    dc_voltage_max_v: PositiveFloat | None = None
    continuous_dc_current_a: PositiveFloat | None = None
    dc_discharge_power_kw: PositiveFloat | None = None
    ac_discharge_power_kw: PositiveFloat | None = None
    ac_apparent_power_kva: PositiveFloat | None = None
    ac_voltage_v: PositiveFloat | None = None
    aggregate_current_basis: Literal["sum_of_port_currents"] | None = None
    ports: list[PcsPortCapability] = Field(min_length=1, max_length=MAX_CAPABILITY_ITEMS)
    dc_buses: list[PcsBusCapability] = Field(min_length=1, max_length=MAX_CAPABILITY_ITEMS)

    @model_validator(mode="after")
    def _voltage_and_bus_references(self) -> Self:
        _ordered_range(
            self.dc_voltage_min_v,
            self.dc_voltage_max_v,
            name="PCS DC voltage",
            exclusive=True,
        )
        if (self.ac_discharge_power_kw is not None and self.ac_apparent_power_kva is not None
                and self.ac_discharge_power_kw > self.ac_apparent_power_kva):
            raise ValueError("PCS active power cannot exceed apparent power under the same rating conditions")
        _require_unique([port.port_id for port in self.ports], "PCS port IDs")
        groups = [bus.dc_bus_group for bus in self.dc_buses]
        _require_unique(groups, "PCS DC bus groups")
        used_groups = {port.dc_bus_group for port in self.ports}
        if used_groups != set(groups):
            raise ValueError("PCS ports must reference every declared DC bus group exactly by identity")
        return self


class LvWindingCapability(_CapabilityModel):
    winding_id: StableId
    voltage_v: PositiveFloat | None = None
    continuous_kva: PositiveFloat | None = None


class TransformerCapability(_CapabilityModel):
    total_kva: PositiveFloat | None = None
    hv_voltage_kv: PositiveFloat | None = None
    vector_group: NonEmptyText | None = None
    windings: list[LvWindingCapability] = Field(
        min_length=1, max_length=MAX_CAPABILITY_ITEMS
    )

    @model_validator(mode="after")
    def _unique_windings(self) -> Self:
        _require_unique([winding.winding_id for winding in self.windings], "LV winding IDs")
        return self


class EquipmentCapabilityPackage(_CapabilityModel):
    schema_version: Literal[1] = 1
    package_code: PackageCode
    revision: PackageRevision
    kind: Literal["pcs", "transformer"]
    model: NonEmptyText
    manufacturer: NonEmptyText
    source_ref: NonEmptyText
    conditions: CapabilityConditions
    pcs: PcsCapability | None = None
    transformer: TransformerCapability | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _strict_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be the integer 1")
        return value

    @model_validator(mode="after")
    def _equipment_kind(self) -> Self:
        if self.kind == "pcs" and (self.pcs is None or self.transformer is not None):
            raise ValueError("A PCS package requires only its PCS capability declaration")
        if self.kind == "transformer" and (
            self.transformer is None or self.pcs is not None
        ):
            raise ValueError("A transformer package requires only its transformer declaration")
        return self


def capability_package_sha256(
    package: EquipmentCapabilityPackage | dict[str, object],
) -> str:
    """Hash the validated typed representation, never caller JSON formatting."""
    if isinstance(package, EquipmentCapabilityPackage):
        package = package.model_dump(mode="python")
    parsed = EquipmentCapabilityPackage.model_validate(package)
    encoded = json.dumps(
        parsed.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "MAX_CAPABILITY_ITEMS",
    "CapabilityConditions",
    "DischargeDutyBasis",
    "EquipmentCapabilityPackage",
    "LvWindingCapability",
    "PcsBusCapability",
    "PcsCapability",
    "PcsPortCapability",
    "TransformerCapability",
    "capability_package_sha256",
]
