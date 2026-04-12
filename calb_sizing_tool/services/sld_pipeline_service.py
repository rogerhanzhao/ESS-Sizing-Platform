from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.schemas.diagram_inputs import (
    AcSnapshot,
    DiagramArtifactBundle,
    LayoutRuleSnapshot,
    SldRenderInput,
    SldRenderOptions,
    TopologySnapshot,
)
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_topology import SldTopology
from calb_sizing_tool.services.artifact_service import persist_artifacts
from calb_sizing_tool.services.sld_authoritative_builder import build_sld_authoritative_result


@dataclass
class PreparedSldPipeline:
    plugin_id: str
    plugin_version: str
    validation_mode: str
    render_input: SldRenderInput
    topology: SldTopology
    plugin: Any


@dataclass
class ExecutedSldPipeline:
    prepared: PreparedSldPipeline
    render_output: dict[str, Any]
    artifact_bundle: DiagramArtifactBundle


def resolve_sld_validation_mode(options: SldRenderOptions) -> str:
    return "draft" if bool(options.override_mode) else "strict"


def prepare_sld_pipeline_from_run_bundle(
    run_bundle: DcRunBundle,
    *,
    ac_snapshot: AcSnapshot,
    options: SldRenderOptions,
    project_settings: dict[str, Any] | None = None,
    topology_snapshot: TopologySnapshot | None = None,
    layout_rules: LayoutRuleSnapshot | None = None,
    plugin_id: str = "sld_engineering_v1",
) -> PreparedSldPipeline:
    """Prepare the authoritative SLD runtime chain.

    Formal flow:
    AcSnapshot -> SldCanonicalInput -> SldTopology -> renderer compatibility spec.
    Legacy snapshot/spec builders are not part of this path.
    """
    registry = get_plugin_registry()
    plugin = registry.get(plugin_id)
    if plugin is None:
        raise ValueError(f"SLD plugin not found: {plugin_id}")

    validation_mode = resolve_sld_validation_mode(options)
    authoritative = build_sld_authoritative_result(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        validation_mode=validation_mode,
    )
    canonical_input = authoritative.canonical_input
    topology = (
        SldTopology.model_validate(topology_snapshot.payload)
        if topology_snapshot and topology_snapshot.payload
        else authoritative.topology
    )
    render_input = SldRenderInput(
        run_id=run_bundle.run_id,
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        topology_snapshot=TopologySnapshot(payload=topology.model_dump(mode="python")),
        layout_rules=layout_rules,
        options=options,
        canonical_input=canonical_input,
    )
    errors = plugin.validate_input(render_input)
    if errors:
        raise ValueError("; ".join(errors))

    return PreparedSldPipeline(
        plugin_id=plugin.metadata.plugin_id,
        plugin_version=plugin.metadata.plugin_version,
        validation_mode=validation_mode,
        render_input=render_input,
        topology=topology,
        plugin=plugin,
    )


def render_prepared_sld_pipeline(prepared: PreparedSldPipeline) -> dict[str, Any]:
    return prepared.plugin.render(prepared.render_input)


def run_sld_pipeline_from_run_bundle(
    run_bundle: DcRunBundle,
    *,
    ac_snapshot: AcSnapshot,
    options: SldRenderOptions,
    project_settings: dict[str, Any] | None = None,
    topology_snapshot: TopologySnapshot | None = None,
    layout_rules: LayoutRuleSnapshot | None = None,
    plugin_id: str = "sld_engineering_v1",
    actor: str | None = None,
    db_url: str | None = None,
) -> ExecutedSldPipeline:
    if not str(run_bundle.run_id or "").strip():
        raise ValueError("SLD artifact registration requires a valid run_id.")

    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        topology_snapshot=topology_snapshot,
        layout_rules=layout_rules,
        plugin_id=plugin_id,
    )
    render_output = render_prepared_sld_pipeline(prepared)
    artifacts = prepared.plugin.emit_artifact(render_output)
    metadata = prepared.plugin.metadata_payload(prepared.render_input, render_output)

    persist_artifacts(
        run_id=run_bundle.run_id,
        artifacts=artifacts,
        plugin_id=prepared.plugin_id,
        plugin_version=prepared.plugin_version,
        actor=actor,
        db_url=db_url,
        source_ref="sld_pipeline_service",
    )

    artifact_bundle = DiagramArtifactBundle(
        plugin_id=prepared.plugin_id,
        plugin_version=prepared.plugin_version,
        run_id=run_bundle.run_id,
        metadata=metadata,
        artifacts=[artifact.__dict__ for artifact in artifacts],
    )
    return ExecutedSldPipeline(
        prepared=prepared,
        render_output=render_output,
        artifact_bundle=artifact_bundle,
    )


def _round_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _round_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_value(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def normalize_sld_topology(topology: SldTopology | dict[str, Any]) -> dict[str, Any]:
    payload = topology if isinstance(topology, dict) else topology.model_dump(mode="python")
    return _round_value(payload)


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _normalize_attr_value(value: str) -> Any:
    text = str(value).strip()
    if not text:
        return ""
    try:
        return round(float(text), 6)
    except Exception:
        return " ".join(text.split())


def normalize_sld_svg(svg_bytes: bytes | str) -> dict[str, Any]:
    raw_text = svg_bytes.decode("utf-8") if isinstance(svg_bytes, bytes) else str(svg_bytes)
    root = ET.fromstring(raw_text)
    element_counts: dict[str, int] = {}
    class_counts: dict[str, int] = {}
    text_nodes: list[str] = []
    geometry: list[dict[str, Any]] = []

    for element in root.iter():
        tag = _strip_ns(element.tag)
        element_counts[tag] = element_counts.get(tag, 0) + 1
        class_name = element.attrib.get("class")
        if class_name:
            class_counts[class_name] = class_counts.get(class_name, 0) + 1

        text = " ".join((element.text or "").split())
        if text:
            text_nodes.append(text)

        if tag in {"rect", "line", "circle", "polygon", "polyline", "text"}:
            attrs: dict[str, Any] = {"tag": tag}
            for key in ("class", "x", "y", "x1", "y1", "x2", "y2", "width", "height", "cx", "cy", "r", "points", "text-anchor"):
                if key in element.attrib:
                    attrs[key] = _normalize_attr_value(element.attrib[key])
            if text:
                attrs["text"] = text
            geometry.append(attrs)

    return {
        "svg": {
            "width": _normalize_attr_value(root.attrib.get("width", "")),
            "height": _normalize_attr_value(root.attrib.get("height", "")),
            "viewBox": _normalize_attr_value(root.attrib.get("viewBox", "")),
        },
        "element_counts": dict(sorted(element_counts.items())),
        "class_counts": dict(sorted(class_counts.items())),
        "text_nodes": text_nodes,
        "geometry": geometry,
    }


def normalize_sld_render_output(render_output: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(render_output.get("metadata") or {})
    metadata.pop("generated_at", None)
    return {
        "metadata": _round_value(metadata),
        "spec": _round_value(dict(render_output.get("spec") or {})),
        "svg": normalize_sld_svg(render_output.get("svg_bytes") or b""),
    }


def write_normalized_json(path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
