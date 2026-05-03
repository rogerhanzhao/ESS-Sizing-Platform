from __future__ import annotations

import math
import posixpath
import zipfile
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from calb_sizing_tool.infra.db.models import DegradationCurve, ProductAsset, ProductCell, ProductDCBlock
from calb_sizing_tool.infra.db.session import session_scope

DEFAULT_314_EXCEL_PATH = Path("data/ess_sizing_data_dictionary_v13_dc_autofit_rte314_fix05_025C94_v2.xlsx")
DEFAULT_BROCHURE_SOURCE = "New Microsoft PowerPoint Presentation.pptx"
DEFAULT_314_DEGRADATION_CURVE_CODE = "DEG-CALB-314AH-0P5C-365CY"


class ProductCatalogSeedService:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url

    def seed_brochure_catalog(
        self,
        *,
        excel_path: Path | str = DEFAULT_314_EXCEL_PATH,
        brochure_source: str = DEFAULT_BROCHURE_SOURCE,
        brochure_pptx_path: Path | str | None = None,
        asset_root: Path | str = Path("var/product_assets"),
    ) -> dict[str, int]:
        excel_path = Path(excel_path)
        pptx_path = Path(brochure_pptx_path) if brochure_pptx_path else None
        asset_root = Path(asset_root)
        with session_scope(self.db_url) as session:
            cells = _seed_cells(session, brochure_source=brochure_source)
            curves = _seed_314_degradation_curves(
                session,
                cell_id_by_code=cells,
                excel_path=excel_path,
                brochure_source=brochure_source,
            )
            blocks = _seed_dc_blocks(
                session,
                cell_id_by_code=cells,
                brochure_source=brochure_source,
            )
            assets = _seed_product_assets(
                session,
                cell_id_by_code=cells,
                block_id_by_code=blocks,
                brochure_source=brochure_source,
                brochure_pptx_path=pptx_path,
                asset_root=asset_root,
            )
            return {
                "cells": len(cells),
                "degradation_curves": curves,
                "dc_blocks": len(blocks),
                "assets": assets,
            }


