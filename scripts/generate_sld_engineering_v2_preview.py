from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calb_diagrams.sld_engineering_v2_layout import build_sld_engineering_v2_layout_plan
from calb_diagrams.sld_engineering_v2_renderer import render_sld_engineering_v2_svg
from calb_diagrams.sld_engineering_v2_validation import validate_sld_engineering_v2_layout
from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
from calb_sizing_tool.services.sld_engineering_v2_builder import build_sld_engineering_v2_graph
from calb_sizing_tool.services.sld_pipeline_service import prepare_sld_pipeline_from_run_bundle
from tests.integration.sld_regression_support import build_case_inputs, load_case_definition

DEFAULT_CASE_DIR = Path("tests/fixtures/sld_cases/case01_container_only_group1")
DEFAULT_OUTPUT_DIR = Path("outputs/sld_engineering_v2_preview/case01_container_only_group1")


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", payload[16:24])


def _parse_dc_blocks_per_feeder(value: str | None) -> list[int] | None:
    if not value:
        return None
    parsed = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not parsed:
        raise ValueError("--dc-blocks-per-feeder must contain at least one integer")
    if any(item < 0 for item in parsed):
        raise ValueError("--dc-blocks-per-feeder cannot contain negative values")
    return parsed


def _with_dc_blocks_per_feeder(ac_snapshot: AcSnapshot, allocation: list[int] | None) -> AcSnapshot:
    if allocation is None:
        return ac_snapshot
    output = dict(ac_snapshot.output)
    dc_allocation_plan = list(output.get("dc_allocation_plan") or [])
    if not dc_allocation_plan:
        raise ValueError("case AC snapshot has no dc_allocation_plan to override")
    first_plan = dict(dc_allocation_plan[0])
    first_plan["dc_blocks_total"] = sum(allocation)
    first_plan["feeder_allocations"] = list(allocation)
    dc_allocation_plan[0] = first_plan
    output["dc_allocation_plan"] = dc_allocation_plan
    return ac_snapshot.model_copy(update={"output": output})


