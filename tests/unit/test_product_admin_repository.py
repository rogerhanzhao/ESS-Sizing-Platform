from __future__ import annotations

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.session import create_engine_for_url
from calb_sizing_tool.services.product_catalog_seed_service import (
    DEFAULT_314_DEGRADATION_CURVE_CODE,
    ProductCatalogSeedService,
)
from calb_sizing_tool.services.product_admin_service import ProductAdminService


def test_product_admin_service_creates_phase_b_records(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'product_admin.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    service = ProductAdminService(db_url)
    cell_id = service.create_cell(
        {
            "cell_code": "LFP-314",
            "model_name": "LFP 314Ah",
            "chemistry": "LFP",
            "nominal_capacity_ah": 314.0,
            "nominal_voltage_v": 3.2,
        }
    )
    service.create_dc_block(
        {
            "block_code": "DC-5MWH",
            "block_name": "5MWh DC Block",
            "product_cell_id": cell_id,
            "cells_in_series": 416,
            "strings_in_parallel": 12,
        }
    )
    service.create_ac_block(
        {
            "block_code": "AC-2500",
            "block_name": "2.5MW AC Block",
            "pcs_model": "PCS-1250",
            "pcs_power_kw": 1250.0,
            "pcs_count": 2,
        }
    )
    service.create_asset(
        {
            "asset_code": "DC-5MWH-DATASHEET",
            "owner_entity": "product_dc_block",
            "owner_code": "DC-5MWH",
            "asset_kind": "datasheet",
            "title": "5MWh DC Block Datasheet",
            "proposal_section": "Standard Product Information",
            "data_json": {"block_code": "DC-5MWH"},
        }
    )
    service.create_degradation_curve(
        {
            "curve_code": "DEG-LFP-25C",
            "product_cell_id": cell_id,
            "condition_label": "25C / 80 DoD",
            "temperature_c": 25.0,
            "dod_pct": 80.0,
        }
    )
    service.create_rte_curve(
        {
            "curve_code": "RTE-LFP-25C",
            "product_cell_id": cell_id,
            "condition_label": "25C nominal",
            "rte_pct": 93.0,
        }
    )
    service.create_plugin(
        {
            "plugin_key": "pybamm",
            "name": "PyBaMM",
            "plugin_version": "1.0.0",
            "entrypoint": "calb_sizing_tool.plugins.degradation.pybamm:simulate",
            "schema_version": "v1",
        }
    )

    snapshot = service.snapshot()
    assert snapshot["counts"] == {
        "product_cell": 1,
        "product_dc_block": 1,
        "product_ac_block": 1,
        "product_asset": 1,
        "degradation_curve": 1,
        "rte_curve": 1,
        "degradation_plugin": 1,
    }
    assert snapshot["cells"][0]["cell_code"] == "LFP-314"
    assert snapshot["dc_blocks"][0]["product_cell_id"] == cell_id


def test_product_admin_service_updates_records(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'product_admin_update.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    service = ProductAdminService(db_url)
    cell_id = service.create_cell(
        {
            "cell_code": "LFP-280",
            "model_name": "LFP 280Ah",
            "chemistry": "LFP",
        }
    )

    assert service.update_record(
        "cell",
        cell_id,
        {
            "model_name": "LFP 280Ah Rev B",
            "nominal_capacity_ah": 281.0,
            "is_active": False,
            "is_published": True,
        },
    )

    snapshot = service.snapshot()
    row = snapshot["cells"][0]
    assert row["model_name"] == "LFP 280Ah Rev B"
    assert row["nominal_capacity_ah"] == 281.0
    assert row["is_active"] is False
    assert row["is_published"] is True


def test_product_catalog_seed_from_brochure_defaults(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'product_catalog_seed.sqlite').as_posix()}"
    engine = create_engine_for_url(db_url)
    Base.metadata.create_all(bind=engine)

    result = ProductCatalogSeedService(db_url).seed_brochure_catalog()

    assert result == {"cells": 6, "degradation_curves": 12, "dc_blocks": 4, "assets": 10}
    snapshot = ProductAdminService(db_url).snapshot()
    cell_codes = {row["cell_code"] for row in snapshot["cells"]}
    block_codes = {row["block_code"] for row in snapshot["dc_blocks"]}
    assert "CALB-280AH" not in cell_codes
    assert {"CALB-314AH-A", "CALB-314AH-B", "CALB-588AH", "CALB-661AH"}.issubset(cell_codes)
    assert {
        "CALB-418KWH-DC-CABINET-314AH",
        "CALB-5P01596MWH-20FT-314AH",
        "CALB-6P26208MWH-20FT-588AH",
        "CALB-10P05143MWH-10500MM-661AH",
    }.issubset(block_codes)

    five_mwh = next(row for row in snapshot["dc_blocks"] if row["block_code"] == "CALB-5P01596MWH-20FT-314AH")
    six_mwh = next(row for row in snapshot["dc_blocks"] if row["block_code"] == "CALB-6P26208MWH-20FT-588AH")
    assert five_mwh["rated_capacity_kwh"] == 5015.96
    assert five_mwh["default_degradation_curve_code"] == DEFAULT_314_DEGRADATION_CURVE_CODE
    assert six_mwh["default_degradation_curve_code"] is None
    asset_codes = {row["asset_code"] for row in snapshot["assets"]}
    assert "CALB-5P01596MWH-20FT-314AH-DATASHEET" in asset_codes
    assert "CALB-314AH-B-DATASHEET" in asset_codes
