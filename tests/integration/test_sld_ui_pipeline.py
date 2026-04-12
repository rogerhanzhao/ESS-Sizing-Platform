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

    def _fake_pipeline(bundle, *, ac_snapshot, options, plugin_id, actor):
        calls["bundle"] = bundle
        calls["ac_snapshot"] = ac_snapshot
        calls["options"] = options
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
    assert calls["plugin_id"] == "sld_engineering_v1"
    assert calls["actor"] == "tester"


def test_sld_ui_module_does_not_own_core_builder_logic():
    source = inspect.getsource(single_line_diagram_view)
    assert "run_sld_pipeline_from_run_bundle" in source
    assert "build_sld_canonical_input" not in source
    assert "build_sld_topology" not in source
    assert "render_sld_svg" not in source
    assert "build_sld_group_spec" not in source
