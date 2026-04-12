from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

from calb_sizing_tool.common.allocation import allocate_dc_blocks, evenly_distribute


SUPPORTED_AC_DC_RATIOS: tuple[str, ...] = ("1:1", "1:2", "1:4")
DEFAULT_RECOMMENDED_RATIO = "1:2"
K_MAX_PCS_PER_BLOCK = 6
SMALL_SYSTEM_MAX_DC_BLOCKS = 4
LARGE_SYSTEM_MIN_DC_BLOCKS = 8
STANDARD_PCS_COUNTS: tuple[int, ...] = (2, 4)
STANDARD_PCS_RATINGS_KW: tuple[int, ...] = (1250, 1500, 1725, 2000, 2500)
OPTIMAL_PCS_RATINGS_KW: tuple[int, ...] = (1000, 1250, 1500, 1725, 2000, 2500, 3000, 3500, 4000, 4500, 5000)
SUGGESTION_PCS_RATINGS_KW: tuple[int, ...] = (1000, 1250, 1500, 1725, 2000, 2500)
AC_BLOCK_CONTAINER_SWITCH_MW = 5.0
AC_BLOCK_CONTAINER_SWITCH_PCS_COUNT = 4


@dataclass
class PCSRecommendation:
    pcs_count: int
    pcs_kw: int
    total_kw: int
    is_custom: bool = False

    @property
    def readable(self) -> str:
        return f"{self.pcs_count} x {self.pcs_kw}kW = {self.total_kw}kW"


@dataclass
class ACBlockRatioOption:
    ratio: str
    ac_block_count: int
    dc_blocks_per_ac: List[int]
    pcs_recommendations: List[PCSRecommendation]
    description: str = ""
    is_recommended: bool = False

    @property
    def readable_description(self) -> str:
        avg_dc = sum(self.dc_blocks_per_ac) / len(self.dc_blocks_per_ac) if self.dc_blocks_per_ac else 0
        return f"{self.ratio} - {self.ac_block_count} AC Blocks, ~{avg_dc:.1f} DC Blocks each"


def _build_standard_pcs_recommendations(pcs_count: int) -> List[PCSRecommendation]:
    return [
        PCSRecommendation(
            pcs_count=pcs_count,
            pcs_kw=pcs_kw,
            total_kw=pcs_count * pcs_kw,
        )
        for pcs_kw in STANDARD_PCS_RATINGS_KW
    ]


STANDARD_PCS_RECOMMENDATIONS_BY_COUNT: Dict[int, List[PCSRecommendation]] = {
    pcs_count: _build_standard_pcs_recommendations(pcs_count)
    for pcs_count in STANDARD_PCS_COUNTS
}


def standard_pcs_recommendations() -> List[PCSRecommendation]:
    recommendations: List[PCSRecommendation] = []
    for pcs_count in STANDARD_PCS_COUNTS:
        recommendations.extend(STANDARD_PCS_RECOMMENDATIONS_BY_COUNT[pcs_count])
    return recommendations


def generate_ac_sizing_options(
    dc_blocks_total: int,
    target_mw: float,
    target_mwh: float,
    dc_block_mwh: float = 5.0,
) -> List[ACBlockRatioOption]:
    """Generate the frozen AC:DC ratio set used by the current product."""
    del target_mw, target_mwh, dc_block_mwh

    options: List[ACBlockRatioOption] = []
    recommendation_library = standard_pcs_recommendations()

    options.append(
        ACBlockRatioOption(
            ratio="1:1",
            ac_block_count=dc_blocks_total,
            dc_blocks_per_ac=[1] * dc_blocks_total if dc_blocks_total > 0 else [],
            pcs_recommendations=list(recommendation_library),
            description="1 AC Block per 1 DC Block. Maximum flexibility and modularity.",
            is_recommended=dc_blocks_total <= SMALL_SYSTEM_MAX_DC_BLOCKS,
        )
    )

    ac_blocks_b = math.ceil(dc_blocks_total / 2) if dc_blocks_total > 0 else 0
    options.append(
        ACBlockRatioOption(
            ratio="1:2",
            ac_block_count=ac_blocks_b,
            dc_blocks_per_ac=evenly_distribute(dc_blocks_total, ac_blocks_b),
            pcs_recommendations=list(recommendation_library),
            description="1 AC Block per 2 DC Blocks. Balanced approach for most projects.",
            is_recommended=True,
        )
    )

    ac_blocks_c = math.ceil(dc_blocks_total / 4) if dc_blocks_total > 0 else 0
    options.append(
        ACBlockRatioOption(
            ratio="1:4",
            ac_block_count=ac_blocks_c,
            dc_blocks_per_ac=evenly_distribute(dc_blocks_total, ac_blocks_c),
            pcs_recommendations=list(recommendation_library),
            description="1 AC Block per 4 DC Blocks. Compact design for large-scale projects.",
            is_recommended=dc_blocks_total >= LARGE_SYSTEM_MIN_DC_BLOCKS,
        )
    )

    return options


