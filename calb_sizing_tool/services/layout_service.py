from __future__ import annotations

from calb_sizing_tool.plugins.registry import get_plugin_registry
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, LayoutRuleSnapshot, TopologySnapshot
from calb_sizing_tool.schemas.layout_inputs import LayoutArtifactBundle, LayoutRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.services.artifact_service import persist_artifacts


def render_layout_from_run_bundle(
    run_bundle: DcRunBundle,
    *,
    ac_snapshot: AcSnapshot,
    options: LayoutRenderOptions,
    topology_snapshot: TopologySnapshot | None = None,
    layout_rules: LayoutRuleSnapshot | None = None,
    plugin_id: str = "layout_engineering_v1",
    actor: str | None = None,
    db_url: str | None = None,
) -> LayoutArtifactBundle:
    registry = get_plugin_registry()
    plugin = registry.get(plugin_id)
    if plugin is None:
        raise ValueError(f"Layout plugin not found: {plugin_id}")

    render_input = plugin.build_input_from_run(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        topology_snapshot=topology_snapshot,
        layout_rules=layout_rules,
        options=options,
    )
    errors = plugin.validate_input(render_input)
    if errors:
        raise ValueError("; ".join(errors))

    render_output = plugin.render(render_input)
    artifacts = plugin.emit_artifact(render_output)
    metadata = plugin.metadata_payload(render_input, render_output)

    persist_artifacts(
        run_id=run_bundle.run_id,
        artifacts=artifacts,
        plugin_id=plugin.metadata.plugin_id,
        plugin_version=plugin.metadata.plugin_version,
        actor=actor,
        db_url=db_url,
        source_ref="layout_service",
    )

    return LayoutArtifactBundle(
        plugin_id=plugin.metadata.plugin_id,
        plugin_version=plugin.metadata.plugin_version,
        run_id=run_bundle.run_id,
        metadata=metadata,
        artifacts=[artifact.__dict__ for artifact in artifacts],
    )
