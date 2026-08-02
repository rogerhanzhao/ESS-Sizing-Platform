from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_render_input import SldCanonicalInput
from calb_sizing_tool.sld.transformer_vector_group import (
    TransformerVectorGroupError,
    parse_transformer_vector_group,
)


@dataclass(frozen=True)
class SldFormalReadinessIssue:
    issue_id: str
    severity: str
    message: str


@dataclass(frozen=True)
class SldFormalReadinessReport:
    ready: bool
    error_count: int
    warning_count: int
    issues: tuple[SldFormalReadinessIssue, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _missing_text(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text.lower() in {"tbd", "n/a", "na", "none"}


def _issue(issue_id: str, severity: str, message: str) -> SldFormalReadinessIssue:
    return SldFormalReadinessIssue(issue_id=issue_id, severity=severity, message=message)


def _entry_dc_block_total(entry: dict) -> int | None:
    """DC Block count for one AC-Block allocation entry.

    ``feeder_allocations`` counts DC Blocks *per feeder*, so a DC Block shared
    across N feeders appears N times — summing it double-counts shared blocks
    (2 shared blocks over 4 feeders would read as 4). Prefer the explicit total,
    then the distinct blocks in the connection plan, and only fall back to the
    feeder sum when no block is shared.
    """
    block_total = _safe_int(entry.get("dc_blocks_total"))
    if block_total is not None:
        return block_total

    connections = entry.get("dc_block_connections")
    if isinstance(connections, list) and connections:
        block_indices = {
            _safe_int(connection.get("dc_block_index"))
            for connection in connections
            if isinstance(connection, dict)
        }
        block_indices.discard(None)
        if block_indices:
            return len(block_indices)

    feeder_allocations = entry.get("feeder_allocations")
    if not isinstance(feeder_allocations, list):
        return None
    parsed = [_safe_int(item) for item in feeder_allocations]
    if not all(item is not None and item >= 0 for item in parsed):
        return None
    return sum(int(item) for item in parsed if item is not None)


def _ac_allocation_total(ac_snapshot: AcSnapshot) -> int | None:
    direct = _safe_int(ac_snapshot.output.get("dc_blocks_total"))
    if direct is not None:
        return direct
    plan = ac_snapshot.output.get("dc_allocation_plan")
    if not isinstance(plan, list) or not plan:
        return None
    total = 0
    for entry in plan:
        if not isinstance(entry, dict):
            return None
        block_total = _entry_dc_block_total(entry)
        if block_total is None:
            return None
        total += int(block_total)
    return total


def _ac_group_total(ac_snapshot: AcSnapshot, group_index: int) -> int | None:
    plan = ac_snapshot.output.get("dc_allocation_plan")
    if not isinstance(plan, list) or not plan:
        return None
    zero_based = max(0, int(group_index) - 1)
    if zero_based >= len(plan):
        return None
    entry = plan[zero_based]
    if not isinstance(entry, dict):
        return None
    return _entry_dc_block_total(entry)


def assess_sld_formal_readiness(
    *,
    run_bundle: DcRunBundle,
    ac_snapshot: AcSnapshot,
    canonical_input: SldCanonicalInput,
    options: SldRenderOptions,
    project_settings: dict[str, Any] | None = None,
) -> SldFormalReadinessReport:
    """Assess whether a prepared SLD can be treated as a formal drawing.

    This service validates cross-source consistency only. It must not calculate
    DC sizing, AC sizing, or renderer topology.
    """
    issues: list[SldFormalReadinessIssue] = []
    project_settings = project_settings or {}

    # A mixed AC Block station cannot be drawn as one uniform SLD (SLD V1 is
    # uniform-only), so it is projected onto its representative Head AC-Block
    # fleet. That projection is a legitimate concept drawing but NEVER a formal
    # whole-station SLD — the tail AC Block model(s) are not on it. Mark it
    # non-official explicitly, so the drawing is watermarked CONCEPT for this
    # honest reason rather than the incidental head-vs-whole DC-total mismatch.
    is_representative_of_mixed = bool(ac_snapshot.output.get("sld_representative_of_mixed"))
    if is_representative_of_mixed:
        issues.append(
            _issue(
                "representative_head_fleet_only",
                "error",
                "This SLD is the representative Head AC-Block fleet of a mixed AC Block "
                "station, not a full-site drawing. Tail AC Block model(s) are described in "
                "the report AC Block schedule; a per-model mixed SLD is required "
                "for a formal whole-station SLD.",
            )
        )

    if canonical_input.validation_mode != "strict" or bool(canonical_input.override_mode):
        issues.append(
            _issue(
                "not_strict_formal_mode",
                "error",
                "Formal SLD requires strict validation mode without engineering override mode.",
            )
        )

    # A transformer is defined by a vector group that declares one LV token per
    # independent LV winding (e.g. Dyn11 for two-winding, Dyn11yn11 / Dy11y11 for
    # a three-winding with two independent LV secondaries). The canonical input
    # already resolves the authoritative value (from the AC output or case
    # engineering settings) and normalizes an unconfirmed value to "TBD". A "TBD"
    # winding symbol is not a readable engineering drawing, so it can never be a
    # formal SLD — this keeps a three-winding station out of official output
    # until a real dual-LV vector group is confirmed.
    lv_winding_count = int(canonical_input.lv_winding_count or 1)
    vector_group_raw = str(canonical_input.transformer_vector_group or "").strip()
    if _missing_text(vector_group_raw):
        issues.append(
            _issue(
                "transformer_vector_group_unconfirmed",
                "error",
                f"Formal SLD requires a confirmed transformer vector group with "
                f"{lv_winding_count} LV token(s); none is set (TBD).",
            )
        )
    else:
        try:
            parse_transformer_vector_group(vector_group_raw, lv_winding_count=lv_winding_count)
        except TransformerVectorGroupError as exc:
            issues.append(
                _issue(
                    "transformer_vector_group_topology_mismatch",
                    "error",
                    f"Transformer vector group {vector_group_raw!r} does not match a "
                    f"{lv_winding_count}-LV-winding transformer: {exc}",
                )
            )

    # A syntactically valid vector group is still not formal if it is an assumed
    # standard default (filled because the OEM datasheet stated none). The
    # ``*_basis`` marker travels from the product catalogue on the AC output;
    # ``standard_default_pending_confirmation`` must be confirmed by the owner/OEM
    # before it can back a formal SLD.
    vector_group_basis = str(ac_snapshot.output.get("transformer_vector_group_basis") or "").strip()
    if vector_group_basis == "standard_default_pending_confirmation":
        issues.append(
            _issue(
                "transformer_vector_group_assumed_default",
                "error",
                "Transformer vector group is an assumed standard default "
                "(pending OEM/owner confirmation) and cannot back a formal SLD.",
            )
        )

    run_id = str(run_bundle.run_id or "").strip()
    source_run_id = str(ac_snapshot.output.get("source_run_id") or "").strip()
    if not source_run_id:
        issues.append(
            _issue(
                "missing_ac_snapshot_provenance",
                "error",
                "AC runtime snapshot is missing source_run_id and cannot be treated as formal.",
            )
        )
    elif run_id and source_run_id != run_id:
        issues.append(
            _issue(
                "ac_snapshot_run_mismatch",
                "error",
                f"AC runtime snapshot belongs to run {source_run_id}, not active run {run_id}.",
            )
        )

    dc_run_blocks_total = int(run_bundle.snapshot.stage2.container_count + run_bundle.snapshot.stage2.cabinet_count)
    ac_blocks_total = _ac_allocation_total(ac_snapshot)
    if ac_blocks_total is None:
        issues.append(
            _issue(
                "missing_ac_dc_allocation_total",
                "error",
                "AC allocation total DC Block count is unavailable.",
            )
        )
    elif dc_run_blocks_total != ac_blocks_total and not is_representative_of_mixed:
        # For a representative Head fleet the head-only DC total is expected to be
        # smaller than the whole DC run; the explicit representative blocker above
        # already keeps the drawing non-official, so this incidental mismatch is
        # suppressed to avoid a misleading "data error" reason.
        issues.append(
            _issue(
                "dc_ac_block_total_mismatch",
                "error",
                f"DC run has {dc_run_blocks_total} DC Blocks, but AC allocation carries {ac_blocks_total}.",
            )
        )

    ac_group_total = _ac_group_total(ac_snapshot, canonical_input.group_index)
    _allocation_plan = ac_snapshot.output.get("dc_allocation_plan")
    _has_allocation_plan = isinstance(_allocation_plan, list) and bool(_allocation_plan)
    if ac_group_total is None:
        # FAIL CLOSED: an unresolvable group must not silently skip the check.
        # The drawn group index can point past the end of the AC allocation (e.g.
        # SLD group 3 while the allocation has 2 AC Blocks), which would otherwise
        # let a formal SLD be issued for an AC Block that does not exist.
        if _has_allocation_plan:
            issues.append(
                _issue(
                    "sld_group_not_in_ac_allocation",
                    "error",
                    f"SLD group {canonical_input.group_index} cannot be resolved in the AC "
                    f"allocation plan ({len(_allocation_plan)} AC Block group(s)); the drawn "
                    f"group must exist in the AC allocation.",
                )
            )
    elif ac_group_total != canonical_input.dc_blocks_total_in_group:
        issues.append(
            _issue(
                "sld_group_allocation_mismatch",
                "error",
                f"SLD group carries {canonical_input.dc_blocks_total_in_group} DC Blocks, "
                f"but AC allocation group {canonical_input.group_index} carries {ac_group_total}.",
            )
        )

    dc_run_mwh = _safe_float(run_bundle.snapshot.stage2.dc_nameplate_bol_mwh)
    ac_total_mwh = _safe_float(ac_snapshot.output.get("dc_total_mwh"))
    if dc_run_mwh is not None and ac_total_mwh is not None and abs(dc_run_mwh - ac_total_mwh) > 0.01:
        issues.append(
            _issue(
                "dc_ac_energy_total_mismatch",
                "error",
                f"DC run nameplate is {dc_run_mwh:.3f} MWh, but AC snapshot carries {ac_total_mwh:.3f} MWh.",
            )
        )

    if dc_run_mwh is not None and ac_blocks_total is not None and not is_representative_of_mixed:
        represented_mwh = float(canonical_input.dc_block_energy_mwh) * float(ac_blocks_total)
        if abs(represented_mwh - dc_run_mwh) > max(0.01, dc_run_mwh * 0.001):
            issues.append(
                _issue(
                    "sld_dc_energy_representation_mismatch",
                    "error",
                    f"SLD DC Block energy represents {represented_mwh:.3f} MWh across AC allocation, "
                    f"but DC run nameplate is {dc_run_mwh:.3f} MWh.",
                )
            )

    ratings = canonical_input.equipment_ratings
    professional_fields = {
        "mv_cable_spec": ratings.cables.mv_cable_spec,
        "lv_cable_spec": ratings.cables.lv_cable_spec,
        "dc_cable_spec": ratings.cables.dc_cable_spec,
        "battery_cell_spec": ratings.battery_cell_spec,
    }
    for field_name, value in professional_fields.items():
        if _missing_text(value):
            issues.append(
                _issue(
                    f"missing_professional_field:{field_name}",
                    "error",
                    f"Formal professional SLD requires explicit {field_name}.",
                )
            )

    if not isinstance(project_settings.get("equipment_ratings"), dict):
        issues.append(
            _issue(
                "missing_persisted_project_settings",
                "warning",
                "Case-level SLD engineering settings were not passed to the formal readiness check.",
            )
        )

    if str(options.renderer_mode or "").strip() != "engineering_v2":
        issues.append(
            _issue(
                "non_professional_renderer_mode",
                "warning",
                "Current renderer mode is not engineering_v2 professional template candidate.",
            )
        )

    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return SldFormalReadinessReport(
        ready=not errors,
        error_count=len(errors),
        warning_count=len(warnings),
        issues=tuple(issues),
    )