def _seed_cells(session: Session, *, brochure_source: str) -> dict[str, str]:
    rows = [
        {
            "cell_code": "CALB-314AH-A",
            "model_name": "CALB 314Ah-A LFP",
            "chemistry": "LFP",
            "manufacturer": "CALB",
            "nominal_capacity_ah": 314.0,
            "shipping_capacity_ah": 321.0,
            "nominal_voltage_v": 3.2,
            "rated_energy_wh": 1004.8,
            "length_mm": 174.7,
            "width_mm": 71.57,
            "height_mm": 207.2,
            "shoulder_height_mm": 204.57,
            "weight_kg": 5.56,
            "volume_l": 2.55,
            "gravimetric_density_wh_kg": 180.7,
            "volumetric_density_wh_l": 393.3,
            "energy_efficiency_pct": 94.5,
            "dcr_mohm": 0.45,
            "rated_c_rate_label": "0.5P",
            "cycle_life_cycles": 9000,
            "cycle_life_rate_label": "0.5P/0.5P",
            "cycle_life_dod_pct": 100.0,
            "end_of_life_soh_pct": 60.0,
            "manufacturing_process": "Winding",
            "launch_year": 2023,
            "notes": "PPT slide 2 314Ah-A specification; 280Ah intentionally excluded.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [1, 2],
                "raw_dimension": "174.7(W)*71.57(T)*207.2(Total H), 204.57(Shoulder H)",
                "raw_cycle_life": "9000cls @0.5P/0.5P >=60% SOH 100%DoD@25C",
            },
        },
        {
            "cell_code": "CALB-314AH-B",
            "model_name": "CALB 314Ah-B LFP",
            "chemistry": "LFP",
            "manufacturer": "CALB",
            "nominal_capacity_ah": 314.0,
            "shipping_capacity_ah": 321.0,
            "nominal_voltage_v": 3.2,
            "rated_energy_wh": 1004.8,
            "length_mm": 174.7,
            "width_mm": 71.6,
            "height_mm": 207.2,
            "shoulder_height_mm": 204.57,
            "weight_kg": 5.60,
            "volume_l": 2.55,
            "gravimetric_density_wh_kg": 179.4,
            "volumetric_density_wh_l": 393.3,
            "energy_efficiency_pct": 95.0,
            "dcr_mohm": 0.45,
            "rated_c_rate_label": "0.5P",
            "cycle_life_cycles": 15000,
            "cycle_life_rate_label": "0.5P/0.5P",
            "cycle_life_dod_pct": 100.0,
            "end_of_life_soh_pct": 60.0,
            "manufacturing_process": "Winding",
            "launch_year": 2024,
            "notes": "PPT slide 2 314Ah-B specification.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [1, 2],
                "raw_dimension": "174.7(W)*71.6(T)*207.2(Total H), shoulder height inherited from 314Ah platform table",
                "raw_cycle_life": "15000cls @0.5P/0.5P >=60% SOH 100%DoD@25C",
            },
        },
        {
            "cell_code": "CALB-588AH",
            "model_name": "CALB 588Ah LFP",
            "chemistry": "LFP",
            "manufacturer": "CALB",
            "nominal_capacity_ah": 588.0,
            "nominal_voltage_v": 3.2,
            "rated_energy_wh": 1881.6,
            "length_mm": 288.0,
            "width_mm": 72.5,
            "height_mm": 216.3,
            "gravimetric_density_wh_kg": 184.4,
            "rated_c_rate_label": "0.5P",
            "cycle_life_cycles": 12000,
            "cycle_life_rate_label": "0.5P",
            "end_of_life_soh_pct": 60.0,
            "manufacturing_process": "Winding",
            "launch_year": 2026,
            "notes": "PPT slide 1 588Ah roadmap data; used by 6.25MWh DC Block.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [1, 5],
                "raw_dimension": "288*72.5*216.3mm",
                "raw_cycle_life": "0.5P 12000 cls @60%",
            },
        },
        {
            "cell_code": "CALB-640AH",
            "model_name": "CALB 640Ah LFP",
            "chemistry": "LFP",
            "manufacturer": "CALB",
            "nominal_capacity_ah": 640.0,
            "nominal_voltage_v": 3.2,
            "rated_energy_wh": 2048.0,
            "rated_c_rate_label": "0.5P/0.25P",
            "cycle_life_cycles": 15000,
            "cycle_life_rate_label": "0.5P",
            "end_of_life_soh_pct": 60.0,
            "manufacturing_process": "Stacking",
            "launch_year": 2026,
            "notes": "PPT slide 1 roadmap data; no DC Block seeded yet.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [1],
                "raw_cycle_life": "0.5P 15000 cls @60%",
                "data_completeness": "partial",
            },
        },
        {
            "cell_code": "CALB-661AH",
            "model_name": "CALB 661Ah LFP",
            "chemistry": "LFP",
            "manufacturer": "CALB",
            "nominal_capacity_ah": 661.0,
            "nominal_voltage_v": 3.2,
            "rated_energy_wh": 2115.2,
            "rated_c_rate_label": "0.25P",
            "cycle_life_cycles": 15000,
            "cycle_life_rate_label": "0.25P",
            "end_of_life_soh_pct": 60.0,
            "manufacturing_process": "Stacking",
            "launch_year": 2026,
            "notes": "PPT slide 1 and slide 6 661Ah cell for 10MWh DC Block.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [1, 6],
                "raw_cycle_life": "0.25P 15000 cls @60%",
            },
        },
        {
            "cell_code": "CALB-684AH",
            "model_name": "CALB 684Ah LFP",
            "chemistry": "LFP",
            "manufacturer": "CALB",
            "nominal_capacity_ah": 684.0,
            "nominal_voltage_v": 3.2,
            "rated_energy_wh": 2188.8,
            "rated_c_rate_label": "0.25P",
            "cycle_life_cycles": 10000,
            "cycle_life_rate_label": "0.25P",
            "end_of_life_soh_pct": 60.0,
            "manufacturing_process": "Stacking",
            "launch_year": 2026,
            "notes": "PPT slide 1 roadmap data; no DC Block seeded yet.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [1],
                "raw_cycle_life": "0.25P 10000 cls @60%",
                "data_completeness": "partial",
            },
        },
    ]
    return {
        row["cell_code"]: _upsert(session, ProductCell, "cell_code", row).product_cell_id
        for row in rows
    }


