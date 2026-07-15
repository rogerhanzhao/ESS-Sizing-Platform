from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from itertools import combinations

from calb_diagrams.sld_engineering_v2_layout import SldV2LayoutBox, SldV2LayoutPlan


@dataclass(frozen=True)
class SldV2LayoutIssue:
    issue_id: str
    severity: str
    message: str


def _box_bounds(box: SldV2LayoutBox) -> tuple[float, float, float, float]:
    return box.x, box.y, box.x + box.width, box.y + box.height


def _overlaps(a: SldV2LayoutBox, b: SldV2LayoutBox, *, margin: float = 0.0) -> bool:
    ax1, ay1, ax2, ay2 = _box_bounds(a)
    bx1, by1, bx2, by2 = _box_bounds(b)
    return ax1 < bx2 - margin and ax2 > bx1 + margin and ay1 < by2 - margin and ay2 > by1 + margin


def _is_allowed_nested_overlap(a: SldV2LayoutBox, b: SldV2LayoutBox) -> bool:
    types = {a.node_type, b.node_type}
    if "rmu_switchgear" in types and any(item.startswith("rmu_") and item != "rmu_switchgear" for item in types):
        return True
    if types == {"lv_feeder", "pcs"} and a.feeder_index == b.feeder_index:
        return True
    return False


def _estimated_text_width(text: str) -> float:
    return len(text) * 6.2


def _check_text_fit(box: SldV2LayoutBox) -> SldV2LayoutIssue | None:
    if box.node_type in {
        "transformer",
        "dc_interface",
        "lv_busbar",
        "lv_feeder",
        "mv_ring_in_terminal",
        "mv_ring_out_terminal",
    }:
        return None
    if not box.text_lines:
        return None
    max_width = max(_estimated_text_width(line) for line in box.text_lines)
    if max_width > box.width - 12.0:
        return SldV2LayoutIssue(
            issue_id=f"text_overflow:{box.node_id}",
            severity="error",
            message=f"text in {box.node_id} is wider than its layout box",
        )
    required_height = 14.0 * len(box.text_lines) + 8.0
    if required_height > box.height:
        return SldV2LayoutIssue(
            issue_id=f"text_height_overflow:{box.node_id}",
            severity="error",
            message=f"text in {box.node_id} is taller than its layout box",
        )
    return None


def validate_sld_engineering_v2_layout(plan: SldV2LayoutPlan) -> list[SldV2LayoutIssue]:
    issues: list[SldV2LayoutIssue] = []
    sections = {section.section_id: section for section in plan.sections}

    for box in plan.boxes:
        section = sections.get(box.section_id)
        if section is None:
            issues.append(
                SldV2LayoutIssue(
                    issue_id=f"missing_section:{box.node_id}",
                    severity="error",
                    message=f"{box.node_id} references unknown section {box.section_id}",
                )
            )
            continue
        if (
            box.x < section.x
            or box.y < section.y
            or box.x + box.width > section.x + section.width
            or box.y + box.height > section.y + section.height
        ):
            issues.append(
                SldV2LayoutIssue(
                    issue_id=f"box_outside_section:{box.node_id}",
                    severity="error",
                    message=f"{box.node_id} crosses its section boundary",
                )
            )

        text_issue = _check_text_fit(box)
        if text_issue:
            issues.append(text_issue)

    for left, right in combinations(plan.boxes, 2):
        if left.section_id != right.section_id:
            continue
        if _is_allowed_nested_overlap(left, right):
            continue
        if _overlaps(left, right, margin=2.0):
            issues.append(
                SldV2LayoutIssue(
                    issue_id=f"box_overlap:{left.node_id}:{right.node_id}",
                    severity="error",
                    message=f"{left.node_id} overlaps {right.node_id}",
                )
            )

    texts = [line for box in plan.boxes for line in box.text_lines] + [
        row.item for row in plan.equipment_rows
    ] + [row.spec for row in plan.equipment_rows]
    forbidden_terms = ("DC BUSBAR", "BUSBAR A", "BUSBAR B", "Circuit A", "Circuit B", "DC + BUSBAR", "DC - BUSBAR")
    for term in forbidden_terms:
        if any(term in text for text in texts):
            issues.append(
                SldV2LayoutIssue(
                    issue_id=f"forbidden_label:{term}",
                    severity="error",
                    message=f"engineering_v2 layout still contains forbidden floating busbar label: {term}",
                )
            )

    for row in plan.equipment_rows:
        if str(row.spec or "").strip().upper().startswith("MISSING:"):
            issues.append(
                SldV2LayoutIssue(
                    issue_id=f"missing_professional_input:{row.item}",
                    severity="warning",
                    message=f"{row.item} is not specified in authoritative SLD inputs: {row.spec}",
                )
            )

    transformer = next((box for box in plan.boxes if box.node_type == "transformer"), None)
    if transformer is None:
        issues.append(SldV2LayoutIssue("missing_transformer", "error", "transformer box is missing"))
    else:
        joined = " ".join(transformer.text_lines)
        for required in ("Transformer", "kV", "MVA", "Uk="):
            if required not in joined:
                issues.append(
                    SldV2LayoutIssue(
                        issue_id=f"transformer_label_missing:{required}",
                        severity="error",
                        message=f"transformer label is missing {required}",
                    )
                )

    connector_ids = [connector.edge_id for connector in plan.connectors]
    if len(connector_ids) != len(set(connector_ids)):
        issues.append(SldV2LayoutIssue("duplicate_connector_id", "error", "layout contains duplicate connector IDs"))

    return issues


