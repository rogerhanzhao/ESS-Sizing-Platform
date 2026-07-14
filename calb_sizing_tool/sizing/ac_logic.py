"""Authoritative AC sizing facade.

The frozen AC sizing law is implemented in `calb_sizing_tool.services.ac_sizing_service`.
This module exists as a stable semantic import point for future refactors.
"""

from calb_sizing_tool.common.ac_block import derive_ac_template_fields
from calb_sizing_tool.services.ac_sizing_service import (
    ACBlockConfig,
    ACBlockModelOption,
    ACBlockRatioOption,
    PCSRecommendation,
    allocate_dc_blocks_to_pcs,
    build_simplified_ac_block_models,
    build_dc_allocation_plan,
    calculate_optimal_pcs_rating,
    evaluate_ac_sizing_feasibility,
    generate_ac_sizing_options,
    select_ac_block_container_type,
    standard_pcs_recommendations,
    suggest_pcs_count_and_rating,
)

__all__ = [
    "ACBlockConfig",
    "ACBlockModelOption",
    "ACBlockRatioOption",
    "PCSRecommendation",
    "allocate_dc_blocks_to_pcs",
    "build_simplified_ac_block_models",
    "build_dc_allocation_plan",
    "calculate_optimal_pcs_rating",
    "derive_ac_template_fields",
    "evaluate_ac_sizing_feasibility",
    "generate_ac_sizing_options",
    "select_ac_block_container_type",
    "standard_pcs_recommendations",
    "suggest_pcs_count_and_rating",
]
