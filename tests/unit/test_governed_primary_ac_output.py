"""Single governed entry for ANY DC total (the AC Sizing page's governed run).

`build_governed_primary_ac_output` is what the AC Sizing governed panel stores for
any DC total, so a non-multiple-of-8 project reaches the governed identity instead
of the generic average-ratio grouping (23 x 4-PCS + a fabricated 5.56 MVA). The
head group stays a uniform, SLD-renderable block; a mixed site carries the true
site rollup + per-group breakdown for the report.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.ac_to_sld_adapter import normalize_ac_output_for_sld
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.ac_block_product_seed_service import seed_ac_block_products
from calb_sizing_tool.services.governed_ac_block_service import (
    build_governed_primary_ac_output,
)


@pytest.fixture()
def seeded_db(tmp_path) -> str:
    db_url = f"sqlite:///{(tmp_path / 'products.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    seed_ac_block_products(db_url=db_url)
    return db_url


def test_multiple_of_eight_is_plain_uniform_output():
    # 24 DC = 3 x 8 -> one governed group, no mixed rollup (identical to Phase A).
    out = build_governed_primary_ac_output(24)
    assert out["configuration_code"] == "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"
    assert out["num_blocks"] == 3
    assert out.get("governed_is_mixed") is None
    assert "governed_groups" not in out


def test_non_multiple_of_eight_reaches_governed_with_true_rollup():
    # 92 DC (the reported failing case) must NOT fall back to generic 23 x 4-PCS.
    out = build_governed_primary_ac_output(92)
    assert out["governed_configuration"] is True
    assert out["governed_is_mixed"] is True
    # Head stays the uniform 8-PCS bilateral block (SLD-renderable topology).
    assert out["pcs_per_block"] == 8
    assert out["num_blocks"] == 11
    # True site rollup: 11x10 MW + 1x5 MW = 12 AC blocks / 115 MW / 92 PCS.
    assert out["governed_site_ac_blocks_total"] == 12
    assert out["governed_site_total_ac_mw"] == 115.0
    assert out["governed_site_pcs_total"] == 92
    codes = [g["configuration_code"] for g in out["governed_groups"]]
    assert codes == [
        "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL",
        "ACBLK-5MW-4PCS-4DC-40FT-LINEAR",
    ]
    counts = {g["configuration_code"]: g["ac_block_count"] for g in out["governed_groups"]}
    assert counts["ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"] == 11
    assert counts["ACBLK-5MW-4PCS-4DC-40FT-LINEAR"] == 1


def test_settings_only_head_never_fabricates_mva():
    # No product, no owner MVA -> transformer_mva absent (gated), never 10/0.9.
    out = build_governed_primary_ac_output(92)
    assert "transformer_mva" not in out
    assert "transformer_mva" in out["provisional_unresolved"]


def test_head_product_resolves_head_mva_and_keeps_sld_renderable(seeded_db):
    out = build_governed_primary_ac_output(
        92,
        head_product_block_code="SINENG-EH-10000-HB-UD-10-33",
        db_url=seeded_db,
    )
    # Head nameplate comes from the real product (10 MVA), not MW / PF.
    assert out["transformer_mva"] == 10.0
    assert out["transformer_vector_group"].startswith("Dy11")
    # Head is still a single uniform, SLD-renderable block.
    norm = normalize_ac_output_for_sld(out)
    assert norm.transformer_mva == 10.0
    assert norm.lv_winding_count == 2
    assert norm.num_blocks == 11
    # The 5 MW tail auto-binds its own catalogue product in the rollup.
    tail = next(g for g in out["governed_groups"] if g["pcs_per_ac_block"] == 4)
    assert tail["bound_product_code"] is not None
    assert tail["transformer_mva"] == 5.0
    # Head MVA resolved -> no longer on the unresolved union.
    assert "transformer_mva" not in out["provisional_unresolved"]


def test_all_tail_site_below_eight_still_governed():
    # 6 DC = 4 + 2 (no 10 MW head at all) still resolves to governed groups.
    out = build_governed_primary_ac_output(6)
    assert out["governed_is_mixed"] is True
    codes = [g["configuration_code"] for g in out["governed_groups"]]
    assert codes == [
        "ACBLK-5MW-4PCS-4DC-40FT-LINEAR",
        "ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR",
    ]
    assert out["governed_site_total_ac_mw"] == 7.5
