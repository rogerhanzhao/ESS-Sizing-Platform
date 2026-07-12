from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from calb_sizing_tool.adapters.excel_loader_adapter import REQUIRED_DC_SHEETS
from calb_sizing_tool.domain.enums import ValidationSeverity
from calb_sizing_tool.schemas.master_data import ImportValidationIssue


REQUIRED_COLUMNS = {
    "ess_sizing_case": {"Field Name", "Default Value"},
    "dc_block_template_314_data": {"Dc_Block_Code", "Dc_Block_Name", "Block_Form", "Block_Nameplate_Capacity_Mwh"},
    "battery_cell_type_314_data": {"Cell_Type_Id", "Cell_Model", "Cell_Capacity_Ah"},
    "pack_type_314_data": {"Pack_Type_Id", "Cell_Type_Id", "Cells_In_Series", "Cells_In_Parallel"},
    "rack_type_314_data": {"Rack_Type_Id", "Pack_Type_Id", "Packs_Per_Rack"},
    "soh_profile_314_data": {"Profile_Id", "Cycles_Per_Year", "C_Rate"},
    "soh_curve_314_template": {"Profile_Id", "Life_Year_Index", "Soh_Dc_Pct"},
    "rte_profile_314_data": {"Profile_Id", "C_Rate"},
    "rte_curve_314_template": {"Profile_Id", "Soh_Band_Min_Pct", "Rte_Dc_Pct"},
}

REQUIRED_NON_NULL_COLUMNS = {
    "soh_profile_314_data": ["Profile_Id", "Cycles_Per_Year", "C_Rate"],
    "soh_curve_314_template": ["Profile_Id", "Life_Year_Index", "Soh_Dc_Pct"],
    "rte_profile_314_data": ["Profile_Id", "C_Rate"],
    "rte_curve_314_template": ["Profile_Id", "Soh_Band_Min_Pct", "Rte_Dc_Pct"],
}

# The legacy 314Ah dictionary contains deliberately unpopulated *tail* rows
# for profiles whose published curve stops before the workbook horizon.  Those
# rows retain a profile and coordinate but have no usable curve value.  They
# must not be coerced to zero or inserted into the non-null DB point tables.
# They are therefore warnings (and omitted during payload construction), while
# all other missing curve keys/values remain import-blocking errors.
_OMITTABLE_CURVE_VALUE_GAPS = {
    "soh_curve_314_template": {
        "value_column": "Soh_Dc_Pct",
        "anchor_columns": ("Profile_Id", "Life_Year_Index"),
    },
    "rte_curve_314_template": {
        "value_column": "Soh_Band_Min_Pct",
        "anchor_columns": ("Profile_Id", "Rte_Dc_Pct"),
    },
}

NUMERIC_RANGE_RULES = {
    "battery_cell_type_314_data": {
        "Cell_Capacity_Ah": (0.0, None),
        "Cell_Nominal_Voltage_V": (0.0, None),
        "Cell_Energy_Wh": (0.0, None),
    },
    "pack_type_314_data": {
        "Cells_In_Series": (0.0, None),
        "Cells_In_Parallel": (0.0, None),
        "Pack_Nominal_Voltage_V": (0.0, None),
        "Pack_Nameplate_Capacity_Kwh": (0.0, None),
    },
    "rack_type_314_data": {
        "Packs_Per_Rack": (0.0, None),
        "Rack_Nameplate_Capacity_Mwh": (0.0, None),
        "Rack_Aux_Energy_Kwh": (0.0, None),
    },
    "dc_block_template_314_data": {
        "Container_Length_Ft": (0.0, None),
        "Racks_Per_Block": (0.0, None),
        "Packs_Per_Block": (0.0, None),
        "Block_Nameplate_Capacity_Mwh": (0.0, None),
        "Block_Aux_Energy_Kwh": (0.0, None),
        "Design_Max_C_Rate": (0.0, None),
    },
    "soh_profile_314_data": {
        "Cycles_Per_Year": (0.0, None),
        "C_Rate": (0.0, None),
        "Reference_Temperature_C": (-100.0, 200.0),
    },
    "soh_curve_314_template": {
        "Life_Year_Index": (0.0, None),
        "Cycle_Index": (0.0, None),
    },
    "rte_profile_314_data": {
        "Cycles_Per_Year": (0.0, None),
        "C_Rate": (0.0, None),
    },
}

