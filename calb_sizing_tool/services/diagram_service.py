from __future__ import annotations

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, DiagramArtifactBundle, LayoutRuleSnapshot, SldRenderOptions, TopologySnapshot
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.services.sld_pipeline_service import run_sld_pipeline_from_run_bundle


def render_sld_from_run_bundle(
    run_bundle: DcRunBundle,
    *,
    ac_snapshot: AcSnapshot,
    options: SldRenderOptions,
    project_settings: dict | None = None,
    topology_snapshot: TopologySnapshot | None = None,
    layout_rules: LayoutRuleSnapshot | None = None,
    plugin_id: str = "sld_engineering_v1",
    actor: str | None = None,
    db_url: str | None = None,
) -> DiagramArtifactBundle:
    execution = run_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        topology_snapshot=topology_snapshot,
        layout_rules=layout_rules,
        plugin_id=plugin_id,
        actor=actor,
        db_url=db_url,
    )
    return execution.artifact_bundle
