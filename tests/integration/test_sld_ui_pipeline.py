from __future__ import annotations

import inspect
from types import SimpleNamespace

from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot, DiagramArtifactBundle, SldRenderOptions
from calb_sizing_tool.ui import single_line_diagram_view


def test_sld_ui_pipeline_delegates_to_pipeline_service(monkeypatch):
    calls = {}

    fake_result = SimpleNamespace(
        prepared=SimpleNamespace(
            validation_mode="draft",
            render_input=SimpleNamespace(canonical_input=SimpleNamespace(draft_warnings=["draft test"])),
            topology=SimpleNamespace(summary=SimpleNamespace(group_index=1), nodes=[1, 2], edges=[1]),
        ),
        artifact_bundle=DiagramArtifactBundle(
            plugin_id="sld_engineering_v1",
            plugin_version="1.0.0",
            run_id="run-1",
            metadata={},
            artifacts=[],
        ),
    )

    def _fake_pipeline(bundle, *, ac_snapshot, options, project_settings, plugin_id, actor):
        calls["bundle"] = bundle
        calls["ac_snapshot"] = ac_snapshot
        calls["options"] = options
        calls["project_settings"] = project_settings
        calls["plugin_id"] = plugin_id
        calls["actor"] = actor
        return fake_result

    monkeypatch.setattr(single_line_diagram_view, "run_sld_pipeline_from_run_bundle", _fake_pipeline)

    bundle = SimpleNamespace(run_id="run-1")
    ac_snapshot = AcSnapshot(inputs={}, output={"num_blocks": 1}, results={})
    options = SldRenderOptions(group_index=1, theme="dark")

    result = single_line_diagram_view._execute_sld_pipeline(
        bundle=bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        plugin_id="sld_engineering_v1",
        actor="tester",
    )

    assert result is fake_result
    assert calls["bundle"] is bundle
    assert calls["ac_snapshot"] is ac_snapshot
    assert calls["options"] == options
    assert calls["project_settings"] is None
    assert calls["plugin_id"] == "sld_engineering_v1"
    assert calls["actor"] == "tester"


def test_sld_ui_module_does_not_own_core_builder_logic():
    source = inspect.getsource(single_line_diagram_view)
    assert "run_sld_pipeline_from_run_bundle" in source
    assert "build_sld_canonical_input" not in source
    assert "build_sld_topology" not in source
    assert "render_sld_svg" not in source
    assert "build_sld_group_spec" not in source


def test_sld_ui_rejects_missing_ac_snapshot_provenance():
    message = single_line_diagram_view._validate_ac_snapshot_context(
        {"num_blocks": 1, "pcs_per_block": 2},
        expected_run_id="run-1",
    )

    assert "missing source_run_id provenance" in message


def test_sld_ui_rejects_ac_snapshot_from_different_run():
    message = single_line_diagram_view._validate_ac_snapshot_context(
        {
            "source_project_id": "project-1",
            "source_case_id": "case-1",
            "source_run_id": "run-old",
        },
        expected_run_id="run-new",
        expected_case_id="case-1",
        expected_project_id="project-1",
    )

    assert "run `run-old`" in message
    assert "run `run-new`" in message


def test_sld_ui_clears_cached_preview_when_render_controls_change(monkeypatch):
    session_state = {
        "sld_artifacts": {"artifact": "old"},
        "sld_pipeline_meta": {"run_id": "run-1"},
    }
    monkeypatch.setattr(single_line_diagram_view, "st", SimpleNamespace(session_state=session_state))

    first_signature = single_line_diagram_view._build_sld_preview_control_signature(
        run_id="run-1",
        group_index=1,
        theme="dark",
        compact_mode=False,
        draw_summary=False,
        renderer_mode="legacy_server",
        plugin_id="sld_engineering_v1",
    )
    changed_signature = single_line_diagram_view._build_sld_preview_control_signature(
        run_id="run-1",
        group_index=1,
        theme="light",
        compact_mode=False,
        draw_summary=False,
        renderer_mode="engineering_v2",
        plugin_id="sld_engineering_v1",
    )

    assert single_line_diagram_view._sync_sld_preview_control_signature(first_signature) is False
    assert "sld_artifacts" in session_state

    assert single_line_diagram_view._sync_sld_preview_control_signature(changed_signature) is True
    assert "sld_artifacts" not in session_state
    assert "sld_pipeline_meta" not in session_state
    assert session_state[single_line_diagram_view.SLD_PREVIEW_CONTROL_SIGNATURE_KEY] == changed_signature
