from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_render_input import (
    SldCanonicalInput,
    SldEquipmentRatings,
    SldInputOverride,
    SldLabels,
    legacy_sld_override_preset,
)


SOURCE_PRIORITY_V1 = {
    "A": "explicit snapshot / canonical run data",
    "B": "ac_output authoritative allocation",
    "C": "project-level persisted settings",
    "D": "UI override with explicit override_mode only",
    "E": "all other sources forbidden",
}


class SldInputValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _deep_get(mapping: dict[str, Any], *path: str) -> Any:
    node: Any = mapping
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


class SldInputBuilder:
    def build_from_sources(
        self,
        *,
        run_bundle: DcRunBundle,
        ac_snapshot: AcSnapshot,
        options: SldRenderOptions,
        project_settings: dict[str, Any] | None = None,
        validation_mode: str = "strict",
    ) -> SldCanonicalInput:
        errors: list[str] = []
        draft_warnings: list[str] = []
        project_settings = project_settings or {}
        ac_output = ac_snapshot.output if isinstance(ac_snapshot.output, dict) else {}
        override = options.overrides
        override_mode = bool(options.override_mode)

        if override is not None and not override_mode:
            errors.append("SLD overrides were provided but override_mode is disabled.")

        input_payload = {}
        if run_bundle.input_snapshot and isinstance(run_bundle.input_snapshot.payload, dict):
            input_payload = run_bundle.input_snapshot.payload
        case_input = input_payload.get("case_input") or {}

        ac_blocks_total = self._required_int(
            "ac_blocks_total",
            [ac_output.get("num_blocks"), ac_output.get("ac_blocks_total")],
            errors,
        )

        group_index = _safe_int(options.group_index)
        if group_index is None or group_index <= 0:
            errors.append("group_index is required and must be > 0.")
            group_index = 1
        elif ac_blocks_total is not None and group_index > ac_blocks_total:
            errors.append("group_index cannot exceed ac_blocks_total.")

        project_name = self._required_text(
            "project_name",
            [
                run_bundle.project_name,
                getattr(run_bundle.snapshot.stage1, "project_name", None),
                case_input.get("project_name"),
            ],
            errors,
        )
        scenario_id = self._required_text(
            "scenario_id",
            [
                run_bundle.scenario_mode,
                case_input.get("scenario_id"),
                getattr(run_bundle.snapshot.stage2, "mode", None),
            ],
            errors,
        )

        project_frequency_hz = self._optional_float(
            [case_input.get("poi_frequency_hz"), ac_snapshot.inputs.get("grid_frequency_hz")]
        )

        mv_voltage_kv = self._required_float(
            "mv_voltage_kv",
            [
                case_input.get("poi_nominal_voltage_kv"),
                ac_output.get("mv_voltage_kv"),
                ac_output.get("mv_kv"),
                ac_output.get("grid_kv"),
            ],
            errors,
        )

        lv_voltage_v_ll = self._required_float(
            "lv_voltage_v_ll",
            [
                ac_output.get("lv_voltage_v"),
                ac_output.get("lv_v"),
                ac_output.get("inverter_lv_v"),
                ac_snapshot.inputs.get("lv_voltage_v"),
            ],
            errors,
        )

        transformer_rating_mva = self._required_float(
            "transformer_rating_mva",
            [
                ac_output.get("transformer_mva"),
                self._kva_to_mva(ac_output.get("transformer_kva")),
                project_settings.get("transformer_rating_mva"),
            ],
            errors,
        )
        transformer_rating_mva = self._fill_from_override_if_missing(
            "transformer_rating_mva",
            transformer_rating_mva,
            override_mode,
            override.transformer_rating_mva if override else None,
            errors,
        )

        transformer_vector_group = self._optional_text(
            [_deep_get(project_settings, "transformer", "vector_group")]
        )
        transformer_vector_group = self._fill_text_from_override_or_draft(
            "transformer_vector_group",
            transformer_vector_group,
            override_mode,
            override.transformer_vector_group if override else None,
            validation_mode,
            draft_warnings,
            errors,
            legacy_sld_override_preset().get("transformer_vector_group"),
        )

        transformer_uk_percent = self._optional_float(
            [_deep_get(project_settings, "transformer", "uk_percent")]
        )
        transformer_uk_percent = self._fill_float_from_override_or_draft(
            "transformer_uk_percent",
            transformer_uk_percent,
            override_mode,
            override.transformer_uk_percent if override else None,
            validation_mode,
            draft_warnings,
            errors,
            legacy_sld_override_preset().get("transformer_uk_percent"),
        )

        pcs_count = self._resolve_group_pcs_count(ac_output, group_index, errors)
        pcs_rating_kw_list = self._resolve_group_pcs_ratings(ac_output, group_index, pcs_count, errors)

        dc_block_energy_mwh = self._resolve_dc_block_energy(run_bundle, errors)
        dc_blocks_per_feeder = self._resolve_dc_blocks_per_feeder(
            ac_output,
            group_index,
            pcs_count,
            errors,
            override_available=bool(override_mode and override and override.dc_blocks_per_feeder),
        )
        dc_blocks_per_feeder = self._fill_list_from_override_if_missing(
            "dc_blocks_per_feeder",
            dc_blocks_per_feeder,
            override_mode,
            override.dc_blocks_per_feeder if override else None,
            errors,
        )
        dc_blocks_total_in_group = sum(dc_blocks_per_feeder or [])

        dc_block_voltage_v = self._optional_float([project_settings.get("dc_block_voltage_v")])
        dc_block_voltage_v = self._fill_float_from_override_or_draft(
            "dc_block_voltage_v",
            dc_block_voltage_v,
            override_mode,
            override.dc_block_voltage_v if override else None,
            validation_mode,
            draft_warnings,
            errors,
            None,
        )

        labels = self._resolve_labels(
            project_settings=project_settings,
            override=override,
            override_mode=override_mode,
            validation_mode=validation_mode,
            draft_warnings=draft_warnings,
            errors=errors,
        )
        equipment_ratings = self._resolve_equipment(
            project_settings=project_settings,
            override=override,
            override_mode=override_mode,
            validation_mode=validation_mode,
            draft_warnings=draft_warnings,
            errors=errors,
        )

        if errors:
            raise SldInputValidationError(errors)

        try:
            return SldCanonicalInput(
                run_id=run_bundle.run_id,
                project_name=project_name,
                scenario_id=scenario_id,
                group_index=group_index,
                ac_blocks_total=ac_blocks_total,
                project_frequency_hz=project_frequency_hz,
                mv_voltage_kv=mv_voltage_kv,
                lv_voltage_v_ll=lv_voltage_v_ll,
                transformer_rating_mva=transformer_rating_mva,
                transformer_vector_group=transformer_vector_group,
                transformer_uk_percent=transformer_uk_percent,
                pcs_count=pcs_count,
                pcs_rating_kw_list=pcs_rating_kw_list,
                dc_block_energy_mwh=dc_block_energy_mwh,
                dc_blocks_total_in_group=dc_blocks_total_in_group,
                dc_blocks_per_feeder=dc_blocks_per_feeder,
                dc_block_voltage_v=dc_block_voltage_v,
                equipment_ratings=equipment_ratings,
                labels=labels,
                diagram_mode="one_ac_block_group",
                theme=options.theme or "dark",
                compact_mode=bool(options.compact_mode),
                draw_summary=bool(options.draw_summary),
                validation_mode=validation_mode,
                override_mode=override_mode,
                source_trace=dict(SOURCE_PRIORITY_V1),
                draft_warnings=draft_warnings,
            )
        except ValidationError as exc:
            normalized = [f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()]
            raise SldInputValidationError(normalized) from exc

    def _resolve_group_pcs_count(self, ac_output: dict[str, Any], group_index: int, errors: list[str]) -> int | None:
        group_idx = max(0, group_index - 1)
        pcs_count_by_block = ac_output.get("pcs_count_by_block")
        if isinstance(pcs_count_by_block, list) and group_idx < len(pcs_count_by_block):
            value = _safe_int(pcs_count_by_block[group_idx])
            if value is not None and value > 0:
                return value
        for key in ("pcs_count_per_ac_block", "pcs_per_block"):
            value = _safe_int(ac_output.get(key))
            if value is not None and value > 0:
                return value
        errors.append("pcs_count is required from authoritative AC output. No silent default is allowed.")
        return None

    def _resolve_group_pcs_ratings(
        self,
        ac_output: dict[str, Any],
        group_index: int,
        pcs_count: int | None,
        errors: list[str],
    ) -> list[float]:
        if not pcs_count:
            return []
        ratings_by_block = ac_output.get("pcs_rating_kw_list_by_block")
        group_idx = max(0, group_index - 1)
        if isinstance(ratings_by_block, list) and group_idx < len(ratings_by_block):
            candidate = ratings_by_block[group_idx]
            if isinstance(candidate, list) and len(candidate) == pcs_count:
                parsed = [_safe_float(value) for value in candidate]
                if all(value is not None and value > 0 for value in parsed):
                    return [float(value) for value in parsed if value is not None]
        for key in ("pcs_rating_kw_each", "pcs_kw", "pcs_power_kw"):
            rating = _safe_float(ac_output.get(key))
            if rating is not None and rating > 0:
                return [float(rating) for _ in range(pcs_count)]
        errors.append("pcs_rating_kw_list is required from authoritative AC output. No silent default is allowed.")
        return []

    def _resolve_dc_block_energy(self, run_bundle: DcRunBundle, errors: list[str]) -> float | None:
        capacities = sorted(
            {
                round(float(item.unit_capacity_mwh), 6)
                for item in run_bundle.snapshot.stage2.block_config_items
                if getattr(item, "count", 0) and float(item.unit_capacity_mwh) > 0
            }
        )
        if len(capacities) == 1:
            return capacities[0]
        if not capacities:
            errors.append("dc_block_energy_mwh is missing from canonical run data.")
        else:
            errors.append(
                "dc_block_energy_mwh is ambiguous in the current run data. Provide an explicit canonical source before rendering."
            )
        return None

    def _resolve_dc_blocks_per_feeder(
        self,
        ac_output: dict[str, Any],
        group_index: int,
        pcs_count: int | None,
        errors: list[str],
        *,
        override_available: bool,
    ) -> list[int] | None:
        if not pcs_count:
            return None
        group_idx = max(0, group_index - 1)
        plan = ac_output.get("dc_allocation_plan")
        if isinstance(plan, list) and group_idx < len(plan):
            entry = plan[group_idx]
            if isinstance(entry, dict):
                feeder_allocations = entry.get("feeder_allocations")
                if isinstance(feeder_allocations, list) and len(feeder_allocations) == pcs_count:
                    parsed = [_safe_int(value) for value in feeder_allocations]
                    if all(value is not None and value >= 0 for value in parsed):
                        return [int(value) for value in parsed if value is not None]
        by_block = ac_output.get("dc_blocks_per_feeder_by_block")
        if isinstance(by_block, list) and group_idx < len(by_block):
            candidate = by_block[group_idx]
            if isinstance(candidate, list) and len(candidate) == pcs_count:
                parsed = [_safe_int(value) for value in candidate]
                if all(value is not None and value >= 0 for value in parsed):
                    return [int(value) for value in parsed if value is not None]
        allocation = ac_output.get("dc_block_allocation")
        if isinstance(allocation, dict):
            per_ac_block = allocation.get("per_ac_block")
            if isinstance(per_ac_block, list) and group_idx < len(per_ac_block):
                per_feeder = per_ac_block[group_idx].get("per_feeder")
                if isinstance(per_feeder, dict):
                    values = [per_feeder[key] for key in sorted(per_feeder.keys())]
                    if len(values) == pcs_count:
                        parsed = [_safe_int(value) for value in values]
                        if all(value is not None and value >= 0 for value in parsed):
                            return [int(value) for value in parsed if value is not None]
        if not override_available:
            errors.append(
                "dc_blocks_per_feeder is required from AC authoritative allocation or explicit override. No even-distribution fallback is allowed."
            )
        return None

    def _resolve_labels(
        self,
        *,
        project_settings: dict[str, Any],
        override: SldInputOverride | None,
        override_mode: bool,
        validation_mode: str,
        draft_warnings: list[str],
        errors: list[str],
    ) -> SldLabels | None:
        try:
            if isinstance(project_settings.get("labels"), dict):
                return SldLabels.model_validate(project_settings["labels"])
            if isinstance(project_settings.get("mv_labels"), dict):
                return SldLabels.model_validate(project_settings["mv_labels"])
            if override_mode and override and override.labels is not None:
                return override.labels
            if validation_mode == "draft":
                draft_warnings.append("labels were filled from legacy draft preset.")
                return SldLabels.model_validate(legacy_sld_override_preset()["labels"])
            errors.append("labels are required in strict mode from project settings or explicit override.")
            return None
        except ValidationError as exc:
            errors.append(f"labels: {exc.errors()[0]['msg']}")
            return None

    def _resolve_equipment(
        self,
        *,
        project_settings: dict[str, Any],
        override: SldInputOverride | None,
        override_mode: bool,
        validation_mode: str,
        draft_warnings: list[str],
        errors: list[str],
    ) -> SldEquipmentRatings | None:
        try:
            if isinstance(project_settings.get("equipment_ratings"), dict):
                return SldEquipmentRatings.model_validate(project_settings["equipment_ratings"])
            if override_mode and override and override.equipment_ratings is not None:
                return override.equipment_ratings
            if validation_mode == "draft":
                draft_warnings.append("equipment_ratings were filled from legacy draft preset.")
                return SldEquipmentRatings.model_validate(legacy_sld_override_preset()["equipment_ratings"])
            errors.append("equipment_ratings are required in strict mode from project settings or explicit override.")
            return None
        except ValidationError as exc:
            errors.append(f"equipment_ratings: {exc.errors()[0]['msg']}")
            return None

    def _required_text(self, field_name: str, candidates: list[Any], errors: list[str]) -> str | None:
        for value in candidates:
            resolved = str(value or "").strip()
            if resolved:
                return resolved
        errors.append(f"{field_name} is required from authoritative sources.")
        return None

    def _optional_text(self, candidates: list[Any]) -> str | None:
        for value in candidates:
            resolved = str(value or "").strip()
            if resolved:
                return resolved
        return None

    def _required_float(self, field_name: str, candidates: list[Any], errors: list[str]) -> float | None:
        value = self._optional_float(candidates)
        if value is None or value <= 0:
            errors.append(f"{field_name} is required from authoritative sources and must be > 0.")
            return None
        return value

    def _required_int(self, field_name: str, candidates: list[Any], errors: list[str]) -> int | None:
        for raw in candidates:
            value = _safe_int(raw)
            if value is not None and value > 0:
                return value
        errors.append(f"{field_name} is required from authoritative sources and must be > 0.")
        return None

    def _optional_float(self, candidates: list[Any]) -> float | None:
        for raw in candidates:
            value = _safe_float(raw)
            if value is not None:
                return value
        return None

    def _fill_from_override_if_missing(
        self,
        field_name: str,
        current_value: float | None,
        override_mode: bool,
        override_value: float | None,
        errors: list[str],
    ) -> float | None:
        if current_value is not None and override_mode and override_value is not None:
            errors.append(f"{field_name} override is not allowed when an authoritative value already exists.")
            return current_value
        if current_value is None and override_mode and override_value is not None and override_value > 0:
            return float(override_value)
        return current_value

    def _fill_list_from_override_if_missing(
        self,
        field_name: str,
        current_value: list[int] | None,
        override_mode: bool,
        override_value: list[int] | None,
        errors: list[str],
    ) -> list[int] | None:
        if current_value is not None and override_mode and override_value is not None:
            if current_value != [int(v) for v in override_value]:
                errors.append(f"{field_name} override is not allowed when authoritative allocation already exists.")
            return current_value
        if current_value is None and override_mode and override_value is not None:
            return [int(v) for v in override_value]
        return current_value

    def _fill_text_from_override_or_draft(
        self,
        field_name: str,
        current_value: str | None,
        override_mode: bool,
        override_value: str | None,
        validation_mode: str,
        draft_warnings: list[str],
        errors: list[str],
        draft_value: str | None,
    ) -> str | None:
        if current_value:
            if override_mode and override_value and override_value.strip() != current_value:
                errors.append(f"{field_name} override is not allowed when an authoritative/project value already exists.")
            return current_value
        if override_mode and override_value and override_value.strip():
            return override_value.strip()
        if validation_mode == "draft" and draft_value:
            draft_warnings.append(f"{field_name} was filled from legacy draft preset.")
            return draft_value
        if validation_mode == "strict":
            errors.append(f"{field_name} is required in strict mode.")
        return None

    def _fill_float_from_override_or_draft(
        self,
        field_name: str,
        current_value: float | None,
        override_mode: bool,
        override_value: float | None,
        validation_mode: str,
        draft_warnings: list[str],
        errors: list[str],
        draft_value: float | None,
    ) -> float | None:
        if current_value is not None and current_value > 0:
            if override_mode and override_value is not None and float(override_value) != float(current_value):
                errors.append(f"{field_name} override is not allowed when an authoritative/project value already exists.")
            return float(current_value)
        if override_mode and override_value is not None and float(override_value) > 0:
            return float(override_value)
        if validation_mode == "draft" and draft_value is not None:
            draft_warnings.append(f"{field_name} was filled from legacy draft preset.")
            return float(draft_value)
        if validation_mode == "strict":
            errors.append(f"{field_name} is required in strict mode.")
        return None

    def _kva_to_mva(self, value: Any) -> float | None:
        parsed = _safe_float(value)
        if parsed is None or parsed <= 0:
            return None
        return parsed / 1000.0


def build_sld_canonical_input(
    *,
    run_bundle: DcRunBundle,
    ac_snapshot: AcSnapshot,
    options: SldRenderOptions,
    project_settings: dict[str, Any] | None = None,
    validation_mode: str = "strict",
) -> SldCanonicalInput:
    return SldInputBuilder().build_from_sources(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        validation_mode=validation_mode,
    )
