from __future__ import annotations

import datetime
import hashlib
import struct
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_engineering_v2_renderer import render_sld_engineering_v2_svg
from calb_diagrams.sld_engineering_v2_validation import validate_sld_engineering_v2_layout
from calb_diagrams.specs import build_sld_group_spec_from_topology
from calb_diagrams.sld_server_baseline_renderer import render_sld_pro_svg as render_sld_server_baseline_svg
from calb_diagrams.sld_pro_renderer import render_sld_svg
from calb_sizing_tool.plugins.base import ArtifactPayload, DiagramPlugin, PluginMetadata, json_bytes
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, LayoutRuleSnapshot, SldRenderInput, SldRenderOptions, TopologySnapshot
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_topology import SldTopology
from calb_sizing_tool.services.sld_authoritative_builder import build_sld_authoritative_result
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from calb_sizing_tool.services.sld_renderer_mode_service import normalize_sld_renderer_mode
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_json(payload: dict[str, Any]) -> str:
    return _hash_bytes(json_bytes(payload))


def _png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", payload[16:24])


def _resolve_artifact_mode(validation_mode: str, override_mode: bool) -> str:
    return "draft_override" if validation_mode == "draft" or override_mode else "official"


def _artifact_file_name(base_name: str, extension: str, artifact_mode: str) -> str:
    suffix = ".draft" if artifact_mode == "draft_override" else ""
    return f"{base_name}{suffix}.{extension}"


def _svg_bytes_to_png(svg_bytes: bytes) -> bytes:
    import cairosvg

    return cairosvg.svg2png(bytestring=svg_bytes, background_color="white")


def _renderer_lineage(renderer_mode: str) -> str:
    if renderer_mode == "legacy_server":
        return "legacy_compatibility_patched"
    if renderer_mode == "topology_v1":
        return "refactored_topology_v1"
    if renderer_mode == "engineering_v2":
        return "port_bay_engineering_v2_preview"
    return "unknown"


