from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

from calb_sizing_tool.common.allocation import evenly_distribute
from calb_sizing_tool.schemas.ac_electrical_topology import build_dc_block_connection_plan


SUPPORTED_AC_DC_RATIOS: tuple[str, ...] = ("1:1", "1:2", "1:4", "1:8")
DEFAULT_RECOMMENDED_RATIO = "1:2"
K_MAX_PCS_PER_BLOCK = 6
SMALL_SYSTEM_MAX_DC_BLOCKS = 4
LARGE_SYSTEM_MIN_DC_BLOCKS = 8
VERY_LARGE_SYSTEM_MIN_DC_BLOCKS = 16
STANDARD_PCS_COUNTS: tuple[int, ...] = (2, 4)
STANDARD_PCS_RATINGS_KW: tuple[int, ...] = (1250, 1500, 1725, 2000, 2500)
OPTIMAL_PCS_RATINGS_KW: tuple[int, ...] = (1000, 1250, 1500, 1725, 2000, 2500, 3000, 3500, 4000, 4500, 5000)
SUGGESTION_PCS_RATINGS_KW: tuple[int, ...] = (1000, 1250, 1500, 1725, 2000, 2500)
AC_BLOCK_CONTAINER_SWITCH_MW = 5.0
DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS = 2


@dataclass
class PCSRecommendation:
    pcs_count: int
    pcs_kw: int
    total_kw: int
    is_custom: bool = False
    is_optimal: bool = False

    @property
    def readable(self) -> str:
        return f"{self.pcs_count} x {self.pcs_kw}kW = {self.total_kw}kW"


SIMPLIFIED_AC_BLOCK_MODEL_SOURCE = "simplified_dropdown"
ONE_TO_EIGHT_SMALL_PCS_CANDIDATE_SOURCE = "one_to_eight_small_pcs_candidate"
ONE_TO_EIGHT_SMALL_PCS_COUNT = 8
ONE_TO_EIGHT_SMALL_PCS_KW = 1250


@dataclass(frozen=True)
class ACBlockModelOption:
    """Simplified AC Block model used before governed product records exist."""

    model_code: str
    display_name: str
    pcs_count: int
    pcs_kw: int
    block_size_mw: float
    container_type: str
    source: str = SIMPLIFIED_AC_BLOCK_MODEL_SOURCE
    is_optimal: bool = False

    @property
    def total_kw(self) -> int:
        return int(round(self.pcs_count * self.pcs_kw))

    @property
    def readable(self) -> str:
        return self.display_name


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


def _build_ac_block_model_code(pcs_count: int, pcs_kw: int, container_type: str) -> str:
    return f"ACBLK-{int(pcs_count)}X{int(pcs_kw)}KW-{str(container_type).upper()}"