def calculate_optimal_pcs_rating(
    dc_blocks_in_ac_block: int,
    dc_block_mwh: float,
    pcs_per_ac_block: int,
    transformer_efficiency: float = 0.9,
    pcs_efficiency: float = 0.97,
) -> float:
    del pcs_per_ac_block

    dc_total_mwh = dc_blocks_in_ac_block * dc_block_mwh
    discharge_hours = 4.0
    required_power_mw = dc_total_mwh / discharge_hours / (pcs_efficiency * transformer_efficiency)
    required_power_kw = required_power_mw * 1000
    return min(rating for rating in OPTIMAL_PCS_RATINGS_KW if rating >= required_power_kw)


def suggest_pcs_count_and_rating(
    dc_blocks_per_ac: int,
    target_power_mw: float,
    ac_block_count: int,
    safety_factor: float = 1.1,
) -> Tuple[int, int]:
    del dc_blocks_per_ac

    power_per_ac_mw = target_power_mw / ac_block_count * safety_factor
    power_per_ac_kw = power_per_ac_mw * 1000

    best_pcs_count = 2
    best_pcs_kw = STANDARD_PCS_RATINGS_KW[0]
    best_fit_error = float("inf")

    for pcs_kw in SUGGESTION_PCS_RATINGS_KW:
        for pcs_count in range(1, K_MAX_PCS_PER_BLOCK + 1):
            total_kw = pcs_count * pcs_kw
            error = abs(total_kw - power_per_ac_kw)
            if error < best_fit_error and total_kw >= power_per_ac_kw:
                best_fit_error = error
                best_pcs_count = pcs_count
                best_pcs_kw = pcs_kw

    return best_pcs_count, best_pcs_kw


def select_ac_block_container_type(block_size_mw: float, pcs_per_block: int) -> str:
    if float(block_size_mw) > AC_BLOCK_CONTAINER_SWITCH_MW or int(pcs_per_block) >= AC_BLOCK_CONTAINER_SWITCH_PCS_COUNT:
        return "40ft"
    return "20ft"


