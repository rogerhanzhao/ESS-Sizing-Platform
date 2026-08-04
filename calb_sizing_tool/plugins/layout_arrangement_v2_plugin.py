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
要同步调整 … 摆放方式最好还是原来那套引擎的视角，要统一一下." One product must not
have two arrangements, so this plugin puts the page on the report's engine.

Engine selection is the SAME shape test the report applies: an 8-PCS block with
8 DC Blocks is the 10 MW / 40 ft product and draws the single-axis bilateral
unit (west 4-DC | central 40 ft station | east 4-DC); everything else draws the
linear rule-based row. Nothing about the geometry is settable from the page —
spacing comes from the rule profile and the station from the block class — which
is the point: the page can no longer disagree with the report.
"""

from __future__ import annotations

import datetime
from typing import Any

from calb_diagrams.ac_block_arrangement_v2 import (
    US_NFPA_OIL,
    compute_layout,
    render_plan_svg,
)
from calb_diagrams.ac_block_bilateral_layout import (
    LAYOUT_VARIANT as BILATERAL_LAYOUT_VARIANT,
    compute_bilateral_layout,
    render_bilateral_plan_svg,
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _apply_concept_watermark(svg_bytes: bytes) -> bytes:
    svg_text = svg_bytes.decode("utf-8")
    overlay = (
        '<g id="calb-document-status" pointer-events="none">'
        '<text x="50%" y="52%" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="30" font-weight="700" '
        'fill="#B42318" fill-opacity="0.25">'
        'CONCEPT ONLY - NOT FOR CONSTRUCTION</text></g>'
    )
    if "</svg>" not in svg_text:
        raise ValueError("Arrangement renderer returned malformed SVG without a closing tag.")
    return svg_text.rsplit("</svg>", 1)[0].encode("utf-8") + overlay.encode("utf-8") + b"</svg>"


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

    # -- block resolution --------------------------------------------------
    @staticmethod
    def _dc_counts_by_block(ac_output: dict) -> dict[int, int]:
        counts: dict[int, int] = {}
        plan = ac_output.get("dc_allocation_plan")
        if isinstance(plan, list):
            for entry in plan:
                if not isinstance(entry, dict):
                    continue
                idx = entry.get("ac_block_index")
                total = entry.get("dc_blocks_total")
                if isinstance(idx, int) and isinstance(total, int):
                    counts[idx] = total
        return counts

    @staticmethod
    def _pcs_for_block(ac_output: dict, block_index: int) -> int:
        per_block = ac_output.get("pcs_count_by_block")
        if isinstance(per_block, list) and 1 <= block_index <= len(per_block):
            resolved = _safe_int(per_block[block_index - 1])
            if resolved > 0:
                return resolved
        return _safe_int(ac_output.get("pcs_per_block"))

    @staticmethod
    def _block_power_mw(ac_output: dict, pcs_count: int) -> float:
        """This AC Block's power — from the run, never a constant.

        ``block_size_mw`` is the fleet-nominal block; a tail AC Block with fewer
        PCS is smaller, so prefer PCS x PCS rating when both are known.
        """
        pcs_kw = _safe_float(ac_output.get("pcs_kw"))
        if pcs_count > 0 and pcs_kw > 0:
            return pcs_count * pcs_kw / 1000.0
        return _safe_float(ac_output.get("block_size_mw"))

    # -- render ------------------------------------------------------------
    def render(self, render_input: LayoutRenderInput) -> dict[str, Any]:
        ac_output = render_input.ac_snapshot.output
        options = render_input.options

        block_index = max(1, _safe_int(options.block_index, 1))
        counts = self._dc_counts_by_block(ac_output)
        dc_blocks_total = counts.get(block_index, 0)
        if dc_blocks_total <= 0 and counts:
            dc_blocks_total = next(iter(counts.values()))
        if dc_blocks_total <= 0:
            dc_blocks_total = _safe_int(ac_output.get("dc_blocks_per_block"))
        if dc_blocks_total <= 0:
            raise RuntimeError(
                "AC snapshot carries no DC Block count for this AC Block; "
                "re-run AC sizing before generating the arrangement."
            )

        pcs_count = self._pcs_for_block(ac_output, block_index)
        block_power_mw = self._block_power_mw(ac_output, pcs_count)

        # SAME shape test as the report's §8 — one product, one geometry.
        is_bilateral = pcs_count == 8 and dc_blocks_total == 8
        model_label = str(
            ac_output.get("ac_block_model_name")
            or ac_output.get("configuration_code")
            or ""
        ).strip()

        if is_bilateral:
            layout = compute_bilateral_layout(dc_blocks_total)
            label = model_label or (
                f"TYPICAL AC BLOCK {block_index} · {pcs_count} PCS / "
                f"{dc_blocks_total} DC · 40 FT CENTRAL STATION"
            )
            svg_text = render_bilateral_plan_svg(layout, block_label=label)
            layout_variant = BILATERAL_LAYOUT_VARIANT
            station_length_m = max(
                p.height_m for p in layout.by_type("ac_station")
            )
            provisional_notes = list(layout.provisional_notes)
            placements = [
                {
                    "equipment_id": p.equipment_id,
                    "equipment_type": p.equipment_type,
                    "x_m": p.x_m,
                    "y_m": p.y_m,
                    "width_m": p.width_m,
                    "height_m": p.height_m,
                    "door_orientation": p.door_orientation,
                    "feeder_index": p.feeder_index,
                    "provisional": p.provisional,
                }
                for p in layout.placements
            ]
        else:
            label = model_label or f"TYPICAL AC BLOCK {block_index}"
            svg_text, linear = render_plan_svg(
                dc_blocks_total,
                ARRANGEMENT_PROFILE,
                label,
                pcs_count=pcs_count,
                block_power_mw=block_power_mw,
            )
            layout = linear
            layout_variant = "linear_mirrored_pairs"
            station_length_m = linear.station_length_m
            provisional_notes = []
            placements = []

        svg_bytes = _apply_concept_watermark(svg_text.encode("utf-8"))
        png_bytes = _svg_bytes_to_png(svg_bytes)

        spec = {
            "engine": "ac_block_arrangement_v2",
            "layout_variant": layout_variant,
            "rule_profile_key": ARRANGEMENT_PROFILE.key,
            "rule_profile_market": ARRANGEMENT_PROFILE.market_label,
            "block_index": block_index,
            "pcs_count": pcs_count,
            "block_power_mw": round(block_power_mw, 3),
            "dc_blocks_total": dc_blocks_total,
            "station_length_m": round(float(station_length_m), 3),
            "envelope_w_m": layout.envelope_w_m,
            "envelope_d_m": layout.envelope_d_m,
            "clearances_m": {
                "dc_pair_gap": ARRANGEMENT_PROFILE.dc_pair_gap_m,
                "dc_to_mv_aisle": ARRANGEMENT_PROFILE.dc_to_mv_aisle_m,
                "pair_to_pair_plain_end": ARRANGEMENT_PROFILE.pair_to_pair_gap_m,
                "dc_equipment_end": ARRANGEMENT_PROFILE.dc_equipment_end_gap_m,
            },
            "code_basis": [
                {"parameter": item, "value": value, "basis": basis}
                for item, value, basis in ARRANGEMENT_PROFILE.basis
            ],
            "placements": placements,
            "provisional_notes": provisional_notes,
        }

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
            "dc_blocks_total": dc_blocks_total,
            "pcs_count": pcs_count,
            "arrangement": layout_variant,
            "engine": "ac_block_arrangement_v2",
            "rule_profile_key": ARRANGEMENT_PROFILE.key,
            "station_length_m": round(float(station_length_m), 3),
            "envelope_w_m": layout.envelope_w_m,
            "envelope_d_m": layout.envelope_d_m,
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
