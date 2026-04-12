# -*- coding: utf-8 -*-
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

from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency
    import svgwrite
except Exception:  # pragma: no cover
    svgwrite = None

try:
    import cairosvg
except Exception:  # pragma: no cover - optional dependency
    cairosvg = None

from calb_diagrams.sld_layout_engine import (
    LayoutProfileId,
    SldLayoutPlan,
    build_sld_layout_plan,
)
from calb_diagrams.symbol_library import draw_symbol, resolve_palette
from calb_diagrams.specs import (
    SLD_DASH_ARRAY,
    SLD_FONT_FAMILY,
    SLD_FONT_SIZE,
    SLD_FONT_SIZE_SMALL,
    SLD_FONT_SIZE_TITLE,
    SLD_STROKE_OUTLINE,
    SLD_STROKE_THICK,
    SLD_STROKE_THIN,
    SldGroupSpec,
)
from calb_sizing_tool.schemas.sld_topology import SldTopology
from calb_sizing_tool.schemas.sld_render_input import SldEquipmentRatings, SldLabels


def _write_png(svg_path: Path, png_path: Path) -> None:
    if cairosvg is None:
        raise ImportError("cairosvg is required to export PNG from SVG.")
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


def _topology_from_legacy_spec(spec: SldGroupSpec) -> SldTopology:
    """DEPRECATED compatibility adapter.

    This path exists only for legacy callers that still hand renderer-facing
    SldGroupSpec objects to the renderer. Any defaults applied here are draft
    compatibility behavior and must never be treated as formal runtime input.
    """
    equipment_list = spec.equipment_list if isinstance(spec.equipment_list, dict) else {}
    mv_labels = equipment_list.get("mv_labels") if isinstance(equipment_list.get("mv_labels"), dict) else {}
    rmu_payload = {
        "rated_kv": 24.0,
        "rated_a": 630.0,
        "short_circuit_ka_3s": 25.0,
        "ct_ratio": "200/1",
        "ct_class": "5P20",
        "ct_va": 10.0,
    }
    if isinstance(equipment_list.get("rmu"), dict):
        rmu_payload.update({key: value for key, value in equipment_list["rmu"].items() if value not in (None, "")})
    lv_busbar_payload = {"rated_a": 2500.0, "short_circuit_ka": 25.0}
    if isinstance(equipment_list.get("lv_busbar"), dict):
        lv_busbar_payload.update(
            {key: value for key, value in equipment_list["lv_busbar"].items() if value not in (None, "")}
        )
    cables_payload = {"mv_cable_spec": "TBD", "lv_cable_spec": "TBD", "dc_cable_spec": "TBD"}
    if isinstance(equipment_list.get("cables"), dict):
        cables_payload.update({key: value for key, value in equipment_list["cables"].items() if value not in (None, "")})
    dc_fuse_payload = {"fuse_spec": "TBD"}
    if isinstance(equipment_list.get("dc_fuse"), dict):
        dc_fuse_payload.update({key: value for key, value in equipment_list["dc_fuse"].items() if value not in (None, "")})
    labels = SldLabels.model_validate(
        {
            "to_switchgear": mv_labels.get("to_switchgear") or "To Switchgear",
            "to_other_rmu": mv_labels.get("to_other_rmu") or "To Other RMU",
        }
    )
    transformer = equipment_list.get("transformer") if isinstance(equipment_list.get("transformer"), dict) else {}
    equipment_ratings = SldEquipmentRatings.model_validate(
        {
            "rmu": rmu_payload,
            "lv_busbar": lv_busbar_payload,
            "cables": cables_payload,
            "dc_fuse": dc_fuse_payload,
            "transformer_tap_range": transformer.get("tap_range"),
            "transformer_cooling": transformer.get("cooling"),
        }
    )

    dc_bus_nodes: list[dict[str, Any]] = []
    pcs_nodes: list[dict[str, Any]] = []
    dc_block_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for feeder_index, rating in enumerate(spec.pcs_rating_kw_list, start=1):
        pcs_node_id = f"G{spec.group_index:02d}-F{feeder_index:02d}-PCS-NODE"
        dc_bus_node_id = f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR-NODE"
        pcs_nodes.append(
            {
                "node_id": pcs_node_id,
                "node_type": "pcs",
                "display_name": f"PCS {feeder_index}",
                "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-PCS",
                "feeder_index": feeder_index,
                "attributes": {"pcs_rating_kw": rating},
            }
        )
        dc_bus_nodes.append(
            {
                "node_id": dc_bus_node_id,
                "node_type": "dc_busbar",
                "display_name": f"DC Busbar {feeder_index}",
                "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR",
                "feeder_index": feeder_index,
                "attributes": {"dc_block_count": spec.dc_blocks_per_feeder[feeder_index - 1]},
            }
        )
        edges.append(
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-LV-PCS-{feeder_index:02d}",
                "edge_type": "lv_busbar_to_pcs",
                "source_node_id": f"G{spec.group_index:02d}-LV-BUSBAR-NODE",
                "target_node_id": pcs_node_id,
                "feeder_index": feeder_index,
            }
        )
        edges.append(
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-PCS-DCBUS-{feeder_index:02d}",
                "edge_type": "pcs_to_dc_busbar",
                "source_node_id": pcs_node_id,
                "target_node_id": dc_bus_node_id,
                "feeder_index": feeder_index,
            }
        )

    dc_block_index = 0
    for feeder_index, count in enumerate(spec.dc_blocks_per_feeder, start=1):
        for local_index in range(1, count + 1):
            dc_block_index += 1
            node_id = f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BLOCK-{local_index:02d}-NODE"
            dc_block_nodes.append(
                {
                    "node_id": node_id,
                    "node_type": "dc_block",
                    "display_name": f"DC Block {dc_block_index}",
                    "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BLOCK-{local_index:02d}",
                    "feeder_index": feeder_index,
                    "dc_block_index": dc_block_index,
                    "attributes": {"dc_block_energy_mwh": spec.dc_block_energy_mwh},
                }
            )
            edges.append(
                {
                    "edge_id": f"G{spec.group_index:02d}-EDGE-DCBUS-BLOCK-{dc_block_index:02d}",
                    "edge_type": "dc_busbar_to_dc_block",
                    "source_node_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR-NODE",
                    "target_node_id": node_id,
                    "feeder_index": feeder_index,
                }
            )

    topology_payload = {
        "run_id": None,
        "project_name": "Legacy SLD Group",
        "scenario_id": "legacy_sld_group_spec",
        "source_trace": {
            "A": "deprecated renderer compatibility adapter",
            "B": "legacy spec defaults are draft-only and non-authoritative",
        },
        "validation_mode": "draft",
        "labels": labels.model_dump(mode="python"),
        "equipment_ratings": equipment_ratings.model_dump(mode="python"),
        "summary": {
            "group_index": spec.group_index,
            "ac_blocks_total": spec.group_index,
            "feeder_count": spec.pcs_count,
            "pcs_count": spec.pcs_count,
            "dc_blocks_total_in_group": spec.dc_blocks_total_in_group,
            "dc_blocks_per_feeder": list(spec.dc_blocks_per_feeder),
            "mv_voltage_kv": spec.mv_voltage_kv,
            "lv_voltage_v_ll": spec.lv_voltage_v_ll,
            "transformer_rating_mva": spec.transformer_mva,
            "transformer_vector_group": transformer.get("vector_group") or spec.transformer_vector_group or "Dyn11",
            "transformer_uk_percent": transformer.get("uk_percent") or spec.transformer_uk_percent or 7.0,
            "pcs_rating_kw_list": list(spec.pcs_rating_kw_list),
            "dc_block_energy_mwh": spec.dc_block_energy_mwh,
            "dc_block_voltage_v": equipment_list.get("dc_block_voltage_v") or 1500.0,
            "project_frequency_hz": equipment_list.get("project_hz"),
            "diagram_mode": "one_ac_block_group",
            "theme": (spec.layout_params or {}).get("theme") or "light",
            "compact_mode": bool((spec.layout_params or {}).get("compact_mode")),
            "draw_summary": bool((spec.layout_params or {}).get("draw_summary")),
        },
        "nodes": [
            {
                "node_id": f"G{spec.group_index:02d}-MV-BUS",
                "node_type": "mv_bus",
                "display_name": "MV Bus",
                "attributes": {"mv_voltage_kv": spec.mv_voltage_kv},
            },
            {
                "node_id": f"G{spec.group_index:02d}-RMU-NODE",
                "node_type": "rmu",
                "display_name": "RMU",
                "equipment_id": f"G{spec.group_index:02d}-RMU",
            },
            {
                "node_id": f"G{spec.group_index:02d}-TX-NODE",
                "node_type": "transformer",
                "display_name": "Transformer",
                "equipment_id": f"G{spec.group_index:02d}-TX",
            },
            {
                "node_id": f"G{spec.group_index:02d}-LV-BUSBAR-NODE",
                "node_type": "lv_busbar",
                "display_name": "LV Busbar",
                "equipment_id": f"G{spec.group_index:02d}-LV-BUSBAR",
            },
            *pcs_nodes,
            *dc_bus_nodes,
            *dc_block_nodes,
        ],
        "equipment": [
            {"equipment_id": f"G{spec.group_index:02d}-RMU", "equipment_type": "rmu", "display_name": "RMU"},
            {"equipment_id": f"G{spec.group_index:02d}-TX", "equipment_type": "transformer", "display_name": "Transformer"},
            {"equipment_id": f"G{spec.group_index:02d}-LV-BUSBAR", "equipment_type": "lv_busbar", "display_name": "LV Busbar"},
            *[
                {
                    "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-PCS",
                    "equipment_type": "pcs",
                    "display_name": f"PCS {feeder_index}",
                    "feeder_index": feeder_index,
                }
                for feeder_index in range(1, spec.pcs_count + 1)
            ],
            *[
                {
                    "equipment_id": f"G{spec.group_index:02d}-F{feeder_index:02d}-DC-BUSBAR",
                    "equipment_type": "dc_busbar",
                    "display_name": f"DC Busbar {feeder_index}",
                    "feeder_index": feeder_index,
                }
                for feeder_index in range(1, spec.pcs_count + 1)
            ],
            *[
                {
                    "equipment_id": item["equipment_id"],
                    "equipment_type": "dc_block",
                    "display_name": item["display_name"],
                    "feeder_index": item["feeder_index"],
                    "dc_block_index": item["dc_block_index"],
                }
                for item in dc_block_nodes
            ],
        ],
        "edges": [
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-MV-RMU",
                "edge_type": "mv_link",
                "source_node_id": f"G{spec.group_index:02d}-MV-BUS",
                "target_node_id": f"G{spec.group_index:02d}-RMU-NODE",
            },
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-RMU-TX",
                "edge_type": "rmu_to_transformer",
                "source_node_id": f"G{spec.group_index:02d}-RMU-NODE",
                "target_node_id": f"G{spec.group_index:02d}-TX-NODE",
            },
            {
                "edge_id": f"G{spec.group_index:02d}-EDGE-TX-LVBUS",
                "edge_type": "transformer_to_lv_busbar",
                "source_node_id": f"G{spec.group_index:02d}-TX-NODE",
                "target_node_id": f"G{spec.group_index:02d}-LV-BUSBAR-NODE",
            },
            *edges,
        ],
    }
    return SldTopology.model_validate(topology_payload)


