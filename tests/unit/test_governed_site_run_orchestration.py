"""Multi-group run orchestration for a mixed governed (Phase B) site.

``build_governed_site_run`` turns the Phase B decomposition into a runnable
multi-block site: one valid, individually SLD-renderable ``SldAuthoritativeAcOutput``
per governed group (not a single per-group demo). A 14-DC site (8 + 4 + 2) yields
three distinct AC outputs, each of which normalizes cleanly for the SLD pipeline.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.ac_to_sld_adapter import normalize_ac_output_for_sld
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.ac_block_product_seed_service import seed_ac_block_products
from calb_sizing_tool.services.governed_ac_block_service import (
    GovernedSiteRun,
    build_governed_site_run,
)


@pytest.fixture()
def seeded_db(tmp_path) -> str:
    db_url = f"sqlite:///{(tmp_path / 'products.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    seed_ac_block_products(db_url=db_url)
    return db_url


def test_run_yields_one_ac_output_per_governed_group():
    run = build_governed_site_run(14)  # 8 + 4 + 2
    assert isinstance(run, GovernedSiteRun)
    assert run.dc_blocks_total == 14
    assert run.ac_blocks_total == 3
    assert run.ac_power_mw_total == 17.5
    codes = [g.configuration_code for g in run.groups]
    assert codes == [
        "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL",
        "ACBLK-5MW-4PCS-4DC-40FT-LINEAR",
        "ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR",
    ]


def test_each_group_output_normalizes_for_the_sld_pipeline(seeded_db):
    # Product binding supplies the transformer MVA the SLD contract requires;
    # without it the output is intentionally not renderable (MVA never fabricated).
    run = build_governed_site_run(14, db_url=seeded_db, bind_products=True)
    for group in run.groups:
        norm = normalize_ac_output_for_sld(group.ac_output)
        # Each group is internally uniform: one representative SLD covers it.
        assert norm.num_blocks == group.ac_block_count
        assert all(c == group.pcs_per_ac_block for c in norm.pcs_count_by_block)
    # The bilateral head keeps its three-winding / 2-LV identity.
    head = normalize_ac_output_for_sld(run.groups[0].ac_output)
    assert head.lv_winding_count == 2
    # The linear tails are two-winding / single-LV.
    tail = normalize_ac_output_for_sld(run.groups[1].ac_output)
    assert tail.lv_winding_count == 1


def test_multiple_of_eight_collapses_to_a_single_group():
    run = build_governed_site_run(16)  # 2 x 8, one group
    assert len(run.groups) == 1
    assert run.groups[0].ac_block_count == 2
    assert run.groups[0].ac_output["num_blocks"] == 2
    assert run.ac_power_mw_total == 20.0


def test_settings_only_run_leaves_mva_unresolved_and_unioned():
    # No product binding, no owner MVA -> transformer_mva stays unresolved and
    # is surfaced on the run's union so downstream SLD/report stay gated.
    run = build_governed_site_run(14, bind_products=False)
    assert all(g.bound_product_code is None for g in run.groups)
    assert "transformer_mva" in run.provisional_unresolved
    assert all("transformer_mva" in g.provisional_unresolved for g in run.groups)


def test_product_bound_run_removes_mva_tbd(seeded_db):
    run = build_governed_site_run(14, db_url=seeded_db, bind_products=True)
    # The head and the 4-DC / 2-DC tails all have a catalogue product.
    head, tail4, tail2 = run.groups
    assert head.bound_product_code is not None
    assert head.ac_output["transformer_mva"] == 10.0
    assert tail4.bound_product_code is not None
    assert tail4.ac_output["transformer_mva"] == 5.0
    assert tail2.bound_product_code is not None
    assert tail2.ac_output["transformer_mva"] == 2.5
    # MVA resolved everywhere -> not on the run's unresolved union.
    assert "transformer_mva" not in run.provisional_unresolved
    # The bound head is the real three-winding skid (Dy11(-)y11 dual secondary).
    assert head.ac_output["transformer_vector_group"].startswith("Dy11")
    assert head.ac_output["transformer_vector_group"].count("y11") == 2
    assert normalize_ac_output_for_sld(head.ac_output).lv_winding_count == 2


def test_one_dc_tail_has_no_product_but_still_runs(seeded_db):
    # 15 = 8 + 4 + 2 + 1; the 1-DC tail has no catalogue product yet still
    # produces a valid AC output (settings/provisional), never dropped.
    run = build_governed_site_run(15, db_url=seeded_db, bind_products=True)
    codes = [g.configuration_code for g in run.groups]
    assert "ACBLK-1P25MW-1PCS-1DC-20FT-LINEAR" in codes
    one = next(g for g in run.groups if g.dc_blocks_per_ac_block == 1)
    assert one.bound_product_code is None
    assert one.eligible_product_codes == ()
    assert one.ac_output["num_blocks"] == 1
    # No product and no owner MVA -> the 1-DC tail stays gated (MVA never
    # fabricated), so it is reported unresolved rather than silently rendered.
    assert "transformer_mva" in one.provisional_unresolved
    assert "transformer_mva" in run.provisional_unresolved


def test_run_totals_match_group_sum(seeded_db):
    run = build_governed_site_run(190, db_url=seeded_db, bind_products=True)  # 23x8 + 4 + 2
    assert run.ac_blocks_total == sum(g.ac_block_count for g in run.groups)
    assert run.dc_blocks_total == sum(g.dc_blocks_total for g in run.groups)
    assert run.ac_power_mw_total == pytest.approx(
        sum(g.ac_power_mw_total for g in run.groups)
    )
