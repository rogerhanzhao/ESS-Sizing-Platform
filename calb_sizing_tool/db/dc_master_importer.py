from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


REQUIRED_TABLES = {
    "dictionary_versions",
    "battery_cell_masters",
    "battery_cell_revisions",
    "battery_cell_types",
    "pack_types",
    "rack_types",
    "dc_block_masters",
    "dc_block_revisions",
    "dc_block_templates",
    "soh_profiles",
    "soh_curve_points",
    "rte_profiles",
    "rte_curve_points",
    "master_publish_batches",
    "master_publish_batch_items",
}


def _jsonb(value: Any) -> Jsonb:
    return Jsonb(value)


def ensure_schema_ready(conn: Connection[Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
        existing = {row[0] for row in cur.fetchall()}
    missing = sorted(REQUIRED_TABLES - existing)
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "PostgreSQL schema is incomplete. Apply 001_init_postgres.sql and "
            f"002_master_data_publish_flow.sql first. Missing tables: {joined}"
        )


def find_existing_dictionary_version(
    conn: Connection[Any],
    *,
    domain_code: str,
    source_file_sha256: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dictionary_version_id, version_label, is_active
            FROM dictionary_versions
            WHERE domain_code = %s AND source_file_sha256 = %s
            """,
            (domain_code, source_file_sha256),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "dictionary_version_id": row[0],
        "version_label": row[1],
        "is_active": row[2],
    }


def _deactivate_active_dictionary(conn: Connection[Any], *, domain_code: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dictionary_versions
            SET is_active = FALSE
            WHERE domain_code = %s AND is_active = TRUE
            """,
            (domain_code,),
        )
        return cur.rowcount


def _next_revision_no(conn: Connection[Any], table: str, key_column: str, key_value: str) -> int:
    query = f"SELECT COALESCE(MAX(revision_no), 0) + 1 FROM {table} WHERE {key_column} = %s"
    with conn.cursor() as cur:
        cur.execute(query, (key_value,))
        row = cur.fetchone()
    return int(row[0])


def _archive_published_cell_revisions(conn: Connection[Any], cell_master_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE battery_cell_revisions
            SET revision_status = 'archived',
                updated_at = NOW()
            WHERE cell_master_id = %s AND revision_status = 'published'
            """,
            (cell_master_id,),
        )
        return cur.rowcount


def _archive_published_block_revisions(conn: Connection[Any], dc_block_master_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dc_block_revisions
            SET revision_status = 'archived',
                updated_at = NOW()
            WHERE dc_block_master_id = %s AND revision_status = 'published'
            """,
            (dc_block_master_id,),
        )
        return cur.rowcount


def _insert_dictionary_version(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dictionary_versions (
                dictionary_version_id,
                domain_code,
                version_label,
                source_file_name,
                source_file_sha256,
                is_active,
                loaded_at,
                meta_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["dictionary_version_id"],
                row["domain_code"],
                row["version_label"],
                row["source_file_name"],
                row["source_file_sha256"],
                row["is_active"],
                row["loaded_at"],
                _jsonb(row["meta_json"]),
            ),
        )


def _upsert_cell_master(conn: Connection[Any], row: dict[str, Any]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO battery_cell_masters (
                cell_master_id,
                cell_code,
                cell_model,
                vendor_name,
                chemistry_code,
                record_status,
                remarks,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cell_code) DO UPDATE SET
                cell_model = EXCLUDED.cell_model,
                vendor_name = EXCLUDED.vendor_name,
                chemistry_code = EXCLUDED.chemistry_code,
                record_status = EXCLUDED.record_status,
                remarks = EXCLUDED.remarks,
                updated_at = EXCLUDED.updated_at
            RETURNING cell_master_id
            """,
            (
                row["cell_master_id"],
                row["cell_code"],
                row["cell_model"],
                row["vendor_name"],
                row["chemistry_code"],
                row["record_status"],
                row["remarks"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        return str(cur.fetchone()[0])


def _insert_cell_revision(conn: Connection[Any], row: dict[str, Any], *, cell_master_id: str, revision_no: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO battery_cell_revisions (
                cell_revision_id,
                cell_master_id,
                revision_no,
                revision_status,
                source_type,
                published_dictionary_version_id,
                nominal_capacity_ah,
                nominal_voltage_v,
                nominal_energy_wh,
                parameter_json,
                created_at,
                updated_at,
                published_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["cell_revision_id"],
                cell_master_id,
                revision_no,
                row["revision_status"],
                row["source_type"],
                row["published_dictionary_version_id"],
                row["nominal_capacity_ah"],
                row["nominal_voltage_v"],
                row["nominal_energy_wh"],
                _jsonb(row["parameter_json"]),
                row["created_at"],
                row["updated_at"],
                row["published_at"],
            ),
        )


def _insert_cell_snapshot(conn: Connection[Any], row: dict[str, Any], *, cell_master_id: str, cell_revision_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO battery_cell_types (
                cell_type_id,
                dictionary_version_id,
                source_cell_master_id,
                source_cell_revision_id,
                source_cell_type_id,
                cell_model,
                cell_capacity_ah,
                cell_nominal_voltage_v,
                cell_energy_wh,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["cell_type_id"],
                row["dictionary_version_id"],
                cell_master_id,
                cell_revision_id,
                row["source_cell_type_id"],
                row["cell_model"],
                row["cell_capacity_ah"],
                row["cell_nominal_voltage_v"],
                row["cell_energy_wh"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _insert_pack_snapshot(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pack_types (
                pack_type_id,
                dictionary_version_id,
                source_pack_type_id,
                source_cell_type_id,
                cells_in_series,
                cells_in_parallel,
                pack_nominal_voltage_v,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["pack_type_id"],
                row["dictionary_version_id"],
                row["source_pack_type_id"],
                row["source_cell_type_id"],
                row["cells_in_series"],
                row["cells_in_parallel"],
                row["pack_nominal_voltage_v"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _insert_rack_snapshot(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rack_types (
                rack_type_id,
                dictionary_version_id,
                source_rack_type_id,
                source_pack_type_id,
                packs_per_rack,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                row["rack_type_id"],
                row["dictionary_version_id"],
                row["source_rack_type_id"],
                row["source_pack_type_id"],
                row["packs_per_rack"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _upsert_block_master(conn: Connection[Any], row: dict[str, Any]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dc_block_masters (
                dc_block_master_id,
                block_code,
                block_name,
                block_form,
                vendor_name,
                enclosure_type,
                record_status,
                remarks,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (block_code) DO UPDATE SET
                block_name = EXCLUDED.block_name,
                block_form = EXCLUDED.block_form,
                vendor_name = EXCLUDED.vendor_name,
                enclosure_type = EXCLUDED.enclosure_type,
                record_status = EXCLUDED.record_status,
                remarks = EXCLUDED.remarks,
                updated_at = EXCLUDED.updated_at
            RETURNING dc_block_master_id
            """,
            (
                row["dc_block_master_id"],
                row["block_code"],
                row["block_name"],
                row["block_form"],
                row["vendor_name"],
                row["enclosure_type"],
                row["record_status"],
                row["remarks"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        return str(cur.fetchone()[0])


def _insert_block_revision(conn: Connection[Any], row: dict[str, Any], *, dc_block_master_id: str, revision_no: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dc_block_revisions (
                dc_block_revision_id,
                dc_block_master_id,
                revision_no,
                revision_status,
                source_type,
                published_dictionary_version_id,
                racks_per_block,
                packs_per_rack,
                block_nameplate_capacity_mwh,
                charge_power_limit_mw,
                discharge_power_limit_mw,
                auxiliary_power_kw,
                enclosure_size_ft,
                parameter_json,
                created_at,
                updated_at,
                published_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["dc_block_revision_id"],
                dc_block_master_id,
                revision_no,
                row["revision_status"],
                row["source_type"],
                row["published_dictionary_version_id"],
                row["racks_per_block"],
                row["packs_per_rack"],
                row["block_nameplate_capacity_mwh"],
                row["charge_power_limit_mw"],
                row["discharge_power_limit_mw"],
                row["auxiliary_power_kw"],
                row["enclosure_size_ft"],
                _jsonb(row["parameter_json"]),
                row["created_at"],
                row["updated_at"],
                row["published_at"],
            ),
        )


def _insert_block_snapshot(conn: Connection[Any], row: dict[str, Any], *, dc_block_master_id: str, dc_block_revision_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dc_block_templates (
                dc_block_template_id,
                dictionary_version_id,
                source_dc_block_master_id,
                source_dc_block_revision_id,
                source_dc_block_code,
                source_dc_block_name,
                block_form,
                source_rack_type_id,
                racks_per_block,
                block_nameplate_capacity_mwh,
                is_active,
                is_default_option,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["dc_block_template_id"],
                row["dictionary_version_id"],
                dc_block_master_id,
                dc_block_revision_id,
                row["source_dc_block_code"],
                row["source_dc_block_name"],
                row["block_form"],
                row["source_rack_type_id"],
                row["racks_per_block"],
                row["block_nameplate_capacity_mwh"],
                row["is_active"],
                row["is_default_option"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _insert_soh_profile(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soh_profiles (
                soh_profile_id,
                dictionary_version_id,
                source_profile_id,
                c_rate,
                cycles_per_year,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                row["soh_profile_id"],
                row["dictionary_version_id"],
                row["source_profile_id"],
                row["c_rate"],
                row["cycles_per_year"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _insert_soh_curve_point(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO soh_curve_points (
                soh_curve_point_id,
                soh_profile_id,
                life_year_index,
                soh_dc_pct,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                row["soh_curve_point_id"],
                row["soh_profile_id"],
                row["life_year_index"],
                row["soh_dc_pct"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _insert_rte_profile(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rte_profiles (
                rte_profile_id,
                dictionary_version_id,
                source_profile_id,
                c_rate,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                row["rte_profile_id"],
                row["dictionary_version_id"],
                row["source_profile_id"],
                row["c_rate"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _insert_rte_curve_point(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rte_curve_points (
                rte_curve_point_id,
                rte_profile_id,
                soh_band_min_pct,
                rte_dc_pct,
                raw_row_json
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                row["rte_curve_point_id"],
                row["rte_profile_id"],
                row["soh_band_min_pct"],
                row["rte_dc_pct"],
                _jsonb(row["raw_row_json"]),
            ),
        )


def _insert_publish_batch(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO master_publish_batches (
                publish_batch_id,
                domain_code,
                version_label,
                batch_status,
                summary,
                requested_by,
                approved_by,
                published_by,
                requested_at,
                approved_at,
                published_at,
                dictionary_version_id,
                meta_json,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["publish_batch_id"],
                row["domain_code"],
                row["version_label"],
                row["batch_status"],
                row["summary"],
                row["requested_by"],
                row["approved_by"],
                row["published_by"],
                row["requested_at"],
                row["approved_at"],
                row["published_at"],
                row["dictionary_version_id"],
                _jsonb(row["meta_json"]),
                row["created_at"],
                row["updated_at"],
            ),
        )


def _insert_publish_batch_item(conn: Connection[Any], row: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO master_publish_batch_items (
                publish_batch_item_id,
                publish_batch_id,
                entity_type,
                cell_revision_id,
                dc_block_revision_id,
                item_status,
                snapshot_hash,
                snapshot_payload_json,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["publish_batch_item_id"],
                row["publish_batch_id"],
                row["entity_type"],
                row.get("cell_revision_id"),
                row.get("dc_block_revision_id"),
                row["item_status"],
                row["snapshot_hash"],
                _jsonb(row["snapshot_payload_json"]),
                row["created_at"],
                row["updated_at"],
            ),
        )


def import_dc_master_payload(
    conn: Connection[Any],
    payload: dict[str, Any],
    *,
    on_existing: str = "skip",
    actor: str = "excel-import",
) -> dict[str, Any]:
    if on_existing not in {"skip", "error"}:
        raise ValueError("on_existing must be 'skip' or 'error'")

    ensure_schema_ready(conn)
    dict_row = payload["dictionary_version"]
    existing = find_existing_dictionary_version(
        conn,
        domain_code=dict_row["domain_code"],
        source_file_sha256=dict_row["source_file_sha256"],
    )
    if existing:
        if on_existing == "skip":
            return {
                "status": "skipped",
                "reason": "dictionary_version_exists",
                "dictionary_version_id": existing["dictionary_version_id"],
                "version_label": existing["version_label"],
                "is_active": existing["is_active"],
            }
        raise RuntimeError(
            f"Dictionary version already exists for sha {dict_row['source_file_sha256']}: "
            f"{existing['dictionary_version_id']}"
        )

    archived_cell_revision_count = 0
    archived_block_revision_count = 0
    deactivated_dictionary_count = 0

    if dict_row["is_active"]:
        deactivated_dictionary_count = _deactivate_active_dictionary(conn, domain_code=dict_row["domain_code"])

    _insert_dictionary_version(conn, dict_row)

    cell_revision_map: dict[str, str] = {}
    for entry in payload["cells"]:
        master_id = _upsert_cell_master(conn, entry["master"])
        archived_cell_revision_count += _archive_published_cell_revisions(conn, master_id)
        revision_no = _next_revision_no(conn, "battery_cell_revisions", "cell_master_id", master_id)
        _insert_cell_revision(conn, entry["revision"], cell_master_id=master_id, revision_no=revision_no)
        cell_revision_id = entry["revision"]["cell_revision_id"]
        cell_revision_map[cell_revision_id] = cell_revision_id
        _insert_cell_snapshot(conn, entry["snapshot"], cell_master_id=master_id, cell_revision_id=cell_revision_id)

    for row in payload["packs"]:
        _insert_pack_snapshot(conn, row)

    for row in payload["racks"]:
        _insert_rack_snapshot(conn, row)

    block_revision_map: dict[str, str] = {}
    for entry in payload["blocks"]:
        master_id = _upsert_block_master(conn, entry["master"])
        archived_block_revision_count += _archive_published_block_revisions(conn, master_id)
        revision_no = _next_revision_no(conn, "dc_block_revisions", "dc_block_master_id", master_id)
        _insert_block_revision(conn, entry["revision"], dc_block_master_id=master_id, revision_no=revision_no)
        revision_id = entry["revision"]["dc_block_revision_id"]
        block_revision_map[revision_id] = revision_id
        _insert_block_snapshot(conn, entry["snapshot"], dc_block_master_id=master_id, dc_block_revision_id=revision_id)

    for row in payload["soh_profiles"]:
        _insert_soh_profile(conn, row)
    for row in payload["soh_curve_points"]:
        _insert_soh_curve_point(conn, row)
    for row in payload["rte_profiles"]:
        _insert_rte_profile(conn, row)
    for row in payload["rte_curve_points"]:
        _insert_rte_curve_point(conn, row)

    publish_batch = dict(payload["publish_batch"])
    publish_batch["requested_by"] = actor
    publish_batch["approved_by"] = actor
    publish_batch["published_by"] = actor
    _insert_publish_batch(conn, publish_batch)

    for row in payload["publish_batch_items"]:
        _insert_publish_batch_item(conn, row)

    return {
        "status": "imported",
        "dictionary_version_id": dict_row["dictionary_version_id"],
        "version_label": dict_row["version_label"],
        "source_file_sha256": dict_row["source_file_sha256"],
        "deactivated_dictionary_count": deactivated_dictionary_count,
        "archived_cell_revision_count": archived_cell_revision_count,
        "archived_block_revision_count": archived_block_revision_count,
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


def format_import_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