def build_simplified_ac_block_models(
    recommendations: List[PCSRecommendation],
    *,
    grouping_ratio: str | None = None,
) -> List[ACBlockModelOption]:
    """Convert PCS recommendations into selectable simplified AC Block models.

    The model list deliberately derives from the PCS recommendation library. It is
    not a product database source and does not imply approved equipment data.

    The owner-authorized 1:8 grouping also exposes an 8 x 1250 kW small-PCS
    combination. This is a selectable sizing candidate, not a mandated product
    and not a fixed 1:8 station identity. A real product can be bound only after
    the user has chosen the PCS architecture.
    """
    models: List[ACBlockModelOption] = []
    seen: set[tuple[int, int, str]] = set()

    for rec in recommendations:
        pcs_count = int(getattr(rec, "pcs_count", 0) or 0)
        pcs_kw = int(getattr(rec, "pcs_kw", 0) or 0)
        if pcs_count <= 0 or pcs_kw <= 0:
            continue
        block_size_mw = pcs_count * pcs_kw / 1000.0
        container_type = select_ac_block_container_type(block_size_mw, pcs_count)
        key = (pcs_count, pcs_kw, container_type)
        if key in seen:
            continue
        seen.add(key)

        model_code = _build_ac_block_model_code(pcs_count, pcs_kw, container_type)
        models.append(
            ACBlockModelOption(
                model_code=model_code,
                display_name=(
                    f"{block_size_mw:.2f} MW AC Block - "
                    f"{pcs_count} x {pcs_kw} kW PCS - {container_type} simplified model"
                ),
                pcs_count=pcs_count,
                pcs_kw=pcs_kw,
                block_size_mw=block_size_mw,
                container_type=container_type,
                is_optimal=bool(getattr(rec, "is_optimal", False)),
            )
        )

    if grouping_ratio == "1:8":
        pcs_count = ONE_TO_EIGHT_SMALL_PCS_COUNT
        pcs_kw = ONE_TO_EIGHT_SMALL_PCS_KW
        block_size_mw = pcs_count * pcs_kw / 1000.0
        container_type = select_ac_block_container_type(block_size_mw, pcs_count)
        key = (pcs_count, pcs_kw, container_type)
        if key not in seen:
            models.append(
                ACBlockModelOption(
                    model_code=_build_ac_block_model_code(pcs_count, pcs_kw, container_type),
                    display_name=(
                        f"{block_size_mw:.2f} MW AC Block - "
                        f"{pcs_count} x {pcs_kw} kW PCS - {container_type} "
                        "1:8 small-PCS combination"
                    ),
                    pcs_count=pcs_count,
                    pcs_kw=pcs_kw,
                    block_size_mw=block_size_mw,
                    container_type=container_type,
                    source=ONE_TO_EIGHT_SMALL_PCS_CANDIDATE_SOURCE,
                )
            )
        # Make the optional 1:8 architecture visible without turning it into
        # a product lock. The UI still exposes every generic candidate and
        # applies its physical feeder-capacity gate before a run can issue.
        models.sort(
            key=lambda model: (
                0 if (model.pcs_count, model.pcs_kw) == (pcs_count, pcs_kw) else 1,
                model.pcs_count,
                model.pcs_kw,
            )
        )

    return models


def calculate_optimal_pcs_rating(
    dc_blocks_in_ac_block: int,
    dc_block_mwh: float,
    pcs_per_ac_block: int,
    discharge_duration_h: float,
    transformer_efficiency: float = 0.9,
    pcs_efficiency: float = 0.97,
) -> int:
    """Return the minimum standard PCS unit rating (kW) that satisfies the power requirement.

    Uses the real discharge duration (poi_energy_req_mwh / poi_power_req_mw) rather than
    a hardcoded assumption, so 2-hour and 6-hour systems are sized correctly.
    """
    dc_total_mwh = dc_blocks_in_ac_block * dc_block_mwh
    total_required_kw = dc_total_mwh / discharge_duration_h / (pcs_efficiency * transformer_efficiency) * 1000
    per_pcs_required_kw = total_required_kw / pcs_per_ac_block
    candidates = [r for r in OPTIMAL_PCS_RATINGS_KW if r >= per_pcs_required_kw]
    return int(min(candidates)) if candidates else int(OPTIMAL_PCS_RATINGS_KW[-1])


def _mark_optimal_recommendations(
    recommendations: List[PCSRecommendation],
    max_dc_blocks: int,
    dc_block_mwh: float,
    discharge_duration_h: float,
) -> List[PCSRecommendation]:
    """Return a new list with is_optimal=True on the energy/power-derived best choice per pcs_count."""
    optimal_kw_by_count = {
        pcs_count: calculate_optimal_pcs_rating(
            max_dc_blocks, dc_block_mwh, pcs_count, discharge_duration_h
        )
        for pcs_count in STANDARD_PCS_COUNTS
    }
    return [
        PCSRecommendation(
            pcs_count=rec.pcs_count,
            pcs_kw=rec.pcs_kw,
            total_kw=rec.total_kw,
            is_custom=rec.is_custom,
            is_optimal=(rec.pcs_kw == optimal_kw_by_count.get(rec.pcs_count)),
        )
        for rec in recommendations
    ]


