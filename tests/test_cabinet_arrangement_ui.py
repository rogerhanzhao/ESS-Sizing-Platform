from streamlit.testing.v1 import AppTest


def _guest():
    import streamlit as st
    from tests.test_cabinet_sld_renderer import cabinet_output
    from calb_sizing_tool.ui.cabinet_arrangement_view import show_cabinet_arrangement
    output = cabinet_output()
    output['grid_kv'] = st.session_state.get('test_grid', 33)
    show_cabinet_arrangement(output, parent_run_id='guest', workspace={}, is_guest=True,
        auth_user=None, authoritative=False)


def test_guest_switches_arrangement_without_writes_and_input_change_clears_it(monkeypatch):
    page = AppTest.from_function(_guest, default_timeout=60).run()
    next(b for b in page.button if b.label == 'Generate Cabinet Arrangement').click()
    page = page.run()
    assert not page.exception and len(page.get('download_button')) == 4
    from calb_sizing_tool.services import cabinet_arrangement_service as service
    def forbidden(*args, **kwargs): raise AssertionError('Preview switch rendered or persisted')
    monkeypatch.setattr(service, 'generate_cabinet_arrangement', forbidden)
    monkeypatch.setattr(service, 'persist_artifacts', forbidden)
    next(s for s in page.selectbox if s.label == 'AC Block to preview').select(2)
    page = page.run()
    assert not page.exception and page.session_state['layout_artifacts'].metadata['selected_ac_block'] == 2
    assert len(page.get('download_button')) == 4
    page.session_state['test_grid'] = 34
    page = page.run()
    assert not page.exception and 'layout_artifacts' not in page.session_state
    assert not page.get('download_button')
    assert not any(b.label == 'Report Export →' for b in page.button)  # Existing registered-account boundary.