PERCENT_COLUMNS = {
    "soh_curve_314_template": ["Soh_Dc_Pct"],
    "rte_curve_314_template": ["Soh_Band_Min_Pct", "Soh_Band_Max_Pct", "Rte_Dc_Pct"],
}


def _issue(
    severity: ValidationSeverity,
    sheet_name: str,
    message: str,
    *,
    field_name: str | None = None,
    row_ref: str | None = None,
) -> ImportValidationIssue:
    return ImportValidationIssue(
        severity=severity.value,
        sheet_name=sheet_name,
        field_name=field_name,
        row_ref=row_ref,
        message=message,
    )


def _is_missing(value: Any) -> bool:
    return value is None or pd.isna(value)


def _to_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace("%", "").replace(",", "")
        return float(value)
    except Exception:
        return None


def _load_raw_sheets(path: Path) -> tuple[list[ImportValidationIssue], dict[str, pd.DataFrame]]:
    issues: list[ImportValidationIssue] = []
    raw: dict[str, pd.DataFrame] = {}
    if not path.is_file():
        return [_issue(ValidationSeverity.ERROR, "workbook", f"Workbook not found: {path}")], raw

    xls = pd.ExcelFile(path)
    missing_sheets = [sheet for sheet in REQUIRED_DC_SHEETS if sheet not in xls.sheet_names]
    for sheet in missing_sheets:
        issues.append(_issue(ValidationSeverity.ERROR, sheet, f"Missing required sheet: {sheet}"))

    for sheet in REQUIRED_DC_SHEETS:
        if sheet not in xls.sheet_names:
            continue
        df = pd.read_excel(xls, sheet)
        raw[sheet] = df
        missing_columns = sorted(REQUIRED_COLUMNS.get(sheet, set()) - set(df.columns))
        for column in missing_columns:
            issues.append(_issue(ValidationSeverity.ERROR, sheet, f"Missing required column: {column}", field_name=column))

    return issues, raw


def _validate_required_non_null(raw: dict[str, pd.DataFrame]) -> list[ImportValidationIssue]:
    issues: list[ImportValidationIssue] = []
    for sheet, columns in REQUIRED_NON_NULL_COLUMNS.items():
        df = raw.get(sheet)
        if df is None:
            continue
        for idx, row in df.iterrows():
            for column in columns:
                if column in df.columns and _is_missing(row.get(column)):
                    omission_rule = _OMITTABLE_CURVE_VALUE_GAPS.get(sheet)
                    if (
                        omission_rule is not None
                        and column == omission_rule["value_column"]
                        and all(not _is_missing(row.get(anchor)) for anchor in omission_rule["anchor_columns"])
                    ):
                        issues.append(
                            _issue(
                                ValidationSeverity.WARNING,
                                sheet,
                                "Legacy source curve value is blank; the undefined point will be omitted without interpolation.",
                                field_name=column,
                                row_ref=str(idx + 2),
                            )
                        )
                        continue
                    issues.append(
                        _issue(
                            ValidationSeverity.ERROR,
                            sheet,
                            f"Required value is empty for column {column}.",
                            field_name=column,
                            row_ref=str(idx + 2),
                        )
                    )
    return issues


