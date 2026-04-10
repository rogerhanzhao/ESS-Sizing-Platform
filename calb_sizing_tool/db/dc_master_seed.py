from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID, uuid5

import pandas as pd

from calb_sizing_tool.common.nameplate import apply_block_nameplate_recalc
from calb_sizing_tool.config import DC_DATA_PATH


UUID_NAMESPACE = UUID("2c603d5f-32ce-4f4b-a02e-0d6cc64f6f6f")
DEFAULT_SEED_SQL_OUTPUT = Path("deploy/sql/003_seed_dc_master_data_from_excel.sql")


def stable_uuid(*parts: Any) -> str:
    token = "::".join("" if p is None else str(p) for p in parts)
    return str(uuid5(UUID_NAMESPACE, token))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_python(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if value.is_integer():
            return int(value)
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def as_int(value: Any) -> int | None:
    value = to_python(value)
    if value is None:
        return None
    return int(value)


def as_float(value: Any) -> float | None:
    value = to_python(value)
    if value is None:
        return None
    return float(value)


def as_bool_flag(value: Any) -> bool:
    value = to_python(value)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def clean_text(value: Any) -> str | None:
    value = to_python(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: to_python(value) for key, value in record.items()}


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "NULL"
        return format(value, ".15g")
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        escaped = text.replace("'", "''")
        return f"'{escaped}'::jsonb"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def insert_sql(table: str, columns: Iterable[str], values: Iterable[Any]) -> str:
    col_list = ", ".join(columns)
    val_list = ", ".join(sql_literal(value) for value in values)
    return f"INSERT INTO {table} ({col_list}) VALUES ({val_list});"


def infer_vendor(model_or_code: str | None) -> str | None:
    if not model_or_code:
        return None
    token = model_or_code.strip().split("_", 1)[0].strip()
    return token or None


def default_import_version_label(workbook_name: str, workbook_sha: str) -> str:
    return f"{workbook_name}#{workbook_sha[:8]}"


def load_dc_workbook(workbook: Path) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(workbook)
    data = {
        "cells": pd.read_excel(xls, "battery_cell_type_314_data"),
        "packs": pd.read_excel(xls, "pack_type_314_data"),
        "racks": pd.read_excel(xls, "rack_type_314_data"),
        "blocks": pd.read_excel(xls, "dc_block_template_314_data"),
        "soh_profiles": pd.read_excel(xls, "soh_profile_314_data"),
        "soh_curves": pd.read_excel(xls, "soh_curve_314_template"),
        "rte_profiles": pd.read_excel(xls, "rte_profile_314_data"),
        "rte_curves": pd.read_excel(xls, "rte_curve_314_template"),
    }
    data["blocks"] = apply_block_nameplate_recalc(
        data["blocks"], data["racks"], data["packs"], data["cells"]
    )
    return data


def build_seed_payload(
    workbook: Path,
    version_label: str | None,
    activate_version: bool,
    output_sql: Path | None = None,
) -> dict[str, Any]:
    data = load_dc_workbook(workbook)
    rack_lookup = {
        as_int(record.get("Rack_Type_Id")): sanitize_record(record)
        for record in data["racks"].to_dict("records")
        if as_int(record.get("Rack_Type_Id")) is not None
    }
    workbook_sha = file_sha256(workbook)
    seeded_at = datetime.fromtimestamp(workbook.stat().st_mtime, tz=timezone.utc).replace(microsecond=0)
    timestamp = seeded_at.isoformat()
    dictionary_version_id = stable_uuid("dictionary_version", "dc", workbook_sha)
    publish_batch_id = stable_uuid("publish_batch", "dc", workbook_sha)
    effective_version_label = version_label or workbook.name

    dictionary_meta = {
        "source_workbook": workbook.name,
        "source_sha256": workbook_sha,
        "generated_sql": str(output_sql.as_posix()) if output_sql else None,
        "sheet_row_counts": {
            "battery_cell_type_314_data": int(len(data["cells"])),
            "pack_type_314_data": int(len(data["packs"])),
            "rack_type_314_data": int(len(data["racks"])),
            "dc_block_template_314_data": int(len(data["blocks"])),
            "soh_profile_314_data": int(len(data["soh_profiles"])),
            "soh_curve_314_template": int(len(data["soh_curves"])),
            "rte_profile_314_data": int(len(data["rte_profiles"])),
            "rte_curve_314_template": int(len(data["rte_curves"])),
        },
    }

    payload: dict[str, Any] = {
        "workbook": workbook,
        "workbook_sha": workbook_sha,
        "timestamp": timestamp,
        "dictionary_version": {
            "dictionary_version_id": dictionary_version_id,
            "domain_code": "dc",
            "version_label": effective_version_label,
            "source_file_name": workbook.name,
            "source_file_sha256": workbook_sha,
            "is_active": activate_version,
            "loaded_at": timestamp,
            "meta_json": dictionary_meta,
        },
        "cells": [],
        "packs": [],
        "racks": [],
        "blocks": [],
        "soh_profiles": [],
        "soh_curve_points": [],
        "rte_profiles": [],
        "rte_curve_points": [],
        "publish_batch": None,
        "publish_batch_items": [],
    }

    cell_revision_ids: list[str] = []
    block_revision_ids: list[str] = []

    for row in data["cells"].sort_values("Cell_Type_Id").to_dict("records"):
        record = sanitize_record(row)
        source_cell_type_id = as_int(record.get("Cell_Type_Id"))
        cell_model = clean_text(record.get("Cell_Model"))
        if source_cell_type_id is None or cell_model is None:
            continue
        cell_master_id = stable_uuid("battery_cell_master", cell_model)
        cell_revision_id = stable_uuid("battery_cell_revision", cell_model, workbook_sha)
        cell_revision_ids.append(cell_revision_id)
        is_active = as_bool_flag(record.get("Is_Active"))
        payload["cells"].append(
            {
                "master": {
                    "cell_master_id": cell_master_id,
                    "cell_code": cell_model,
                    "cell_model": cell_model,
                    "vendor_name": infer_vendor(cell_model),
                    "chemistry_code": clean_text(record.get("Cell_Chemistry")),
                    "record_status": "active" if is_active else "inactive",
                    "remarks": f"Seeded from {workbook.name}",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                "revision": {
                    "cell_revision_id": cell_revision_id,
                    "cell_master_id": cell_master_id,
                    "revision_no": 1,
                    "revision_status": "published",
                    "source_type": "imported",
                    "published_dictionary_version_id": dictionary_version_id,
                    "nominal_capacity_ah": as_float(record.get("Cell_Capacity_Ah")),
                    "nominal_voltage_v": as_float(record.get("Cell_Nominal_Voltage_V")),
                    "nominal_energy_wh": as_float(record.get("Cell_Energy_Wh")),
                    "parameter_json": {
                        "source_kind": "excel_seed",
                        "source_sheet": "battery_cell_type_314_data",
                        "source_cell_type_id": source_cell_type_id,
                        "raw_row_json": record,
                    },
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "published_at": timestamp,
                },
                "snapshot": {
                    "cell_type_id": stable_uuid("battery_cell_type", workbook_sha, source_cell_type_id),
                    "dictionary_version_id": dictionary_version_id,
                    "source_cell_master_id": cell_master_id,
                    "source_cell_revision_id": cell_revision_id,
                    "source_cell_type_id": source_cell_type_id,
                    "cell_model": cell_model,
                    "cell_capacity_ah": as_float(record.get("Cell_Capacity_Ah")),
                    "cell_nominal_voltage_v": as_float(record.get("Cell_Nominal_Voltage_V")),
                    "cell_energy_wh": as_float(record.get("Cell_Energy_Wh")),
                    "raw_row_json": record,
                },
            }
        )

    for row in data["packs"].sort_values("Pack_Type_Id").to_dict("records"):
        record = sanitize_record(row)
        source_pack_type_id = as_int(record.get("Pack_Type_Id"))
        if source_pack_type_id is None:
            continue
        payload["packs"].append(
            {
                "pack_type_id": stable_uuid("pack_type", workbook_sha, source_pack_type_id),
                "dictionary_version_id": dictionary_version_id,
                "source_pack_type_id": source_pack_type_id,
                "source_cell_type_id": as_int(record.get("Cell_Type_Id")),
                "cells_in_series": as_int(record.get("Cells_In_Series")),
                "cells_in_parallel": as_int(record.get("Cells_In_Parallel")),
                "pack_nominal_voltage_v": as_float(record.get("Pack_Nominal_Voltage_V")),
                "raw_row_json": record,
            }
        )

    for row in data["racks"].sort_values("Rack_Type_Id").to_dict("records"):
        record = sanitize_record(row)
        source_rack_type_id = as_int(record.get("Rack_Type_Id"))
        if source_rack_type_id is None:
            continue
        payload["racks"].append(
            {
                "rack_type_id": stable_uuid("rack_type", workbook_sha, source_rack_type_id),
                "dictionary_version_id": dictionary_version_id,
                "source_rack_type_id": source_rack_type_id,
                "source_pack_type_id": as_int(record.get("Pack_Type_Id")),
                "packs_per_rack": as_int(record.get("Packs_Per_Rack")),
                "raw_row_json": record,
            }
        )

    for row in data["blocks"].sort_values("Dc_Block_Template_Id").to_dict("records"):
        record = sanitize_record(row)
        source_dc_block_template_id = as_int(record.get("Dc_Block_Template_Id"))
        block_code = clean_text(record.get("Dc_Block_Code"))
        if source_dc_block_template_id is None or block_code is None:
            continue
        block_name = clean_text(record.get("Dc_Block_Name")) or block_code
        block_master_id = stable_uuid("dc_block_master", block_code)
        block_revision_id = stable_uuid("dc_block_revision", block_code, workbook_sha)
        block_revision_ids.append(block_revision_id)
        block_form = clean_text(record.get("Block_Form")) or "container"
        container_length_ft = as_int(record.get("Container_Length_Ft"))
        source_rack_type_id = as_int(record.get("Rack_Type_Id"))
        rack_record = rack_lookup.get(source_rack_type_id)
        packs_per_rack = as_int(rack_record.get("Packs_Per_Rack")) if rack_record else None
        is_active = as_bool_flag(record.get("Is_Active"))
        payload["blocks"].append(
            {
                "master": {
                    "dc_block_master_id": block_master_id,
                    "block_code": block_code,
                    "block_name": block_name,
                    "block_form": block_form,
                    "vendor_name": infer_vendor(block_code),
                    "enclosure_type": block_form if container_length_ft is None else f"{block_form}_{container_length_ft}ft",
                    "record_status": "active" if is_active else "inactive",
                    "remarks": f"Seeded from {workbook.name}",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                "revision": {
                    "dc_block_revision_id": block_revision_id,
                    "dc_block_master_id": block_master_id,
                    "revision_no": 1,
                    "revision_status": "published",
                    "source_type": "imported",
                    "published_dictionary_version_id": dictionary_version_id,
                    "racks_per_block": as_int(record.get("Racks_Per_Block")),
                    "packs_per_rack": packs_per_rack,
                    "block_nameplate_capacity_mwh": as_float(record.get("Block_Nameplate_Capacity_Mwh")),
                    "charge_power_limit_mw": None,
                    "discharge_power_limit_mw": None,
                    "auxiliary_power_kw": as_float(record.get("Block_Aux_Energy_Kwh")),
                    "enclosure_size_ft": container_length_ft,
                    "parameter_json": {
                        "source_kind": "excel_seed",
                        "source_sheet": "dc_block_template_314_data",
                        "source_dc_block_template_id": source_dc_block_template_id,
                        "design_max_c_rate": as_float(record.get("Design_Max_C_Rate")),
                        "packs_per_block": as_int(record.get("Packs_Per_Block")),
                        "block_aux_energy_kwh": as_float(record.get("Block_Aux_Energy_Kwh")),
                        "rack_type_id": source_rack_type_id,
                        "raw_row_json": record,
                    },
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "published_at": timestamp,
                },
                "snapshot": {
                    "dc_block_template_id": stable_uuid("dc_block_template", workbook_sha, source_dc_block_template_id),
                    "dictionary_version_id": dictionary_version_id,
                    "source_dc_block_master_id": block_master_id,
                    "source_dc_block_revision_id": block_revision_id,
                    "source_dc_block_code": block_code,
                    "source_dc_block_name": block_name,
                    "block_form": block_form,
                    "source_rack_type_id": source_rack_type_id,
                    "racks_per_block": as_int(record.get("Racks_Per_Block")),
                    "block_nameplate_capacity_mwh": as_float(record.get("Block_Nameplate_Capacity_Mwh")),
                    "is_active": is_active,
                    "is_default_option": as_bool_flag(record.get("Is_Default_Option")),
                    "raw_row_json": record,
                },
            }
        )

    soh_profile_uuid_by_source: dict[int, str] = {}
    for row in data["soh_profiles"].sort_values("Profile_Id").to_dict("records"):
        record = sanitize_record(row)
        source_profile_id = as_int(record.get("Profile_Id"))
        if source_profile_id is None:
            continue
        soh_profile_id = stable_uuid("soh_profile", workbook_sha, source_profile_id)
        soh_profile_uuid_by_source[source_profile_id] = soh_profile_id
        payload["soh_profiles"].append(
            {
                "soh_profile_id": soh_profile_id,
                "dictionary_version_id": dictionary_version_id,
                "source_profile_id": source_profile_id,
                "c_rate": as_float(record.get("C_Rate")),
                "cycles_per_year": as_int(record.get("Cycles_Per_Year")),
                "raw_row_json": record,
            }
        )

    for row in data["soh_curves"].sort_values(["Profile_Id", "Life_Year_Index"]).to_dict("records"):
        record = sanitize_record(row)
        source_profile_id = as_int(record.get("Profile_Id"))
        life_year_index = as_int(record.get("Life_Year_Index"))
        if source_profile_id is None or life_year_index is None:
            continue
        soh_profile_id = soh_profile_uuid_by_source.get(source_profile_id)
        if soh_profile_id is None:
            continue
        payload["soh_curve_points"].append(
            {
                "soh_curve_point_id": stable_uuid("soh_curve_point", workbook_sha, source_profile_id, life_year_index),
                "soh_profile_id": soh_profile_id,
                "life_year_index": life_year_index,
                "soh_dc_pct": as_float(record.get("Soh_Dc_Pct")),
                "raw_row_json": record,
            }
        )

    rte_profile_uuid_by_source: dict[int, str] = {}
    for row in data["rte_profiles"].sort_values("Profile_Id").to_dict("records"):
        record = sanitize_record(row)
        source_profile_id = as_int(record.get("Profile_Id"))
        if source_profile_id is None:
            continue
        rte_profile_id = stable_uuid("rte_profile", workbook_sha, source_profile_id)
        rte_profile_uuid_by_source[source_profile_id] = rte_profile_id
        payload["rte_profiles"].append(
            {
                "rte_profile_id": rte_profile_id,
                "dictionary_version_id": dictionary_version_id,
                "source_profile_id": source_profile_id,
                "c_rate": as_float(record.get("C_Rate")),
                "raw_row_json": record,
            }
        )

    for row in data["rte_curves"].sort_values(["Profile_Id", "Soh_Band_Min_Pct"]).to_dict("records"):
        record = sanitize_record(row)
        source_profile_id = as_int(record.get("Profile_Id"))
        soh_band_min_pct = as_float(record.get("Soh_Band_Min_Pct"))
        if source_profile_id is None or soh_band_min_pct is None:
            continue
        rte_profile_id = rte_profile_uuid_by_source.get(source_profile_id)
        if rte_profile_id is None:
            continue
        payload["rte_curve_points"].append(
            {
                "rte_curve_point_id": stable_uuid("rte_curve_point", workbook_sha, source_profile_id, soh_band_min_pct),
                "rte_profile_id": rte_profile_id,
                "soh_band_min_pct": soh_band_min_pct,
                "rte_dc_pct": as_float(record.get("Rte_Dc_Pct")),
                "raw_row_json": record,
            }
        )

    payload["publish_batch"] = {
        "publish_batch_id": publish_batch_id,
        "domain_code": "dc",
        "version_label": effective_version_label,
        "batch_status": "published",
        "summary": f"Seeded from {workbook.name}",
        "requested_by": "seed-script",
        "approved_by": "seed-script",
        "published_by": "seed-script",
        "requested_at": timestamp,
        "approved_at": timestamp,
        "published_at": timestamp,
        "dictionary_version_id": dictionary_version_id,
        "meta_json": {
            "source_workbook": workbook.name,
            "source_sha256": workbook_sha,
            "cell_revision_count": len(cell_revision_ids),
            "dc_block_revision_count": len(block_revision_ids),
        },
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    for cell_revision_id in cell_revision_ids:
        payload["publish_batch_items"].append(
            {
                "publish_batch_item_id": stable_uuid("publish_batch_item", publish_batch_id, "battery_cell", cell_revision_id),
                "publish_batch_id": publish_batch_id,
                "entity_type": "battery_cell",
                "cell_revision_id": cell_revision_id,
                "item_status": "published",
                "snapshot_hash": workbook_sha,
                "snapshot_payload_json": {"dictionary_version_id": dictionary_version_id},
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )

    for block_revision_id in block_revision_ids:
        payload["publish_batch_items"].append(
            {
                "publish_batch_item_id": stable_uuid("publish_batch_item", publish_batch_id, "dc_block", block_revision_id),
                "publish_batch_id": publish_batch_id,
                "entity_type": "dc_block",
                "dc_block_revision_id": block_revision_id,
                "item_status": "published",
                "snapshot_hash": workbook_sha,
                "snapshot_payload_json": {"dictionary_version_id": dictionary_version_id},
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )

    return payload


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_workbook": payload["workbook"].name,
        "source_sha256": payload["workbook_sha"],
        "version_label": payload["dictionary_version"]["version_label"],
        "activate_version": payload["dictionary_version"]["is_active"],
        "counts": {
            "cells": len(payload["cells"]),
            "packs": len(payload["packs"]),
            "racks": len(payload["racks"]),
            "blocks": len(payload["blocks"]),
            "soh_profiles": len(payload["soh_profiles"]),
            "soh_curve_points": len(payload["soh_curve_points"]),
            "rte_profiles": len(payload["rte_profiles"]),
            "rte_curve_points": len(payload["rte_curve_points"]),
            "publish_batch_items": len(payload["publish_batch_items"]),
        },
    }


def build_sql(
    workbook: Path,
    output_sql: Path,
    version_label: str | None,
    activate_version: bool,
) -> str:
    payload = build_seed_payload(
        workbook=workbook,
        version_label=version_label,
        activate_version=activate_version,
        output_sql=output_sql,
    )
    lines: list[str] = []
    lines.append("BEGIN;")
    lines.append("")
    lines.append(f"-- Generated from {workbook.as_posix()}")
    lines.append(f"-- Source sha256: {payload['workbook_sha']}")
    lines.append(f"-- Generated at: {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}")
    lines.append("")

    dict_row = payload["dictionary_version"]
    lines.append("-- dictionary_versions")
    lines.append(
        insert_sql(
            "dictionary_versions",
            list(dict_row.keys()),
            list(dict_row.values()),
        )
    )
    lines.append("")

    lines.append("-- battery_cell_masters / battery_cell_revisions / battery_cell_types")
    for entry in payload["cells"]:
        lines.append(insert_sql("battery_cell_masters", entry["master"].keys(), entry["master"].values()))
        lines.append(insert_sql("battery_cell_revisions", entry["revision"].keys(), entry["revision"].values()))
        lines.append(insert_sql("battery_cell_types", entry["snapshot"].keys(), entry["snapshot"].values()))
    lines.append("")

    lines.append("-- pack_types")
    for row in payload["packs"]:
        lines.append(insert_sql("pack_types", row.keys(), row.values()))
    lines.append("")

    lines.append("-- rack_types")
    for row in payload["racks"]:
        lines.append(insert_sql("rack_types", row.keys(), row.values()))
    lines.append("")

    lines.append("-- dc_block_masters / dc_block_revisions / dc_block_templates")
    for entry in payload["blocks"]:
        lines.append(insert_sql("dc_block_masters", entry["master"].keys(), entry["master"].values()))
        lines.append(insert_sql("dc_block_revisions", entry["revision"].keys(), entry["revision"].values()))
        lines.append(insert_sql("dc_block_templates", entry["snapshot"].keys(), entry["snapshot"].values()))
    lines.append("")

    lines.append("-- soh_profiles / soh_curve_points")
    for row in payload["soh_profiles"]:
        lines.append(insert_sql("soh_profiles", row.keys(), row.values()))
    for row in payload["soh_curve_points"]:
        lines.append(insert_sql("soh_curve_points", row.keys(), row.values()))
    lines.append("")

    lines.append("-- rte_profiles / rte_curve_points")
    for row in payload["rte_profiles"]:
        lines.append(insert_sql("rte_profiles", row.keys(), row.values()))
    for row in payload["rte_curve_points"]:
        lines.append(insert_sql("rte_curve_points", row.keys(), row.values()))
    lines.append("")

    lines.append("-- master_publish_batches / master_publish_batch_items")
    lines.append(
        insert_sql(
            "master_publish_batches",
            payload["publish_batch"].keys(),
            payload["publish_batch"].values(),
        )
    )
    for row in payload["publish_batch_items"]:
        lines.append(insert_sql("master_publish_batch_items", row.keys(), row.values()))
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")
    return "\n".join(lines)