class SldEngineeringPlugin:
    metadata = PluginMetadata(
        plugin_id="sld_engineering_v1",
        plugin_name="SLD Engineering Renderer",
        plugin_version="1.3.0",
        supported_artifact_kind=[
            "sld_svg",
            "sld_png",
            "sld_topology_json",
            "sld_render_spec_json",
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
        validation_mode = "draft" if bool(options.override_mode) else "strict"
        authoritative = build_sld_authoritative_result(
            run_bundle=run_bundle,
            ac_snapshot=ac_snapshot,
            options=options,
            validation_mode=validation_mode,
        )
        return SldRenderInput(
            run_id=run_bundle.run_id,
            run_bundle=run_bundle,
            ac_snapshot=ac_snapshot,
            topology_snapshot=topology_snapshot or TopologySnapshot(payload=authoritative.topology.model_dump(mode="python")),
            layout_rules=layout_rules,
            options=options,
            canonical_input=authoritative.canonical_input,
        )

    def validate_input(self, render_input: SldRenderInput) -> list[str]:
        errors: list[str] = []
        if not render_input.ac_snapshot or not render_input.ac_snapshot.output:
            errors.append("AC snapshot is required for SLD rendering.")
        if not render_input.run_bundle:
            errors.append("Run bundle is required.")
        return errors

    def render(self, render_input: SldRenderInput) -> dict[str, dict | bytes]:
        if render_input.topology_snapshot and render_input.topology_snapshot.payload:
            topology = SldTopology.model_validate(render_input.topology_snapshot.payload)
        else:
            topology = build_sld_topology(render_input.canonical_input)
        group_index = topology.summary.group_index
        sld_spec = build_sld_group_spec_from_topology(topology)
        renderer_mode = normalize_sld_renderer_mode(render_input.options.renderer_mode)
        engineering_v2_graph_payload: dict[str, Any] | None = None
        engineering_v2_layout_payload: dict[str, Any] | None = None
        engineering_v2_layout_issues_payload: list[dict[str, Any]] | None = None
        engineering_v2_graph_hash: str | None = None
        engineering_v2_layout_hash: str | None = None

        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = Path(tmpdir) / "sld_engineering.svg"
            layout_profile = "compact" if topology.summary.compact_mode else "engineering_readable"
            if renderer_mode == "legacy_server":
                render_sld_server_baseline_svg(sld_spec, svg_path)
            elif renderer_mode == "topology_v1":
                render_sld_svg(topology, layout_profile, topology.summary.theme, svg_path)
            elif renderer_mode == "engineering_v2":
                engineering_v2_graph = build_sld_engineering_v2_graph(topology)
                engineering_v2_layout = build_sld_engineering_v2_layout_plan(engineering_v2_graph)
                engineering_v2_layout_issues = validate_sld_engineering_v2_layout(engineering_v2_layout)
                engineering_v2_layout_issues_payload = [asdict(issue) for issue in engineering_v2_layout_issues]
                engineering_v2_layout_errors = [
                    issue for issue in engineering_v2_layout_issues if issue.severity == "error"
                ]
                engineering_v2_layout_warnings = [
                    issue for issue in engineering_v2_layout_issues if issue.severity == "warning"
                ]
                if engineering_v2_layout_errors:
                    summary = "; ".join(f"{issue.issue_id}: {issue.message}" for issue in engineering_v2_layout_errors)
                    raise ValueError(f"engineering_v2 layout acceptance failed: {summary}")
                engineering_v2_graph_payload = engineering_v2_graph.model_dump(mode="python")
                engineering_v2_layout_payload = asdict(engineering_v2_layout)
                engineering_v2_graph_hash = _hash_json(engineering_v2_graph_payload)
                engineering_v2_layout_hash = _hash_json(engineering_v2_layout_payload)
                render_sld_engineering_v2_svg(engineering_v2_layout, svg_path)
            else:  # pragma: no cover - normalize_sld_renderer_mode guards this branch.
                raise ValueError(f"Unsupported SLD renderer mode: {renderer_mode}")
            svg_bytes = svg_path.read_bytes() if svg_path.exists() else b""

        if not svg_bytes:
            raise RuntimeError("SLD SVG render failed.")

        png_bytes = _svg_bytes_to_png(svg_bytes)
        canonical_input_payload = render_input.canonical_input.model_dump(mode="python")
        topology_payload = topology.model_dump(mode="python")
        render_spec_payload = asdict(sld_spec)
        artifact_mode = _resolve_artifact_mode(
            render_input.canonical_input.validation_mode,
            bool(render_input.canonical_input.override_mode),
        )
        input_hash = _hash_json(canonical_input_payload)
        topology_hash = _hash_json(topology_payload)
        render_spec_hash = _hash_json(render_spec_payload)
        svg_hash = _hash_bytes(svg_bytes)
        png_hash = _hash_bytes(png_bytes)
        png_dimensions = _png_dimensions(png_bytes)

        metadata = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "run_id": render_input.run_id,
            "group_index": group_index,
            "scenario_id": render_input.canonical_input.scenario_id,
            "validation_mode": render_input.canonical_input.validation_mode,
            "artifact_mode": artifact_mode,
            "renderer_version": self.metadata.plugin_version,
            "renderer_mode": renderer_mode,
            "renderer_lineage": _renderer_lineage(renderer_mode),
            "server_baseline_commit": "8568af4" if renderer_mode == "legacy_server" else None,
            "input_hash": input_hash,
            "topology_hash": topology_hash,
            "render_spec_hash": render_spec_hash,
            "svg_hash": svg_hash,
            "png_hash": png_hash,
            "topology_node_count": len(topology.nodes),
            "topology_edge_count": len(topology.edges),
        }
        if renderer_mode == "engineering_v2":
            metadata.update(
                {
                    "engineering_v2_graph_hash": engineering_v2_graph_hash,
                    "engineering_v2_layout_hash": engineering_v2_layout_hash,
                    "engineering_v2_node_count": len(engineering_v2_graph_payload.get("nodes", []))
                    if engineering_v2_graph_payload
                    else 0,
                    "engineering_v2_edge_count": len(engineering_v2_graph_payload.get("edges", []))
                    if engineering_v2_graph_payload
                    else 0,
                    "engineering_v2_connector_count": len(engineering_v2_layout_payload.get("connectors", []))
                    if engineering_v2_layout_payload
                    else 0,
                    "engineering_v2_layout_issue_count": len(engineering_v2_layout_errors),
                    "engineering_v2_layout_warning_count": len(engineering_v2_layout_warnings),
                    "engineering_v2_png_width": png_dimensions[0] if png_dimensions else None,
                    "engineering_v2_png_height": png_dimensions[1] if png_dimensions else None,
                    "engineering_v2_template": "professional_electrical_reference_v1",
                }
            )

        return {
            "canonical_input": canonical_input_payload,
            "topology": topology_payload,
            "spec": render_spec_payload,
            "engineering_v2_graph": engineering_v2_graph_payload,
            "engineering_v2_layout": engineering_v2_layout_payload,
            "engineering_v2_layout_issues": engineering_v2_layout_issues_payload,
            "svg_bytes": svg_bytes,
            "png_bytes": png_bytes,
            "metadata": metadata,
        }

    def emit_artifact(self, render_output: dict[str, Any]) -> list[ArtifactPayload]:
        metadata = dict(render_output.get("metadata") or {})
        artifact_mode = str(metadata.get("artifact_mode") or "official")
        common_metadata = {
            "run_id": metadata.get("run_id"),
            "scenario_id": metadata.get("scenario_id"),
            "group_index": metadata.get("group_index"),
            "validation_mode": metadata.get("validation_mode"),
            "artifact_mode": artifact_mode,
            "renderer_version": metadata.get("renderer_version"),
            "renderer_mode": metadata.get("renderer_mode"),
            "renderer_lineage": metadata.get("renderer_lineage"),
            "server_baseline_commit": metadata.get("server_baseline_commit"),
            "input_hash": metadata.get("input_hash"),
            "topology_hash": metadata.get("topology_hash"),
            "render_spec_hash": metadata.get("render_spec_hash"),
        }
        if metadata.get("renderer_mode") == "engineering_v2":
            common_metadata.update(
                {
                    "engineering_v2_graph_hash": metadata.get("engineering_v2_graph_hash"),
                    "engineering_v2_layout_hash": metadata.get("engineering_v2_layout_hash"),
                    "engineering_v2_png_width": metadata.get("engineering_v2_png_width"),
                    "engineering_v2_png_height": metadata.get("engineering_v2_png_height"),
                    "engineering_v2_template": metadata.get("engineering_v2_template"),
                }
            )
        artifacts: list[ArtifactPayload] = []
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_render_spec_json",
                file_name=_artifact_file_name("sld_render_spec", "json", artifact_mode),
                media_type="application/json",
                content=json_bytes(render_output["spec"]),
                metadata={
                    **common_metadata,
                    "content_hash": _hash_json(render_output["spec"]),
                },
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_topology_json",
                file_name=_artifact_file_name("sld_topology", "json", artifact_mode),
                media_type="application/json",
                content=json_bytes(render_output["topology"]),
                metadata={
                    **common_metadata,
                    "content_hash": _hash_json(render_output["topology"]),
                },
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_svg",
                file_name=_artifact_file_name("sld_render", "svg", artifact_mode),
                media_type="image/svg+xml",
                content=render_output["svg_bytes"],
                metadata={
                    **common_metadata,
                    "content_hash": metadata.get("svg_hash"),
                },
            )
        )
        artifacts.append(
            ArtifactPayload(
                artifact_kind="sld_png",
                file_name=_artifact_file_name("sld_render", "png", artifact_mode),
                media_type="image/png",
                content=render_output["png_bytes"],
                metadata={
                    **common_metadata,
                    "content_hash": metadata.get("png_hash"),
                },
            )
        )
        return artifacts

    def metadata_payload(self, render_input: SldRenderInput, render_output: dict[str, Any]) -> dict[str, Any]:
        payload = dict(render_output.get("metadata") or {})
        payload.update(self.metadata.as_dict())
        payload["run_id"] = render_input.run_id
        return payload
