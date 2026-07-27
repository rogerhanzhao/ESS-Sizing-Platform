from pathlib import Path

from calb_sizing_tool.services import sld_pipeline_service
from calb_sizing_tool.services.sld_pipeline_service import run_sld_pipeline_from_run_bundle
from tests.integration.sld_regression_support import build_case_inputs, load_case_definition


def test_session_preview_does_not_register_artifacts(monkeypatch):
    case_dir = Path(__file__).resolve().parents[1] / "fixtures" / "sld_cases" / "case01_container_only_group1"
    run_bundle, ac_snapshot, options, project_settings = build_case_inputs(load_case_definition(case_dir))

    def _unexpected_registration(**_kwargs):
        raise AssertionError("guest/session preview must not register artifacts")

    monkeypatch.setattr(sld_pipeline_service, "persist_artifacts", _unexpected_registration)

    execution = run_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options.model_copy(update={"override_mode": True}),
        project_settings=project_settings,
        actor="guest",
        register_artifacts=False,
    )

    assert execution.artifact_bundle.metadata["artifacts_registered"] is False
    assert any(item["artifact_kind"] == "sld_svg" for item in execution.artifact_bundle.artifacts)
