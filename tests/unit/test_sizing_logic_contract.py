from __future__ import annotations

from calb_sizing_tool.services.stage1_service import calc_sc_loss_pct
from calb_sizing_tool.services.stage2_service import build_config_cabinet_only, build_config_hybrid


def test_stage1_sc_loss_schedule_is_frozen():
    assert calc_sc_loss_pct(0) == 0.0
    assert calc_sc_loss_pct(1) == 2.0
    assert calc_sc_loss_pct(3) == 2.0
    assert calc_sc_loss_pct(4) == 2.5
    assert calc_sc_loss_pct(12) == 4.5
    assert calc_sc_loss_pct(24) == 5.1


def test_stage2_hybrid_rolls_over_to_next_container_when_cabinet_count_exceeds_kmax():
    result = build_config_hybrid(
        required_dc_mwh=15.0,
        container_unit=10.0,
        container_code="CONT",
        container_name="Container",
        cabinet_unit=1.0,
        cabinet_code="CAB",
        cabinet_name="Cabinet",
        k_max=4,
    )

    assert result.mode == "hybrid"
    assert result.container_count == 2
    assert result.cabinet_count == 0
    assert result.busbars_needed == 0
    assert result.dc_nameplate_bol_mwh == 20.0
    assert result.oversize_mwh == 5.0


def test_stage2_cabinet_only_busbar_grouping_is_frozen():
    result = build_config_cabinet_only(
        required_dc_mwh=21.0,
        cabinet_unit=2.0,
        cabinet_code="CAB",
        cabinet_name="Cabinet",
        k_max=10,
    )

    assert result.mode == "cabinet_only"
    assert result.cabinet_count == 11
    assert result.busbars_needed == 2
    assert result.dc_nameplate_bol_mwh == 22.0
