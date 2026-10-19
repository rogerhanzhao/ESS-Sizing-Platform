from streamlit.testing.v1 import AppTest


def _nullable_form():
    import streamlit as st
    from calb_sizing_tool.ui import admin_portal_view as view

    class Service:
        def update_record(self, entity, record_id, values):
            st.session_state['saved'] = values
            return True

    view._refresh = lambda: None
    view._render_edit_form(
        service=Service(), title='QA', entity='ac_block',
        items=[dict(id='qa', block_name='Original', voltage=None, count=None, aux=0.0)],
        id_field='id', label_fields=['block_name'], specs=[
            dict(key='block_name',label='Name'),
            dict(key='voltage',label='Voltage',kind='float'),
            dict(key='count',label='Count',kind='int'),
            dict(key='aux',label='Aux',kind='float'),
        ])


def test_rename_keeps_unknown_numbers_null_and_real_zero_zero():
    app=AppTest.from_function(_nullable_form,default_timeout=30).run()
    app.text_input[0].set_value('Renamed')
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['saved']['voltage'] is None
    assert app.session_state['saved']['count'] is None
    assert app.session_state['saved']['aux']==0.0


def test_unknown_can_be_set_and_existing_number_can_be_cleared():
    app=AppTest.from_function(_nullable_form,default_timeout=30).run()
    app.number_input[0].set_value(33.0)
    next(c for c in app.checkbox if c.label=='Clear Aux').check()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['saved']['voltage']==33.0
    assert app.session_state['saved']['aux'] is None
