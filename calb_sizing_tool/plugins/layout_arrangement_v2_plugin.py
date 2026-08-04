# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

"""Typical AC Block Arrangement renderer backed by the RULE-BASED engine.

Why this plugin exists
----------------------
The web page and the exported report were drawing the same "Typical AC Block
Arrangement" from two different engines:

- the report used ``calb_diagrams.ac_block_arrangement_v2`` /
  ``ac_block_bilateral_layout`` — spacing from an ``ArrangementRuleProfile``,
  station length resolved from the AC Block class, mirrored back-to-back pairs;
- the page used the older ``layout_block_renderer`` grid, whose ``2x2 / 1x4 /
  4x1`` presets and free-text clearance fields have no code basis and ignore the
  20 ft / 40 ft station distinction.

Owner instruction 2026-08-03: "网页上 TYPICAL AC BLOCK arrangement 时的排布引擎也
要同步调整 … 摆放方式最好还是原来那套引擎的视角，要统一一下" and then "无论是导出的
报告还是页面展示的 typical ac block arrangement 都要一致的逻辑排布和绘制."

So this plugin holds NO arrangement logic of its own. It resolves the selected
block's shape from the run and hands it to
``calb_diagrams.typical_ac_block_arrangement.render_typical_ac_block`` — the very
function the exported report calls. Engine selection, title, geometry and drawing
all live there, once.
``tests/unit/test_typical_ac_block_arrangement.py`` asserts the two surfaces emit
the identical SVG.

Nothing about the geometry is settable from the page: spacing comes from the rule
profile and the station from the AC Block class. That is the point — the page
cannot be nudged away from the report.
"""

from __future__ import annotations

import datetime
from typing import Any

from calb_diagrams.ac_block_arrangement_v2 import US_NFPA_OIL
from calb_diagrams.typical_ac_block_arrangement import (
    AcBlockShape,
    arrangement_spec,
    render_typical_ac_block,
    resolve_block_power_mw,
    resolve_dc_blocks_for_block,
    resolve_pcs_for_block,
)
from calb_sizing_tool.plugins.base import ArtifactPayload, PluginMetadata, json_bytes
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, LayoutRuleSnapshot, TopologySnapshot
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderInput, LayoutRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.services.site_constraint_readiness_service import (
    assess_site_constraint_readiness,
    build_site_constraint_template,
)

ARRANGEMENT_PROFILE = US_NFPA_OIL


