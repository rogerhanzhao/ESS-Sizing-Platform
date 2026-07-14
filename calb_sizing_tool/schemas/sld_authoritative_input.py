from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from calb_sizing_tool.schemas.common import CanonicalBaseModel


class SldAcBlockAllocation(CanonicalBaseModel):
    ac_block_index: int
    pcs_count: int
    pcs_rating_kw: float
    dc_blocks_total: int
    feeder_allocations: list[int]

    @field_validator("ac_block_index", "pcs_count")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("value must be > 0")
        return int(value)

    @field_validator("dc_blocks_total")
    @classmethod
    def _non_negative_total(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("value must be >= 0")
        return int(value)

    @field_validator("pcs_rating_kw")
    @classmethod
    def _positive_float(cls, value: float) -> float:
        if float(value) <= 0:
            raise ValueError("value must be > 0")
        return float(value)

    @field_validator("feeder_allocations")
    @classmethod
    def _non_negative_feeder_allocations(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("feeder_allocations must be non-empty")
        normalized = []
        for item in value:
            if int(item) < 0:
                raise ValueError("feeder_allocations cannot contain negative values")
            normalized.append(int(item))
        return normalized

    @model_validator(mode="after")
    def _validate_consistency(self) -> "SldAcBlockAllocation":
        if len(self.feeder_allocations) != self.pcs_count:
            raise ValueError("feeder_allocations length must match pcs_count")
        if sum(self.feeder_allocations) != self.dc_blocks_total:
            raise ValueError("dc_blocks_total must equal sum(feeder_allocations)")
        return self


class SldAuthoritativeAcOutput(CanonicalBaseModel):
    num_blocks: int
    pcs_per_block: int
    pcs_count_by_block: list[int]
    pcs_kw: float
    pcs_rating_kw_list_by_block: list[list[float]]
    block_size_mw: float
    dc_allocation_plan: list[SldAcBlockAllocation]
    dc_blocks_total_by_block: list[int]
    dc_blocks_per_feeder_by_block: list[list[int]]
    dc_blocks_total: int | None = None
    dc_total_mwh: float | None = None
    transformer_mva: float
    lv_winding_count: int
    transformer_count: int | None = None
    pcs_count_total: int | None = None
    mv_voltage_kv: float | None = None
    lv_voltage_v: float | None = None
    legacy_aliases_used: list[str] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)

    @field_validator("num_blocks", "pcs_per_block", "lv_winding_count")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("value must be > 0")
        return int(value)

    @field_validator("dc_blocks_total", "transformer_count", "pcs_count_total")
    @classmethod
    def _optional_non_negative_int(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if int(value) < 0:
            raise ValueError("value must be >= 0")
        return int(value)

    @field_validator("pcs_kw", "block_size_mw", "dc_total_mwh", "transformer_mva", "mv_voltage_kv", "lv_voltage_v")
    @classmethod
    def _optional_positive_float(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if float(value) <= 0:
            raise ValueError("value must be > 0")
        return float(value)

    @field_validator("pcs_count_by_block")
    @classmethod
    def _positive_count_list(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("pcs_count_by_block must be non-empty")
        normalized = []
        for item in value:
            if int(item) <= 0:
                raise ValueError("pcs_count_by_block values must be > 0")
            normalized.append(int(item))
        return normalized

    @field_validator("pcs_rating_kw_list_by_block")
    @classmethod
    def _positive_rating_matrix(cls, value: list[list[float]]) -> list[list[float]]:
        if not value:
            raise ValueError("pcs_rating_kw_list_by_block must be non-empty")
        normalized: list[list[float]] = []
        for row in value:
            if not row:
                raise ValueError("pcs_rating_kw_list_by_block rows must be non-empty")
            normalized_row = []
            for item in row:
                if float(item) <= 0:
                    raise ValueError("pcs ratings must be > 0")
                normalized_row.append(float(item))
            normalized.append(normalized_row)
        return normalized

    @field_validator("dc_blocks_total_by_block")
    @classmethod
    def _non_negative_total_list(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("dc_blocks_total_by_block must be non-empty")
        normalized = []
        for item in value:
            if int(item) < 0:
                raise ValueError("dc_blocks_total_by_block values must be >= 0")
            normalized.append(int(item))
        return normalized

    @field_validator("dc_blocks_per_feeder_by_block")
    @classmethod
    def _non_negative_feeder_matrix(cls, value: list[list[int]]) -> list[list[int]]:
        if not value:
            raise ValueError("dc_blocks_per_feeder_by_block must be non-empty")
        normalized: list[list[int]] = []
        for row in value:
            if not row:
                raise ValueError("dc_blocks_per_feeder_by_block rows must be non-empty")
            normalized_row = []
            for item in row:
                if int(item) < 0:
                    raise ValueError("dc_blocks_per_feeder_by_block values must be >= 0")
                normalized_row.append(int(item))
            normalized.append(normalized_row)
        return normalized

    @field_validator("legacy_aliases_used")
    @classmethod
    def _normalize_aliases(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip() for item in value if str(item).strip()})

    @field_validator("field_sources")
    @classmethod
    def _normalize_sources(cls, value: dict[str, Any]) -> dict[str, str]:
        return {str(key): str(item) for key, item in dict(value or {}).items()}

    @model_validator(mode="after")
    def _validate_consistency(self) -> "SldAuthoritativeAcOutput":
        if len(self.pcs_count_by_block) != self.num_blocks:
            raise ValueError("pcs_count_by_block length must match num_blocks")
        expected_lv_winding_count = (self.pcs_per_block + 1) // 2
        if self.lv_winding_count != expected_lv_winding_count:
            raise ValueError("lv_winding_count must provide one independent LV winding per two PCS feeders")
        if len(self.pcs_rating_kw_list_by_block) != self.num_blocks:
            raise ValueError("pcs_rating_kw_list_by_block length must match num_blocks")
        if len(self.dc_allocation_plan) != self.num_blocks:
            raise ValueError("dc_allocation_plan length must match num_blocks")
        if len(self.dc_blocks_total_by_block) != self.num_blocks:
            raise ValueError("dc_blocks_total_by_block length must match num_blocks")
        if len(self.dc_blocks_per_feeder_by_block) != self.num_blocks:
            raise ValueError("dc_blocks_per_feeder_by_block length must match num_blocks")

        derived_block_size_mw = round(self.pcs_per_block * self.pcs_kw / 1000.0, 6)
        if abs(self.block_size_mw - derived_block_size_mw) > 1e-6:
            raise ValueError("block_size_mw must equal pcs_per_block * pcs_kw / 1000")

        derived_pcs_total = sum(self.pcs_count_by_block)
        if self.pcs_count_total is not None and self.pcs_count_total != derived_pcs_total:
            raise ValueError("pcs_count_total must equal sum(pcs_count_by_block)")
        if self.transformer_count is not None and self.transformer_count != self.num_blocks:
            raise ValueError("transformer_count must equal num_blocks in SLD V1")

        for block_idx, pcs_count in enumerate(self.pcs_count_by_block, start=1):
            if pcs_count != self.pcs_per_block:
                raise ValueError("pcs_count_by_block must be uniform and equal pcs_per_block in SLD V1")
            if len(self.pcs_rating_kw_list_by_block[block_idx - 1]) != pcs_count:
                raise ValueError("pcs_rating_kw_list_by_block rows must match pcs_count_by_block")
            if len(self.dc_blocks_per_feeder_by_block[block_idx - 1]) != pcs_count:
                raise ValueError("dc_blocks_per_feeder_by_block rows must match pcs_count_by_block")
            if self.dc_allocation_plan[block_idx - 1].ac_block_index != block_idx:
                raise ValueError("dc_allocation_plan must be ordered by ac_block_index")
            if self.dc_allocation_plan[block_idx - 1].pcs_count != pcs_count:
                raise ValueError("dc_allocation_plan pcs_count must match pcs_count_by_block")
            if any(abs(item - self.pcs_kw) > 1e-6 for item in self.pcs_rating_kw_list_by_block[block_idx - 1]):
                raise ValueError("pcs_rating_kw_list_by_block must match pcs_kw in SLD V1")
            if abs(self.dc_allocation_plan[block_idx - 1].pcs_rating_kw - self.pcs_kw) > 1e-6:
                raise ValueError("dc_allocation_plan pcs_rating_kw must match pcs_kw in SLD V1")
            if self.dc_blocks_total_by_block[block_idx - 1] != self.dc_allocation_plan[block_idx - 1].dc_blocks_total:
                raise ValueError("dc_blocks_total_by_block must match dc_allocation_plan")
            if self.dc_blocks_per_feeder_by_block[block_idx - 1] != self.dc_allocation_plan[block_idx - 1].feeder_allocations:
                raise ValueError("dc_blocks_per_feeder_by_block must match dc_allocation_plan")

        if self.dc_blocks_total is not None and self.dc_blocks_total != sum(self.dc_blocks_total_by_block):
            raise ValueError("dc_blocks_total must equal sum(dc_blocks_total_by_block)")
        return self