def _seed_314_degradation_curves(
    session: Session,
    *,
    cell_id_by_code: dict[str, str],
    excel_path: Path,
    brochure_source: str,
) -> int:
    if not excel_path.exists():
        return 0
    profile_df = pd.read_excel(excel_path, sheet_name="soh_profile_314_data")
    curve_df = pd.read_excel(excel_path, sheet_name="soh_curve_314_template")
    count = 0
    product_cell_id = cell_id_by_code.get("CALB-314AH-B") or cell_id_by_code.get("CALB-314AH-A")
    for profile in profile_df.to_dict(orient="records"):
        profile_id = _clean_int(profile.get("Profile_Id"))
        if profile_id is None:
            continue
        points = curve_df[curve_df["Profile_Id"] == profile_id].sort_values("Life_Year_Index")
        c_rate = _clean_float(profile.get("C_Rate"))
        cycles_per_year = _clean_int(profile.get("Cycles_Per_Year"))
        curve_code = _curve_code(c_rate, cycles_per_year)
        cycle_points = []
        calendar_points = []
        for point in points.to_dict(orient="records"):
            life_year = _clean_int(point.get("Life_Year_Index"))
            cycle_index = _clean_int(point.get("Cycle_Index"))
            soh = _clean_float(point.get("Soh_Dc_Pct"))
            if life_year is None or soh is None:
                continue
            payload = {
                "life_year_index": life_year,
                "cycle_index": cycle_index,
                "soh_relative": soh,
                "soh_pct": round(soh * 100.0, 6),
            }
            cycle_points.append(payload)
            calendar_points.append({"calendar_year": life_year, "soh_relative": soh, "soh_pct": payload["soh_pct"]})
        _upsert(
            session,
            DegradationCurve,
            "curve_code",
            {
                "curve_code": curve_code,
                "product_cell_id": product_cell_id,
                "curve_type": "hybrid_year_cycle",
                "curve_family": "CALB 314Ah default SOH",
                "basis_cell_code": "CALB-314AH",
                "default_scope": "314Ah DC Block",
                "data_status": "active_default_314Ah",
                "condition_label": str(profile.get("Profile_Name") or f"314Ah {c_rate}C {cycles_per_year}cy"),
                "temperature_c": _clean_float(profile.get("Reference_Temperature_C")),
                "dod_pct": None,
                "c_rate": c_rate,
                "calendar_years": max((p["life_year_index"] for p in cycle_points), default=None),
                "end_of_life_soh_pct": min((p["soh_pct"] for p in cycle_points), default=None),
                "cycle_points_json": cycle_points,
                "calendar_points_json": calendar_points,
                "source": str(excel_path.as_posix()),
                "notes": "Default project SOH curve from current 314Ah Excel dictionary. Used by 418kWh and 5MWh 314Ah products until product-specific curves are available.",
                "metadata_json": {
                    "source_document": brochure_source,
                    "source_excel": str(excel_path.as_posix()),
                    "source_sheets": ["soh_profile_314_data", "soh_curve_314_template"],
                    "source_profile_id": profile_id,
                    "cycles_per_year": cycles_per_year,
                    "c_rate": c_rate,
                },
            },
        )
        count += 1
    return count


