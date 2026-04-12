from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_render_input import SldCanonicalInput
from calb_sizing_tool.schemas.sld_topology import SldTopology
from calb_sizing_tool.services.sld_input_builder import build_sld_canonical_input
from calb_sizing_tool.services.sld_topology_builder import build_sld_topology


@dataclass(frozen=True)
class SldAuthoritativeBuildResult:
    canonical_input: SldCanonicalInput
    topology: SldTopology


def build_sld_authoritative_result(
    *,
    run_bundle: DcRunBundle,
    ac_snapshot: AcSnapshot,
    options: SldRenderOptions,
    project_settings: dict[str, Any] | None = None,
    validation_mode: str = "strict",
) -> SldAuthoritativeBuildResult:
    """AUTHORITATIVE builder.

    Formal SLD generation must flow through:
    AcSnapshot -> build_sld_canonical_input() -> build_sld_topology().
    Any renderer-friendly spec is a compatibility view derived from topology only.
    """
    canonical_input = build_sld_canonical_input(
        run_bundle=run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
        validation_mode=validation_mode,
    )
    topology = build_sld_topology(canonical_input)
    return SldAuthoritativeBuildResult(canonical_input=canonical_input, topology=topology)