def _draw_panel(dwg, panel) -> None:
    dwg.add(dwg.rect(insert=(panel.x, panel.y), size=(panel.width, panel.height), class_="outline"))
    dwg.add(dwg.text(panel.title, insert=(panel.x + 8, panel.y + 18), class_="label title"))
    split_x = panel.x + panel.width * 0.37
    current_y = panel.y + 36
    dwg.add(dwg.line((split_x, panel.y + 24), (split_x, panel.y + panel.height), class_="thin"))
    for row in panel.rows:
        current_y += 28
        dwg.add(dwg.line((panel.x, current_y - 18), (panel.x + panel.width, current_y - 18), class_="thin"))
        dwg.add(dwg.text(row.item, insert=(panel.x + 8, current_y), class_="small"))
        dwg.add(dwg.text(row.spec, insert=(split_x + 8, current_y), class_="small"))


def _draw_summary_box(dwg, plan: SldLayoutPlan) -> None:
    if not plan.draw_summary or not plan.summary_lines:
        return
    box_width = 420.0
    box_height = 34.0 + len(plan.summary_lines) * 18.0
    box_x = plan.width - box_width - 40.0
    box_y = plan.height - box_height - 28.0
    dwg.add(dwg.rect(insert=(box_x, box_y), size=(box_width, box_height), class_="outline"))
    dwg.add(dwg.text("Allocation Summary", insert=(box_x + 8, box_y + 18), class_="label title"))
    for index, line in enumerate(plan.summary_lines):
        dwg.add(dwg.text(line, insert=(box_x + 8, box_y + 40 + index * 18), class_="small"))


