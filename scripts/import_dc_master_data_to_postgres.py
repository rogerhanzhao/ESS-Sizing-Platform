from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.db.dc_master_importer import format_import_result, import_dc_master_payload
from calb_sizing_tool.db.dc_master_seed import (
    build_seed_payload,
    default_import_version_label,
    file_sha256,
    summarize_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import the current DC Excel dictionary into PostgreSQL master/revision/snapshot tables."
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection string. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=DC_DATA_PATH,
        help="Path to the DC Excel workbook.",
    )
    parser.add_argument(
        "--version-label",
        type=str,
        default=None,
        help="Optional business version label. Defaults to filename plus sha suffix.",
    )
    parser.add_argument(
        "--inactive-version",
        action="store_true",
        help="Import the dictionary version as inactive.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the payload and print the summary without connecting to PostgreSQL.",
    )
    parser.add_argument(
        "--on-existing",
        choices=("skip", "error"),
        default="skip",
        help="Behavior when the same workbook sha already exists in dictionary_versions.",
    )
    parser.add_argument(
        "--actor",
        type=str,
        default=os.environ.get("USERNAME") or os.environ.get("USER") or "excel-import",
        help="Actor name written into the publish batch.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook = args.workbook.resolve()
    if not workbook.is_file():
        raise FileNotFoundError(f"Workbook not found: {workbook}")

    workbook_sha = file_sha256(workbook)
    version_label = args.version_label or default_import_version_label(workbook.name, workbook_sha)
    payload = build_seed_payload(
        workbook=workbook,
        version_label=version_label,
        activate_version=not args.inactive_version,
        output_sql=None,
    )

    if args.dry_run:
        print(format_import_result({"status": "dry_run", **summarize_payload(payload)}))
        return 0

    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required unless --dry-run is used.")

    with psycopg.connect(args.database_url) as conn:
        with conn.transaction():
            result = import_dc_master_payload(
                conn,
                payload,
                on_existing=args.on_existing,
                actor=args.actor,
            )

    print(format_import_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
