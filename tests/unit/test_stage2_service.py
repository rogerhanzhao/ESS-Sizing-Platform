from __future__ import annotations

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.services.stage2_service import (
    K_MAX_FIXED,
    build_config_cabinet_only,
    build_config_container_only,
    build_config_hybrid,
    pick_dc_block,
)


def test_stage2_service_builds_container_and_hybrid_configs():
    bundle = load_dc_excel_bundle_from_path(DC_DATA_PATH)
    cont_code, cont_name, cont_unit = pick_dc_block(bundle.df_blocks, "container")
    cab_code, cab_name, cab_unit = pick_dc_block(bundle.df_blocks, "cabinet")

    container = build_config_container_only(401.0, cont_unit, cont_code, cont_name)
    cabinet = build_config_cabinet_only(21.0, cab_unit, cab_code, cab_name, k_max=K_MAX_FIXED)
    hybrid = build_config_hybrid(430.0, cont_unit, cont_code, cont_name, cab_unit, cab_code, cab_name, k_max=K_MAX_FIXED)

    assert container.container_count > 0
    assert container.cabinet_count == 0
    assert cabinet.cabinet_count > 0
    assert hybrid.container_count >= 0
    assert hybrid.busbars_needed in (0, 1)
