from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from calb_sizing_tool.schemas.common import CanonicalBaseModel


SldValidationMode = Literal["strict", "draft"]
SldDiagramMode = Literal["one_ac_block_group"]
SldTheme = Literal["dark", "light"]


class SldLabels(CanonicalBaseModel):
    to_switchgear: str
    to_other_rmu: str

    @field_validator("to_switchgear", "to_other_rmu")
    @classmethod
    def _non_empty_label(cls, value: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise ValueError("label must be non-empty")
        return resolved


class SldRmuRatings(CanonicalBaseModel):
    rated_kv: float
    rated_a: float
    short_circuit_ka_3s: float
    ct_ratio: str
    ct_class: str
    ct_va: float

    @field_validator("rated_kv", "rated_a", "short_circuit_ka_3s", "ct_va")
    @classmethod
    def _positive_number(cls, value: float) -> float:
        if float(value) <= 0:
            raise ValueError("value must be > 0")
        return float(value)

    @field_validator("ct_ratio", "ct_class")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise ValueError("value must be non-empty")
        return resolved


class SldLvBusbarRatings(CanonicalBaseModel):
    rated_a: float
    short_circuit_ka: float

    @field_validator("rated_a", "short_circuit_ka")
    @classmethod
    def _positive_number(cls, value: float) -> float:
        if float(value) <= 0:
            raise ValueError("value must be > 0")
        return float(value)


class SldCableSpecs(CanonicalBaseModel):
    mv_cable_spec: str
    lv_cable_spec: str
    dc_cable_spec: str

    @field_validator("mv_cable_spec", "lv_cable_spec", "dc_cable_spec")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise ValueError("cable spec must be non-empty")
        return resolved


class SldDcFuseSpec(CanonicalBaseModel):
    fuse_spec: str

    @field_validator("fuse_spec")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise ValueError("fuse spec must be non-empty")
        return resolved


class SldEquipmentRatings(CanonicalBaseModel):
    rmu: SldRmuRatings
    lv_busbar: SldLvBusbarRatings
    cables: SldCableSpecs
    dc_fuse: SldDcFuseSpec
    transformer_tap_range: str | None = None
    transformer_cooling: str | None = None


class SldInputOverride(CanonicalBaseModel):
    transformer_rating_mva: float | None = None
    transformer_vector_group: str | None = None
    transformer_uk_percent: float | None = None
    dc_block_voltage_v: float | None = None
    dc_blocks_per_feeder: list[int] | None = None
    labels: SldLabels | None = None
    equipment_ratings: SldEquipmentRatings | None = None


class SldCanonicalInput(CanonicalBaseModel):
    run_id: str | None = None
    project_name: str
    scenario_id: str
    group_index: int
    ac_blocks_total: int
    project_frequency_hz: float | None = None
    mv_voltage_kv: float
    lv_voltage_v_ll: float
    transformer_rating_mva: float
    transformer_vector_group: str
    transformer_uk_percent: float
    pcs_count: int
    pcs_rating_kw_list: list[float]
    dc_block_energy_mwh: float
    dc_blocks_total_in_group: int
    dc_blocks_per_feeder: list[int]
    dc_block_voltage_v: float
    equipment_ratings: SldEquipmentRatings
    labels: SldLabels
    diagram_mode: SldDiagramMode = "one_ac_block_group"
    theme: SldTheme = "dark"
    compact_mode: bool = False
    draw_summary: bool = False
    validation_mode: SldValidationMode = "strict"
    override_mode: bool = False
    source_trace: dict[str, str] = Field(default_factory=dict)
    draft_warnings: list[str] = Field(default_factory=list)

    @field_validator("group_index", "ac_blocks_total", "pcs_count", "dc_blocks_total_in_group")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("value must be > 0")
        return int(value)

    @field_validator(
        "mv_voltage_kv",
        "lv_voltage_v_ll",
        "transformer_rating_mva",
        "transformer_uk_percent",
        "dc_block_energy_mwh",
        "dc_block_voltage_v",
    )
    @classmethod
    def _positive_float(cls, value: float) -> float:
        if float(value) <= 0:
            raise ValueError("value must be > 0")
        return float(value)

    @field_validator("project_name", "scenario_id", "transformer_vector_group")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise ValueError("value must be non-empty")
        return resolved

    @field_validator("pcs_rating_kw_list")
    @classmethod
    def _non_empty_ratings(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("pcs_rating_kw_list must be non-empty")
        for rating in value:
            if float(rating) <= 0:
                raise ValueError("pcs rating must be > 0")
        return [float(rating) for rating in value]

    @field_validator("dc_blocks_per_feeder")
    @classmethod
    def _positive_feeders(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("dc_blocks_per_feeder must be non-empty")
        normalized = []
        for item in value:
            if int(item) < 0:
                raise ValueError("dc_blocks_per_feeder cannot contain negative values")
            normalized.append(int(item))
        return normalized

    @model_validator(mode="after")
    def _validate_consistency(self) -> "SldCanonicalInput":
        if self.group_index > self.ac_blocks_total:
            raise ValueError("group_index cannot exceed ac_blocks_total")
        if len(self.pcs_rating_kw_list) != self.pcs_count:
            raise ValueError("pcs_count must match pcs_rating_kw_list length")
        if len(self.dc_blocks_per_feeder) != self.pcs_count:
            raise ValueError("dc_blocks_per_feeder length must match pcs_count")
        if sum(self.dc_blocks_per_feeder) != self.dc_blocks_total_in_group:
            raise ValueError("dc_blocks_total_in_group must equal sum(dc_blocks_per_feeder)")
        return self


def legacy_sld_override_preset() -> dict:
    return {
        "labels": {
            "to_switchgear": "To Switchgear",
            "to_other_rmu": "To Other RMU",
        },
        "equipment_ratings": {
            "rmu": {
                "rated_kv": 24.0,
                "rated_a": 630.0,
                "short_circuit_ka_3s": 25.0,
                "ct_ratio": "200/1",
                "ct_class": "5P20",
                "ct_va": 10.0,
            },
            "lv_busbar": {
                "rated_a": 2500.0,
                "short_circuit_ka": 25.0,
            },
            "cables": {
                "mv_cable_spec": "TBD",
                "lv_cable_spec": "TBD",
                "dc_cable_spec": "TBD",
            },
            "dc_fuse": {
                "fuse_spec": "TBD",
            },
            "transformer_tap_range": "+/-2x2.5%",
            "transformer_cooling": "ONAN",
        },
        "transformer_vector_group": "Dyn11",
        "transformer_uk_percent": 7.0,
    }
