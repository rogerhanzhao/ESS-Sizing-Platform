from streamlit.testing.v1 import AppTest


def _guest_page():
    import streamlit as st
    from tests.test_cabinet_sld_renderer import cabinet_output
    from calb_sizing_tool.ui.cabinet_sld_view import show_cabinet_sld
    output = cabinet_output()
    output['grid_kv'] = st.session_state.get('test_grid_kv', 33)
    show_cabinet_sld(output,parent_run_id='guest',workspace={},is_guest=True,auth_user=None,authoritative=False)


def _registered_page():
    from types import SimpleNamespace
    from tests.test_cabinet_sld_renderer import cabinet_output
    from calb_sizing_tool.ui.cabinet_sld_view import show_cabinet_sld
    show_cabinet_sld(cabinet_output(),parent_run_id='dc',workspace={'ac_run_id':'ac'},is_guest=False,
                     auth_user=SimpleNamespace(username='review'),authoritative=True)


def test_guest_sheet_switch_reuses_all_sheets_without_regeneration(monkeypatch):
    page=AppTest.from_function(_guest_page,default_timeout=60).run()
    assert not page.exception
    next(b for b in page.button if b.label=='Generate Cabinet SLD').click()
    page=page.run()
    assert not page.exception
    assert page.session_state['sld_artifacts'].metadata['artifacts_registered'] is False
    assert len(page.get('download_button'))==4
    import calb_diagrams.cabinet_sld as renderer
    from calb_sizing_tool.services import cabinet_sld_service as service
    def unexpected(*args, **kwargs):
        raise AssertionError('Switching preview must not render or persist artifacts')
    monkeypatch.setattr(renderer, 'render_cabinet_sld', unexpected)
    monkeypatch.setattr(service, 'persist_artifacts', unexpected)
    next(s for s in page.selectbox if s.label=='AC Block to preview').select(2)
    page=page.run()
    assert not page.exception
    bundle = page.session_state['sld_artifacts']
    assert bundle.metadata['selected_ac_block'] == 2
    assert not bundle.metadata['artifacts_registered']
    svg = next(a['content'] for a in bundle.artifacts if a['artifact_kind']=='sld_svg')
    assert b'C025' in svg and b'C048' in svg and b'C001' not in svg
    assert len(page.get('download_button')) == 4
    next(s for s in page.selectbox if s.label=='AC Block to preview').select(1)
    page=page.run()
    assert not page.exception
    assert page.session_state['sld_artifacts'].metadata['selected_ac_block'] == 1
    assert any(b.label=='Typical AC Block Arrangement →' for b in page.button)


def test_actual_electrical_input_change_clears_previous_shared_bundle():
    page=AppTest.from_function(_guest_page,default_timeout=60).run()
    next(b for b in page.button if b.label=='Generate Cabinet SLD').click()
    page=page.run()
    assert not page.exception
    page.session_state['test_grid_kv'] = 35
    page=page.run()
    assert not page.exception
    assert 'sld_artifacts' not in page.session_state
    assert 'sld_pipeline_meta' not in page.session_state
    assert not page.get('download_button')
    assert any(b.label=='Typical AC Block Arrangement →' for b in page.button)


def test_source_access_denied_shows_message_instead_of_traceback(tmp_path,monkeypatch):
    from calb_sizing_tool.services.access_control_service import AccessControlService
    monkeypatch.setenv('CALB_DATABASE_URL',f"sqlite:///{(tmp_path/'access.sqlite').as_posix()}")
    def denied(*args): raise PermissionError('Denied')
    monkeypatch.setattr(AccessControlService,'load_dc_run_bundle',denied)
    page=AppTest.from_function(_registered_page,default_timeout=60).run()
    assert not page.exception
    assert any('do not have access' in str(e.value) for e in page.error)
    assert not any(b.label=='Generate Cabinet SLD' for b in page.button)


def _restored_parent_page():
    import streamlit as st
    from types import SimpleNamespace
    from tests.test_cabinet_sld_renderer import cabinet_output
    from calb_sizing_tool.ui.cabinet_sld_view import show_cabinet_sld
    output=cabinet_output()
    output['source_run_id']='dc'
    show_cabinet_sld(output,parent_run_id='dc',workspace={'ac_run_id':st.session_state.get('active_ac_run_id')},
                    is_guest=False,auth_user=SimpleNamespace(username='review'),authoritative=True)


def test_restored_parent_selects_only_exact_matching_saved_alternative(tmp_path,monkeypatch):
    from calb_sizing_tool.services.access_control_service import AccessControlService
    from calb_sizing_tool.ui import cabinet_sld_view as view
    monkeypatch.setenv('CALB_DATABASE_URL',f"sqlite:///{(tmp_path/'restore.sqlite').as_posix()}")
    monkeypatch.setattr(AccessControlService,'load_dc_run_bundle',lambda *args: object())
    monkeypatch.setattr(view,'matching_saved_cabinet_alternative',lambda *args,**kwargs:'exact-child')
    monkeypatch.setattr(view,'saved_cabinet_sld_block',lambda *args,**kwargs:None)
    monkeypatch.setattr(view,'restore_cabinet_sld',lambda *args,**kwargs:(None,[]))
    page=AppTest.from_function(_restored_parent_page,default_timeout=60).run()
    assert not page.exception
    assert page.session_state['active_ac_run_id']=='exact-child'
    assert any(b.label=='Generate Cabinet SLD' for b in page.button)
