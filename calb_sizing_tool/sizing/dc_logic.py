"""Authoritative DC sizing facade.

The frozen DC sizing law lives in the Stage 1-3 services and guarantee loop service.
This module prevents placeholder formulas from diverging from the real pipeline.
"""

from calb_sizing_tool.services.dc_pipeline_service import run_dc_pipeline, size_with_guarantee
from calb_sizing_tool.services.stage1_service import calc_sc_loss_pct, run_stage1
from calb_sizing_tool.services.stage2_service import (
    K_MAX_FIXED,
    build_config_cabinet_only,
    build_config_container_only,
    build_config_hybrid,
    pick_dc_block,
    rebuild_stage2_counts,
)
from calb_sizing_tool.services.stage3_service import run_stage3

__all__ = [
    "K_MAX_FIXED",
    "build_config_cabinet_only",
    "build_config_container_only",
    "build_config_hybrid",
    "calc_sc_loss_pct",
    "pick_dc_block",
    "rebuild_stage2_counts",
    "run_dc_pipeline",
    "run_stage1",
    "run_stage3",
    "size_with_guarantee",
]
