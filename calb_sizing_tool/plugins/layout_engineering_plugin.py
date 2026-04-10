from __future__ import annotations

import datetime
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from calb_diagrams.layout_block_renderer import render_layout_block_svg
from calb_diagrams.specs import build_layout_block_spec
from calb_sizing_tool.plugins.base import ArtifactPayload, PluginMetadata, json_bytes
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, LayoutRuleSnapshot, TopologySnapshot
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderInput, LayoutRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle


def _svg_bytes_to_png(svg_bytes: bytes) -> bytes:
    import cairosvg

    return cairosvg.svg2png(bytestring=svg_bytes, background_color="white")


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


class LayoutEngineeringPlugin:
    metadata = PluginMetadata(
        plugin_id="layout_engineering_v1",
        plugin_name="Layout Engineering Renderer",
        plugin_version="1.0.0",
        supported_artifact_kind=[
            "layout_svg",
            "layout_png",
            "layout_spec_json",
            "layout_metadata_json",
        ],
    )

    def build_input_from_run(
        self,
        *,
        run_bundle: DcRunBundle,
        ac_snapshot: AcSnapshot,
        topology_snapshot: TopologySnapshot | None,
        layout_rules: LayoutRuleSnapshot | None,
        options: LayoutRenderOptions,
    ) -> LayoutRenderInput:
        return LayoutRenderInput(
            run_id=run_bundle.run_id,
            run_bundle=run_bundle,
            ac_snapshot=ac_snapshot,
            topology_snapshot=topology_snapshot,
            layout_rules=layout_rules,
            options=options,
        )

    def validate_input(self, render_input: LayoutRenderInput) -> list[str]:
        errors: list[str] = []
        if not render_input.ac_snapshot or not render_input.ac_snapshot.output:
            errors.append("AC snapshot is required for layout rendering.")
        if not render_input.run_bundle:
            errors.append("Run bundle is required.")
        return errors

    def _resolve_block_counts(self, ac_output: dict) -> dict[int, int]:
        counts: dict[int, int] = {}
        allocation_plan = ac_output.get("dc_allocation_plan")
        if isinstance(allocation_plan, list):
            for plan in allocation_plan:
                idx = plan.get("ac_block_index")
                count = plan.get("dc_blocks_total")
                if isinstance(idx, int) and isinstance(count, int):
                    counts[idx] = count
        return counts

    def render(self, render_input: LayoutRenderInput) -> dict[str, Any]:
        ac_output = render_input.ac_snapshot.output
        options = render_input.options

        block_index = max(1, _safe_int(options.block_index, 1))
        block_counts = self._resolve_block_counts(ac_output)
        dc_blocks_total = block_counts.get(block_index, 0)
        if dc_blocks_total == 0 and block_counts:
            dc_blocks_total = next(iter(block_counts.values()))

        arrangement = options.arrangement
        if arrangement == "Auto":
            if dc_blocks_total <= 1:
                arrangement = "1x4"
            elif dc_blocks_total <= 2:
                arrangement = "1x4"
            elif dc_blocks_total <= 4:
                arrangement = "2x2"
            elif dc_blocks_total <= 8:
                arrangement = "4x2"
            else:
                arrangement = "4x4"

        pcs_count = _safe_int(ac_output.get("pcs_per_block"), 4)
        if not pcs_count:
            pcs_counts = ac_output.get("pcs_count_by_block")
            if isinstance(pcs_counts, list) and pcs_counts:
                pcs_count = _safe_int(pcs_counts[block_index - 1], 4)
            else:
                pcs_count = 4

        labels = {
            "block_title": options.block_title or "Block {index}: DC Blocks={dc_blocks}",
            "bess_range_text": options.bess_range_text or "BESS {start}~{end}",
            "skid_text": options.skid_text or "PCS&MVT SKID (AC Block)",
            "skid_subtext": options.skid_subtext or "TBD",
        }

        spec = build_layout_block_spec(
            ac_output=ac_output,
            block_indices_to_render=[block_index],
            labels=labels,
            pcs_count=pcs_count,
            dc_blocks_per_block=dc_blocks_total,
            dc_block_counts_by_block=block_counts,
            arrangement=arrangement,
            show_skid=options.show_skid,
            dc_to_dc_clearance_m=options.dc_to_dc_clearance_m,
            dc_to_ac_clearance_m=options.dc_to_ac_clearance_m,
            perimeter_clearance_m=options.perimeter_clearance_m,
            dc_block_mirrored=options.dc_block_mirrored,
            use_template=False,
            scale=options.scale,
            left_margin=options.left_margin,
            top_margin=options.top_margin,
            theme=options.theme,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = Path(tmpdir) / "layout_engineering.svg"
            svg_result, warning = render_layout_block_svg(spec, svg_path)
            if svg_result is None:
                raise RuntimeError(warning or "Layout renderer unavailable.")
            svg_bytes = svg_path.read_bytes() if svg_path.exists() else b""

        if not svg_bytes:
            raise RuntimeError("Layout SVG render failed.")

        png_bytes = _svg_bytes_to_png(svg_bytes)

        metadata = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "block_index": block_index,
            "dc_blocks_total": dc_blocks_total,
            "arrangement": arrangement,
        }

        return {
            "spec": asdict(spec),
            "svg_bytes": svg_bytes,
            "png_bytes": png_bytes,
            "metadata": metadata,
        }

    def emit_artifact(self, render_output: dict[str, Any]) -> list[ArtifactPayload]:
        artifacts: list[ArtifactPayload] = []
        artifacts.append(
            ArtifactPayload(
                artifact_kind="layout_spec_json",
                file_name="layout_spec.json",
                media_type="application/json",
                content=json_bytes(render_output["spec"]),
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="layout_svg",
                file_name="layout_render.svg",
                media_type="image/svg+xml",
                content=render_output["svg_bytes"],
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="layout_png",
                file_name="layout_render.png",
                media_type="image/png",
                content=render_output["png_bytes"],
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="layout_metadata_json",
                file_name="layout_metadata.json",
                media_type="application/json",
                content=json_bytes(render_output["metadata"]),
            )
        )
        return artifacts

    def metadata_payload(self, render_input: LayoutRenderInput, render_output: dict[str, Any]) -> dict[str, Any]:
        payload = dict(render_output.get("metadata") or {})
        payload.update(self.metadata.as_dict())
        payload["run_id"] = render_input.run_id
        return payload
