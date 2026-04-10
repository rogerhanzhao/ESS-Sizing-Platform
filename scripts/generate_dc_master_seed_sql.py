from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.db.dc_master_seed import DEFAULT_SEED_SQL_OUTPUT, build_sql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate seed SQL for DC master data, dictionary snapshots, and publish history."
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=DC_DATA_PATH,
        help="Path to the DC Excel workbook.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SEED_SQL_OUTPUT,
        help="Output SQL path.",
    )
    parser.add_argument(
        "--version-label",
        type=str,
        default=None,
        help="Optional version label for dictionary_versions and publish batch.",
    )
    parser.add_argument(
        "--inactive-version",
        action="store_true",
        help="Generate the dictionary version as inactive.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook = args.workbook.resolve()
    output = args.output.resolve()
    if not workbook.is_file():
        raise FileNotFoundError(f"Workbook not found: {workbook}")

    output.parent.mkdir(parents=True, exist_ok=True)
    sql = build_sql(
        workbook=workbook,
        output_sql=output,
        version_label=args.version_label,
        activate_version=not args.inactive_version,
    )
    output.write_text(sql, encoding="utf-8", newline="\n")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
