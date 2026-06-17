from __future__ import annotations

from dataclasses import asdict
from typing import Any

from calb_sizing_tool.plugins.base import ArtifactPayload, PluginMetadata, json_bytes
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderInput, LayoutRenderOptions, LayoutArtifactBundle
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


class PromptLayoutPlugin:
    metadata = PluginMetadata(
        plugin_id="layout_prompt_v1",
        plugin_name="Layout Prompt Generator",
        plugin_version="1.0.0",
        supported_artifact_kind=[
            "layout_prompt_payload",
            "layout_prompt_text",
        ],
    )

    def build_input_from_run(
        self,
        *,
        run_bundle: DcRunBundle,
        ac_snapshot: AcSnapshot | None,
        options: LayoutRenderOptions | None,
        topology_snapshot=None,
        layout_rules=None,
    ) -> LayoutRenderInput:
        return LayoutRenderInput(
            run_id=run_bundle.run_id,
            run_bundle=run_bundle,
            ac_snapshot=ac_snapshot or AcSnapshot(),
            topology_snapshot=topology_snapshot,
            layout_rules=layout_rules,
            options=options or LayoutRenderOptions(),
        )

    def validate_input(self, render_input: LayoutRenderInput) -> list[str]:
        errors: list[str] = []
        if not render_input.run_bundle:
            errors.append("Run bundle is required.")
        return errors

    def _derive_prompt_payload(self, render_input: LayoutRenderInput) -> dict[str, Any]:
        snapshot = render_input.run_bundle.snapshot
        stage2 = snapshot.stage2
        dc_block_total = int(stage2.container_count + stage2.cabinet_count)
        block_energy = None
        if stage2.block_config_items:
            block_energy = stage2.block_config_items[0].unit_capacity_mwh

        ac_output = render_input.ac_snapshot.output if render_input.ac_snapshot else {}
        if not isinstance(ac_output, dict):
            ac_output = {}
        derived_ac_block_count = max(1, int(round(dc_block_total / 4))) if dc_block_total > 0 else 1
        try:
            ac_block_count = int(
                ac_output.get("num_blocks")
                or ac_output.get("ac_blocks_total")
                or derived_ac_block_count
            )
        except Exception:
            ac_block_count = derived_ac_block_count
        try:
            pcs_per_block = int(ac_output.get("pcs_per_block") or 4)
        except Exception:
            pcs_per_block = 4

        case_input = {}
        if render_input.run_bundle.input_snapshot and isinstance(render_input.run_bundle.input_snapshot.payload, dict):
            case_input = render_input.run_bundle.input_snapshot.payload.get("case_input") or {}

        payload = {
            "schema_version": "layout_prompt_v1",
            "run_id": render_input.run_id,
            "project": {
                "project_name": render_input.run_bundle.project_name,
                "case_name": render_input.run_bundle.case_name,
                "scenario_mode": render_input.run_bundle.scenario_mode,
            },
            "run_metadata": {
                "dc_block_total": dc_block_total,
                "dc_block_energy_mwh": block_energy,
                "poi_power_req_mw": snapshot.stage1.poi_power_req_mw,
                "poi_energy_req_mwh": snapshot.stage1.poi_energy_req_mwh,
                "poi_nominal_voltage_kv": case_input.get("poi_nominal_voltage_kv"),
                "poi_frequency_hz": case_input.get("poi_frequency_hz"),
            },
            "ac_assumptions": {
                "ac_block_count": ac_block_count,
                "pcs_per_block": pcs_per_block,
                "transformer_mva": ac_output.get("transformer_mva"),
                "assumption_note": (
                    "Loaded from persisted AC snapshot."
                    if ac_output
                    else "Derived from DC blocks; update if AC snapshot exists."
                ),
            },
            "layout_rules": {
                "arrangement": render_input.options.arrangement,
                "clearances_m": {
                    "dc_to_dc": render_input.options.dc_to_dc_clearance_m,
                    "dc_to_ac": render_input.options.dc_to_ac_clearance_m,
                    "perimeter": render_input.options.perimeter_clearance_m,
                },
                "door_vent_mirror_rules": {
                    "mirror_interior": render_input.options.dc_block_mirrored,
                    "keep_doors_clear": True,
                },
                "no_go_constraints": [
                    "Do not change DC block count.",
                    "Do not resize DC block dimensions.",
                ],
            },
            "branding_rules": {
                "brand": "CALB",
                "preferred_palette": ["#1f4d7a", "#ffffff", "#2e2e2e"],
            },
            "labels": {
                "block_title": render_input.options.block_title or "Block {index}: DC Blocks={dc_blocks}",
                "bess_range_text": render_input.options.bess_range_text or "BESS {start}~{end}",
                "skid_text": render_input.options.skid_text or "PCS&MVT SKID (AC Block)",
                "skid_subtext": render_input.options.skid_subtext or "TBD",
            },
            "forbidden_modifications": [
                "Do not alter run_id or project identifiers.",
                "Do not override deterministic engineering layout.",
            ],
            "expected_return_format": {
                "image": "png or svg",
                "metadata_json": {
                    "layout_notes": "short rationale",
                    "assumptions": ["list of assumptions"],
                },
            },
        }
        return payload

    def render(self, render_input: LayoutRenderInput) -> dict[str, Any]:
        payload = self._derive_prompt_payload(render_input)
        prompt_text = _prompt_text(payload)
        return {"payload": payload, "prompt_text": prompt_text}

    def emit_artifact(self, render_output: dict[str, Any]) -> list[ArtifactPayload]:
        return [
            ArtifactPayload(
                artifact_kind="layout_prompt_payload",
                file_name="layout_prompt_payload.json",
                media_type="application/json",
                content=json_bytes(render_output["payload"]),
            ),
            ArtifactPayload(
                artifact_kind="layout_prompt_text",
                file_name="layout_prompt.txt",
                media_type="text/plain",
                content=render_output["prompt_text"].encode("utf-8"),
            ),
        ]

    def metadata_payload(self, render_input: LayoutRenderInput, render_output: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "run_id": render_input.run_id,
            "plugin_id": self.metadata.plugin_id,
            "plugin_version": self.metadata.plugin_version,
        }
        return payload


def _prompt_text(payload: dict[str, Any]) -> str:
    project = payload.get("project", {})
    rules = payload.get("layout_rules", {})
    ac_assumptions = payload.get("ac_assumptions", {})
    return "\n".join(
        [
            "You are generating a conceptual layout preview for a CALB BESS project.",
            f"Run ID: {payload.get('run_id')}",
            f"Project: {project.get('project_name')}",
            f"Case: {project.get('case_name')} ({project.get('scenario_mode')})",
            "",
            "Key counts:",
            f"- DC blocks total: {payload.get('run_metadata', {}).get('dc_block_total')}",
            f"- AC block count (assumed): {ac_assumptions.get('ac_block_count')}",
            "",
            "Layout rules:",
            f"- Arrangement: {rules.get('arrangement')}",
            f"- Clearances (m): {rules.get('clearances_m')}",
            f"- Door/vent mirror rules: {rules.get('door_vent_mirror_rules')}",
            "",
            "Branding rules:",
            f"- Brand: {payload.get('branding_rules', {}).get('brand')}",
            "",
            "Forbidden modifications:",
            "- Do not change DC block count or dimensions.",
            "- Do not override deterministic engineering layout.",
            "",
            "Return format:",
            "- Provide PNG or SVG image.",
            "- Provide metadata JSON with assumptions and layout notes.",
        ]
    )
