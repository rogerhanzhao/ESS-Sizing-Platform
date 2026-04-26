from __future__ import annotations

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


def assert_sld_engineering_v2_layout_acceptance(plan: SldV2LayoutPlan) -> None:
    issues = [issue for issue in validate_sld_engineering_v2_layout(plan) if issue.severity == "error"]
    if issues:
        summary = "; ".join(f"{issue.issue_id}: {issue.message}" for issue in issues)
        raise ValueError(f"engineering_v2 layout acceptance failed: {summary}")
