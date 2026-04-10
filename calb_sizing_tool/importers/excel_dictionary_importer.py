from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.domain.enums import ImportMode, ValidationSeverity
from calb_sizing_tool.importers.import_preview import build_dc_import_preview
from calb_sizing_tool.importers.import_validators import collect_dc_import_validation_issues, validate_dc_workbook
from calb_sizing_tool.importers.parameter_definition_catalog import build_parameter_definition_catalog
from calb_sizing_tool.repositories.master_data_repository import MasterDataRepository
from calb_sizing_tool.repositories.parameter_repository import ParameterRepository
from calb_sizing_tool.repositories.run_repository import RunRepository
from calb_sizing_tool.schemas.master_data import ImportDiffSample, ImportJobSummary, ImportObjectSummary, ImportValidationIssue
from calb_sizing_tool.schemas.master_data import ImportPreview


def _records_with_raw(df: pd.DataFrame, rename_map: dict[str, str], keep_fields: list[str]) -> list[dict]:
    renamed = df.rename(columns=rename_map).copy()
    records: list[dict] = []
    for _, row in renamed.iterrows():
        item = {field: row.get(field) for field in keep_fields if field in renamed.columns}
        item["raw_row_json"] = row.to_dict()
        records.append(item)
    return records


def _records_only(df: pd.DataFrame, rename_map: dict[str, str], keep_fields: list[str]) -> list[dict]:
    renamed = df.rename(columns=rename_map).copy()
    return [{field: row.get(field) for field in keep_fields if field in renamed.columns} for _, row in renamed.iterrows()]


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_value(val) for key, val in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        return round(value, 10)
    return value


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalize_value(value) for key, value in sorted(record.items(), key=lambda item: str(item[0]))}


def _key_for_record(object_name: str, record: dict[str, Any]) -> str:
    if object_name == "parameter_definition":
        return f"field_code={record.get('field_code')}"
    if object_name == "battery_cell_type":
        return f"source_cell_type_id={record.get('source_cell_type_id')}"
    if object_name == "pack_type":
        return f"source_pack_type_id={record.get('source_pack_type_id')}"
    if object_name == "rack_type":
        return f"source_rack_type_id={record.get('source_rack_type_id')}"
    if object_name == "dc_block_template":
        return f"source_dc_block_template_id={record.get('source_dc_block_template_id')}"
    if object_name in {"soh_profile", "rte_profile"}:
        return f"source_profile_id={record.get('source_profile_id')}"
    if object_name == "soh_curve_point":
        return "profile={profile}|year={year}|cycle={cycle}".format(
            profile=record.get("source_profile_id"),
            year=record.get("life_year_index"),
            cycle=record.get("cycle_index"),
        )
    if object_name == "rte_curve_band":
        return "profile={profile}|min={min_band}|max={max_band}".format(
            profile=record.get("source_profile_id"),
            min_band=record.get("soh_band_min_pct"),
            max_band=record.get("soh_band_max_pct"),
        )
    return str(record)


def _diff_object(
    object_name: str,
    incoming: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    *,
    sample_limit: int,
) -> ImportObjectSummary:
    incoming_map = {_key_for_record(object_name, _normalize_record(item)): _normalize_record(item) for item in incoming}
    existing_map = {_key_for_record(object_name, _normalize_record(item)): _normalize_record(item) for item in existing}

    insert_keys = [key for key in incoming_map if key not in existing_map]
    update_keys = [key for key in incoming_map if key in existing_map and incoming_map[key] != existing_map[key]]
    skip_keys = [key for key in incoming_map if key in existing_map and incoming_map[key] == existing_map[key]]
    delete_keys = [key for key in existing_map if key not in incoming_map]

    diff_samples: list[ImportDiffSample] = []
    for key in insert_keys[:sample_limit]:
        diff_samples.append(ImportDiffSample(key=key, action="insert", before=None, after=incoming_map[key]))
    remaining = sample_limit - len(diff_samples)
    for key in update_keys[: max(remaining, 0)]:
        diff_samples.append(ImportDiffSample(key=key, action="update", before=existing_map[key], after=incoming_map[key]))
    remaining = sample_limit - len(diff_samples)
    for key in delete_keys[: max(remaining, 0)]:
        diff_samples.append(ImportDiffSample(key=key, action="delete", before=existing_map[key], after=None))

    return ImportObjectSummary(
        object_name=object_name,
        source_row_count=len(incoming),
        existing_row_count=len(existing),
        changed_rows_count=len(insert_keys) + len(update_keys) + len(delete_keys),
        insert_count=len(insert_keys),
        update_count=len(update_keys),
        skip_count=len(skip_keys),
        delete_count=len(delete_keys),
        diff_samples=diff_samples,
    )


