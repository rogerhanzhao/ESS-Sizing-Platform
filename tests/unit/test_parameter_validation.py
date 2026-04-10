from __future__ import annotations

from pathlib import Path

import pandas as pd

from calb_sizing_tool.importers.import_validators import validate_dc_workbook


def test_parameter_validation_detects_missing_sheets(tmp_path: Path):
    workbook = tmp_path / "invalid.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame([{"Field Name": "project_name", "Default Value": "Demo"}]).to_excel(
            writer, sheet_name="ess_sizing_case", index=False
        )

    issues = validate_dc_workbook(workbook)
    assert issues
    assert "Missing required sheets" in issues[0]
