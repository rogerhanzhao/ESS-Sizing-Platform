"""Bind the governed configuration to the real product catalogue.

Selecting an actual 10 MW / 8-DC / three-winding product (Sineng EH-10000, NR
PCS-9567MV-10000, Kehua BCS10000K-C-HUD/T8) supplies the transformer nameplate /
LV / vector / cooling from the datasheet-derived record, removing the MVA "TBD"
using real product data. Uk% is never published, so it stays unresolved.
"""
from __future__ import annotations

import pytest

from calb_sizing_tool.adapters.ac_to_sld_adapter import normalize_ac_output_for_sld
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.ac_block_product_seed_service import seed_ac_block_products
from calb_sizing_tool.services.governed_ac_block_service import (
    build_governed_ac_output_from_product,
    build_governed_site_plan,
    eligible_products_for,
    product_overrides,
)
from calb_sizing_tool.schemas.governed_ac_block_config import (
    ACBLK_10MW_8PCS_8DC_40FT_BILATERAL as CFG,
)

CODE = "ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"


@pytest.fixture()
def seeded_db(tmp_path) -> str:
    db_url = f"sqlite:///{(tmp_path / 'products.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    seed_ac_block_products(db_url=db_url)
    return db_url


def test_eligible_products_are_the_three_10mw_8dc_skids(seeded_db):
    codes = {p["block_code"] for p in eligible_products_for(CODE, db_url=seeded_db)}
    assert codes == {
        "SINENG-EH-10000-HB-UD-10-33",
        "NR-PCS9567MV-10000-V2.3",
        "KEHUA-BCS10000K-C-HUD-T8",
    }


def test_product_overrides_pull_confirmed_values(seeded_db):
    ov = product_overrides("SINENG-EH-10000-HB-UD-10-33", CFG, db_url=seeded_db)
    assert ov["transformer_mva"] == 10.0          # 10000 kVA, not 11.11
    assert ov["lv_voltage_v"] == 690.0
    assert ov["transformer_vector_group"] == "Dy11y11"
    assert ov["transformer_cooling"] == "ONAN"
    assert ov["ac_station_length_m"] == 12.192     # 40 ft container footprint
    assert ov["ac_station_width_m"] == 2.438
    # Uk% is never sourced from a datasheet.
    assert "transformer_uk_percent" not in ov


def test_build_from_product_removes_mva_tbd_and_validates(seeded_db):
    out = build_governed_ac_output_from_product(
        CODE, "KEHUA-BCS10000K-C-HUD-T8", dc_blocks_total=8, db_url=seeded_db
    )
    assert out["transformer_mva"] == 10.0
    assert out["num_blocks"] == 1
    # MVA resolved from the product; Uk% is not a provisional blocker at all
    # (SLD uses a standard typical), so it never appears as unresolved.
    assert "transformer_mva" not in out["provisional_unresolved"]
    assert "transformer_uk_percent" not in out["provisional_unresolved"]
    norm = normalize_ac_output_for_sld(out)
    assert norm.transformer_mva == 10.0
    assert norm.lv_winding_count == 2


def test_engineering_settings_override_product_values(seeded_db):
    # Owner-entered MVA in settings must win over the product default.
    out = build_governed_ac_output_from_product(
        CODE,
        "SINENG-EH-10000-HB-UD-10-33",
        project_settings={"transformer_rating_mva": 11.0},
        dc_blocks_total=8,
        db_url=seeded_db,
    )
    assert out["transformer_mva"] == 11.0


def test_product_vector_group_and_cooling_thread_to_output(seeded_db):
    """The product's confirmed vector group must reach the AC output so the SLD
    draws the correct two-LV winding symbol (Dy11y11), without inferring an
    earth connection from any vector-group token."""
    out = build_governed_ac_output_from_product(
        CODE, "SINENG-EH-10000-HB-UD-10-33", dc_blocks_total=8, db_url=seeded_db
    )
    assert out["transformer_vector_group"] == "Dy11y11"
    assert out["transformer_cooling"] == "ONAN"
    assert out["governed_product_block_code"] == "SINENG-EH-10000-HB-UD-10-33"


def test_product_vector_group_cannot_be_silently_overridden_by_engineering_settings(seeded_db):
    out = build_governed_ac_output_from_product(
        CODE,
        "SINENG-EH-10000-HB-UD-10-33",
        project_settings={"transformer": {"vector_group": "Dyn11"}},
        dc_blocks_total=8,
        db_url=seeded_db,
    )

    assert out["transformer_vector_group"] == "Dy11y11"
    assert out["transformer_vector_group_conflict"] == {
        "product": "Dy11y11",
        "engineering_setting": "Dyn11",
    }


def test_multi_unit_from_product(seeded_db):
    out = build_governed_ac_output_from_product(
        CODE, "NR-PCS9567MV-10000-V2.3", dc_blocks_total=16, db_url=seeded_db
    )
    assert out["num_blocks"] == 2
    assert out["total_ac_mw"] == 20.0
    assert out["transformer_mva"] == 10.0


def test_unknown_product_rejected(seeded_db):
    with pytest.raises(ValueError):
        product_overrides("DOES-NOT-EXIST", CFG, db_url=seeded_db)


def test_tail_configs_bind_to_real_products(seeded_db):
    # 5 MW / 4-DC tail -> NR-5000 + Kehua BCS5000K (topology unknown, not excluded)
    five = {p["block_code"] for p in eligible_products_for("ACBLK-5MW-4PCS-4DC-40FT-LINEAR", db_url=seeded_db)}
    assert "NR-PCS9567MV-5000-V2.2" in five
    assert "KEHUA-BCS5000K-C-HUD-T4" in five
    # 2.5 MW / 2-DC tail -> Kehua BCS2500K variants
    two_five = {p["block_code"] for p in eligible_products_for("ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR", db_url=seeded_db)}
    assert "KEHUA-BCS2500K-C-HUD-T2" in two_five
    assert all("2500K" in code for code in two_five)
    # 1.25 MW / 1-DC tail -> no catalogue product at that size
    assert eligible_products_for("ACBLK-1P25MW-1PCS-1DC-20FT-LINEAR", db_url=seeded_db) == []


def test_site_plan_with_products_annotates_each_group(seeded_db):
    plan = build_governed_site_plan(14, db_url=seeded_db, with_products=True)  # 8 + 4 + 2
    by_code = {g.configuration_code: g for g in plan.groups}
    assert "SINENG-EH-10000-HB-UD-10-33" in by_code["ACBLK-10MW-8PCS-8DC-40FT-BILATERAL"].eligible_product_codes
    assert "NR-PCS9567MV-5000-V2.2" in by_code["ACBLK-5MW-4PCS-4DC-40FT-LINEAR"].eligible_product_codes
    assert by_code["ACBLK-2P5MW-2PCS-2DC-20FT-LINEAR"].eligible_product_codes  # non-empty


def test_site_plan_without_products_is_structural_only():
    plan = build_governed_site_plan(14)  # no db -> no product annotation
    assert all(g.eligible_product_codes == () for g in plan.groups)
