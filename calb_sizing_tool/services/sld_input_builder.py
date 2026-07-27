from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from calb_sizing_tool.adapters.ac_to_sld_adapter import AcToSldAdapterError, normalize_ac_output_for_sld
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.ac_electrical_topology import DcBlockConnection
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_render_input import (
    SldCanonicalInput,
    SldEquipmentRatings,
    SldInputOverride,
    SldLabels,
    legacy_sld_override_preset,
)
from calb_sizing_tool.sld.standard_transformer_impedance import (
    STANDARD_IMPEDANCE_BASIS,
    standard_impedance_percent,
)
from calb_sizing_tool.sld.transformer_vector_group import (
    TransformerVectorGroupError,
    parse_transformer_vector_group,
)
from calb_sizing_tool.sld.voltage_contract import resolve_mv_rmu_voltage_contract


SOURCE_PRIORITY_V1 = {
    "A": "authoritative builder: build_sld_canonical_input()",
    "B": "authoritative AC output normalized by adapters.ac_to_sld_adapter.normalize_ac_output_for_sld()",
    "C": "project-level persisted engineering settings",
    "D": "draft-only override payload from ui.sld_inputs when override_mode is enabled",
    "MV_RMU_CONTRACT": "Phase 1 contract: POI / MV voltage is the single authoritative MV field and RMU rated voltage mirrors it.",
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
    """AUTHORITATIVE builder for formal SLD runtime input.

    This builder accepts the run bundle, the raw AC snapshot, and the optional
    draft override payload. It must not guess AC/DC topology from scattered
    aliases. AC aliases are normalized once inside adapters.ac_to_sld_adapter.
    """

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

        try:
            authoritative_ac = normalize_ac_output_for_sld(ac_output)
        except AcToSldAdapterError as exc:
            errors.extend(exc.errors)
            authoritative_ac = None

        input_payload = {}
        if run_bundle.input_snapshot and isinstance(run_bundle.input_snapshot.payload, dict):
            input_payload = run_bundle.input_snapshot.payload
        case_input = input_payload.get("case_input") or {}

        ac_blocks_total = authoritative_ac.num_blocks if authoritative_ac is not None else None
        if ac_blocks_total is None:
            errors.append("ac_blocks_total is unavailable because AC->SLD normalization failed.")

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

        project_frequency_hz = self._resolve_preferred_optional_float(
            field_name="project_frequency_hz",
            primary_value=case_input.get("poi_frequency_hz"),
            secondary_value=ac_snapshot.inputs.get("grid_frequency_hz"),
            primary_label="case_input.poi_frequency_hz",
            secondary_label="ac_snapshot.inputs.grid_frequency_hz",
            errors=errors,
        )

        mv_voltage_kv = self._resolve_preferred_required_float(
            field_name="mv_voltage_kv",
            primary_value=case_input.get("poi_nominal_voltage_kv"),
            secondary_value=authoritative_ac.mv_voltage_kv if authoritative_ac else None,
            primary_label="case_input.poi_nominal_voltage_kv",
            secondary_label="authoritative_ac.mv_voltage_kv",
            errors=errors,
        )

        lv_voltage_v_ll = self._required_float(
            "lv_voltage_v_ll",
            [
                authoritative_ac.lv_voltage_v if authoritative_ac else None,
                ac_snapshot.inputs.get("lv_voltage_v"),
            ],
            errors,
        )

        transformer_rating_mva = self._required_float(
            "transformer_rating_mva",
            [
                authoritative_ac.transformer_mva if authoritative_ac else None,
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

        # Transformer impedance (Uk%) is NOT a sizing parameter and is usually a
        # project grid-interconnection filing value the owner does not have at
        # concept stage. It must never block the SLD: use a project-declared or
        # override value when present, otherwise a STANDARD TYPICAL by HV class
        # (IEEE C57.12.00/C57.12.10 basis), clearly flagged as typical.
        transformer_uk_percent = self._optional_float(
            [_deep_get(project_settings, "transformer", "uk_percent")]
        )
        if transformer_uk_percent is None and override_mode and override and override.transformer_uk_percent:
            transformer_uk_percent = float(override.transformer_uk_percent)
        if transformer_uk_percent is None or transformer_uk_percent <= 0:
            transformer_uk_percent = standard_impedance_percent(mv_voltage_kv)
            draft_warnings.append(
                f"transformer Uk% not project-declared; using standard typical "
                f"{transformer_uk_percent:g}% ({STANDARD_IMPEDANCE_BASIS})."
            )

        pcs_count = self._resolve_group_value(
            "pcs_count",
            authoritative_ac.pcs_count_by_block if authoritative_ac else None,
            group_index,
            errors,
            must_be_positive=True,
        )
        pcs_rating_kw_list = self._resolve_group_rating_list(
            authoritative_ac.pcs_rating_kw_list_by_block if authoritative_ac else None,
            group_index,
            pcs_count,
            errors,
        )

        # The AC->SLD contract fixes the transformer secondary arrangement:
        # it is selected as part of the AC Block electrical topology, not
        # inferred from the number of PCS feeders.
        lv_winding_count = authoritative_ac.lv_winding_count if authoritative_ac is not None else 1
        transformer_topology = authoritative_ac.transformer_topology if authoritative_ac is not None else None
        configured_lv_winding_count = None
        if override_mode and override and override.lv_winding_count:
            configured_lv_winding_count = override.lv_winding_count
        elif project_settings.get("lv_winding_count"):
            configured_lv_winding_count = project_settings.get("lv_winding_count")
        if authoritative_ac is None and configured_lv_winding_count:
            try:
                lv_winding_count = max(1, int(configured_lv_winding_count))
            except (TypeError, ValueError):
                lv_winding_count = 1
        elif authoritative_ac is not None and configured_lv_winding_count:
            try:
                if int(configured_lv_winding_count) != lv_winding_count:
                    draft_warnings.append(
                        "configured LV winding count was ignored; the authoritative AC block "
                        "topology controls the LV busbar arrangement."
                    )
            except (TypeError, ValueError):
                draft_warnings.append(
                    "configured LV winding count was invalid and was ignored in favour of the authoritative AC block."
                )

        # A vector group declares the actual winding/neutral connection.  It
        # must therefore be resolved only after the authoritative LV topology
        # is known.  Product data owns this declaration for governed AC blocks;
        # a stale Engineering Settings value is a visible conflict, never a
        # silent replacement.  For all other AC sizing paths, persisted project
        # settings remain the owner-facing source before the AC output.
        product_vector = self._optional_text([ac_output.get("transformer_vector_group")])
        project_vector = self._optional_text([
            _deep_get(project_settings, "transformer", "vector_group")
        ])
        product_conflict = ac_output.get("transformer_vector_group_conflict")
        is_governed_product = bool(ac_output.get("governed_product_block_code"))
        if product_conflict:
            detail = (
                f"transformer vector group conflict: product={product_conflict.get('product')!r}, "
                f"engineering_setting={product_conflict.get('engineering_setting')!r}."
                if isinstance(product_conflict, dict)
                else "transformer vector group conflict between the governed product and Engineering Settings."
            )
            if validation_mode == "strict":
                errors.append(detail)
            else:
                draft_warnings.append(detail + " The winding symbol is shown as TBD; no grounding was inferred.")
            transformer_vector_group = "TBD"
        else:
            transformer_vector_group = (
                product_vector if is_governed_product and product_vector else
                self._optional_text([project_vector, product_vector])
            )
            transformer_vector_group = self._fill_text_from_override_or_draft(
                "transformer_vector_group",
                transformer_vector_group,
                override_mode,
                override.transformer_vector_group if override else None,
                validation_mode,
                draft_warnings,
                errors,
                "TBD" if validation_mode == "draft" else None,
            )
        if transformer_vector_group and transformer_vector_group != "TBD":
            try:
                parse_transformer_vector_group(
                    transformer_vector_group,
                    lv_winding_count=lv_winding_count,
                )
            except TransformerVectorGroupError as exc:
                if validation_mode == "strict":
                    errors.append(str(exc))
                else:
                    draft_warnings.append(
                        f"{exc} The winding symbol is shown as TBD; no grounding was inferred."
                    )
                    transformer_vector_group = "TBD"

        dc_block_energy_mwh = self._resolve_dc_block_energy(run_bundle, errors)
        dc_blocks_per_feeder = self._resolve_group_feeder_allocation(
            authoritative_ac.dc_blocks_per_feeder_by_block if authoritative_ac else None,
            group_index,
            pcs_count,
            errors,
            override_available=bool(override_mode and override and override.dc_blocks_per_feeder),
        )
        dc_block_connections = []
        if authoritative_ac is not None:
            connection_index = max(0, group_index - 1)
            if connection_index < len(authoritative_ac.dc_block_connections_by_block):
                dc_block_connections = list(authoritative_ac.dc_block_connections_by_block[connection_index])

        # A draft SLD override is allowed to replace the persisted DC mapping
        # only when the user explicitly turns on override mode.  Convert the
        # legacy per-feeder counts into a fully explicit one-output-per-DCB
        # mapping so every later layer still consumes the same physical model.
        override_dc_blocks_per_feeder = override.dc_blocks_per_feeder if override else None
        if override_mode and override_dc_blocks_per_feeder is not None:
            parsed_override = [_safe_int(value) for value in override_dc_blocks_per_feeder]
            if (
                pcs_count is None
                or len(parsed_override) != pcs_count
                or not all(value is not None and value >= 0 for value in parsed_override)
            ):
                errors.append("dc_blocks_per_feeder draft override must contain one non-negative value per PCS feeder.")
            else:
                dc_blocks_per_feeder = [int(value) for value in parsed_override if value is not None]
                dc_block_connections = self._build_dedicated_dc_block_connections(dc_blocks_per_feeder)
                draft_warnings.append(
                    "draft DC allocation override replaced the authoritative DC Block output mapping for this SLD only."
                )
        else:
            dc_blocks_per_feeder = self._fill_list_from_override_if_missing(
                "dc_blocks_per_feeder",
                dc_blocks_per_feeder,
                override_mode,
                override_dc_blocks_per_feeder,
                errors,
            )
        dc_blocks_total_in_group = len(dc_block_connections) if dc_block_connections else sum(dc_blocks_per_feeder or [])

        dc_block_voltage_v = self._optional_float([project_settings.get("dc_block_voltage_v")])
        dc_block_voltage_v = self._fill_float_from_override_or_draft(
            "dc_block_voltage_v",
            dc_block_voltage_v,
            override_mode,
            override.dc_block_voltage_v if override else None,
            validation_mode,
            draft_warnings,
            errors,
            legacy_sld_override_preset()["dc_block_voltage_v"],
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
            mv_voltage_kv=mv_voltage_kv,
            draft_warnings=draft_warnings,
            errors=errors,
        )

        if authoritative_ac is not None and authoritative_ac.legacy_aliases_used:
            draft_warnings.append(
                "legacy AC aliases were normalized by the compatibility adapter: "
                + ", ".join(authoritative_ac.legacy_aliases_used)
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
                transformer_topology=transformer_topology,
                lv_winding_count=lv_winding_count,
                pcs_count=pcs_count,
                pcs_rating_kw_list=pcs_rating_kw_list,
                dc_block_energy_mwh=dc_block_energy_mwh,
                dc_blocks_total_in_group=dc_blocks_total_in_group,
                dc_blocks_per_feeder=dc_blocks_per_feeder,
                dc_block_connections=dc_block_connections,
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

    def _resolve_group_value(
        self,
        field_name: str,
        values: list[int] | None,
        group_index: int,
        errors: list[str],
        *,
        must_be_positive: bool = False,
    ) -> int | None:
        if not values:
            errors.append(f"{field_name} is required from the authoritative AC->SLD adapter.")
            return None
        group_idx = max(0, group_index - 1)
        if group_idx >= len(values):
            errors.append(f"{field_name} is missing for group_index={group_index}.")
            return None
        value = _safe_int(values[group_idx])
        if value is None:
            errors.append(f"{field_name} is invalid for group_index={group_index}.")
            return None
        if must_be_positive and value <= 0:
            errors.append(f"{field_name} must be > 0 for group_index={group_index}.")
            return None
        return int(value)

    def _resolve_group_rating_list(
        self,
        rating_matrix: list[list[float]] | None,
        group_index: int,
        pcs_count: int | None,
        errors: list[str],
    ) -> list[float]:
        if not pcs_count:
            return []
        if not rating_matrix:
            errors.append("pcs_rating_kw_list is required from the authoritative AC->SLD adapter.")
            return []
        group_idx = max(0, group_index - 1)
        if group_idx >= len(rating_matrix):
            errors.append(f"pcs_rating_kw_list is missing for group_index={group_index}.")
            return []
        candidate = rating_matrix[group_idx]
        parsed = [_safe_float(value) for value in candidate]
        if len(candidate) != pcs_count or not all(value is not None and value > 0 for value in parsed):
            errors.append(f"pcs_rating_kw_list is invalid for group_index={group_index}.")
            return []
        return [float(value) for value in parsed if value is not None]

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

    @staticmethod
    def _build_dedicated_dc_block_connections(
        dc_blocks_per_feeder: list[int],
    ) -> list[DcBlockConnection]:
        """Translate a legacy draft allocation into explicit physical branches."""
        connections: list[DcBlockConnection] = []
        dc_block_index = 1
        for feeder_index, count in enumerate(dc_blocks_per_feeder, start=1):
            for _ in range(count):
                connections.append(
                    DcBlockConnection(
                        dc_block_index=dc_block_index,
                        feeder_indices=[feeder_index],
                        output_circuit_count=1,
                        internal_dc_busbar_mode="common",
                    )
                )
                dc_block_index += 1
        return connections

    def _resolve_group_feeder_allocation(
        self,
        feeder_matrix: list[list[int]] | None,
        group_index: int,
        pcs_count: int | None,
        errors: list[str],
        *,
        override_available: bool,
    ) -> list[int] | None:
        if not pcs_count:
            return None
        if not feeder_matrix:
            if not override_available:
                errors.append(
                    "dc_blocks_per_feeder is required from the authoritative AC allocation or explicit draft override."
                )
            return None
        group_idx = max(0, group_index - 1)
        if group_idx >= len(feeder_matrix):
            errors.append(f"dc_blocks_per_feeder is missing for group_index={group_index}.")
            return None
        candidate = feeder_matrix[group_idx]
        parsed = [_safe_int(value) for value in candidate]
        if len(candidate) != pcs_count or not all(value is not None and value >= 0 for value in parsed):
            errors.append(f"dc_blocks_per_feeder is invalid for group_index={group_index}.")
            return None
        return [int(value) for value in parsed if value is not None]

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
        mv_voltage_kv: float | None,
        draft_warnings: list[str],
        errors: list[str],
    ) -> SldEquipmentRatings | None:
        try:
            if isinstance(project_settings.get("equipment_ratings"), dict):
                equipment = SldEquipmentRatings.model_validate(project_settings["equipment_ratings"])
                return self._sync_rmu_rated_voltage_to_mv(
                    equipment_ratings=equipment,
                    mv_voltage_kv=mv_voltage_kv,
                    draft_warnings=draft_warnings,
                    errors=errors,
                    source_name="project_settings.equipment_ratings.rmu.rated_kv",
                )
            if override_mode and override and override.equipment_ratings is not None:
                return self._sync_rmu_rated_voltage_to_mv(
                    equipment_ratings=override.equipment_ratings,
                    mv_voltage_kv=mv_voltage_kv,
                    draft_warnings=draft_warnings,
                    errors=errors,
                    source_name="override.equipment_ratings.rmu.rated_kv",
                )
            if validation_mode == "draft":
                draft_warnings.append("equipment_ratings were filled from legacy draft preset.")
                return self._sync_rmu_rated_voltage_to_mv(
                    equipment_ratings=SldEquipmentRatings.model_validate(legacy_sld_override_preset()["equipment_ratings"]),
                    mv_voltage_kv=mv_voltage_kv,
                    draft_warnings=draft_warnings,
                    errors=errors,
                    source_name="legacy draft preset rmu.rated_kv",
                )
            errors.append("equipment_ratings are required in strict mode from project settings or explicit override.")
            return None
        except ValidationError as exc:
            errors.append(f"equipment_ratings: {exc.errors()[0]['msg']}")
            return None

    def _sync_rmu_rated_voltage_to_mv(
        self,
        *,
        equipment_ratings: SldEquipmentRatings,
        mv_voltage_kv: float | None,
        draft_warnings: list[str],
        errors: list[str],
        source_name: str,
    ) -> SldEquipmentRatings | None:
        try:
            contract = resolve_mv_rmu_voltage_contract(mv_nominal_voltage_kv=mv_voltage_kv)
        except ValueError as exc:
            errors.append(str(exc))
            return None

        existing_rated_kv = _safe_float(equipment_ratings.rmu.rated_kv)
        if existing_rated_kv is not None and abs(float(existing_rated_kv) - float(contract.rmu_rated_voltage_kv)) > 1e-6:
            draft_warnings.append(
                f"{source_name}={float(existing_rated_kv):g} kV was ignored; "
                f"using authoritative POI / MV voltage {contract.rmu_rated_voltage_kv:g} kV for RMU rated voltage."
            )

        payload = equipment_ratings.model_dump(mode="python")
        rmu_payload = dict(payload.get("rmu") or {})
        rmu_payload["rated_kv"] = float(contract.rmu_rated_voltage_kv)
        payload["rmu"] = rmu_payload
        return SldEquipmentRatings.model_validate(payload)

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

    def _optional_float(self, candidates: list[Any]) -> float | None:
        for raw in candidates:
            value = _safe_float(raw)
            if value is not None:
                return value
        return None

    def _resolve_preferred_required_float(
        self,
        field_name: str,
        primary_value: Any,
        secondary_value: Any,
        primary_label: str,
        secondary_label: str,
        errors: list[str],
    ) -> float | None:
        value = self._resolve_preferred_optional_float(
            field_name=field_name,
            primary_value=primary_value,
            secondary_value=secondary_value,
            primary_label=primary_label,
            secondary_label=secondary_label,
            errors=errors,
        )
        if value is None or value <= 0:
            errors.append(f"{field_name} is required from authoritative sources and must be > 0.")
            return None
        return value

    def _resolve_preferred_optional_float(
        self,
        *,
        field_name: str,
        primary_value: Any,
        secondary_value: Any,
        primary_label: str,
        secondary_label: str,
        errors: list[str],
    ) -> float | None:
        primary = _safe_float(primary_value)
        secondary = _safe_float(secondary_value)
        if primary is not None and primary > 0:
            if secondary is not None and secondary > 0 and abs(float(primary) - float(secondary)) > 1e-6:
                errors.append(
                    f"{field_name} conflicts between {primary_label}={float(primary):g} and "
                    f"{secondary_label}={float(secondary):g}."
                )
            return float(primary)
        if secondary is not None and secondary > 0:
            return float(secondary)
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