def generate_ac_sizing_options(
    dc_blocks_total: int,
    target_mw: float,
    target_mwh: float,
    dc_block_mwh: float = 5.0,
) -> List[ACBlockRatioOption]:
    """Generate the frozen AC:DC ratio set used by the current product.

    discharge_duration_h is derived from the real POI E/P ratio (target_mwh / target_mw)
    so PCS optimal markers are correct for any system duration, not just 4-hour systems.
    """
    discharge_duration_h = target_mwh / target_mw if target_mw > 0 else 4.0

    base_recommendations = standard_pcs_recommendations()
    options: List[ACBlockRatioOption] = []

    dc_per_ac_11 = [1] * dc_blocks_total if dc_blocks_total > 0 else []
    options.append(
        ACBlockRatioOption(
            ratio="1:1",
            ac_block_count=dc_blocks_total,
            dc_blocks_per_ac=dc_per_ac_11,
            pcs_recommendations=_mark_optimal_recommendations(
                base_recommendations, max(dc_per_ac_11, default=1), dc_block_mwh, discharge_duration_h
            ),
            description="1 AC Block per 1 DC Block. Maximum flexibility and modularity.",
            is_recommended=dc_blocks_total <= SMALL_SYSTEM_MAX_DC_BLOCKS,
        )
    )

    ac_blocks_b = math.ceil(dc_blocks_total / 2) if dc_blocks_total > 0 else 0
    dc_per_ac_12 = evenly_distribute(dc_blocks_total, ac_blocks_b)
    options.append(
        ACBlockRatioOption(
            ratio="1:2",
            ac_block_count=ac_blocks_b,
            dc_blocks_per_ac=dc_per_ac_12,
            pcs_recommendations=_mark_optimal_recommendations(
                base_recommendations, max(dc_per_ac_12, default=1), dc_block_mwh, discharge_duration_h
            ),
            description="1 AC Block per 2 DC Blocks. Balanced approach for most projects.",
            is_recommended=True,
        )
    )

    ac_blocks_c = math.ceil(dc_blocks_total / 4) if dc_blocks_total > 0 else 0
    dc_per_ac_14 = evenly_distribute(dc_blocks_total, ac_blocks_c)
    options.append(
        ACBlockRatioOption(
            ratio="1:4",
            ac_block_count=ac_blocks_c,
            dc_blocks_per_ac=dc_per_ac_14,
            pcs_recommendations=_mark_optimal_recommendations(
                base_recommendations, max(dc_per_ac_14, default=1), dc_block_mwh, discharge_duration_h
            ),
            description="1 AC Block per 4 DC Blocks. Compact design for large-scale projects.",
            is_recommended=dc_blocks_total >= LARGE_SYSTEM_MIN_DC_BLOCKS,
        )
    )

    ac_blocks_d = math.ceil(dc_blocks_total / 8) if dc_blocks_total > 0 else 0
    dc_per_ac_18 = evenly_distribute(dc_blocks_total, ac_blocks_d)
    options.append(
        ACBlockRatioOption(
            ratio="1:8",
            ac_block_count=ac_blocks_d,
            dc_blocks_per_ac=dc_per_ac_18,
            pcs_recommendations=_mark_optimal_recommendations(
                base_recommendations, max(dc_per_ac_18, default=1), dc_block_mwh, discharge_duration_h
            ),
            description=(
                "1 AC Block per up to 8 DC Blocks. Select PCS architecture separately; "
                "the optional 8 x 1250 kW combination is not a locked product."
            ),
            is_recommended=dc_blocks_total >= VERY_LARGE_SYSTEM_MIN_DC_BLOCKS,
        )
    )

    return options


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


def select_ac_block_container_type(block_size_mw: float, _pcs_per_block: int) -> str:
    """Return the container class from the power of one AC Block.

    The PCS-count parameter is retained for call compatibility only. A block of
    5 MW or less uses 20ft regardless of its PCS count; only a block above 5 MW
    uses 40ft.
    """
    if float(block_size_mw) > AC_BLOCK_CONTAINER_SWITCH_MW:
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