def _draw_connectors(dwg, plan: SldLayoutPlan) -> None:
    for connector in plan.connectors:
        if len(connector.points) < 2:
            continue
        if len(connector.points) == 2:
            dwg.add(dwg.line(connector.points[0], connector.points[1], class_=connector.style))
        else:
            dwg.add(dwg.polyline(points=list(connector.points), class_=connector.style, fill="none"))
        if connector.label:
            label_x, label_y = connector.points[-1]
            dwg.add(dwg.text(connector.label, insert=(label_x + 4, label_y - 4), class_="small"))


def _build_svg_drawing(plan: SldLayoutPlan):
    palette = resolve_palette(plan.theme)
    dwg = svgwrite.Drawing(
        size=(f"{plan.width}px", f"{plan.height}px"),
        viewBox=f"0 0 {plan.width} {plan.height}",
    )
    dwg.add(
        dwg.style(
            f"""
svg {{ font-family: {SLD_FONT_FAMILY}; font-size: {SLD_FONT_SIZE}px; }}
.outline {{ stroke: {palette.outline}; stroke-width: {max(2.0, SLD_STROKE_OUTLINE)}; fill: none; }}
.thin {{ stroke: {palette.thin}; stroke-width: {max(1.4, SLD_STROKE_THIN)}; fill: none; }}
.thick {{ stroke: {palette.thick}; stroke-width: {max(2.0, SLD_STROKE_THICK)}; fill: none; }}
.dash {{ stroke: {palette.dash}; stroke-width: {max(2.0, SLD_STROKE_OUTLINE)}; fill: none; stroke-dasharray: {SLD_DASH_ARRAY}; }}
.busbar {{ stroke: {palette.busbar}; stroke-width: {max(2.2, SLD_STROKE_THICK)}; fill: none; }}
.label {{ fill: {palette.text}; }}
.title {{ font-size: {SLD_FONT_SIZE_TITLE}px; font-weight: bold; fill: {palette.title}; }}
.small {{ font-size: {SLD_FONT_SIZE_SMALL}px; fill: {palette.text}; }}
"""
        )
    )
    dwg.add(dwg.rect(insert=(0, 0), size=(plan.width, plan.height), fill=palette.background))
    return dwg, palette


