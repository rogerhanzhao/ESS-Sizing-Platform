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
    run_bundle, ac_snapshot, options = build_case_inputs(case_definition)

    prepared_a = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
    )
    prepared_b = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
    )

    normalized_a = normalize_sld_render_output(render_prepared_sld_pipeline(prepared_a))
    normalized_b = normalize_sld_render_output(render_prepared_sld_pipeline(prepared_b))

    assert normalized_a == normalized_b
    assert normalized_a == baseline
