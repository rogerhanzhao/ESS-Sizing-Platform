from __future__ import annotations

import pytest

from calb_sizing_tool.services.site_constraint_readiness_service import (
    SITE_CONSTRAINT_SCHEMA_VERSION,
    assess_site_constraint_readiness,
    build_site_constraint_template,
)
from calb_sizing_tool.services.site_constraint_set_service import register_site_constraint_set


def _template() -> dict:
    return build_site_constraint_template(
        run_id="run-001",
        project_context={"project_name": "Constraint Test", "case_name": "Base"},
        ac_output={"num_blocks": 4, "poi_power_mw": 100.0, "mv_voltage_kv": 33.0},
    )


def test_default_site_constraint_template_is_not_master_layout_ready():
    template = _template()

    assessment = assess_site_constraint_readiness(template)

    assert template["schema_version"] == SITE_CONSTRAINT_SCHEMA_VERSION
    assert assessment["ready"] is False
    assert assessment["provided_count"] == 0
    assert assessment["required_count"] == 9
    assert assessment["master_layout_status"] == "blocked_by_missing_site_constraints"


def test_complete_site_constraint_set_is_ready_for_next_validation_phase():
    template = _template()
    template["coordinate_system"] = {"crs": "EPSG:3857", "north_reference": "Grid north"}
    template["site_boundary"]["coordinates"] = [[0, 0], [100, 0], [100, 100], [0, 100]]
    template["poi_interface"]["location"] = [95, 50]
    template["access_and_egress"]["routes"] = [{"name": "main access", "geometry": [[0, 10], [100, 10]]}]
    template["safety_maintenance"]["fire_egress_constraints"] = [{"source": "project fire strategy"}]
    template["equipment_footprints"] = {"catalog_reference": "equipment_catalog_v1", "items": [{"id": "bess"}]}
    template["utility_corridors"]["mv_collection_path"] = [[95, 50], [80, 50]]
    template["project_rules"]["clearance_rule_basis"] = "Approved technical agreement"
    template["by_others"]["scope_interfaces"] = [{"name": "POI bay"}]

    assessment = assess_site_constraint_readiness(template)

    assert assessment["ready"] is True
    assert assessment["provided_count"] == assessment["required_count"] == 9
    assert assessment["master_layout_status"] == "ready_for_constraint_validation"


def test_register_rejects_constraint_set_declared_for_another_run():
    template = _template()

    with pytest.raises(ValueError, match="source_run.run_id"):
        register_site_constraint_set(
            run_id="run-002",
            constraint_set=template,
            actor="tester",
        )
