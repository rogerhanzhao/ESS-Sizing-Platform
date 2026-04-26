from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, SldRenderOptions
from calb_sizing_tool.schemas.run_bundle import DcRunBundle
from calb_sizing_tool.schemas.sld_render_input import SldCanonicalInput


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
        block_total = _safe_int(entry.get("dc_blocks_total"))
        if block_total is None:
            feeder_allocations = entry.get("feeder_allocations")
            if not isinstance(feeder_allocations, list):
                return None
            parsed = [_safe_int(item) for item in feeder_allocations]
            if not all(item is not None and item >= 0 for item in parsed):
                return None
            block_total = sum(int(item) for item in parsed if item is not None)
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
    block_total = _safe_int(entry.get("dc_blocks_total"))
    if block_total is not None:
        return block_total
    feeder_allocations = entry.get("feeder_allocations")
    if not isinstance(feeder_allocations, list):
        return None
    parsed = [_safe_int(item) for item in feeder_allocations]
    if not all(item is not None and item >= 0 for item in parsed):
        return None
    return sum(int(item) for item in parsed if item is not None)


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

    if canonical_input.validation_mode != "strict" or bool(canonical_input.override_mode):
        issues.append(
            _issue(
                "not_strict_formal_mode",
                "error",
                "Formal SLD requires strict validation mode without engineering override mode.",
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
    elif dc_run_blocks_total != ac_blocks_total:
        issues.append(
            _issue(
                "dc_ac_block_total_mismatch",
                "error",
                f"DC run has {dc_run_blocks_total} DC Blocks, but AC allocation carries {ac_blocks_total}.",
            )
        )

    ac_group_total = _ac_group_total(ac_snapshot, canonical_input.group_index)
    if ac_group_total is not None and ac_group_total != canonical_input.dc_blocks_total_in_group:
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

    if dc_run_mwh is not None and ac_blocks_total is not None:
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