def evaluate_ac_sizing_feasibility(
    *,
    total_energy_mwh: float,
    target_energy_mwh: float,
    total_ac_mw: float,
    target_power_mw: float,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if total_energy_mwh < target_energy_mwh * 0.95:
        errors.append(f"Insufficient energy: {total_energy_mwh:.0f} MWh < {target_energy_mwh:.0f} MWh")
    elif total_energy_mwh > target_energy_mwh * 1.05:
        warnings.append(
            f"Excess energy: {total_energy_mwh:.0f} MWh > {target_energy_mwh:.0f} MWh "
            f"(+{(total_energy_mwh / target_energy_mwh - 1) * 100:.1f}%)"
        )

    if total_ac_mw < target_power_mw * 0.95:
        errors.append(f"Insufficient power: {total_ac_mw:.1f} MW < {target_power_mw:.1f} MW")
    else:
        overhead = total_ac_mw - target_power_mw
        if overhead > target_power_mw * 0.3:
            warnings.append(
                f"Power overhead: {overhead:.1f} MW ({overhead / target_power_mw * 100:.0f}% of POI requirement)"
            )

    return errors, warnings


def build_dc_allocation_plan(dc_blocks_total: int, ac_block_count: int, pcs_per_block: int) -> list[dict]:
    dc_blocks_per_ac_block = evenly_distribute(dc_blocks_total, ac_block_count)
    allocation_plan = []
    for index, dc_blocks_in_group in enumerate(dc_blocks_per_ac_block, start=1):
        feeder_allocations = allocate_dc_blocks(dc_blocks_in_group, pcs_per_block)
        allocation_plan.append(
            {
                "ac_block_index": index,
                "dc_blocks_total": dc_blocks_in_group,
                "feeder_allocations": feeder_allocations,
            }
        )
    return allocation_plan


class DCACRatio(str, Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_TWO = "1:2"
    ONE_TO_FOUR = "1:4"


class ACBlockConfig:
    """Compatibility wrapper for legacy AC sizing config APIs."""

    def __init__(self) -> None:
        self._pcs_configs_by_count = {
            pcs_count: list(STANDARD_PCS_RECOMMENDATIONS_BY_COUNT[pcs_count])
            for pcs_count in STANDARD_PCS_COUNTS
        }

    def get_pcs_recommendations_for_pcs_count(self, pcs_count: int) -> List[PCSRecommendation]:
        return list(self._pcs_configs_by_count.get(int(pcs_count), []))

    def calculate_ac_blocks(self, dc_blocks_total: int, ratio: DCACRatio) -> Dict[str, int]:
        dc_blocks_total = int(dc_blocks_total or 0)
        if ratio == DCACRatio.ONE_TO_ONE:
            ac_blocks = dc_blocks_total
        elif ratio == DCACRatio.ONE_TO_TWO:
            ac_blocks = math.ceil(dc_blocks_total / 2) if dc_blocks_total > 0 else 0
        elif ratio == DCACRatio.ONE_TO_FOUR:
            ac_blocks = math.ceil(dc_blocks_total / 4) if dc_blocks_total > 0 else 0
        else:
            ac_blocks = dc_blocks_total
        return {"ac_blocks": ac_blocks}

    def get_pcs_recommendations_for_dc_ac_ratio(
        self, dc_blocks_total: int, ratio: DCACRatio
    ) -> List[PCSRecommendation]:
        options = generate_ac_sizing_options(
            int(dc_blocks_total or 0),
            target_mw=0.0,
            target_mwh=0.0,
        )
        ratio_value = ratio.value if isinstance(ratio, DCACRatio) else str(ratio)
        for option in options:
            if option.ratio == ratio_value:
                return list(option.pcs_recommendations)
        return standard_pcs_recommendations()


def allocate_dc_blocks_to_pcs(dc_blocks_total: int, pcs_count: int) -> Dict[int, int]:
    counts = evenly_distribute(int(dc_blocks_total or 0), int(pcs_count or 0))
    return {index + 1: count for index, count in enumerate(counts)}


__all__ = [
    "ACBlockConfig",
    "ACBlockRatioOption",
    "AC_BLOCK_CONTAINER_SWITCH_MW",
    "AC_BLOCK_CONTAINER_SWITCH_PCS_COUNT",
    "DCACRatio",
    "DEFAULT_RECOMMENDED_RATIO",
    "K_MAX_PCS_PER_BLOCK",
    "LARGE_SYSTEM_MIN_DC_BLOCKS",
    "OPTIMAL_PCS_RATINGS_KW",
    "PCSRecommendation",
    "SMALL_SYSTEM_MAX_DC_BLOCKS",
    "STANDARD_PCS_COUNTS",
    "STANDARD_PCS_RATINGS_KW",
    "SUGGESTION_PCS_RATINGS_KW",
    "SUPPORTED_AC_DC_RATIOS",
    "allocate_dc_blocks_to_pcs",
    "build_dc_allocation_plan",
    "calculate_optimal_pcs_rating",
    "evaluate_ac_sizing_feasibility",
    "generate_ac_sizing_options",
    "select_ac_block_container_type",
    "standard_pcs_recommendations",
    "suggest_pcs_count_and_rating",
]
