"""Preset AC Block product seed loader.

Verifies the vendor-datasheet catalogue loads into product_ac_block, is
idempotent (re-running updates in place, never duplicates), and preserves the
governed 10 MW products' key confirmed values while leaving unpublished fields
(transformer Uk%) null.
"""
from __future__ import annotations

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import ProductACBlock
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.services.ac_block_product_seed_service import (
    load_seed_document,
    seed_ac_block_products,
)


def _db(tmp_path) -> str:
    db_url = f"sqlite:///{(tmp_path / 'ac_products.sqlite').as_posix()}"
    Base.metadata.create_all(bind=create_engine_for_url(db_url))
    return db_url


EXPECTED_PRODUCT_COUNT = 18


def test_seed_document_is_wellformed():
    doc = load_seed_document()
    codes = [p["block_code"] for p in doc["products"]]
    assert "SINENG-EH-10000-HB-UD-10-33" in codes
    assert "NR-PCS9567MV-10000-V2.3" in codes
    assert "KEHUA-BCS10000K-C-HUD-T8" in codes
    assert len(codes) == len(set(codes))  # unique block codes
    assert len(codes) == EXPECTED_PRODUCT_COUNT


def test_seed_creates_all_products(tmp_path):
    db_url = _db(tmp_path)
    result = seed_ac_block_products(db_url=db_url)
    assert result["total"] == EXPECTED_PRODUCT_COUNT
    assert len(result["created"]) == EXPECTED_PRODUCT_COUNT
    assert result["updated"] == []
    with session_scope(db_url) as session:
        assert session.query(ProductACBlock).count() == EXPECTED_PRODUCT_COUNT


def test_seed_is_idempotent(tmp_path):
    db_url = _db(tmp_path)
    seed_ac_block_products(db_url=db_url)
    second = seed_ac_block_products(db_url=db_url)
    assert second["created"] == []
    assert len(second["updated"]) == EXPECTED_PRODUCT_COUNT
    with session_scope(db_url) as session:
        assert session.query(ProductACBlock).count() == EXPECTED_PRODUCT_COUNT  # no duplicates


def test_governed_10mw_products_carry_confirmed_values(tmp_path):
    db_url = _db(tmp_path)
    seed_ac_block_products(db_url=db_url)
    with session_scope(db_url) as session:
        sineng = (
            session.query(ProductACBlock)
            .filter_by(block_code="SINENG-EH-10000-HB-UD-10-33")
            .one()
        )
        # 10 MW / 8 x 1250 kW / 40 ft, three-winding Dy11y11, ONAN, 690 V.
        assert sineng.transformer_kva == 10000.0
        assert sineng.pcs_count == 8
        assert sineng.pcs_power_kw == 1250.0
        assert sineng.lv_voltage_v == 690.0
        assert sineng.metadata_json["transformer_vector_group"] == "Dy11y11"
        assert sineng.metadata_json["transformer_topology"] == "three_winding"
        assert sineng.metadata_json["transformer_cooling"] == "ONAN"
        assert sineng.metadata_json["dc_inputs"] == 8
        # Uk% is not published on the datasheet — must stay null, not inferred.
        assert sineng.metadata_json["transformer_uk_percent"] is None

        nr = (
            session.query(ProductACBlock)
            .filter_by(block_code="NR-PCS9567MV-10000-V2.3")
            .one()
        )
        assert nr.transformer_kva == 10000.0
        assert nr.metadata_json["transformer_vector_group"] == "Dy11-y11"
        assert nr.metadata_json["pcs_inverter_blocks"] == 8

        kehua = (
            session.query(ProductACBlock)
            .filter_by(block_code="KEHUA-BCS10000K-C-HUD-T8")
            .one()
        )
        # Kehua 10 MW skid: 8 DC inputs -> 8 x 1250 kW, three-winding Dy11-y11.
        assert kehua.transformer_kva == 10000.0
        assert kehua.pcs_count == 8
        assert kehua.pcs_power_kw == 1250.0
        assert kehua.metadata_json["dc_inputs"] == 8
        assert kehua.metadata_json["transformer_vector_group"] == "Dy11-y11"
        assert kehua.metadata_json["transformer_topology"] == "three_winding"


def test_seed_updates_changed_scalar_values(tmp_path):
    db_url = _db(tmp_path)
    seed_ac_block_products(db_url=db_url)
    with session_scope(db_url) as session:
        row = session.query(ProductACBlock).filter_by(block_code="NR-PCS9567MV-5000-V2.2").one()
        row.transformer_kva = 1.0  # simulate drift
    seed_ac_block_products(db_url=db_url)
    with session_scope(db_url) as session:
        row = session.query(ProductACBlock).filter_by(block_code="NR-PCS9567MV-5000-V2.2").one()
        assert row.transformer_kva == 5000.0  # restored from seed