def _seed_dc_blocks(session: Session, *, cell_id_by_code: dict[str, str], brochure_source: str) -> dict[str, str]:
    cell_314 = cell_id_by_code.get("CALB-314AH-B") or cell_id_by_code.get("CALB-314AH-A")
    rows = [
        {
            "block_code": "CALB-418KWH-DC-CABINET-314AH",
            "block_name": "CALB 418kWh DC Cabinet - 314Ah Platform",
            "product_model": None,
            "product_cell_id": cell_314,
            "cells_in_series": 416,
            "strings_in_parallel": 1,
            "racks_per_block": 1,
            "pack_count": 8,
            "configuration": "1P*52S*8S",
            "container_type": "DC Cabinet",
            "thermal_management": "Liquid Cooling",
            "gross_energy_mwh": 0.418,
            "rated_capacity_kwh": 418.0,
            "nominal_voltage_v": 1331.2,
            "nominal_power_kw": 209.0,
            "max_c_rate": 0.5,
            "charge_discharge_rate": "0.5P",
            "ingress_protection": "IP55",
            "relative_humidity": "0~95% (No Condensation)",
            "working_temp_min_c": -25.0,
            "working_temp_max_c": 50.0,
            "altitude_m": 3000.0,
            "bms_communication": "Ethernet/RS485/CAN",
            "compliance_standards": "EN 62477-1, EN 61000-6-2/4, IEC 62619, IEC 63056, UN 38.3",
            "default_degradation_curve_code": DEFAULT_314_DEGRADATION_CURVE_CODE,
            "notes": "PPT slide 3 418kWh DC Cabinet. Dimensions/weight were blank in source table.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [3],
                "raw_cell_label": "LFP 314Ah",
                "degradation_curve_status": "uses_current_314Ah_default",
            },
        },
        {
            "block_code": "CALB-5P01596MWH-20FT-314AH",
            "block_name": "CALB 5.01596MWh 20ft DC Container - 314Ah Platform",
            "product_model": "C173F5016",
            "product_cell_id": cell_314,
            "cells_in_series": 416,
            "strings_in_parallel": 12,
            "racks_per_block": 12,
            "racks_per_container": 12,
            "packs_per_rack": 4,
            "pack_count": 48,
            "container_count": 1,
            "configuration": "12P416S (12 racks); pack 1P104S; rack 1P416S",
            "container_type": "20ft ISO container",
            "thermal_management": "Smart liquid cooling/heating",
            "enclosure": "20ft / ISO container",
            "gross_energy_mwh": 5.01596,
            "rated_capacity_kwh": 5015.96,
            "nominal_voltage_v": 1331.2,
            "voltage_min_v": 1164.8,
            "voltage_max_v": 1476.8,
            "max_c_rate": 0.5,
            "charge_discharge_rate": "0.5P/0.5P",
            "dod_pct": 95.0,
            "cycle_life_cycles": 6000,
            "end_of_life_soh_pct": 80.0,
            "service_life_years": 20.0,
            "dimension_width_mm": 2438.0,
            "dimension_depth_mm": 6058.0,
            "dimension_height_mm": 2896.0,
            "weight_kg": 43000.0,
            "ingress_protection": "IP55",
            "relative_humidity": "<=95% (non-condensing)",
            "storage_temp_min_c": -30.0,
            "storage_temp_max_c": 55.0,
            "altitude_m": 3000.0,
            "compliance_standards": "UL9540A/UL1973/UN38.3/IEC62619/UL9540",
            "seismic_rating": ">=8",
            "coating": "RAL7035 / C4 Coating",
            "firefighting_system": "Aerosol-based suppression system, pipe sprinkler system",
            "explosion_protection": "Explosion Relief Panel (NFPA68-2023)",
            "default_degradation_curve_code": DEFAULT_314_DEGRADATION_CURVE_CODE,
            "notes": "PPT slide 4 314Ah Platform 5MWh DC Container. Source row '5.015.96MWh' normalized to 5.01596MWh.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [4],
                "raw_nominal_capacity": "5.015.96MWh",
                "normalized_nominal_capacity_mwh": 5.01596,
                "degradation_curve_status": "uses_current_314Ah_default",
            },
        },
        {
            "block_code": "CALB-6P26208MWH-20FT-588AH",
            "block_name": "CALB 6.26208MWh 20ft DC Container - 588Ah Platform",
            "product_cell_id": cell_id_by_code.get("CALB-588AH"),
            "cells_in_series": 416,
            "strings_in_parallel": 8,
            "racks_per_block": 8,
            "racks_per_container": 8,
            "packs_per_rack": 4,
            "pack_count": 32,
            "container_count": 1,
            "configuration": "1P*416S*8; 4*8 packs",
            "container_type": "20ft DC Container",
            "thermal_management": "Liquid Cooling",
            "gross_energy_mwh": 6.26208,
            "rated_capacity_kwh": 6262.08,
            "nominal_voltage_v": 1331.2,
            "max_c_rate": 0.5,
            "charge_discharge_rate": "0.25P/0.5P",
            "cycle_life_cycles": 10000,
            "system_efficiency_pct": 95.0,
            "dimension_width_mm": 2438.0,
            "dimension_depth_mm": 6058.0,
            "dimension_height_mm": 2896.0,
            "ingress_protection": "IP55",
            "relative_humidity": "0~95% (No Condensation)",
            "working_temp_min_c": -25.0,
            "working_temp_max_c": 50.0,
            "altitude_m": 3000.0,
            "bms_communication": "Ethernet/RS485/CAN",
            "default_degradation_curve_code": None,
            "notes": "PPT slide 5 6.25MWh DC-Block. Product-specific degradation curve not available yet.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [5],
                "degradation_curve_status": "pending_product_specific_curve",
            },
        },
        {
            "block_code": "CALB-10P05143MWH-10500MM-661AH",
            "block_name": "CALB 10.05143MWh DC Block - 661Ah Platform",
            "product_cell_id": cell_id_by_code.get("CALB-661AH"),
            "cells_in_series": 396,
            "strings_in_parallel": 12,
            "container_count": 4,
            "configuration": "1P*396S*4*3",
            "container_type": "10ft*3 + 5ft*1 modular DC Block",
            "thermal_management": "Liquid Cooling",
            "gross_energy_mwh": 10.05143,
            "rated_capacity_kwh": 10051.43,
            "nominal_voltage_v": 1331.2,
            "max_c_rate": 0.25,
            "charge_discharge_rate": "0.25P",
            "cycle_life_cycles": 15000,
            "system_efficiency_pct": 96.0,
            "dimension_width_mm": 2438.0,
            "dimension_depth_mm": 10500.0,
            "dimension_height_mm": 3246.0,
            "ingress_protection": "IP55",
            "relative_humidity": "0~95% (No Condensation)",
            "working_temp_min_c": -25.0,
            "working_temp_max_c": 50.0,
            "altitude_m": 3000.0,
            "bms_communication": "Ethernet/RS485/CAN",
            "default_degradation_curve_code": None,
            "notes": "PPT slide 6 10MWh DC-Block. Product-specific degradation curve not available yet.",
            "metadata_json": {
                "source_document": brochure_source,
                "source_slides": [6],
                "raw_configuration": "1P*396S*4*3",
                "source_nominal_voltage_v": 1331.2,
                "configuration_voltage_note": "396S at 3.2V implies 1267.2V; source table also states 1331.2V. Kept source nominal voltage and raw configuration for engineering review.",
                "degradation_curve_status": "pending_product_specific_curve",
            },
        },
    ]
    return {
        row["block_code"]: _upsert(session, ProductDCBlock, "block_code", row).product_dc_block_id
        for row in rows
    }


