from __future__ import annotations

import json
from pathlib import Path

from calb_sizing_tool.services.sld_pipeline_service import (
    normalize_sld_render_output,
    prepare_sld_pipeline_from_run_bundle,
    render_prepared_sld_pipeline,
)
from tests.integration.sld_regression_support import build_case_inputs, load_case_definition


CASE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "sld_cases" / "case01_container_only_group1"


def test_sld_render_regression():
    case_definition = load_case_definition(CASE_DIR)
    baseline = json.loads((CASE_DIR / "render_baseline.json").read_text(encoding="utf-8"))
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

    normalized_a = normalize_sld_render_output(render_prepared_sld_pipeline(prepared_a))
    normalized_b = normalize_sld_render_output(render_prepared_sld_pipeline(prepared_b))

    assert normalized_a == normalized_b
    assert normalized_a == baseline
    assert normalized_a["metadata"]["validation_mode"] == "strict"
    assert normalized_a["metadata"]["artifact_mode"] == "official"
    assert normalized_a["metadata"]["input_hash"]
    assert normalized_a["metadata"]["topology_hash"]
    assert normalized_a["metadata"]["render_spec_hash"]
    assert normalized_a["spec"]["pcs_count"] == 4
    assert normalized_a["spec"]["dc_blocks_per_feeder"] == [1, 1, 1, 1]
    text_nodes = normalized_a["svg"]["text_nodes"]
    assert "PCS & MVT SKID (AC BLOCK)" in text_nodes
    assert "RMU-01 / MV Switchgear" in text_nodes
    assert "Ring In" in text_nodes
    assert "Transformer Feeder" in text_nodes
    assert "Ring Out" in text_nodes
    assert "INV-01" in text_nodes
    assert "BESS-01" in text_nodes  # battery bank identified by per-block tags
    assert "T-01" in text_nodes
    assert any("SINGLE LINE DIAGRAM" in t for t in text_nodes)
    assert "TBD" not in text_nodes
    assert "DC BUSBAR" not in text_nodes
    assert "MV BUS" not in text_nodes
