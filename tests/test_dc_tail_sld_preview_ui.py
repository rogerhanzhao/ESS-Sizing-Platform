"""Original AC Next -> SLD page: a preview cannot become a formal artifact."""
from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.infra.db.models import RunOutputSnapshot, SizingRun, ArtifactRegistry
from tests.test_dc_page_run_smoke import signed_in_workspace, _state
from tests.test_dc_tail_runtime_ui import authorized_tail_workspace
from tests.test_dc_tail_ac_original_ui import _dc_run, _open_ac, _run_ac, _forbid_stage3, _saved_ac


def _counts():
    with session_scope() as session:
        return tuple(session.query(model).count()
                     for model in (SizingRun, RunOutputSnapshot, ArtifactRegistry))


@pytest.mark.parametrize('strings,ratio,drawn', [(10, '1:2', True), (8, '1:2', True),
                                                (8, '1:1', True), (10, '1:1', False)])
def test_original_next_shows_only_scoped_comparison_and_keeps_standard_flow(
        authorized_tail_workspace, monkeypatch, strings, ratio, drawn):
    from calb_sizing_tool.ui import single_line_diagram_view as view

    app, _ = authorized_tail_workspace
    sized = _dc_run(app, strings)
    page = _run_ac(_open_ac(sized, monkeypatch, ratio))
    original_ac = _saved_ac(page)
    original_dc = deepcopy(_state(page, 'dc_result_summary'))
    before = _counts()
    _forbid_stage3(monkeypatch)
    actual_image = view.st.image
    diagrams = []

    def capture_image(image, *args, **kwargs):
        if isinstance(image, str) and '<svg' in image:
            diagrams.append(image)
        return actual_image(image, *args, **kwargs)

    monkeypatch.setattr(view.st, 'image', capture_image)
    next(button for button in page.button if button.label == 'Single Line Diagram →').click()
    page = page.run()
    assert not page.exception
    assert _state(page, 'main_nav') == 'Single Line Diagram'
    assert any(item.label == 'Advanced: Reduced-string tail SLD preview' for item in page.expander)
    assert any(button.label == 'Generate SLD' and not button.disabled for button in page.button)
    assert any(button.label == 'Typical AC Block Arrangement →' for button in page.button)
    assert _state(page, 'dc_result_summary') == original_dc
    assert _saved_ac(page) == original_ac
    assert _counts() == before
    assert not _state(page, 'sld_artifacts')
    assert not _state(page, 'sld_pipeline_meta')
    assert bool(diagrams) is drawn
    if drawn:
        assert f'{strings}-string' in diagrams[-1]
        assert 'NOT FOR CONSTRUCTION' in diagrams[-1].upper()
        assert any('not saved as a standard SLD' in str(item.value) for item in page.caption)
        if strings == 8:
            assert 'TBC' in diagrams[-1]
    else:
        assert any('cannot be drawn' in str(item.value) for item in page.warning)


def _hidden_preview_page():
    import streamlit as st
    from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
    from calb_sizing_tool.services.sld_data_source_service import AcSnapshotResolution
    from calb_sizing_tool.ui.single_line_diagram_view import _render_tail_comparison_preview

    _render_tail_comparison_preview(
        AcSnapshotResolution(snapshot=AcSnapshot(output=st.session_state['test_output']),
                             source=st.session_state['test_source']),
        workspace={}, run_id='dc', auth_user=None,
        is_guest=st.session_state['test_guest'],
    )


@pytest.mark.parametrize('guest,source,output', [
    (True, 'persisted_ac_alternative', {'reduced_string_tail_ac_review': {'present': True}}),
    (False, 'session_cache', {'reduced_string_tail_ac_review': {'present': True}}),
    (False, 'persisted_ac_alternative', {'standard': True}),
])
def test_guest_session_or_standard_does_not_read_new_preview(monkeypatch, guest, source, output):
    from calb_sizing_tool.services import dc_tail_preview_source_service as service

    def forbidden(**kwargs):
        raise AssertionError('This original path must not read the optional tail source')

    monkeypatch.setattr(service, 'load_saved_tail_sld_preview', forbidden)
    app = AppTest.from_function(_hidden_preview_page)
    app.session_state['test_guest'] = guest
    app.session_state['test_source'] = source
    app.session_state['test_output'] = output
    app = app.run()
    assert not app.exception
    assert not app.expander