class ExcelDictionaryImporter:
    def __init__(self, session: Session):
        self.session = session
        self.master_data_repository = MasterDataRepository(session)
        self.parameter_repository = ParameterRepository(session)
        self.run_repository = RunRepository(session)

    def preview(self, workbook_path: Path):
        return build_dc_import_preview(workbook_path)

    def _build_master_payload(self, workbook_path: Path) -> dict[str, list[dict[str, Any]]]:
        bundle = load_dc_excel_bundle_from_path(workbook_path)
        raw = bundle.raw_sheets

        return {
            "battery_cell_type": _records_with_raw(
                raw["battery_cell_type_314_data"],
                {
                    "Cell_Type_Id": "source_cell_type_id",
                    "Cell_Model": "cell_model",
                    "Cell_Chemistry": "chemistry_code",
                    "Cell_Capacity_Ah": "cell_capacity_ah",
                    "Cell_Nominal_Voltage_V": "cell_nominal_voltage_v",
                    "Cell_Energy_Wh": "cell_energy_wh",
                    "Is_Active": "is_active",
                },
                [
                    "source_cell_type_id",
                    "cell_model",
                    "chemistry_code",
                    "cell_capacity_ah",
                    "cell_nominal_voltage_v",
                    "cell_energy_wh",
                    "is_active",
                ],
            ),
            "pack_type": _records_with_raw(
                raw["pack_type_314_data"],
                {
                    "Pack_Type_Id": "source_pack_type_id",
                    "Pack_Model": "pack_model",
                    "Cell_Type_Id": "source_cell_type_id",
                    "Cells_In_Series": "cells_in_series",
                    "Cells_In_Parallel": "cells_in_parallel",
                    "Pack_Nominal_Voltage_V": "pack_nominal_voltage_v",
                    "Pack_Nameplate_Capacity_Kwh": "pack_nameplate_capacity_kwh",
                    "Is_Active": "is_active",
                },
                [
                    "source_pack_type_id",
                    "source_cell_type_id",
                    "pack_model",
                    "cells_in_series",
                    "cells_in_parallel",
                    "pack_nominal_voltage_v",
                    "pack_nameplate_capacity_kwh",
                    "is_active",
                ],
            ),
            "rack_type": _records_with_raw(
                raw["rack_type_314_data"],
                {
                    "Rack_Type_Id": "source_rack_type_id",
                    "Rack_Model": "rack_model",
                    "Pack_Type_Id": "source_pack_type_id",
                    "Packs_Per_Rack": "packs_per_rack",
                    "Rack_Nameplate_Capacity_Mwh": "rack_nameplate_capacity_mwh",
                    "Rack_Aux_Energy_Kwh": "rack_aux_energy_kwh",
                    "Is_Active": "is_active",
                },
                [
                    "source_rack_type_id",
                    "source_pack_type_id",
                    "rack_model",
                    "packs_per_rack",
                    "rack_nameplate_capacity_mwh",
                    "rack_aux_energy_kwh",
                    "is_active",
                ],
            ),
            "dc_block_template": _records_with_raw(
                bundle.df_blocks,
                {
                    "Dc_Block_Template_Id": "source_dc_block_template_id",
                    "Rack_Type_Id": "source_rack_type_id",
                    "Dc_Block_Code": "dc_block_code",
                    "Dc_Block_Name": "dc_block_name",
                    "Block_Form": "block_form",
                    "Container_Length_Ft": "container_length_ft",
                    "Racks_Per_Block": "racks_per_block",
                    "Packs_Per_Block": "packs_per_block",
                    "Block_Nameplate_Capacity_Mwh": "block_nameplate_capacity_mwh",
                    "Block_Aux_Energy_Kwh": "block_aux_energy_kwh",
                    "Design_Max_C_Rate": "design_max_c_rate",
                    "Is_Active": "is_active",
                },
                [
                    "source_dc_block_template_id",
                    "source_rack_type_id",
                    "dc_block_code",
                    "dc_block_name",
                    "block_form",
                    "container_length_ft",
                    "racks_per_block",
                    "packs_per_block",
                    "block_nameplate_capacity_mwh",
                    "block_aux_energy_kwh",
                    "design_max_c_rate",
                    "is_active",
                ],
            ),
            "soh_profile": _records_with_raw(
                raw["soh_profile_314_data"],
                {
                    "Profile_Id": "source_profile_id",
                    "Cell_Type_Id": "source_cell_type_id",
                    "Profile_Name": "profile_name",
                    "Cycles_Per_Year": "cycles_per_year",
                    "C_Rate": "c_rate",
                    "Reference_Temperature_C": "reference_temperature_c",
                },
                [
                    "source_profile_id",
                    "source_cell_type_id",
                    "profile_name",
                    "cycles_per_year",
                    "c_rate",
                    "reference_temperature_c",
                ],
            ),
            "rte_profile": _records_with_raw(
                raw["rte_profile_314_data"],
                {
                    "Profile_Id": "source_profile_id",
                    "Cell_Type_Id": "source_cell_type_id",
                    "Profile_Name": "profile_name",
                    "Cycles_Per_Year": "cycles_per_year",
                    "C_Rate": "c_rate",
                },
                [
                    "source_profile_id",
                    "source_cell_type_id",
                    "profile_name",
                    "cycles_per_year",
                    "c_rate",
                ],
            ),
            "soh_curve_point": _records_only(
                raw["soh_curve_314_template"],
                {
                    "Profile_Id": "source_profile_id",
                    "Life_Year_Index": "life_year_index",
                    "Cycle_Index": "cycle_index",
                    "Soh_Dc_Pct": "soh_dc_pct",
                },
                [
                    "source_profile_id",
                    "life_year_index",
                    "cycle_index",
                    "soh_dc_pct",
                ],
            ),
            "rte_curve_band": _records_only(
                raw["rte_curve_314_template"],
                {
                    "Profile_Id": "source_profile_id",
                    "Soh_Band_Min_Pct": "soh_band_min_pct",
                    "Soh_Band_Max_Pct": "soh_band_max_pct",
                    "Rte_Dc_Pct": "rte_dc_pct",
                },
                [
                    "source_profile_id",
                    "soh_band_min_pct",
                    "soh_band_max_pct",
                    "rte_dc_pct",
                ],
            ),
        }

    def _build_import_payload(self, workbook_path: Path) -> dict[str, list[dict[str, Any]]]:
        parameter_definitions = [item.model_dump() for item in build_parameter_definition_catalog()]
        payload = {"parameter_definition": parameter_definitions}
        payload.update(self._build_master_payload(workbook_path))
        return payload

    def _build_existing_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        payload = {"parameter_definition": self.parameter_repository.export_definition_snapshot()}
        payload.update(self.master_data_repository.export_dc_master_data_snapshot())
        return payload

    def run_import(
        self,
        workbook_path: Path,
        *,
        mode: str | ImportMode,
        version_tag: str,
        source_ref: str = "excel_dictionary_importer",
        actor: str | None = None,
        diff_sample_limit: int = 5,
    ) -> ImportJobSummary:
        import_mode = ImportMode(mode)
        workbook_path = Path(workbook_path)
        validation_errors = collect_dc_import_validation_issues(workbook_path)
        try:
            preview = build_dc_import_preview(workbook_path)
        except Exception:
            preview = ImportPreview(
                workbook_name=workbook_path.name,
                sheets_present=[],
                row_counts={},
                column_map={},
            )
        incoming_payload: dict[str, list[dict[str, Any]]] = {}
        try:
            incoming_payload = self._build_import_payload(workbook_path)
        except Exception as exc:
            validation_errors.append(
                ImportValidationIssue(
                    severity=ValidationSeverity.ERROR.value,
                    sheet_name="workbook",
                    message=f"Importer failed to build payload: {exc}",
                )
            )
        existing_payload = self._build_existing_snapshot()

        object_summaries = [
            _diff_object(
                object_name,
                incoming_payload.get(object_name, []),
                existing_payload.get(object_name, []),
                sample_limit=diff_sample_limit if import_mode == ImportMode.PREVIEW_DIFF else diff_sample_limit,
            )
            for object_name in incoming_payload
        ]

        has_errors = any(item.severity == ValidationSeverity.ERROR.value for item in validation_errors)
        applied = False
        if import_mode == ImportMode.APPLY_IMPORT and not has_errors:
            self.parameter_repository.upsert_definitions(
                build_parameter_definition_catalog(),
                version_tag=version_tag,
                source_ref=source_ref,
            )
            master_payload = {key: value for key, value in incoming_payload.items() if key != "parameter_definition"}
            self.master_data_repository.replace_dc_master_data(
                master_payload,
                version_tag=version_tag,
                source_ref=source_ref,
            )
            applied = True

        summary = ImportJobSummary(
            import_job_id=str(uuid.uuid4()),
            mode=import_mode.value,
            workbook_name=preview.workbook_name,
            workbook_path=str(workbook_path.resolve()),
            version_tag=version_tag,
            source_ref=source_ref,
            applied=applied,
            validation_errors=validation_errors,
            object_summaries=object_summaries,
            total_changed_rows_count=sum(item.changed_rows_count for item in object_summaries),
            total_insert_count=sum(item.insert_count for item in object_summaries),
            total_update_count=sum(item.update_count for item in object_summaries),
            total_skip_count=sum(item.skip_count for item in object_summaries),
            total_delete_count=sum(item.delete_count for item in object_summaries),
        )

        audit_row = self.run_repository.add_audit_log(
            entity_type="excel_import_job",
            entity_id=summary.import_job_id,
            action=import_mode.value,
            actor=actor,
            payload_json=summary.model_dump(mode="python"),
            remarks=None if applied else ("Validation errors blocked apply." if has_errors and import_mode == ImportMode.APPLY_IMPORT else "Preview only."),
            version_tag=version_tag,
            source_ref=source_ref,
        )
        self.session.flush()
        summary.audit_log_id = audit_row.audit_log_id
        return summary

    def dry_run(
        self,
        workbook_path: Path,
        *,
        version_tag: str,
        source_ref: str = "excel_dictionary_importer",
        actor: str | None = None,
    ) -> ImportJobSummary:
        return self.run_import(
            workbook_path,
            mode=ImportMode.DRY_RUN,
            version_tag=version_tag,
            source_ref=source_ref,
            actor=actor,
        )

    def preview_diff(
        self,
        workbook_path: Path,
        *,
        version_tag: str,
        source_ref: str = "excel_dictionary_importer",
        actor: str | None = None,
    ) -> ImportJobSummary:
        return self.run_import(
            workbook_path,
            mode=ImportMode.PREVIEW_DIFF,
            version_tag=version_tag,
            source_ref=source_ref,
            actor=actor,
        )

    def apply_import(
        self,
        workbook_path: Path,
        *,
        version_tag: str,
        source_ref: str = "excel_dictionary_importer",
        actor: str | None = None,
    ) -> ImportJobSummary:
        return self.run_import(
            workbook_path,
            mode=ImportMode.APPLY_IMPORT,
            version_tag=version_tag,
            source_ref=source_ref,
            actor=actor,
        )

    def import_dc_dictionary(
        self,
        workbook_path: Path,
        *,
        version_tag: str,
        source_ref: str = "excel_dictionary_importer",
    ) -> dict[str, int]:
        issues = validate_dc_workbook(workbook_path)
        if issues:
            raise ValueError("; ".join(issues))
        summary = self.apply_import(workbook_path, version_tag=version_tag, source_ref=source_ref)
        return {item.object_name: item.source_row_count for item in summary.object_summaries}