def _with_professional_note_specs(
    project_settings: dict[str, Any],
    *,
    mv_cable_spec: str | None = None,
    lv_cable_spec: str | None = None,
    dc_cable_spec: str | None = None,
    battery_cell_spec: str | None = None,
) -> dict[str, Any]:
    if not any((mv_cable_spec, lv_cable_spec, dc_cable_spec, battery_cell_spec)):
        return project_settings
    settings = dict(project_settings)
    equipment = dict(settings.get("equipment_ratings") or {})
    cables = dict(equipment.get("cables") or {})
    if mv_cable_spec:
        cables["mv_cable_spec"] = mv_cable_spec
    if lv_cable_spec:
        cables["lv_cable_spec"] = lv_cable_spec
    if dc_cable_spec:
        cables["dc_cable_spec"] = dc_cable_spec
    equipment["cables"] = cables
    if battery_cell_spec:
        equipment["battery_cell_spec"] = battery_cell_spec
    settings["equipment_ratings"] = equipment
    return settings


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def generate_preview(
    case_dir: Path,
    output_dir: Path,
    *,
    dc_blocks_per_feeder: list[int] | None = None,
    theme: str | None = None,
    mv_cable_spec: str | None = None,
    lv_cable_spec: str | None = None,
    dc_cable_spec: str | None = None,
    battery_cell_spec: str | None = None,
) -> dict[str, Any]:
    case_dir = case_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_bundle, ac_snapshot, options, project_settings = build_case_inputs(load_case_definition(case_dir))
    ac_snapshot = _with_dc_blocks_per_feeder(ac_snapshot, dc_blocks_per_feeder)
    project_settings = _with_professional_note_specs(
        project_settings,
        mv_cable_spec=mv_cable_spec,
        lv_cable_spec=lv_cable_spec,
        dc_cable_spec=dc_cable_spec,
        battery_cell_spec=battery_cell_spec,
    )
    if theme:
        options = options.model_copy(update={"theme": theme})
    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    graph = build_sld_engineering_v2_graph(prepared.topology)
    plan = build_sld_engineering_v2_layout_plan(graph)
    layout_issues = validate_sld_engineering_v2_layout(plan)
    layout_errors = [issue for issue in layout_issues if issue.severity == "error"]
    layout_warnings = [issue for issue in layout_issues if issue.severity == "warning"]
    if layout_errors:
        summary = "; ".join(f"{issue.issue_id}: {issue.message}" for issue in layout_errors)
        raise ValueError(f"engineering_v2 preview layout acceptance failed: {summary}")

    svg_path = output_dir / "sld_engineering_v2.svg"
    png_path = output_dir / "sld_engineering_v2.png"
    result_path, warning = render_sld_engineering_v2_svg(plan, svg_path, png_path)
    if result_path is None:
        raise RuntimeError(warning or "engineering_v2 SVG render failed")

    svg_bytes = svg_path.read_bytes()
    png_bytes = png_path.read_bytes() if png_path.exists() else b""
    png_dimensions = _png_dimensions(png_bytes) if png_bytes else None
    png_hash = _hash_bytes(png_bytes) if png_bytes else None
    metadata = {
        "case_dir": _display_path(case_dir),
        "output_dir": _display_path(output_dir),
        "dc_blocks_per_feeder": list(graph.summary.dc_blocks_per_feeder),
        "theme": plan.theme,
        "engineering_v2_template": "professional_electrical_reference_v1",
        "model_version": graph.model_version,
        "source_topology_hash": graph.source_topology_hash,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "layout_box_count": len(plan.boxes),
        "layout_port_anchor_count": len(plan.port_anchors),
        "layout_connector_count": len(plan.connectors),
        "svg_path": _display_path(svg_path),
        "png_path": _display_path(png_path) if png_path.exists() else None,
        "png_width": png_dimensions[0] if png_dimensions else None,
        "png_height": png_dimensions[1] if png_dimensions else None,
        "svg_hash": _hash_bytes(svg_bytes),
        "png_hash": png_hash,
        "png_warning": warning,
        "layout_issue_count": len(layout_errors),
        "layout_warning_count": len(layout_warnings),
        "layout_warnings": [issue.__dict__ for issue in layout_warnings],
    }
    _write_json(output_dir / "metadata.json", metadata)
    _write_json(output_dir / "engineering_v2_graph.json", graph.model_dump(mode="python"))
    _write_json(
        output_dir / "layout_plan_summary.json",
        {
            "width": plan.width,
            "height": plan.height,
            "theme": plan.theme,
            "sections": [section.__dict__ for section in plan.sections],
            "box_count": len(plan.boxes),
            "port_anchor_count": len(plan.port_anchors),
            "connector_count": len(plan.connectors),
        },
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an engineering_v2 SLD preview artifact.")
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--dc-blocks-per-feeder",
        type=str,
        default=None,
        help="Optional comma-separated feeder allocation for preview stress testing, e.g. 2,1,2,1.",
    )
    parser.add_argument("--theme", choices=["dark", "light"], default=None, help="Optional output background theme.")
    parser.add_argument("--mv-cable-spec", type=str, default=None)
    parser.add_argument("--lv-cable-spec", type=str, default=None)
    parser.add_argument("--dc-cable-spec", type=str, default=None)
    parser.add_argument("--battery-cell-spec", type=str, default=None)
    args = parser.parse_args()
    metadata = generate_preview(
        args.case_dir,
        args.output_dir,
        dc_blocks_per_feeder=_parse_dc_blocks_per_feeder(args.dc_blocks_per_feeder),
        theme=args.theme,
        mv_cable_spec=args.mv_cable_spec,
        lv_cable_spec=args.lv_cable_spec,
        dc_cable_spec=args.dc_cable_spec,
        battery_cell_spec=args.battery_cell_spec,
    )
    print(f"Generated engineering_v2 SLD preview under {metadata['output_dir']}")


if __name__ == "__main__":
    main()
