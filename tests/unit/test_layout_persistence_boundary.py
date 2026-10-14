from types import SimpleNamespace

import pytest

from calb_sizing_tool.services import layout_service
from calb_sizing_tool.schemas.layout_inputs import LayoutRenderOptions


@pytest.mark.parametrize("persist", [False, True])
def test_layout_preview_only_persists_when_requested(monkeypatch, persist):
    artifact = SimpleNamespace(filename="preview.svg", content=b"<svg/>")
    plugin = SimpleNamespace(
        metadata=SimpleNamespace(plugin_id="layout_arrangement_v2", plugin_version="2"),
        build_input_from_run=lambda **kwargs: kwargs,
        validate_input=lambda value: [],
        render=lambda value: value,
        emit_artifact=lambda value: [artifact],
        metadata_payload=lambda *args: {"document_status": "CONCEPT ONLY"},
    )
    monkeypatch.setattr(layout_service, "get_plugin_registry", lambda: {"layout_arrangement_v2": plugin})
    writes = []
    monkeypatch.setattr(layout_service, "persist_artifacts", lambda **kwargs: writes.append(kwargs))
    result = layout_service.render_layout_from_run_bundle(
        SimpleNamespace(run_id="session-only-run"),
        ac_snapshot=SimpleNamespace(), options=LayoutRenderOptions(),
        artifact_run_id="saved-ac-alternative", persist=persist,
    )
    assert result.artifacts[0]["content"] == b"<svg/>"
    assert result.metadata["document_status"] == "CONCEPT ONLY"
    assert len(writes) == int(persist)
    if persist:
        assert writes[0]["run_id"] == "saved-ac-alternative"