def _seed_product_assets(
    session: Session,
    *,
    cell_id_by_code: dict[str, str],
    block_id_by_code: dict[str, str],
    brochure_source: str,
    brochure_pptx_path: Path | None,
    asset_root: Path,
) -> int:
    count = 0
    for cell_code, product_cell_id in cell_id_by_code.items():
        row = session.query(ProductCell).filter(ProductCell.product_cell_id == product_cell_id).one()
        _upsert(
            session,
            ProductAsset,
            "asset_code",
            _datasheet_asset(
                owner_entity="product_cell",
                owner_id=product_cell_id,
                owner_code=cell_code,
                title=f"{row.model_name} Datasheet",
                source=row,
                brochure_source=brochure_source,
                sort_order=10,
            ),
        )
        count += 1

    for block_code, product_dc_block_id in block_id_by_code.items():
        row = session.query(ProductDCBlock).filter(ProductDCBlock.product_dc_block_id == product_dc_block_id).one()
        _upsert(
            session,
            ProductAsset,
            "asset_code",
            _datasheet_asset(
                owner_entity="product_dc_block",
                owner_id=product_dc_block_id,
                owner_code=block_code,
                title=f"{row.block_name} Datasheet",
                source=row,
                brochure_source=brochure_source,
                sort_order=20,
            ),
        )
        count += 1

    slide_images = _extract_brochure_images(brochure_pptx_path, asset_root) if brochure_pptx_path else {}
    image_map = {
        2: [("product_cell", "CALB-314AH-A", cell_id_by_code.get("CALB-314AH-A")),
            ("product_cell", "CALB-314AH-B", cell_id_by_code.get("CALB-314AH-B"))],
        3: [("product_dc_block", "CALB-418KWH-DC-CABINET-314AH", block_id_by_code.get("CALB-418KWH-DC-CABINET-314AH"))],
        4: [("product_dc_block", "CALB-5P01596MWH-20FT-314AH", block_id_by_code.get("CALB-5P01596MWH-20FT-314AH"))],
        5: [("product_cell", "CALB-588AH", cell_id_by_code.get("CALB-588AH")),
            ("product_dc_block", "CALB-6P26208MWH-20FT-588AH", block_id_by_code.get("CALB-6P26208MWH-20FT-588AH"))],
        6: [("product_cell", "CALB-661AH", cell_id_by_code.get("CALB-661AH")),
            ("product_dc_block", "CALB-10P05143MWH-10500MM-661AH", block_id_by_code.get("CALB-10P05143MWH-10500MM-661AH"))],
    }
    for slide_no, owners in image_map.items():
        images = slide_images.get(slide_no) or []
        if not images:
            continue
        primary = images[0]
        for owner_entity, owner_code, owner_id in owners:
            if not owner_id:
                continue
            _upsert(
                session,
                ProductAsset,
                "asset_code",
                {
                    "asset_code": f"{owner_code}-IMAGE-SLIDE{slide_no}",
                    "owner_entity": owner_entity,
                    "owner_id": owner_id,
                    "owner_code": owner_code,
                    "asset_kind": "product_image",
                    "title": f"{owner_code} Product Image",
                    "file_name": primary["file_name"],
                    "mime_type": primary["mime_type"],
                    "source_path": str(brochure_pptx_path.as_posix()),
                    "storage_uri": primary["storage_uri"],
                    "content_sha256": primary["content_sha256"],
                    "caption": f"Product image from brochure slide {slide_no}.",
                    "proposal_section": "Standard Product Information",
                    "sort_order": 30 + slide_no,
                    "is_primary": True,
                    "data_json": {
                        "source_slide": slide_no,
                        "media_name": primary["media_name"],
                        "size_bytes": primary["size_bytes"],
                    },
                    "metadata_json": {
                        "source_document": brochure_source,
                        "source_slides": [slide_no],
                        "asset_extraction": "pptx_media_largest_image_per_slide",
                    },
                },
            )
            count += 1
    return count


