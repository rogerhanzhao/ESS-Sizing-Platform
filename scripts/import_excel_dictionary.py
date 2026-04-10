from __future__ import annotations

import argparse
import json
from pathlib import Path

from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.domain.enums import ImportMode
from calb_sizing_tool.importers.excel_dictionary_importer import ExcelDictionaryImporter
from calb_sizing_tool.infra.db.session import session_scope


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Excel dictionary data into the database.")
    parser.add_argument("--workbook", type=Path, default=DC_DATA_PATH, help="Path to Excel dictionary workbook.")
    parser.add_argument("--mode", type=str, default=ImportMode.DRY_RUN.value, choices=[m.value for m in ImportMode])
    parser.add_argument("--version-tag", type=str, default="manual-import")
    parser.add_argument("--source-ref", type=str, default="cli_import")
    parser.add_argument("--db-url", type=str, default=None, help="Override CALB_DATABASE_URL for this import.")
    args = parser.parse_args()

    with session_scope(args.db_url) as session:
        importer = ExcelDictionaryImporter(session)
        summary = importer.run_import(
            args.workbook,
            mode=args.mode,
            version_tag=args.version_tag,
            source_ref=args.source_ref,
            actor="cli",
        )

    print(json.dumps(summary.model_dump(mode="python"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
