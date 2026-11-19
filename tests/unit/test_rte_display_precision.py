"""Two-decimal input presentation must not round saved engineering values."""
import pytest
from streamlit.testing.v1 import AppTest

from test_curve_release import runtime
from test_rte_review import rte_runtime, _admin_rte_app
from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package
from calb_sizing_tool.services.rte_review_service import _curve_rows


@pytest.fixture(params=['matrix','detailed'])
def precise_draft(rte_runtime,request):
    service,actor,bundle,base,review=rte_runtime
    style=request.param
    config=None
    if style=='matrix':
        anchors=[dict(rate=.5,soh_pct=100,rte_pct=92.567891,source_kind='engineering_override')]
        payload=build_screenshot_package(base['payload'],anchors)
        rows=_curve_rows(payload)
        config={'test_anchors':anchors}
    else:
        rows=_curve_rows(base['payload'])
        rows[0]['rte_pct']=94.123456789
    did=review.save_draft(base['release_id'],'Precise '+style,rows,
        'Retain full reviewed precision while displaying two decimals',actor.user_id,
        matrix_config=config)
    saved=next(d for d in review.list_drafts(actor.user_id) if d['draft_id']==did)
    return service,actor,base,review,saved,style


def _raw_value(draft,style):
    if style=='matrix':
        return draft['payload']['rte_rule']['test_anchors'][0]['rte_pct']
    return _curve_rows(draft['payload'])[0]['rte_pct']


def _field_key(draft,style):
    prefix=f"rte_editor_{draft['base_release_id']}_{draft['draft_id']}_{draft['sha256']}"
    return prefix+('_tests_0.5_100' if style=='matrix' else '_raw_0')


def _open(actor,draft):
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=actor.user_id
    app.session_state['rte_draft_choice']=draft['draft_id']
    return app.run()


def test_two_decimal_inputs_keep_raw_precision_through_unchanged_save_and_reopen(precise_draft,monkeypatch):
    service,actor,base,review,draft,style=precise_draft
    monkeypatch.setenv('CALB_DATABASE_URL',service.db_url)
    original_default=service.get_default()
    original_raw=_raw_value(draft,style)
    assert original_raw!=round(original_raw,2)
    app=_open(actor,draft)
    assert not app.exception and not app.error
    field=app.number_input(key=_field_key(draft,style))
    assert field.proto.format=='%.2f'
    assert field.proto.default==original_raw
    assert field.value==original_raw
    assert not app.button(key='rte_publish_draft').disabled
    if style=='matrix':
        # Untested nodes remain absent, rather than becoming numeric zeros.
        empty=next(v for v in app.number_input if v.label=='0.25P at SOH 100%')
        assert empty.value is None

    app.run()
    assert not app.exception and not app.error
    assert app.number_input(key=_field_key(draft,style)).value==original_raw
    assert not app.button(key='rte_publish_draft').disabled
    app.button(key='rte_save_draft').click().run()
    assert not app.exception and not app.error
    saved=next(d for d in review.list_drafts(actor.user_id) if d['draft_id']==draft['draft_id'])
    assert saved['payload']['rte_bands']==draft['payload']['rte_bands']
    assert _raw_value(saved,style)==original_raw
    if style=='matrix':
        assert saved['payload']['rte_rule']['test_anchors']==draft['payload']['rte_rule']['test_anchors']

    reopened=_open(actor,saved)
    assert not reopened.exception and not reopened.error
    assert reopened.number_input(key=_field_key(saved,style)).value==original_raw
    assert not reopened.button(key='rte_publish_draft').disabled
    assert service.get_default()==original_default


def test_editing_to_the_visible_rounded_value_is_still_a_real_edit(precise_draft,monkeypatch):
    service,actor,base,review,draft,style=precise_draft
    monkeypatch.setenv('CALB_DATABASE_URL',service.db_url)
    raw=_raw_value(draft,style)
    rounded=round(raw,2)
    assert raw!=rounded and f'{raw:.2f}'==f'{rounded:.2f}'
    app=_open(actor,draft)
    assert not app.exception and not app.error
    app.number_input(key=_field_key(draft,style)).set_value(rounded).run()
    assert not app.exception and not app.error
    assert app.button(key='rte_publish_draft').disabled
    unchanged=next(d for d in review.list_drafts(actor.user_id) if d['draft_id']==draft['draft_id'])
    assert unchanged==draft

    app.button(key='rte_save_draft').click().run()
    assert not app.exception and not app.error
    saved=next(d for d in review.list_drafts(actor.user_id) if d['draft_id']==draft['draft_id'])
    assert _raw_value(saved,style)==rounded
    assert saved['sha256']!=draft['sha256']
    assert not app.button(key='rte_publish_draft').disabled
