from __future__ import annotations

from pathlib import Path

import pandas as pd

from calb_sizing_tool.schemas.master_data import ImportPreview


def build_dc_import_preview(path: Path) -> ImportPreview:
    xls = pd.ExcelFile(path)
    sheets_present = list(xls.sheet_names)
    row_counts: dict[str, int] = {}
    column_map: dict[str, list[str]] = {}

    for sheet in sheets_present:
        df = pd.read_excel(xls, sheet)
        row_counts[sheet] = int(len(df))
        column_map[sheet] = [str(column) for column in df.columns]

    return ImportPreview(
        workbook_name=path.name,
        sheets_present=sheets_present,
        row_counts=row_counts,
        column_map=column_map,
    )
