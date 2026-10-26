"""A current DC form choice cannot claim a saved report's historical source."""
import pytest
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.services.ac_run_service import persist_ac_run
from tests.test_report_export_requires_the_figures import (
    _ac_output, _download_offered, session_with_a_finished_run,
)


def test_saved_report_library_source_does_not_follow_current_form_radio(session_with_a_finished_run):
    open_export, run_id = session_with_a_finished_run
    alternative = persist_ac_run(
        dc_run_id=run_id,
        ac_inputs={'grid_kv': 33.0, 'mv_kv': 33.0, 'lv_voltage_v': 800.0},
        ac_output=_ac_output(run_id),
    )
    assert alternative is not None
    page = open_export(active_ac_run_id=alternative.run_id)
    expected = ('DC Block Library: Not recorded in this saved run. '
                'Refer to the saved DC Block configuration.')
    for current_form_source in ('Excel reference library', 'Admin product library'):
        page.session_state['dc_block_source'] = current_form_source
        page = page.run()
        assert not page.exception
        messages = [str(item.value) for item in page.info]
        assert expected in messages
        assert not any(message.startswith('DC Block Library:') and message != expected
                       for message in messages)
        assert page.session_state['active_run_id'] == run_id
        assert page.session_state['active_ac_run_id'] == alternative.run_id
        assert _download_offered(page)


def _ac_source_reference_page(source, recorded_id, selected_id, has_snapshot):
    from calb_sizing_tool.schemas.diagram_inputs import AcSnapshot
    from calb_sizing_tool.services.sld_data_source_service import AcSnapshotResolution
    from calb_sizing_tool.ui.report_export_view import _render_ac_source_reference

    snapshot = AcSnapshot(inputs={}, output={'source_ac_run_id': recorded_id}, results={}) if has_snapshot else None
    _render_ac_source_reference(
        AcSnapshotResolution(snapshot=snapshot, source=source),
        dc_run_id='dc-parent', selected_ac_run_id=selected_id,
    )


@pytest.mark.parametrize('source,recorded_id,selected_id,has_snapshot,kind,message,label_expected', [
    ('persisted_ac_alternative', 'selected-child', 'selected-child', True, 'success',
     'AC data source: saved AC Alternative B.', True),
    ('persisted_ac_alternative', 'legacy-ac-reference', 'selected-child', True, 'success',
     'AC data source: saved AC Alternative B.', True),
    ('persisted_ac_alternative', None, 'selected-child', True, 'success',
     'AC data source: saved AC Alternative B.', True),
    ('persisted_run_snapshot', 'legacy-ac-reference', 'selected-child', True, 'success',
     'AC data source: saved AC configuration attached to this DC run.', False),
    ('compatibility_adapter', 'legacy-ac-reference', 'selected-child', True, 'info',
     'AC data source: current session configuration.', False),
    ('session_cache', 'legacy-ac-reference', 'selected-child', True, 'info',
     'AC data source: current session configuration.', False),
    ('none', None, 'selected-child', False, 'warning',
     'No AC configuration is available for this report.', False),
])
def test_report_source_reference_follows_resolved_source(
        monkeypatch, source, recorded_id, selected_id, has_snapshot, kind, message, label_expected):
    from calb_sizing_tool.services import ac_run_service

    calls = []

    def canonical_label(parent_id, child_id):
        calls.append((parent_id, child_id))
        return 'B'

    monkeypatch.setattr(ac_run_service, 'ac_alternative_label', canonical_label)
    page = AppTest.from_function(
        _ac_source_reference_page,
        args=(source, recorded_id, selected_id, has_snapshot), default_timeout=30,
    ).run()
    assert not page.exception
    assert any(message in str(item.value) for item in getattr(page, kind))
    assert calls == ([('dc-parent', 'selected-child')] if label_expected else [])
    if source in {'compatibility_adapter', 'session_cache'}:
        assert any('save status is not confirmed' in str(item.value) for item in page.info)
        assert not page.success
    assert any(item.label == 'Technical identifiers' and not item.proto.expanded for item in page.expander)
    captions = '\n'.join(str(item.value) for item in page.caption)
    assert 'DC Run ID: `dc-parent`' in captions
    if recorded_id:
        assert f'Recorded AC reference ID: `{recorded_id}`' in captions
    assert ('Selected AC alternative ID:' in captions) is (source == 'persisted_ac_alternative')
