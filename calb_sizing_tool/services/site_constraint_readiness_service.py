from __future__ import annotations

from copy import deepcopy
from typing import Any


SITE_CONSTRAINT_SCHEMA_VERSION = "site_constraint_set.v1"


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _point_present(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    return all(_number(component) is not None for component in value)


def _polygon_present(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 3:
        return False
    return all(_point_present(point) for point in value)


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def build_site_constraint_template(
    *,
    run_id: str | None,
    project_context: dict[str, Any] | None,
    ac_output: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create a neutral project input template for a future master layout.

    All geometry and project-rule fields intentionally begin empty. The sizing
    model only seeds traceability and electrical quantities it already knows;
    it never invents a boundary, road, clearance or POI location.
    """
    project_context = dict(project_context or {})
    ac_output = dict(ac_output or {})
    return {
        "schema_version": SITE_CONSTRAINT_SCHEMA_VERSION,
        "status": "draft_template",
        "source_run": {
            "run_id": str(run_id or "").strip() or None,
            "project_code": project_context.get("project_code"),
            "project_name": project_context.get("project_name"),
            "case_code": project_context.get("case_code"),
            "case_name": project_context.get("case_name"),
        },
        "sizing_reference": {
            "ac_block_count": ac_output.get("num_blocks"),
            "poi_power_mw": ac_output.get("poi_power_mw"),
            "poi_energy_mwh": ac_output.get("poi_energy_mwh"),
            "mv_voltage_kv": ac_output.get("mv_voltage_kv") or ac_output.get("grid_kv"),
        },
        "coordinate_system": {"crs": None, "north_reference": None},
        "site_boundary": {"geometry_type": "Polygon", "coordinates": []},
        "poi_interface": {"location": None, "description": None},
        "access_and_egress": {"routes": []},
        "safety_maintenance": {"fire_egress_constraints": []},
        "equipment_footprints": {"catalog_reference": None, "items": []},
        "utility_corridors": {"mv_collection_path": []},
        "project_rules": {"clearance_rule_basis": None},
        "by_others": {"scope_interfaces": []},
    }


def assess_site_constraint_readiness(constraint_set: dict[str, Any] | None) -> dict[str, Any]:
    """Assess prerequisite completeness for a deterministic master layout.

    This validates presence and basic geometry shape only. It does not validate
    site codes, determine fire clearances or certify a final site plan.
    """
    payload = deepcopy(constraint_set) if isinstance(constraint_set, dict) else {}
    coordinate_system = payload.get("coordinate_system") if isinstance(payload.get("coordinate_system"), dict) else {}
    site_boundary = payload.get("site_boundary") if isinstance(payload.get("site_boundary"), dict) else {}
    poi_interface = payload.get("poi_interface") if isinstance(payload.get("poi_interface"), dict) else {}
    access = payload.get("access_and_egress") if isinstance(payload.get("access_and_egress"), dict) else {}
    safety = payload.get("safety_maintenance") if isinstance(payload.get("safety_maintenance"), dict) else {}
    footprints = payload.get("equipment_footprints") if isinstance(payload.get("equipment_footprints"), dict) else {}
    corridors = payload.get("utility_corridors") if isinstance(payload.get("utility_corridors"), dict) else {}
    project_rules = payload.get("project_rules") if isinstance(payload.get("project_rules"), dict) else {}
    by_others = payload.get("by_others") if isinstance(payload.get("by_others"), dict) else {}

    checks = [
        (
            "coordinate_reference",
            "Coordinate reference",
            _text_present(coordinate_system.get("crs")) and _text_present(coordinate_system.get("north_reference")),
            "Provide CRS and north reference.",
        ),
        (
            "site_boundary",
            "Site boundary",
            _polygon_present(site_boundary.get("coordinates")),
            "Provide a site-boundary polygon with at least three coordinate points.",
        ),
        (
            "poi_location",
            "POI / interconnection location",
            _point_present(poi_interface.get("location")),
            "Provide the POI or interconnection point location.",
        ),
        (
            "access_routes",
            "Access and egress routes",
            _non_empty_list(access.get("routes")),
            "Provide access, construction and emergency route constraints.",
        ),
        (
            "fire_maintenance",
            "Fire and maintenance constraints",
            _non_empty_list(safety.get("fire_egress_constraints")),
            "Provide project-specific fire, egress and maintenance constraints.",
        ),
        (
            "equipment_footprints",
            "Equipment footprint catalogue",
            _text_present(footprints.get("catalog_reference")) and _non_empty_list(footprints.get("items")),
            "Provide a controlled equipment footprint catalogue and reference.",
        ),
        (
            "mv_corridor",
            "MV collection corridor",
            _non_empty_list(corridors.get("mv_collection_path")),
            "Provide the MV collection corridor or routing constraint.",
        ),
        (
            "rule_basis",
            "Project rule basis",
            _text_present(project_rules.get("clearance_rule_basis")),
            "Provide the applicable project, authority or technical-agreement rule basis.",
        ),
        (
            "by_others_interfaces",
            "By-others interfaces",
            _non_empty_list(by_others.get("scope_interfaces")),
            "Provide by-others zones and interface points.",
        ),
    ]
    items = [
        {
            "check_id": check_id,
            "label": label,
            "status": "provided" if passed else "required",
            "message": "Provided for readiness assessment." if passed else message,
        }
        for check_id, label, passed, message in checks
    ]
    provided_count = sum(item["status"] == "provided" for item in items)
    return {
        "schema_version": SITE_CONSTRAINT_SCHEMA_VERSION,
        "ready": provided_count == len(items),
        "provided_count": provided_count,
        "required_count": len(items),
        "items": items,
        "master_layout_status": (
            "ready_for_constraint_validation"
            if provided_count == len(items)
            else "blocked_by_missing_site_constraints"
        ),
        "scope_note": (
            "This readiness assessment confirms input presence only. It does not validate code compliance, "
            "geometry collisions, construction access or final engineering design."
        ),
    }
