# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

"""
AC sizing configuration and recommendation engine.
Generates standard ratio options (1:1, 1:2, 1:4) based on DC block count.
"""
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


@dataclass
class PCSRecommendation:
    """PCS recommendation configuration."""

    pcs_count: int  # PCS count per AC block (typically 2 or 4).
    pcs_kw: int  # PCS power rating per unit (kW).
    total_kw: int  # Total PCS power (kW).
    is_custom: bool = False  # Custom configuration flag.

    @property
    def readable(self) -> str:
        return f"{self.pcs_count} x {self.pcs_kw}kW = {self.total_kw}kW"


@dataclass
class ACBlockRatioOption:
    """AC block ratio option."""

    ratio: str
    ac_block_count: int  # Number of AC blocks.
    dc_blocks_per_ac: List[int]  # DC blocks connected per AC block.
    pcs_recommendations: List[PCSRecommendation]  # PCS recommendations.
    description: str = ""
    is_recommended: bool = False

    @property
    def readable_description(self) -> str:
        avg_dc = sum(self.dc_blocks_per_ac) / len(self.dc_blocks_per_ac) if self.dc_blocks_per_ac else 0
        return f"{self.ratio} - {self.ac_block_count} AC Blocks, ~{avg_dc:.1f} DC Blocks each"


def generate_ac_sizing_options(
    dc_blocks_total: int,
    target_mw: float,
    target_mwh: float,
    dc_block_mwh: float = 5.0,
) -> List[ACBlockRatioOption]:
    """
    Generate standard AC/DC ratio options (1:1, 1:2, 1:4).

    Principles:
    - DC:AC ratio controls how DC blocks are grouped into AC blocks.
    - PCS configuration is independent of the DC:AC ratio.

    Args:
        dc_blocks_total: Total DC blocks (20ft container).
        target_mw: POI power requirement (MW).
        target_mwh: POI energy requirement (MWh).
        dc_block_mwh: DC block capacity (MWh), default 5.0.

    Returns:
        List of ratio options.
    """
    options = []

    # ===== PCS configurations (independent of DC:AC ratio) =====
    pcs_configs_2pcs = [
        PCSRecommendation(pcs_count=2, pcs_kw=1250, total_kw=2500),
        PCSRecommendation(pcs_count=2, pcs_kw=1500, total_kw=3000),
        PCSRecommendation(pcs_count=2, pcs_kw=1725, total_kw=3450),
        PCSRecommendation(pcs_count=2, pcs_kw=2000, total_kw=4000),
        PCSRecommendation(pcs_count=2, pcs_kw=2500, total_kw=5000),
    ]

    pcs_configs_4pcs = [
        PCSRecommendation(pcs_count=4, pcs_kw=1250, total_kw=5000),
        PCSRecommendation(pcs_count=4, pcs_kw=1500, total_kw=6000),
        PCSRecommendation(pcs_count=4, pcs_kw=1725, total_kw=6900),
        PCSRecommendation(pcs_count=4, pcs_kw=2000, total_kw=8000),
        PCSRecommendation(pcs_count=4, pcs_kw=2500, total_kw=10000),
    ]

    # ===== Option A: 1:1 (1 DC Block per AC Block) =====
    ac_blocks_a = dc_blocks_total
    dc_per_ac_a = [1] * ac_blocks_a if ac_blocks_a > 0 else []
    pcs_recommendations_a = pcs_configs_2pcs + pcs_configs_4pcs

    option_a = ACBlockRatioOption(
        ratio="1:1",
        ac_block_count=ac_blocks_a,
        dc_blocks_per_ac=dc_per_ac_a,
        pcs_recommendations=pcs_recommendations_a,
        description="1 AC Block per 1 DC Block. Maximum flexibility and modularity.",
        is_recommended=dc_blocks_total <= 4,
    )
    options.append(option_a)

    # ===== Option B: 1:2 (2 DC Blocks per AC Block) =====
    ac_blocks_b = math.ceil(dc_blocks_total / 2)
    dc_per_ac_b = evenly_distribute(dc_blocks_total, ac_blocks_b)
    pcs_recommendations_b = pcs_configs_2pcs + pcs_configs_4pcs

    option_b = ACBlockRatioOption(
        ratio="1:2",
        ac_block_count=ac_blocks_b,
        dc_blocks_per_ac=dc_per_ac_b,
        pcs_recommendations=pcs_recommendations_b,
        description="1 AC Block per 2 DC Blocks. Balanced approach for most projects.",
        is_recommended=True,
    )
    options.append(option_b)

    # ===== Option C: 1:4 (4 DC Blocks per AC Block) =====
    ac_blocks_c = math.ceil(dc_blocks_total / 4)
    dc_per_ac_c = evenly_distribute(dc_blocks_total, ac_blocks_c)
    pcs_recommendations_c = pcs_configs_2pcs + pcs_configs_4pcs

    option_c = ACBlockRatioOption(
        ratio="1:4",
        ac_block_count=ac_blocks_c,
        dc_blocks_per_ac=dc_per_ac_c,
        pcs_recommendations=pcs_recommendations_c,
        description="1 AC Block per 4 DC Blocks. Compact design for large-scale projects.",
        is_recommended=dc_blocks_total >= 8,
    )
    options.append(option_c)

    return options