# ---------------------------------------------------------------------------
# Rendered-SVG quality gate
#
# The layout-plan checks above validate coordinates that the renderer partly
# re-derives with its own sheet geometry. This gate inspects the *rendered*
# SVG instead, so drawing regressions (label collisions, detached transformer
# winding circles) fail even when the plan looks clean.
# ---------------------------------------------------------------------------

_TITLE_BLOCK_TEXT_CLASSES = {"tb", "tbh", "tbtitle"}
_TITLE_BLOCK_BAND_HEIGHT = 120.0
_CANVAS_MARGIN = 20.0


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_rendered_sld_svg(svg_markup: str) -> list[SldV2LayoutIssue]:
    """Geometric quality checks on the rendered SVG markup.

    - no non-title-block text may intrude into the title-block band;
    - all text anchors stay inside the drawing frame;
    - transformer winding circles (ids ``tx-*``) must share one radius and
      every pair must interlock (one device, not detached satellites).
    """
    issues: list[SldV2LayoutIssue] = []
    try:
        root = ET.fromstring(svg_markup)
    except ET.ParseError as exc:
        return [SldV2LayoutIssue("svg_parse_error", "error", f"rendered SVG is not parseable: {exc}")]

    view_box = (root.attrib.get("viewBox") or "").split()
    if len(view_box) == 4:
        width, height = float(view_box[2]), float(view_box[3])
    else:
        width = float(str(root.attrib.get("width", "0")).replace("px", "") or 0)
        height = float(str(root.attrib.get("height", "0")).replace("px", "") or 0)
    if not width or not height:
        return [SldV2LayoutIssue("svg_size_unknown", "error", "rendered SVG has no resolvable canvas size")]

    title_block_top = height - _TITLE_BLOCK_BAND_HEIGHT
    winding_circles: dict[str, tuple[float, float, float]] = {}

    for element in root.iter():
        tag = _local_tag(element.tag)
        if tag == "text":
            css_class = element.attrib.get("class", "")
            try:
                x = float(element.attrib.get("x", "0"))
                y = float(element.attrib.get("y", "0"))
            except ValueError:
                continue
            label = " ".join((element.text or "").split())
            if css_class not in _TITLE_BLOCK_TEXT_CLASSES and y > title_block_top:
                issues.append(
                    SldV2LayoutIssue(
                        issue_id=f"text_in_title_block:{label[:40]}",
                        severity="error",
                        message=f"text '{label}' (y={y:.0f}) intrudes into the title-block band (y>{title_block_top:.0f})",
                    )
                )
            if not (_CANVAS_MARGIN <= x <= width - _CANVAS_MARGIN):
                issues.append(
                    SldV2LayoutIssue(
                        issue_id=f"text_outside_frame:{label[:40]}",
                        severity="error",
                        message=f"text '{label}' anchored at x={x:.0f} lies outside the drawing frame",
                    )
                )
        elif tag == "circle":
            circle_id = element.attrib.get("id", "")
            if circle_id.startswith("tx-"):
                winding_circles[circle_id] = (
                    float(element.attrib.get("cx", "0")),
                    float(element.attrib.get("cy", "0")),
                    float(element.attrib.get("r", "0")),
                )

    if len(winding_circles) >= 2:
        radii = {round(r, 3) for _, _, r in winding_circles.values()}
        if len(radii) > 1:
            issues.append(
                SldV2LayoutIssue(
                    issue_id="winding_circles_unequal",
                    severity="error",
                    message=f"transformer winding circles have unequal radii: {sorted(radii)}",
                )
            )
        for (id_a, a), (id_b, b) in combinations(sorted(winding_circles.items()), 2):
            distance = math.hypot(a[0] - b[0], a[1] - b[1])
            if distance >= a[2] + b[2]:
                issues.append(
                    SldV2LayoutIssue(
                        issue_id=f"winding_circles_detached:{id_a}:{id_b}",
                        severity="error",
                        message=(
                            f"transformer winding circles {id_a} and {id_b} do not interlock "
                            f"(centre distance {distance:.1f} >= {a[2] + b[2]:.1f})"
                        ),
                    )
                )

    return issues


def assert_sld_engineering_v2_layout_acceptance(plan: SldV2LayoutPlan) -> None:
    issues = [issue for issue in validate_sld_engineering_v2_layout(plan) if issue.severity == "error"]
    if issues:
        summary = "; ".join(f"{issue.issue_id}: {issue.message}" for issue in issues)
        raise ValueError(f"engineering_v2 layout acceptance failed: {summary}")