def _svg_bytes_to_png(svg_bytes: bytes) -> bytes:
    import cairosvg

    from calb_sizing_tool.common.render_lock import RENDER_LOCK

    with RENDER_LOCK:
        return cairosvg.svg2png(bytestring=svg_bytes, background_color="white")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class LayoutArrangementV2Plugin:
    """Rule-based Typical AC Block Arrangement — the report's own engine."""

    metadata = PluginMetadata(
        plugin_id="layout_arrangement_v2",
        plugin_name="Typical AC Block Arrangement (rule-based, report engine)",
        plugin_version="1.0.0",
        supported_artifact_kind=[
            "layout_svg",
            "layout_png",
            "layout_spec_json",
            "layout_metadata_json",
            "layout_master_readiness_manifest_json",
        ],
    )

    # -- input -------------------------------------------------------------
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

    # -- render ------------------------------------------------------------
    def render(self, render_input: LayoutRenderInput) -> dict[str, Any]:
        ac_output = render_input.ac_snapshot.output
        block_index = max(1, _safe_int(render_input.options.block_index, 1))

        # Resolve THIS block's shape from the run, then hand it to the shared
        # arrangement. Everything after this line — engine choice, title,
        # geometry, drawing — is the same code the exported report runs.
        pcs_count = resolve_pcs_for_block(ac_output, block_index)
        shape = AcBlockShape(
            dc_blocks=resolve_dc_blocks_for_block(ac_output, block_index),
            pcs_count=pcs_count,
            block_power_mw=resolve_block_power_mw(ac_output, pcs_count),
            block_index=block_index,
            model_name=str(ac_output.get("ac_block_model_name")
                           or ac_output.get("configuration_code") or "").strip(),
            layout_variant=str(ac_output.get("ac_block_arrangement") or "").strip(),
        )
        if shape.dc_blocks < 1:
            raise RuntimeError(
                "AC snapshot carries no DC Block count for this AC Block; "
                "re-run AC sizing before generating the arrangement."
            )

        # The page hands out a standalone SVG, so the marking goes on the SVG.
        arrangement = render_typical_ac_block(shape, ARRANGEMENT_PROFILE, watermark=True)
        svg_bytes = arrangement.svg.encode("utf-8")
        png_bytes = _svg_bytes_to_png(svg_bytes)

        spec = arrangement_spec(arrangement, ARRANGEMENT_PROFILE)
        spec["block_index"] = block_index

        site_constraint_template = build_site_constraint_template(
            run_id=render_input.run_id,
            project_context={
                "project_code": render_input.run_bundle.project_code,
                "project_name": render_input.run_bundle.project_name,
                "case_code": render_input.run_bundle.case_code,
                "case_name": render_input.run_bundle.case_name,
            },
            ac_output=ac_output,
        )
        master_layout_readiness = assess_site_constraint_readiness(site_constraint_template)

        metadata = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "block_index": block_index,
            "dc_blocks_total": arrangement.dc_blocks,
            "pcs_count": arrangement.pcs_count,
            "arrangement": arrangement.layout_variant,
            "engine": "typical_ac_block_arrangement",
            "rule_profile_key": ARRANGEMENT_PROFILE.key,
            "station_length_m": arrangement.station_length_m,
            "envelope_w_m": arrangement.envelope_w_m,
            "envelope_d_m": arrangement.envelope_d_m,
            "envelope_area_m2": arrangement.envelope_area_m2,
            "document_status": "concept",
            "not_for_construction": True,
            "scope": "typical_ac_block_arrangement",
            "master_layout_readiness": master_layout_readiness,
        }

        return {
            "spec": spec,
            "svg_bytes": svg_bytes,
            "png_bytes": png_bytes,
            "site_constraint_template": site_constraint_template,
            "master_layout_readiness": master_layout_readiness,
            "metadata": metadata,
        }

    # -- artifacts ---------------------------------------------------------
    def emit_artifact(self, render_output: dict[str, Any]) -> list[ArtifactPayload]:
        metadata = dict(render_output.get("metadata") or {})
        return [
            ArtifactPayload(
                artifact_kind="layout_spec_json",
                file_name="typical_ac_block_arrangement_spec.json",
                media_type="application/json",
                content=json_bytes(render_output["spec"]),
                metadata=dict(metadata),
            ),
            ArtifactPayload(
                artifact_kind="layout_svg",
                file_name="typical_ac_block_arrangement.concept.svg",
                media_type="image/svg+xml",
                content=render_output["svg_bytes"],
                metadata=dict(metadata),
            ),
            ArtifactPayload(
                artifact_kind="layout_png",
                file_name="typical_ac_block_arrangement.concept.png",
                media_type="image/png",
                content=render_output["png_bytes"],
                metadata=dict(metadata),
            ),
            ArtifactPayload(
                artifact_kind="layout_metadata_json",
                file_name="typical_ac_block_arrangement_metadata.json",
                media_type="application/json",
                content=json_bytes(render_output["metadata"]),
                metadata=dict(metadata),
            ),
            ArtifactPayload(
                artifact_kind="layout_master_readiness_manifest_json",
                file_name="concept_master_layout_readiness_manifest.json",
                media_type="application/json",
                content=json_bytes(
                    {
                        "site_constraint_template": render_output["site_constraint_template"],
                        "master_layout_readiness": render_output["master_layout_readiness"],
                    }
                ),
                metadata=dict(metadata),
            ),
        ]

    def metadata_payload(self, render_input: LayoutRenderInput,
                         render_output: dict[str, Any]) -> dict[str, Any]:
        payload = dict(render_output.get("metadata") or {})
        payload.update(self.metadata.as_dict())
        payload["run_id"] = render_input.run_id
        return payload


__all__ = ["LayoutArrangementV2Plugin"]