def evenly_distribute(total: int, buckets: int) -> List[int]:
    """
    Evenly distribute total items into a number of buckets.
    Example:
        evenly_distribute(6, 4) -> [2, 1, 1, 2] or [2, 2, 1, 1]
        evenly_distribute(7, 3) -> [3, 2, 2] or [2, 3, 2]
    """
    if buckets <= 0:
        return []

    base = total // buckets
    remainder = total % buckets

    result = []
    for i in range(buckets):
        if i < remainder:
            result.append(base + 1)
        else:
            result.append(base)

    return result


def calculate_optimal_pcs_rating(
    dc_blocks_in_ac_block: int,
    dc_block_mwh: float,
    pcs_per_ac_block: int,
    transformer_efficiency: float = 0.9,
    pcs_efficiency: float = 0.97,
) -> float:
    """
    Calculate a reasonable PCS rating based on DC block count.

    Args:
        dc_blocks_in_ac_block: DC blocks per AC block.
        dc_block_mwh: DC block capacity (MWh).
        pcs_per_ac_block: PCS count per AC block.
        transformer_efficiency: Transformer efficiency.
        pcs_efficiency: PCS efficiency.

    Returns:
        Recommended PCS rating (kW).
    """
    # Total DC capacity.
    dc_total_mwh = dc_blocks_in_ac_block * dc_block_mwh

    # Assume a reasonable discharge duration (4 hours).
    discharge_hours = 4.0

    # Required power = energy / time / efficiency.
    required_power_mw = dc_total_mwh / discharge_hours / (pcs_efficiency * transformer_efficiency)
    required_power_kw = required_power_mw * 1000

    # Round up to nearest standard rating.
    standard_ratings = [1000, 1250, 1500, 1725, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
    optimal_kw = min(r for r in standard_ratings if r >= required_power_kw)

    return optimal_kw


def suggest_pcs_count_and_rating(
    dc_blocks_per_ac: int,
    target_power_mw: float,
    ac_block_count: int,
    safety_factor: float = 1.1,
) -> Tuple[int, int]:
    """
    Recommend PCS count and rating based on DC blocks and target power.

    Args:
        dc_blocks_per_ac: DC blocks per AC block.
        target_power_mw: Target power requirement (MW).
        ac_block_count: Total AC blocks.
        safety_factor: Safety factor (default 1.1).

    Returns:
        (pcs_count, pcs_kw): recommended PCS count and rating.
    """
    # Required power per AC block.
    power_per_ac_mw = target_power_mw / ac_block_count * safety_factor
    power_per_ac_kw = power_per_ac_mw * 1000

    # Try standard ratings and pick the best fit.
    standard_ratings = [1000, 1250, 1500, 1725, 2000, 2500]
    best_pcs_count = 2
    best_pcs_kw = 1250
    best_fit_error = float("inf")

    for pcs_kw in standard_ratings:
        for pcs_count in [1, 2, 3, 4, 5, 6]:
            total_kw = pcs_count * pcs_kw
            error = abs(total_kw - power_per_ac_kw)

            if error < best_fit_error and total_kw >= power_per_ac_kw:
                best_fit_error = error
                best_pcs_count = pcs_count
                best_pcs_kw = pcs_kw

    return best_pcs_count, best_pcs_kw


class DCACRatio(str, Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_TWO = "1:2"
    ONE_TO_FOUR = "1:4"


class ACBlockConfig:
    """Compatibility wrapper for legacy AC sizing config APIs."""

    def __init__(self) -> None:
        self._pcs_configs_by_count = {
            2: [
                PCSRecommendation(pcs_count=2, pcs_kw=1250, total_kw=2500),
                PCSRecommendation(pcs_count=2, pcs_kw=1500, total_kw=3000),
                PCSRecommendation(pcs_count=2, pcs_kw=1725, total_kw=3450),
                PCSRecommendation(pcs_count=2, pcs_kw=2000, total_kw=4000),
                PCSRecommendation(pcs_count=2, pcs_kw=2500, total_kw=5000),
            ],
            4: [
                PCSRecommendation(pcs_count=4, pcs_kw=1250, total_kw=5000),
                PCSRecommendation(pcs_count=4, pcs_kw=1500, total_kw=6000),
                PCSRecommendation(pcs_count=4, pcs_kw=1725, total_kw=6900),
                PCSRecommendation(pcs_count=4, pcs_kw=2000, total_kw=8000),
                PCSRecommendation(pcs_count=4, pcs_kw=2500, total_kw=10000),
            ],
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
        return list(self._pcs_configs_by_count.get(2, [])) + list(self._pcs_configs_by_count.get(4, []))


def allocate_dc_blocks_to_pcs(dc_blocks_total: int, pcs_count: int) -> Dict[int, int]:
    counts = evenly_distribute(int(dc_blocks_total or 0), int(pcs_count or 0))
    return {idx + 1: count for idx, count in enumerate(counts)}