def _datasheet_asset(
    *,
    owner_entity: str,
    owner_id: str,
    owner_code: str,
    title: str,
    source: Any,
    brochure_source: str,
    sort_order: int,
) -> dict[str, Any]:
    data = {
        column.name: _json_value(getattr(source, column.name))
        for column in source.__table__.columns
        if column.name not in {"metadata_json", "created_at", "updated_at"}
    }
    metadata = dict(getattr(source, "metadata_json", {}) or {})
    return {
        "asset_code": f"{owner_code}-DATASHEET",
        "owner_entity": owner_entity,
        "owner_id": owner_id,
        "owner_code": owner_code,
        "asset_kind": "datasheet",
        "title": title,
        "file_name": None,
        "mime_type": "application/json",
        "source_path": brochure_source,
        "storage_uri": None,
        "content_sha256": None,
        "caption": f"Structured datasheet record for {owner_code}.",
        "proposal_section": "Standard Product Information",
        "sort_order": sort_order,
        "is_primary": True,
        "data_json": data,
        "metadata_json": {
            "source_document": brochure_source,
            "source_slides": metadata.get("source_slides", []),
            "proposal_usage": "standard_product_information_chapter",
        },
    }


def _extract_brochure_images(pptx_path: Path | None, asset_root: Path) -> dict[int, list[dict[str, Any]]]:
    if not pptx_path or not pptx_path.exists():
        return {}
    destination = asset_root / "product_brochure"
    destination.mkdir(parents=True, exist_ok=True)
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    images_by_slide: dict[int, list[dict[str, Any]]] = {}
    with zipfile.ZipFile(pptx_path) as zf:
        rel_files = sorted(
            name for name in zf.namelist()
            if name.startswith("ppt/slides/_rels/slide") and name.endswith(".xml.rels")
        )
        for rel_file in rel_files:
            slide_no = _slide_no_from_rels(rel_file)
            if slide_no is None:
                continue
            root = ET.fromstring(zf.read(rel_file))
            for rel in root.findall("r:Relationship", rel_ns):
                rel_type = rel.attrib.get("Type", "")
                if not rel_type.endswith("/image"):
                    continue
                target = rel.attrib.get("Target")
                if not target:
                    continue
                media_path = posixpath.normpath(posixpath.join("ppt/slides", target))
                if media_path not in zf.namelist():
                    continue
                blob = zf.read(media_path)
                digest = sha256(blob).hexdigest()
                suffix = Path(media_path).suffix.lower() or ".bin"
                out_name = f"slide_{slide_no}_{Path(media_path).stem}_{digest[:10]}{suffix}"
                out_path = destination / out_name
                if not out_path.exists():
                    out_path.write_bytes(blob)
                images_by_slide.setdefault(slide_no, []).append(
                    {
                        "media_name": media_path,
                        "file_name": out_name,
                        "mime_type": _mime_type(suffix),
                        "storage_uri": out_path.as_posix(),
                        "content_sha256": digest,
                        "size_bytes": len(blob),
                    }
                )
    for images in images_by_slide.values():
        images.sort(key=lambda item: item["size_bytes"], reverse=True)
    return images_by_slide


