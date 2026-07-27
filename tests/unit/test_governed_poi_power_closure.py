from __future__ import annotations

import pytest

from calb_sizing_tool.services.governed_ac_block_service import (
    DEFAULT_GOVERNED_POI_OVERSIZE_MAX,
    assess_governed_poi_power_closure,
    build_governed_site_plan,
    governed_poi_power_closure_issue,
)


def test_current_202_dc_governed_mix_is_held_at_poi_for_material_oversize():
    """Aging-energy DC additions cannot silently become one extra PCS each."""
    plan = build_governed_site_plan(202)
    closure = assess_governed_poi_power_closure(
        poi_power_mw=200.0,
        site_ac_lv_mw=plan.ac_power_mw_total,
        eff_mvt_frac=0.995,
        eff_ac_cables_sw_rmu_frac=0.992,
        eff_hvt_others_frac=1.0,
    )

    assert plan.ac_power_mw_total == 252.5
    assert closure.required_ac_lv_mw == pytest.approx(202.626, abs=0.001)
    assert closure.deliverable_poi_mw == pytest.approx(249.228, abs=0.001)
    assert closure.poi_oversize_pct == pytest.approx(0.246, abs=0.001)
    assert closure.status == "hold"
    assert closure.blockers == ("poi_oversize_above_guard",)
    assert closure.max_poi_oversize_pct == DEFAULT_GOVERNED_POI_OVERSIZE_MAX


def test_poi_matched_capacity_passes_power_closure_without_claiming_dc_topology():
    closure = assess_governed_poi_power_closure(
        poi_power_mw=200.0,
        site_ac_lv_mw=205.0,
        eff_mvt_frac=0.995,
        eff_ac_cables_sw_rmu_frac=0.992,
        eff_hvt_others_frac=1.0,
    )

    assert closure.is_feasible
    assert closure.deliverable_poi_mw == pytest.approx(202.343, abs=0.001)
    assert closure.poi_oversize_pct == pytest.approx(0.0117, abs=0.0001)


def test_incomplete_or_invalid_stage1_loss_handoff_fails_closed():
    with pytest.raises(ValueError, match="efficiencies"):
        assess_governed_poi_power_closure(
            poi_power_mw=200.0,
            site_ac_lv_mw=205.0,
            eff_mvt_frac=0.0,
            eff_ac_cables_sw_rmu_frac=0.992,
            eff_hvt_others_frac=1.0,
        )


def test_persisted_governed_snapshot_requires_a_passing_power_closure_record():
    assert "no POI power-closure record" in governed_poi_power_closure_issue(
        {"governed_configuration": True}
    )
    assert "on POI power hold" in governed_poi_power_closure_issue(
        {
            "governed_configuration": True,
            "governed_poi_power_closure": {"status": "hold"},
        }
    )
    assert governed_poi_power_closure_issue(
        {
            "governed_configuration": True,
            "governed_poi_power_closure": {"status": "pass"},
        }
    ) is None