def _validate_numeric_ranges(raw: dict[str, pd.DataFrame]) -> list[ImportValidationIssue]:
    issues: list[ImportValidationIssue] = []
    for sheet, rules in NUMERIC_RANGE_RULES.items():
        df = raw.get(sheet)
        if df is None:
            continue
        for idx, row in df.iterrows():
            for column, (minimum, maximum) in rules.items():
                if column not in df.columns or _is_missing(row.get(column)):
                    continue
                value = _to_float(row.get(column))
                if value is None:
                    issues.append(
                        _issue(
                            ValidationSeverity.ERROR,
                            sheet,
                            f"Non-numeric value found in numeric column {column}.",
                            field_name=column,
                            row_ref=str(idx + 2),
                        )
                    )
                    continue
                if minimum is not None and value < minimum:
                    issues.append(
                        _issue(
                            ValidationSeverity.ERROR,
                            sheet,
                            f"Value {value} is below the minimum {minimum}.",
                            field_name=column,
                            row_ref=str(idx + 2),
                        )
                    )
                if maximum is not None and value > maximum:
                    issues.append(
                        _issue(
                            ValidationSeverity.ERROR,
                            sheet,
                            f"Value {value} is above the maximum {maximum}.",
                            field_name=column,
                            row_ref=str(idx + 2),
                        )
                    )
    return issues


def _validate_percent_columns(raw: dict[str, pd.DataFrame]) -> list[ImportValidationIssue]:
    issues: list[ImportValidationIssue] = []
    for sheet, columns in PERCENT_COLUMNS.items():
        df = raw.get(sheet)
        if df is None:
            continue
        for column in columns:
            if column not in df.columns:
                continue
            fraction_style = 0
            percent_style = 0
            for idx, value in enumerate(df[column].tolist(), start=2):
                numeric = _to_float(value)
                if numeric is None:
                    continue
                if numeric < 0 or numeric > 100:
                    issues.append(
                        _issue(
                            ValidationSeverity.ERROR,
                            sheet,
                            f"Percent-like field {column} must be between 0 and 100 or 0 and 1.",
                            field_name=column,
                            row_ref=str(idx),
                        )
                    )
                    continue
                if 0 <= numeric <= 1:
                    fraction_style += 1
                elif numeric > 1:
                    percent_style += 1
            if fraction_style > 0 and percent_style > 0:
                issues.append(
                    _issue(
                        ValidationSeverity.WARNING,
                        sheet,
                        f"Percent-like field {column} mixes fraction-style and percent-style values.",
                        field_name=column,
                    )
                )
    return issues


def _validate_duplicate_profiles(raw: dict[str, pd.DataFrame]) -> list[ImportValidationIssue]:
    issues: list[ImportValidationIssue] = []
    for sheet in ("soh_profile_314_data", "rte_profile_314_data"):
        df = raw.get(sheet)
        if df is None or "Profile_Id" not in df.columns:
            continue
        duplicates = df[df["Profile_Id"].duplicated(keep=False)]
        for _, row in duplicates.iterrows():
            issues.append(
                _issue(
                    ValidationSeverity.ERROR,
                    sheet,
                    f"Duplicate Profile_Id detected: {row['Profile_Id']}",
                    field_name="Profile_Id",
                )
            )
    return issues