def _slide_no_from_rels(rel_file: str) -> int | None:
    stem = Path(rel_file).name.split(".")[0]
    if not stem.startswith("slide"):
        return None
    try:
        return int(stem.removeprefix("slide"))
    except ValueError:
        return None


def _mime_type(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".emf": "image/x-emf",
        ".wmf": "image/x-wmf",
    }.get(suffix.lower(), "application/octet-stream")


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _upsert(session: Session, model: type, unique_field: str, values: dict[str, Any]) -> Any:
    key_value = values[unique_field]
    row = session.query(model).filter(getattr(model, unique_field) == key_value).one_or_none()
    values = {k: v for k, v in values.items() if v is not None or k in {"default_degradation_curve_code"}}
    values.setdefault("source_ref", "product_brochure_seed")
    values.setdefault("is_active", True)
    values.setdefault("is_published", True)
    if row is None:
        row = model(**values)
    else:
        valid_columns = {column.name for column in row.__table__.columns}
        for key, value in values.items():
            if key in valid_columns:
                setattr(row, key, value)
    session.add(row)
    session.flush()
    return row


def _curve_code(c_rate: float | None, cycles_per_year: int | None) -> str:
    rate = str(c_rate).replace(".", "P") if c_rate is not None else "NA"
    cycles = str(cycles_per_year) if cycles_per_year is not None else "NA"
    return f"DEG-CALB-314AH-{rate}C-{cycles}CY"


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    except Exception:
        return None


def _clean_int(value: Any) -> int | None:
    number = _clean_float(value)
    return int(number) if number is not None else None
