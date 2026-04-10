from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import Field

from calb_sizing_tool.schemas.common import CanonicalBaseModel


class ParameterDefinitionSchema(CanonicalBaseModel):
    field_code: str
    display_name_en: str
    display_name_zh: str
    unit: str
    data_type: str
    nullable: bool
    required_for_stage: str
    validation_rule: str
    source_sheet: str
    legacy_field_name: str
    remarks: str = ""


class ParameterSetSchema(CanonicalBaseModel):
    set_code: str
    set_name: str
    stage_scope: str
    parameter_values: dict[str, Any]
    version_tag: str | None = None
    source_ref: str | None = None


class DcExcelMasterDataBundle(CanonicalBaseModel):
    workbook_path: Path
    defaults: dict[str, Any]
    df_blocks: pd.DataFrame
    df_soh_profile: pd.DataFrame
    df_soh_curve: pd.DataFrame
    df_rte_profile: pd.DataFrame
    df_rte_curve: pd.DataFrame
    raw_sheets: dict[str, pd.DataFrame]


class ImportPreview(CanonicalBaseModel):
    workbook_name: str
    sheets_present: list[str]
    row_counts: dict[str, int]
    column_map: dict[str, list[str]]


class ImportValidationIssue(CanonicalBaseModel):
    severity: str
    sheet_name: str
    field_name: str | None = None
    row_ref: str | None = None
    message: str


class ImportDiffSample(CanonicalBaseModel):
    key: str
    action: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class ImportObjectSummary(CanonicalBaseModel):
    object_name: str
    source_row_count: int
    existing_row_count: int
    changed_rows_count: int
    insert_count: int
    update_count: int
    skip_count: int
    delete_count: int = 0
    diff_samples: list[ImportDiffSample] = Field(default_factory=list)


class ImportJobSummary(CanonicalBaseModel):
    import_job_id: str
    mode: str
    workbook_name: str
    workbook_path: str
    version_tag: str
    source_ref: str
    applied: bool
    validation_errors: list[ImportValidationIssue]
    object_summaries: list[ImportObjectSummary]
    total_changed_rows_count: int
    total_insert_count: int
    total_update_count: int
    total_skip_count: int
    total_delete_count: int
    audit_log_id: str | None = None
