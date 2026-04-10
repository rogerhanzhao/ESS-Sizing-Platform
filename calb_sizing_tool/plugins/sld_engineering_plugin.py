from __future__ import annotations

import datetime
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from calb_diagrams.specs import build_sld_group_spec
from calb_diagrams.sld_pro_renderer import render_sld_pro_svg
from calb_sizing_tool.adapters.session_state_adapter import build_dc_result_summary, build_stage13_output
from calb_sizing_tool.plugins.base import ArtifactPayload, DiagramPlugin, PluginMetadata, json_bytes
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, LayoutRuleSnapshot, SldRenderInput, SldRenderOptions, TopologySnapshot
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


def _svg_bytes_to_png(svg_bytes: bytes) -> bytes:
    import cairosvg

    return cairosvg.svg2png(bytestring=svg_bytes, background_color="white")


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


class SldEngineeringPlugin:
    metadata = PluginMetadata(
        plugin_id="sld_engineering_v1",
        plugin_name="SLD Engineering Renderer",
        plugin_version="1.0.0",
        supported_artifact_kind=[
            "sld_svg",
            "sld_png",
            "sld_spec_json",
            "sld_metadata_json",
        ],
    )

    def build_input_from_run(
        self,
        *,
        run_bundle: DcRunBundle,
        ac_snapshot: AcSnapshot,
        topology_snapshot: TopologySnapshot | None,
        layout_rules: LayoutRuleSnapshot | None,
        options: SldRenderOptions,
    ) -> SldRenderInput:
        return SldRenderInput(
            run_id=run_bundle.run_id,
            run_bundle=run_bundle,
            ac_snapshot=ac_snapshot,
            topology_snapshot=topology_snapshot,
            layout_rules=layout_rules,
            options=options,
        )

    def validate_input(self, render_input: SldRenderInput) -> list[str]:
        errors: list[str] = []
        if not render_input.ac_snapshot or not render_input.ac_snapshot.output:
            errors.append("AC snapshot is required for SLD rendering.")
        if not render_input.run_bundle:
            errors.append("Run bundle is required.")
        return errors

    def _build_stage13_output(self, run_bundle: DcRunBundle) -> dict[str, Any]:
        snapshot = run_bundle.snapshot
        dc_block_total_qty = int(snapshot.stage2.container_count + snapshot.stage2.cabinet_count)
        scenario_id = run_bundle.scenario_mode or snapshot.stage2.mode or "container_only"
        case_input = {}
        if run_bundle.input_snapshot and isinstance(run_bundle.input_snapshot.payload, dict):
            case_input = run_bundle.input_snapshot.payload.get("case_input") or {}
        poi_nominal_voltage_kv = case_input.get("poi_nominal_voltage_kv", 33.0)
        poi_frequency_hz = case_input.get("poi_frequency_hz")
        return build_stage13_output(
            snapshot,
            dc_block_total_qty=dc_block_total_qty,
            selected_scenario=str(scenario_id),
            poi_nominal_voltage_kv=float(poi_nominal_voltage_kv),
            poi_frequency_hz=poi_frequency_hz,
        )

    def _build_sld_inputs(self, options: SldRenderOptions) -> dict[str, Any]:
        inputs: dict[str, Any] = {
            "draw_summary": bool(options.draw_summary),
            "theme": options.theme,
        }
        if options.mv_kv is not None:
            inputs["mv_nominal_kv_ac"] = options.mv_kv
        if options.lv_v is not None:
            inputs["pcs_lv_voltage_v_ll"] = options.lv_v
        if options.transformer_mva is not None:
            inputs["transformer_rating_mva"] = options.transformer_mva
        if options.pcs_rating_each_kw is not None:
            inputs["pcs_rating_each_kw"] = options.pcs_rating_each_kw
        if options.dc_block_energy_mwh is not None:
            inputs["dc_block_energy_mwh"] = options.dc_block_energy_mwh
        if options.svg_width is not None:
            inputs["svg_width"] = options.svg_width
        if options.svg_height is not None:
            inputs["svg_height"] = options.svg_height
        if options.pcs_gap is not None:
            inputs["pcs_gap"] = options.pcs_gap
        if options.busbar_gap is not None:
            inputs["busbar_gap"] = options.busbar_gap
        if options.font_scale is not None:
            inputs["font_scale"] = options.font_scale
        if options.dc_blocks_per_feeder:
            inputs["dc_blocks_per_feeder"] = [int(v) for v in options.dc_blocks_per_feeder]
        return inputs

    def render(self, render_input: SldRenderInput) -> dict[str, Any]:
        run_bundle = render_input.run_bundle
        ac_output = render_input.ac_snapshot.output
        stage13_output = self._build_stage13_output(run_bundle)
        dc_summary = build_dc_result_summary(run_bundle.snapshot)

        sld_inputs = self._build_sld_inputs(render_input.options)
        group_index = max(1, _safe_int(render_input.options.group_index, 1))
        sld_spec = build_sld_group_spec(stage13_output, ac_output, dc_summary, sld_inputs, group_index)

        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = Path(tmpdir) / "sld_engineering.svg"
            render_sld_pro_svg(sld_spec, svg_path)
            svg_bytes = svg_path.read_bytes() if svg_path.exists() else b""

        if not svg_bytes:
            raise RuntimeError("SLD SVG render failed.")

        png_bytes = _svg_bytes_to_png(svg_bytes)

        metadata = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "group_index": group_index,
            "scenario_id": run_bundle.scenario_mode,
        }

        return {
            "spec": asdict(sld_spec),
            "svg_bytes": svg_bytes,
            "png_bytes": png_bytes,
            "metadata": metadata,
        }

    def emit_artifact(self, render_output: dict[str, Any]) -> list[ArtifactPayload]:
        artifacts: list[ArtifactPayload] = []
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_spec_json",
                file_name="sld_spec.json",
                media_type="application/json",
                content=json_bytes(render_output["spec"]),
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_svg",
                file_name="sld_render.svg",
                media_type="image/svg+xml",
                content=render_output["svg_bytes"],
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_png",
                file_name="sld_render.png",
                media_type="image/png",
                content=render_output["png_bytes"],
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_metadata_json",
                file_name="sld_metadata.json",
                media_type="application/json",
                content=json_bytes(render_output["metadata"]),
            )
        )
        return artifacts

    def metadata_payload(self, render_input: SldRenderInput, render_output: dict[str, Any]) -> dict[str, Any]:
        payload = dict(render_output.get("metadata") or {})
        payload.update(self.metadata.as_dict())
        payload["run_id"] = render_input.run_id
        return payload
