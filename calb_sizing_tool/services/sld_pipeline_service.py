from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.plugins.base import ArtifactPayload, json_bytes
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
from calb_sizing_tool.services.sld_formal_readiness_service import (
    SldFormalReadinessReport,
    assess_sld_formal_readiness,
)
from calb_sizing_tool.services.sld_proposal_package_service import build_sld_proposal_package_artifacts
from calb_sizing_tool.services.sld_authoritative_builder import build_sld_authoritative_result


@dataclass
class PreparedSldPipeline:
    plugin_id: str
    plugin_version: str
    validation_mode: str
    render_input: SldRenderInput
    topology: SldTopology
    plugin: Any
    formal_readiness: SldFormalReadinessReport


@dataclass
class ExecutedSldPipeline:
    prepared: PreparedSldPipeline
    render_output: dict[str, Any]
    artifact_bundle: DiagramArtifactBundle


def resolve_sld_validation_mode(options: SldRenderOptions) -> str:
    return "draft" if bool(options.override_mode) else "strict"


def _resolve_document_status(prepared: PreparedSldPipeline) -> str:
    if prepared.validation_mode == "draft" or bool(prepared.render_input.canonical_input.override_mode):
        return "draft_override"
    return "official" if prepared.formal_readiness.ready else "concept"


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _svg_to_png(svg_bytes: bytes) -> bytes:
    import cairosvg

    return cairosvg.svg2png(bytestring=svg_bytes, background_color="white")


def _concept_safe_svg(svg_bytes: bytes, document_status: str) -> bytes:
    """Overlay non-formal drawings and remove false-looking equipment values.

    The detailed values remain in the readiness manifest. The drawing itself
    must not look like a released engineering document when those values are
    not yet supplied.
    """
    if document_status == "official":
        return svg_bytes

    svg_text = svg_bytes.decode("utf-8")
    if document_status == "concept":
        # The renderer marks unsupplied engineering values as "MISSING: <label>".
        # Match the marker pattern rather than each label so renderer label
        # changes cannot silently leak a MISSING marker into a concept issue.
        # Case/whitespace-insensitive so a formatting drift ("Missing :", …)
        # cannot leak a raw marker into a NOT-FOR-CONSTRUCTION concept drawing.
        svg_text = re.sub(
            r"MISSING\s*:\s*[^<]*",
            "Not specified - concept only",
            svg_text,
            flags=re.IGNORECASE,
        )
        status_label = "CONCEPT ONLY - NOT FOR CONSTRUCTION"
    else:
        status_label = "DRAFT / OVERRIDE - NOT FOR CONSTRUCTION"

    overlay = (
        '<g id="calb-document-status" pointer-events="none">'
        '<text x="50%" y="52%" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="42" font-weight="700" '
        'fill="#B42318" fill-opacity="0.28">'
        f"{status_label}</text></g>"
    )
    if "</svg>" not in svg_text:
        raise ValueError("SLD renderer returned malformed SVG without a closing tag.")
    return svg_text.rsplit("</svg>", 1)[0].encode("utf-8") + overlay.encode("utf-8") + b"</svg>"


def _apply_document_status(render_output: dict[str, Any], document_status: str) -> None:
    svg_bytes = _concept_safe_svg(bytes(render_output.get("svg_bytes") or b""), document_status)
    if document_status == "official":
        png_bytes = bytes(render_output.get("png_bytes") or b"") or _svg_to_png(svg_bytes)
    else:
        png_bytes = _svg_to_png(svg_bytes)
    metadata = dict(render_output.get("metadata") or {})
    metadata.update(
        {
            "artifact_mode": document_status,
            "document_status": document_status,
            "not_for_construction": document_status != "official",
            "svg_hash": _hash_bytes(svg_bytes),
            "png_hash": _hash_bytes(png_bytes),
        }
    )
    render_output["svg_bytes"] = svg_bytes
    render_output["png_bytes"] = png_bytes
    render_output["metadata"] = metadata


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
    formal_readiness = assess_sld_formal_readiness(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        canonical_input=canonical_input,
        options=options,
        project_settings=project_settings,
    )

    return PreparedSldPipeline(
        plugin_id=plugin.metadata.plugin_id,
        plugin_version=plugin.metadata.plugin_version,
        validation_mode=validation_mode,
        render_input=render_input,
        topology=topology,
        plugin=plugin,
        formal_readiness=formal_readiness,
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
    document_status = _resolve_document_status(prepared)
    _apply_document_status(render_output, document_status)
    artifacts = prepared.plugin.emit_artifact(render_output)
    metadata = prepared.plugin.metadata_payload(prepared.render_input, render_output)
    formal_readiness = prepared.formal_readiness.to_payload()
    metadata.update(
        {
            "formal_readiness": formal_readiness,
            "document_status": document_status,
            "not_for_construction": document_status != "official",
            "proposal_package": {
                "sheets": [
                    "SLD-01 Site Electrical Index",
                    "SLD-02 Typical AC Block SLD",
                    "SLD-03 Electrical Design Basis Schedule",
                    "SLD-04 Concept Interface / Scope",
                ],
                "site_layout_included": False,
            },
        }
    )

    manifest_suffix = {
        "official": "",
        "concept": ".concept",
        "draft_override": ".draft",
    }.get(document_status, ".concept")
    manifest_payload = {
        "run_id": run_bundle.run_id,
        "document_status": document_status,
        "not_for_construction": document_status != "official",
        "validation_mode": prepared.validation_mode,
        "renderer_mode": metadata.get("renderer_mode"),
        "source_trace": prepared.render_input.canonical_input.source_trace,
        "formal_readiness": formal_readiness,
    }
    artifacts.append(
        ArtifactPayload(
            artifact_kind="sld_readiness_manifest_json",
            file_name=f"sld_readiness_manifest{manifest_suffix}.json",
            media_type="application/json",
            content=json_bytes(manifest_payload),
            metadata={
                "content_hash": _hash_bytes(json_bytes(manifest_payload)),
            },
        )
    )
    artifacts.extend(
        build_sld_proposal_package_artifacts(
            run_bundle=run_bundle,
            ac_snapshot=ac_snapshot,
            formal_readiness=formal_readiness,
            document_status=document_status,
            typical_group_index=prepared.topology.summary.group_index,
            svg_to_png=_svg_to_png,
        )
    )
    shared_artifact_metadata = {
        "artifact_mode": document_status,
        "document_status": document_status,
        "not_for_construction": document_status != "official",
        "formal_readiness": formal_readiness,
        "run_id": run_bundle.run_id,
        "validation_mode": metadata.get("validation_mode"),
        "renderer_version": metadata.get("renderer_version"),
        "renderer_mode": metadata.get("renderer_mode"),
        "input_hash": metadata.get("input_hash"),
        "topology_hash": metadata.get("topology_hash"),
        "render_spec_hash": metadata.get("render_spec_hash"),
    }
    for artifact in artifacts:
        artifact.metadata.update(shared_artifact_metadata)
        artifact.metadata.setdefault("content_hash", _hash_bytes(artifact.content))

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


def _normalize_svg_text(text: str) -> str:
    return re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", "<DATE>", text)


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
        text = _normalize_svg_text(text)
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
    metadata.pop("svg_hash", None)
    metadata.pop("png_hash", None)
    return {
        "metadata": _round_value(metadata),
        "spec": _round_value(dict(render_output.get("spec") or {})),
        "svg": normalize_sld_svg(render_output.get("svg_bytes") or b""),
    }


def write_normalized_json(path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
