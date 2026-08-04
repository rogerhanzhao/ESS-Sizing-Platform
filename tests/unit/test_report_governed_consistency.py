"""Report-layer consistency for the governed bilateral configuration.

Locks the Phase A finishing fixes that remove three AC-sizing -> report
contradictions:
  (1) the report must not silently fabricate a transformer nameplate
      (10 MW / 0.9 -> 11.11 MVA) when the governed MVA is unconfirmed;
  (2) Section 8 must route by ``layout_variant`` to the bilateral engine so the
      arrangement figure matches the SLD, not an average DC-per-AC linear draw;
  (3) the linear L2 site-array figure must be suppressed for a governed
      bilateral unit rather than drawn with contradictory single-row geometry.
"""
from __future__ import annotations
import pytest


from calb_diagrams.ac_block_bilateral_layout import LAYOUT_VARIANT
from calb_sizing_tool.reporting.report_context import build_report_context
from calb_sizing_tool.reporting.report_v2 import _compute_site_layout
from calb_sizing_tool.schemas.governed_ac_block_config import (
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as CFG,
)


def _stage13() -> dict:
    return {
        "project_name": "Governed Consistency",
        "poi_power_req_mw": 10.0,
        "poi_energy_req_mwh": 40.0,
        "project_life_years": 20,
        "poi_guarantee_year": 0,
        "cycles_per_year": 365,
    }


def _governed_ctx(*, with_mva: bool):
    overrides = {"transformer_mva": 11.11} if with_mva else None
    ac_output = CFG.to_ac_sld_output(engineering_overrides=overrides)
    # A single governed unit sizes to 8 DC blocks in 1 AC block.
    return build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": _stage13(),
            "ac_output": ac_output,
            "stage2": {"container_count": 8},
        },
        project_inputs={},
    )


def test_report_does_not_fabricate_transformer_mva_when_unconfirmed():
    ctx = _governed_ctx(with_mva=False)
    assert ctx.configuration_code == "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"
    # No silent 11.11 MVA (11,111 kVA). Unconfirmed => unresolved (None -> TBD).
    assert ctx.transformer_rating_kva is None


def test_report_uses_owner_confirmed_transformer_mva():
    ctx = _governed_ctx(with_mva=True)
    assert ctx.transformer_rating_kva == 11110.0


def test_site_array_tiles_the_bilateral_block_itself_not_a_linear_stand_in():
    """The site must compose the block section 8 drew, not a linear stand-in.

    This used to be suppressed outright — the L2 engine could only reconstruct a
    linear block from dc_per_block, so tiling a governed bilateral unit produced a
    contradictory single-row field. The engine now takes the block's REAL
    placements, so it composes the correct block instead of nothing.
    """
    from calb_diagrams.ac_block_bilateral_layout import compute_bilateral_layout

    ctx = _governed_ctx(with_mva=True)
    assert ctx.layout_variant == LAYOUT_VARIANT
    site = _compute_site_layout(ctx)
    assert site is not None
    block = compute_bilateral_layout(8)
    assert site.block_w_m == pytest.approx(block.envelope_w_m, abs=0.001)
    assert site.block_d_m == pytest.approx(block.envelope_d_m, abs=0.001)
    # A central-station block has no station-to-station corridor to share.
    assert site.block_mirrorable is False
    assert len(site.block_placements) == 9
    assert site.land_area_m2 > 0


def test_linear_site_array_still_runs_for_ungoverned_runs():
    ctx = build_report_context(
        session_state={},
        stage_outputs={
            "stage13_output": _stage13(),
            "ac_output": {"num_blocks": 2, "pcs_per_block": 4, "block_size_mw": 5.0},
            "stage2": {"container_count": 4},
        },
        project_inputs={},
    )
    assert ctx.layout_variant is None
    assert _compute_site_layout(ctx) is not None