def minimum_dc_blocks_for_pcs_feeders(
    pcs_per_block: int,
    *,
    dc_block_output_circuits: int = DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS,
) -> int:
    """Minimum DC Blocks needed to supply all PCS feeders in one AC Block.

    Each DC Block has a finite number of protected output circuits. This is a
    connection-capacity check only; it does not change DC or AC sizing formulas.
    """
    if int(pcs_per_block) <= 0:
        return 0
    if int(dc_block_output_circuits) <= 0:
        raise ValueError("DC Block output circuit count must be positive.")
    return int(math.ceil(int(pcs_per_block) / int(dc_block_output_circuits)))


def dc_grouping_has_feeder_capacity(
    dc_blocks_per_ac: List[int],
    pcs_per_block: int,
    *,
    dc_block_output_circuits: int = DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS,
) -> bool:
    """Whether every AC Block in a selected grouping can feed its PCS count."""
    minimum = minimum_dc_blocks_for_pcs_feeders(
        pcs_per_block,
        dc_block_output_circuits=dc_block_output_circuits,
    )
    return all(int(dc_count) >= minimum for dc_count in dc_blocks_per_ac)


def build_dc_allocation_plan(
    dc_blocks_total: int,
    ac_block_count: int,
    pcs_per_block: int,
    *,
    dc_block_output_circuits: int = DEFAULT_DC_BLOCK_OUTPUT_CIRCUITS,
) -> list[dict]:
    dc_blocks_per_ac_block = evenly_distribute(dc_blocks_total, ac_block_count)
    allocation_plan = []
    for index, dc_blocks_in_group in enumerate(dc_blocks_per_ac_block, start=1):
        dc_block_connections = build_dc_block_connection_plan(
            dc_blocks_in_group,
            pcs_per_block,
            output_circuit_count=dc_block_output_circuits,
        )
        feeder_allocations = [
            sum(1 for connection in dc_block_connections if feeder_index in connection["feeder_indices"])
            for feeder_index in range(1, pcs_per_block + 1)
        ]
        allocation_plan.append(
            {
                "ac_block_index": index,
                "dc_blocks_total": dc_blocks_in_group,
                "feeder_allocations": feeder_allocations,
                "dc_block_connections": dc_block_connections,
            }
        )
    return allocation_plan


class DCACRatio(str, Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_TWO = "1:2"
    ONE_TO_FOUR = "1:4"
    ONE_TO_EIGHT = "1:8"


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
        elif ratio == DCACRatio.ONE_TO_EIGHT:
            ac_blocks = math.ceil(dc_blocks_total / 8) if dc_blocks_total > 0 else 0
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
    "ACBlockModelOption",
    "ACBlockRatioOption",
    "AC_BLOCK_CONTAINER_SWITCH_MW",
    "DCACRatio",
    "DEFAULT_RECOMMENDED_RATIO",
    "K_MAX_PCS_PER_BLOCK",
    "LARGE_SYSTEM_MIN_DC_BLOCKS",
    "ONE_TO_EIGHT_SMALL_PCS_CANDIDATE_SOURCE",
    "ONE_TO_EIGHT_SMALL_PCS_COUNT",
    "ONE_TO_EIGHT_SMALL_PCS_KW",
    "OPTIMAL_PCS_RATINGS_KW",
    "PCSRecommendation",
    "SMALL_SYSTEM_MAX_DC_BLOCKS",
    "STANDARD_PCS_COUNTS",
    "STANDARD_PCS_RATINGS_KW",
    "SUGGESTION_PCS_RATINGS_KW",
    "SUPPORTED_AC_DC_RATIOS",
    "VERY_LARGE_SYSTEM_MIN_DC_BLOCKS",
    "allocate_dc_blocks_to_pcs",
    "build_simplified_ac_block_models",
    "dc_grouping_has_feeder_capacity",
    "build_dc_block_connection_plan",
    "build_dc_allocation_plan",
    "calculate_optimal_pcs_rating",
    "evaluate_ac_sizing_feasibility",
    "generate_ac_sizing_options",
    "minimum_dc_blocks_for_pcs_feeders",
    "select_ac_block_container_type",
    "SIMPLIFIED_AC_BLOCK_MODEL_SOURCE",
    "standard_pcs_recommendations",
    "suggest_pcs_count_and_rating",
]