def render_sld_svg(
    topology: SldTopology,
    layout_profile: LayoutProfileId,
    theme: str,
    out_svg: Path,
    out_png: Path | None = None,
) -> tuple[Path | None, str | None]:
    """Pure renderer entrypoint.

    Consumes only authoritative topology + layout profile + theme and emits SVG/PNG.
    No AC/DC/session/stage dict inference is allowed in this function.
    """
    if svgwrite is None:
        return None, "Missing dependency: svgwrite. Please install: pip install svgwrite"

    plan = build_sld_layout_plan(topology, layout_profile=layout_profile, theme=theme)
    dwg, palette = _build_svg_drawing(plan)

    for panel in plan.panels:
        _draw_panel(dwg, panel)
    _draw_connectors(dwg, plan)
    for symbol in plan.symbols:
        draw_symbol(dwg, symbol, palette)
    _draw_summary_box(dwg, plan)

    out_svg = Path(out_svg)
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    dwg.saveas(str(out_svg))

    png_warning = None
    if out_png is not None:
        out_png = Path(out_png)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        try:
            _write_png(out_svg, out_png)
        except ImportError:
            png_warning = "Missing dependency: cairosvg. PNG export skipped."
        except Exception:
            png_warning = "PNG export failed."
    return out_svg, png_warning


def render_sld_pro_svg(
    spec: SldGroupSpec | SldTopology,
    out_svg: Path,
    out_png: Path | None = None,
) -> tuple[Path | None, str | None]:
    """Compatibility wrapper for older SLD call sites.

    Rendering is delegated to render_sld_svg(topology, ...). This wrapper only adapts the legacy
    SldGroupSpec shape into topology and must not contain engineering allocation logic.
    Formal SLD generation must call render_sld_svg() with authoritative topology instead.
    """
    if isinstance(spec, SldTopology):
        topology = spec
        layout_profile: LayoutProfileId = "compact" if topology.summary.compact_mode else "engineering_readable"
        theme = topology.summary.theme
    else:
        topology = _topology_from_legacy_spec(spec)
        layout_profile = "compact" if topology.summary.compact_mode else "engineering_readable"
        theme = topology.summary.theme
    return render_sld_svg(topology, layout_profile, theme, out_svg, out_png)
