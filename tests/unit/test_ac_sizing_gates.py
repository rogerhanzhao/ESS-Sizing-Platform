"""Hard gates for governed AC Sizing (P0 duration gate, POI closure, product status).

Locks the four sizing-validity gates: a governed family may only be built for the
duration it is defined for; the POI power must close within the adjustment band;
auto-bound tail products are marked provisional, not owner-confirmed.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.schemas.governed_ac_block_config import (
    GOVERNED_SUPPORTED_DURATIONS_H,
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as HEAD,
    governed_duration_gate,
)
from calb_sizing_tool.services.ac_power_reconciliation import (
    PCS_OVERLOAD_FACTOR,
    reconcile_governed_power,
)
from calb_sizing_tool.services.governed_ac_block_service import (
    build_governed_primary_ac_output,
)


# --- P0 duration gate --------------------------------------------------------

def test_only_four_hour_families_are_defined():
    assert GOVERNED_SUPPORTED_DURATIONS_H == (4.0,)
    assert HEAD.system_duration_h == 4.0
    assert HEAD.dc_block_nameplate_power_kw == 1250.0


@pytest.mark.parametrize("duration,ok", [(4.0, True), (4.1, True), (3.9, True),
                                         (2.0, False), (3.0, False), (8.0, False), (None, False)])
def test_duration_gate(duration, ok):
    got, msg = governed_duration_gate(duration)
    assert got is ok
    assert msg  # always a human-readable reason
    if not ok and duration:
        assert "not yet defined" in msg or "unknown" in msg


def test_pcs_power_matches_dc_within_overload():
    # 4h: PCS 1250 kW vs DC 1250 kW -> fits (even without overload).
    assert HEAD.pcs_power_matches_dc(overload_factor=1.0)
    # A hypothetical 2h DC power (~3000 kW) would NOT fit the 1250 kW PCS.
    assert (1250.0 * PCS_OVERLOAD_FACTOR) < 3000.0


# --- POI power closure (reconciliation) -------------------------------------

def test_reconciliation_in_band_for_matched_config():
    # 20 MW POI, MV POI plane (eff_hvt_others=1.0), 2x10 MW governed.
    r = reconcile_governed_power(
        poi_power_mw=20.0,
        eff_ac_cables_sw_rmu=0.992,
        eff_hvt_others=1.0,
        eff_chain=0.967,
        ac_rated_total_mw=20.0,
        poi_energy_mwh=80.0,
        pcs_kw=1250.0,
        dc_block_power_kw=1250.0,
    )
    assert r.eff_mv_to_poi == pytest.approx(0.992)
    assert r.poi_within_band          # ~99.2% coverage is within 0.95-1.05
    assert r.pcs_within_overload      # 1250/1250 = 100% <= overload
    assert r.dc_ac_within_band        # dc_power ~20.7 / 20 = 1.03
    assert r.reconciled


def test_reconciliation_flags_undersized_ac():
    # Only 10 MW AC for a 20 MW POI -> coverage ~50%, out of band, with a note.
    r = reconcile_governed_power(
        poi_power_mw=20.0, eff_ac_cables_sw_rmu=0.992, eff_hvt_others=1.0,
        eff_chain=0.967, ac_rated_total_mw=10.0,
    )
    assert not r.poi_within_band
    assert not r.reconciled
    assert any("below the POI requirement" in n for n in r.notes)


def test_reconciliation_flags_pcs_overload_exceeded():
    # A 2h-like DC power (3000 kW) on a 1250 kW PCS exceeds overload.
    r = reconcile_governed_power(
        poi_power_mw=20.0, eff_ac_cables_sw_rmu=0.992, eff_hvt_others=1.0,
        eff_chain=0.967, ac_rated_total_mw=20.0, pcs_kw=1250.0, dc_block_power_kw=3000.0,
    )
    assert not r.pcs_within_overload
    assert any("exceeds PCS" in n for n in r.notes)


# --- tail product confirmation status ---------------------------------------

def test_tail_products_are_provisional_not_owner_confirmed():
    # 92 = 11x8 + 1x4, settings-only head (no owner product) -> head 'none',
    # tail auto-bound would be 'provisional_auto' if a product exists (no DB here
    # -> tails have no product, so 'none'). The status field must always be set.
    out = build_governed_primary_ac_output(92)
    groups = out["governed_groups"]
    for g in groups:
        assert "product_confirmation" in g
        assert g["product_confirmation"] in ("owner_selected", "provisional_auto", "none")
    # head has no owner product in this settings-only run
    head = groups[0]
    assert head["product_confirmation"] == "none"


def test_owner_selected_head_and_auto_tail_statuses(tmp_path):
    from calb_sizing_tool.infra.db.base import Base
    from calb_sizing_tool.infra.db.session import create_engine_for_url
    from calb_sizing_tool.services.ac_block_product_seed_service import seed_ac_block_products

    db_url = f"sqlite:///{(tmp_path / 'p.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    seed_ac_block_products(db_url=db_url)

    out = build_governed_primary_ac_output(
        92, head_product_block_code="SINENG-EH-10000-HB-UD-10-33", db_url=db_url
    )
    groups = {g["configuration_code"]: g for g in out["governed_groups"]}
    head = groups["ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"]
    tail = groups["ACBLK-5MW-4PCS-4DC-40FT-LINEAR"]
    # Owner explicitly picked the head product -> owner_selected.
    assert head["product_confirmation"] == "owner_selected"
    assert head["bound_product_code"] == "SINENG-EH-10000-HB-UD-10-33"
    # The tail was auto-matched -> provisional, NOT owner-confirmed.
    assert tail["product_confirmation"] == "provisional_auto"
    assert tail["bound_product_code"] is not None