def _validate_curve_duplicates(raw: dict[str, pd.DataFrame]) -> list[ImportValidationIssue]:
    issues: list[ImportValidationIssue] = []
    df_soh = raw.get("soh_curve_314_template")
    if df_soh is not None and {"Profile_Id", "Life_Year_Index"}.issubset(df_soh.columns):
        valid_soh = df_soh.dropna(subset=["Profile_Id", "Life_Year_Index", "Soh_Dc_Pct"])
        duplicates = valid_soh[valid_soh.duplicated(subset=["Profile_Id", "Life_Year_Index"], keep=False)]
        for _, row in duplicates.iterrows():
            issues.append(
                _issue(
                    ValidationSeverity.ERROR,
                    "soh_curve_314_template",
                    f"Duplicate SOH curve point for profile {row['Profile_Id']} year {row['Life_Year_Index']}.",
                    field_name="Life_Year_Index",
                )
            )
    df_rte = raw.get("rte_curve_314_template")
    if df_rte is not None and {"Profile_Id", "Soh_Band_Min_Pct"}.issubset(df_rte.columns):
        valid_rte = df_rte.dropna(subset=["Profile_Id", "Soh_Band_Min_Pct", "Rte_Dc_Pct"])
        duplicates = valid_rte[valid_rte.duplicated(subset=["Profile_Id", "Soh_Band_Min_Pct"], keep=False)]
        for _, row in duplicates.iterrows():
            issues.append(
                _issue(
                    ValidationSeverity.ERROR,
                    "rte_curve_314_template",
                    f"Duplicate RTE band for profile {row['Profile_Id']} band {row['Soh_Band_Min_Pct']}.",
                    field_name="Soh_Band_Min_Pct",
                )
            )
    return issues


def _validate_soh_curve_continuity(raw: dict[str, pd.DataFrame]) -> list[ImportValidationIssue]:
    issues: list[ImportValidationIssue] = []
    df = raw.get("soh_curve_314_template")
    if df is None or not {"Profile_Id", "Life_Year_Index"}.issubset(df.columns):
        return issues

    valid_points = df.dropna(subset=["Profile_Id", "Life_Year_Index", "Soh_Dc_Pct"])
    for profile_id, group in valid_points.groupby("Profile_Id", dropna=True):
        year_values: list[int] = []
        for value in group["Life_Year_Index"].tolist():
            numeric = _to_float(value)
            if numeric is None or int(numeric) != numeric:
                issues.append(
                    _issue(
                        ValidationSeverity.ERROR,
                        "soh_curve_314_template",
                        f"Non-integer year index detected for profile {profile_id}.",
                        field_name="Life_Year_Index",
                        row_ref=f"profile={profile_id}",
                    )
                )
                continue
            year_values.append(int(numeric))
        if not year_values:
            continue
        ordered = sorted(set(year_values))
        expected = list(range(ordered[0], ordered[-1] + 1))
        if ordered != expected or ordered[0] != 0:
            issues.append(
                _issue(
                    ValidationSeverity.ERROR,
                    "soh_curve_314_template",
                    f"Life_Year_Index must be continuous and start at 0 for profile {profile_id}. Found {ordered}.",
                    field_name="Life_Year_Index",
                    row_ref=f"profile={profile_id}",
                )
            )
    return issues


def collect_dc_import_validation_issues(path: Path) -> list[ImportValidationIssue]:
    issues, raw = _load_raw_sheets(path)
    fatal_structure = any(issue.severity == ValidationSeverity.ERROR.value for issue in issues)
    if fatal_structure and not raw:
        return issues

    issues.extend(_validate_required_non_null(raw))
    issues.extend(_validate_numeric_ranges(raw))
    issues.extend(_validate_percent_columns(raw))
    issues.extend(_validate_duplicate_profiles(raw))
    issues.extend(_validate_curve_duplicates(raw))
    issues.extend(_validate_soh_curve_continuity(raw))
    return issues


def validate_dc_workbook(path: Path) -> list[str]:
    issues = collect_dc_import_validation_issues(path)
    missing_sheets = [
        issue.sheet_name
        for issue in issues
        if issue.severity == ValidationSeverity.ERROR.value and issue.message.startswith("Missing required sheet:")
    ]
    formatted: list[str] = []
    if missing_sheets:
        formatted.append(f"Missing required sheets: {', '.join(sorted(missing_sheets))}")
    formatted.extend(
        f"{issue.sheet_name}: {issue.message}"
        if issue.field_name is None
        else f"{issue.sheet_name}.{issue.field_name}: {issue.message}"
        for issue in issues
        if issue.severity == ValidationSeverity.ERROR.value and not issue.message.startswith("Missing required sheet:")
    )
    return formatted
