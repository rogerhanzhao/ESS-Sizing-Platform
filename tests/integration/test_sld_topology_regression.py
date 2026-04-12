from __future__ import annotations

import json
from pathlib import Path

from calb_sizing_tool.services.sld_pipeline_service import normalize_sld_topology, prepare_sld_pipeline_from_run_bundle
from tests.integration.sld_regression_support import build_case_inputs, load_case_definition


CASE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "sld_cases" / "case01_container_only_group1"


def test_sld_topology_regression():
    case_definition = load_case_definition(CASE_DIR)
    baseline = json.loads((CASE_DIR / "topology_baseline.json").read_text(encoding="utf-8"))
    run_bundle, ac_snapshot, options, project_settings = build_case_inputs(case_definition)

    prepared_a = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    prepared_b = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )

    normalized_a = normalize_sld_topology(prepared_a.topology)
    normalized_b = normalize_sld_topology(prepared_b.topology)

    assert normalized_a == normalized_b
    assert normalized_a == baseline
    assert normalized_a["summary"]["feeder_count"] == 4
    assert normalized_a["summary"]["pcs_count"] == 4
    assert normalized_a["summary"]["dc_blocks_per_feeder"] == [1, 1, 1, 1]
