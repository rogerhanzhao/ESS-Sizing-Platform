from copy import deepcopy
import pytest
from streamlit.testing.v1 import AppTest

from test_curve_release import runtime
from calb_sizing_tool.config import DC_DATA_PATH
from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.infra.db.models.curve_release import CurveRelease
from calb_sizing_tool.infra.db.models.curve_release_draft import CurveReleaseDraft
from calb_sizing_tool.services.master_data_service import MasterDataService
from calb_sizing_tool.services.curve_release_service import attach_curve_basis, BASIS_KEY, digest
from calb_sizing_tool.services.dc_pipeline_service import run_dc_pipeline
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.rte_review_service import (
    RteReviewService, _curve_rows, derive_legacy_rte, annual_rte_preview,
)
from calb_sizing_tool.services.auth_service import AuthService


@pytest.fixture
def rte_runtime(runtime):
    service,actor,bundle,release=runtime
    old=load_dc_excel_bundle_from_path(DC_DATA_PATH)
    MasterDataService(service.db_url).migrate_soh_rte_from_excel_bundle(old,version_tag='old-rte',source_ref=str(DC_DATA_PATH))
    with session_scope(service.db_url) as s:source=s.get(CurveRelease,release['release_id']).source_import_id
    base=service.publish(source,'RTE base','Use documented old RTE data',actor.user_id)
    return service,actor,bundle,base,RteReviewService(service.db_url)


def test_old_rule_reproduces_all_57_stored_band_values(rte_runtime):
    s,a,b,base,review=rte_runtime
    generated=derive_legacy_rte(base['payload'])
    assert len(generated['rte_bands'])==57
    assert generated['rte_bands']==base['payload']['rte_bands']
    assert generated['rte_rule']['k']==1.6
    rows=_curve_rows(generated)
    bol={r['rate']:r['rte_pct'] for r in rows if r['soh_min_pct']==100}
    assert bol[.25]==94 and bol[.33]==pytest.approx(93.1) and bol[.5]==pytest.approx(92.56)


def test_draft_edit_save_reopen_publish_is_immutable_and_does_not_switch_default(rte_runtime):
    s,a,b,base,review=rte_runtime
    original=deepcopy(base['payload']);old_default=s.get_default()
    rows=_curve_rows(derive_legacy_rte(original));rows[0]['rte_pct']-=.05
    draft=review.save_draft(base['release_id'],'Manual RTE v1',rows,'Engineering override for local review',a.user_id)
    reopened=review.list_drafts(a.user_id)[0]
    assert reopened['draft_id']==draft and reopened['status']=='draft'
    release_id=review.publish_draft(draft,a.user_id,reopened['sha256'])
    published=s.get_release(release_id)
    assert published['payload']['rte_rule']['manual_override'] is True
    assert published['payload']['curves']==original['curves']
    assert s.get_release(base['release_id'])['payload']==original
    assert s.get_default()==old_default
    with pytest.raises(ValueError,match='unpublished'):
        review.save_draft(base['release_id'],'v2',rows,'reason',a.user_id,draft_id=draft,expected_sha=reopened['sha256'])


@pytest.mark.parametrize('mutation,message',[
    (lambda r:r[0].update(rte_pct=101),'finite percentage'),
    (lambda r:r[0].update(rte_pct=float('nan')),'finite percentage'),
    (lambda r:r[0].update(soh_min_pct=99),'fixed'),
    (lambda r:r[0].update(rte_pct=1),'ordering'),
])
def test_invalid_manual_rte_is_rejected_before_saving(rte_runtime,mutation,message):
    s,a,b,base,review=rte_runtime
    rows=_curve_rows(derive_legacy_rte(base['payload']));mutation(rows)
    with pytest.raises(ValueError,match=message):review.save_draft(base['release_id'],'bad',rows,'reason',a.user_id)
    assert review.list_drafts(a.user_id)==[]


def test_draft_conflict_and_non_admin_permissions(rte_runtime):
    s,a,b,base,review=rte_runtime
    rows=_curve_rows(derive_legacy_rte(base['payload']))
    draft=review.save_draft(base['release_id'],'draft',rows,'reason',a.user_id)
    with pytest.raises(ValueError,match='changed'):
        review.save_draft(base['release_id'],'draft2',rows,'reason',a.user_id,draft_id=draft,expected_sha='bad')
    with pytest.raises(ValueError,match='changed'):
        review.publish_draft(draft,a.user_id,'bad')
    user=AuthService(s.db_url).create_user(username='rte-reader',password='test',role_codes=['normal_user'])
    with pytest.raises(PermissionError):review.list_drafts(user.user_id)
    with pytest.raises(PermissionError):review.save_draft(base['release_id'],'bad',rows,'reason',user.user_id)


def test_label_only_draft_change_invalidates_save_and_publication_review_tokens(rte_runtime):
    s,a,b,base,review=rte_runtime
    rows=_curve_rows(derive_legacy_rte(base['payload']))
    note='Same reviewed inputs and applicability'
    did=review.save_draft(base['release_id'],'Original reviewed name',rows,note,a.user_id)
    original=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)

    review.save_draft(base['release_id'],'Renamed by another administrator',rows,note,a.user_id,
                      draft_id=did,expected_sha=original['sha256'])
    renamed=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    assert renamed['sha256']!=original['sha256']
    assert renamed['payload']['rte_bands']==original['payload']['rte_bands']
    assert renamed['payload']['rte_version']==original['payload']['rte_version']
    with pytest.raises(ValueError,match='changed during review'):
        review.save_draft(base['release_id'],'Stale administrator name',rows,note,a.user_id,
                          draft_id=did,expected_sha=original['sha256'])
    with pytest.raises(ValueError,match='changed or failed'):
        review.publish_draft(did,a.user_id,original['sha256'])
    assert next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)==renamed

    review.save_draft(base['release_id'],'Reopened and reviewed name',rows,note,a.user_id,
                      draft_id=did,expected_sha=renamed['sha256'])
    reopened=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    rid=review.publish_draft(did,a.user_id,reopened['sha256'])
    published=s.get_release(rid)
    assert published['version_label']=='Reopened and reviewed name'
    assert published['payload']['rte_rule']['reviewed_version_label']==published['version_label']
    assert published['payload']['rte_bands']==original['payload']['rte_bands']
    assert published['payload']['rte_version']==original['payload']['rte_version']


def test_publication_rejects_name_outside_reviewed_draft_content(rte_runtime):
    s,a,b,base,review=rte_runtime
    rows=_curve_rows(derive_legacy_rte(base['payload']))
    did=review.save_draft(base['release_id'],'Reviewed draft name',rows,'Reviewed source',a.user_id)
    saved=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    with session_scope(s.db_url) as db:
        db.get(CurveReleaseDraft,did).version_label='Name outside reviewed content'
    with pytest.raises(ValueError,match='version label differs'):
        review.publish_draft(did,a.user_id,saved['sha256'])


def test_legacy_draft_without_reviewed_label_remains_publishable(rte_runtime):
    s,a,b,base,review=rte_runtime
    rows=_curve_rows(derive_legacy_rte(base['payload']))
    did=review.save_draft(base['release_id'],'Legacy draft name',rows,'Existing review',a.user_id)
    # Simulate a saved draft from before label-aware review tokens. Its payload
    # and hash stay in the original format; no schema or data migration is needed.
    with session_scope(s.db_url) as db:
        draft=db.get(CurveReleaseDraft,did)
        payload=deepcopy(draft.payload_json)
        payload['rte_rule'].pop('reviewed_version_label')
        draft.payload_json=payload
        draft.payload_sha256=digest(payload)
    saved=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    rid=review.publish_draft(did,a.user_id,saved['sha256'])
    published=s.get_release(rid)
    assert published['version_label']=='Legacy draft name'
    assert 'reviewed_version_label' not in published['payload']['rte_rule']
    assert published['payload']==saved['payload']


def test_new_soh_annual_preview_matches_unchanged_runtime_rte(rte_runtime):
    s,a,b,base,review=rte_runtime
    rows=_curve_rows(derive_legacy_rte(base['payload']))
    draft=review.save_draft(base['release_id'],'generated',rows,'Verified legacy rule',a.user_id)
    d=review.list_drafts(a.user_id)[0];rid=review.publish_draft(draft,a.user_id,d['sha256'])
    release=s.get_release(rid)
    selection=dict(release_id=rid,family_key='soc20.mean',payload_sha256=release['payload_sha256'])
    bundle,basis=s.prepare(b,selection,life_years=3,cycles_per_year=365)
    snapshot=attach_curve_basis(run_dc_pipeline(SizingCaseInput(poi_power_req_mw=1,poi_energy_req_mwh=4,project_life_years=3),bundle),basis)
    trace=snapshot.summary[BASIS_KEY]
    preview=[r for r in annual_rte_preview(release['payload'],'soc20.mean') if r['rate']==trace['source_rate'] and r['cycles_day']==trace['source_cycles_per_day']]
    assert len(preview)==len(snapshot.stage3.rows)
    for expected,actual in zip(preview,snapshot.stage3.rows):assert actual.dc_rte_frac==pytest.approx(expected['dc_rte_pct']/100,abs=1e-14)
    assert trace['rte_rule']['manual_override'] is False


def _admin_rte_app():
    import streamlit as st
    from calb_sizing_tool.ui.rte_review_controls import render_rte_review
    render_rte_review(st.session_state['review_actor'])


def test_admin_can_save_reopen_and_publish_working_copy(rte_runtime,monkeypatch):
    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id;app.run()
    assert not app.exception
    assert next(v for v in app.selectbox if v.label=='Preview operating condition').value=='soc20.mean'
    assert app.button(key='rte_publish_draft').disabled
    next(v for v in app.selectbox if v.label=='Preview operating condition').select('soc50.lower_limit').run()
    next(x for x in app.text_input if x.label=='New version name').set_value('UI RTE draft')
    next(x for x in app.text_area if x.label=='Review note / applicability').set_value('Source formula checked; local review only')
    app.button(key='rte_save_draft').click().run()
    assert not app.exception and not app.error
    draft=review.list_drafts(a.user_id)[0]
    assert draft['version_label']=='UI RTE draft'
    assert draft['payload']['curves']==base['payload']['curves']
    assert app.selectbox(key='rte_draft_choice').value==draft['draft_id']
    assert app.button(key='rte_publish_draft').label=='Publish complete curve version'
    app.button(key='rte_publish_draft').click().run()
    assert not app.exception and not app.error
    published=next(r for r in s.list_releases() if r['version_label']=='UI RTE draft')
    assert published['payload']['curves']==base['payload']['curves']


def test_rte_editor_separates_inputs_reference_values_and_read_only_preview(rte_runtime,monkeypatch):
    from calb_sizing_tool.ui.curve_labels import curve_version_label

    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception and not app.error and not app.warning
    assert any(item.label=='Revise RTE' for item in app.expander)
    headings=[item.value for item in app.subheader]
    assert headings.index('RTE inputs')<headings.index('Calculated RTE reference table')
    structure=next(item for item in app.radio if item.label=='RTE table format')
    assert structure.options==['SOH bands (5%)','Original detailed bands']
    assert structure.value=='Screenshot five-percent SOH bands'
    source=next(item for item in app.selectbox if item.label=='Input source for new or changed values')
    assert source.options==['Entered test value','Entered engineering value']
    assert source.value=='test'
    source.set_value('engineering_override').run()
    assert not app.exception and not app.error
    assert next(item for item in app.selectbox if item.label=='Input source for new or changed values').value=='engineering_override'
    name=next(item for item in app.text_input if item.label=='New version name')
    selected_base=next(item for item in app.selectbox if item.label=='Base curve version').value
    assert name.value==curve_version_label(s.get_release(selected_base))+' – RTE revision'
    details=next(item for item in app.expander if item.label=='Calculation method and applicability')
    preview=next(item for item in app.expander if item.label=='Annual RTE preview (read only)')
    assert not details.proto.expanded and not preview.proto.expanded
    assert any('does not change curve values or sizing settings' in item.value for item in app.caption)
    assert any('does not switch the default or change previous runs' in item.value for item in app.caption)


def test_equal_model_value_test_input_must_be_saved_before_publication(rte_runtime,monkeypatch):
    from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package

    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    initial=build_screenshot_package(base['payload'])
    did=review.save_draft(base['release_id'],'Equal-value test evidence',_curve_rows(initial),
                         'Review evidence without changing model values',a.user_id,
                         matrix_config={'test_anchors':[]})
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.session_state['rte_draft_choice']=did
    app.run()
    assert not app.exception and not app.error
    assert not app.button(key='rte_publish_draft').disabled

    next(v for v in app.number_input if v.label=='0.5P at SOH 100%').set_value(92.56)
    app.run()
    assert not app.exception and not app.error
    assert app.button(key='rte_publish_draft').disabled
    saved=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    assert saved['payload']['rte_rule']['test_anchors']==[]

    app.button(key='rte_save_draft').click().run()
    assert not app.exception and not app.error
    assert not app.button(key='rte_publish_draft').disabled
    saved=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    expected=[dict(rate=.5,soh_pct=100,rte_pct=92.56,source_kind='test')]
    assert saved['payload']['rte_bands']==initial['rte_bands']
    assert saved['payload']['rte_rule']['test_anchors']==expected

    app.button(key='rte_publish_draft').click().run()
    assert not app.exception and not app.error
    published=next(r for r in s.list_releases() if r['version_label']=='Equal-value test evidence')
    assert published['payload']['rte_rule']['test_anchors']==expected


def test_test_input_source_kind_change_must_be_saved_before_publication(rte_runtime,monkeypatch):
    from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package
    from calb_sizing_tool.ui import rte_review_controls

    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    original=[dict(rate=.5,soh_pct=100,rte_pct=92.56,source_kind='test')]
    initial=build_screenshot_package(base['payload'],original)
    did=review.save_draft(base['release_id'],'Reclassified test evidence',_curve_rows(initial),
                         'Review provenance independently of numerical values',a.user_id,
                         matrix_config={'test_anchors':original})
    changed=[dict(original[0],source_kind='engineering_override')]
    # Exercise the publication guard independently of the input form: the
    # source classification is the only changed field and all values stay fixed.
    monkeypatch.setattr(rte_review_controls,'render_test_inputs',lambda *_:deepcopy(changed))
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.session_state['rte_draft_choice']=did
    app.run()
    assert not app.exception and not app.error
    assert app.button(key='rte_publish_draft').disabled

    app.button(key='rte_save_draft').click().run()
    assert not app.exception and not app.error
    assert not app.button(key='rte_publish_draft').disabled
    saved=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    assert saved['payload']['rte_bands']==initial['rte_bands']
    assert saved['payload']['rte_rule']['test_anchors']==changed

    app.button(key='rte_publish_draft').click().run()
    assert not app.exception and not app.error
    published=next(r for r in s.list_releases() if r['version_label']=='Reclassified test evidence')
    assert published['payload']['rte_rule']['test_anchors']==changed


@pytest.mark.parametrize('stale_action',['rte_save_draft','rte_publish_draft'])
def test_concurrent_draft_change_requires_reload_before_save_or_publication(rte_runtime,monkeypatch,stale_action):
    from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package

    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    initial=build_screenshot_package(base['payload'])
    label='Concurrent RTE '+stale_action
    did=review.save_draft(base['release_id'],label,_curve_rows(initial),
                         'Admin A reviewed this original draft',a.user_id,
                         matrix_config={'test_anchors':[]})
    before=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.session_state['rte_draft_choice']=did
    app.run()
    assert not app.exception and not app.error
    if stale_action=='rte_save_draft':
        next(v for v in app.text_area if v.label=='Review note / applicability').set_value('Unsaved Admin A edit')

    anchors=[dict(rate=.5,soh_pct=100,rte_pct=92.3,source_kind='engineering_override')]
    changed=build_screenshot_package(base['payload'],anchors)
    changed_note='Admin B changed the RTE after Admin A reviewed it'
    review.save_draft(base['release_id'],label,_curve_rows(changed),changed_note,a.user_id,
                      draft_id=did,expected_sha=before['sha256'],matrix_config={'test_anchors':anchors})
    latest=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    assert latest['sha256']!=before['sha256']

    app.button(key=stale_action).click().run()
    assert not app.exception
    assert any('changed during review' in error.value for error in app.error)
    after=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    assert after==latest
    assert after['status']=='draft'
    assert not any(r['version_label']==label for r in s.list_releases())

    app.button(key='rte_reload_draft').click().run()
    assert not app.exception and not app.error
    assert next(v for v in app.number_input if v.label=='0.5P at SOH 100%').value==92.3
    assert next(v for v in app.text_area if v.label=='Review note / applicability').value==changed_note
    assert not app.button(key='rte_publish_draft').disabled
    app.button(key='rte_publish_draft').click().run()
    assert not app.exception and not app.error
    published=next(r for r in s.list_releases() if r['version_label']==label)
    assert published['payload']['rte_rule']['test_anchors']==anchors
    assert published['payload']['rte_bands']==changed['rte_bands']
    assert published['review_note']==changed_note


def test_existing_anchor_order_does_not_require_an_unnecessary_save(rte_runtime,monkeypatch):
    from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package

    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    reference=build_screenshot_package(base['payload'])
    # Save the opposite order from the form, which renders SOH 100 before 90.
    anchors=[dict(rate=.5,soh_pct=h,rte_pct=next(row['rte_pct'] for row in
                 reference['rte_rule']['calculation_rows'] if row['rate']==.5 and row['soh_pct']==h),
                 source_kind='test') for h in (90,100)]
    initial=build_screenshot_package(base['payload'],anchors)
    did=review.save_draft(base['release_id'],'Reversed anchor order',_curve_rows(initial),
                         'Equivalent inputs may be stored in any order',a.user_id,
                         matrix_config={'test_anchors':anchors})
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.session_state['rte_draft_choice']=did
    app.run()
    assert not app.exception and not app.error
    assert not app.button(key='rte_publish_draft').disabled
    app.button(key='rte_publish_draft').click().run()
    assert not app.exception and not app.error
    published=next(r for r in s.list_releases() if r['version_label']=='Reversed anchor order')
    assert published['payload']['rte_rule']['test_anchors']==anchors


@pytest.mark.parametrize('entered_value',[92.2,None])
def test_saved_draft_widget_defaults_match_the_server_state(rte_runtime,monkeypatch,entered_value):
    from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package

    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    anchors=[dict(rate=.5,soh_pct=100,rte_pct=92.3,source_kind='engineering_override')]
    initial=build_screenshot_package(base['payload'],anchors)
    did=review.save_draft(base['release_id'],'Older selected draft',_curve_rows(initial),
                         'Saved source evidence',a.user_id,matrix_config={'test_anchors':anchors})
    review.save_draft(base['release_id'],'Newer unselected draft',_curve_rows(initial),
                     'Another working draft',a.user_id,matrix_config={'test_anchors':anchors})
    drafts=review.list_drafts(a.user_id)
    selected=next(d for d in drafts if d['draft_id']==did)
    editor_key=f"rte_editor_{base['release_id']}_{did}_{selected['sha256']}"
    source_key=editor_key+'_source_kind'
    value_key=editor_key+'_tests_0.5_100'
    preview_key=f"rte_family_{base['release_id']}_{did}"
    name_key=f"rte_name_{base['release_id']}_{did}"
    note_key=f"rte_reason_{base['release_id']}_{did}"
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    for key,value in {'review_actor':a.user_id,'rte_draft_choice':did,
                      source_key:'engineering_override',value_key:entered_value,
                      preview_key:'soc50.lower_limit',name_key:'Unsaved version name',
                      note_key:'Unsaved applicability note'}.items():
        app.session_state[key]=value
    app.run()
    assert not app.exception and not app.error
    draft_choice=app.selectbox(key='rte_draft_choice')
    assert draft_choice.value==did
    assert draft_choice.proto.default==1+[d['draft_id'] for d in drafts].index(did)
    source=app.selectbox(key=source_key)
    assert source.value=='engineering_override' and source.proto.default==1
    preview=app.selectbox(key=preview_key)
    assert preview.value=='soc50.lower_limit' and preview.proto.default==3
    number=app.number_input(key=value_key)
    assert number.value==entered_value
    if entered_value is None:
        assert 'default' not in {field.name for field,_ in number.proto.ListFields()}
    else:
        assert number.proto.default==entered_value
    assert app.text_input(key=name_key).value==app.text_input(key=name_key).proto.default=='Unsaved version name'
    assert app.text_area(key=note_key).value==app.text_area(key=note_key).proto.default=='Unsaved applicability note'
    assert app.button(key='rte_publish_draft').disabled
    assert next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)==selected


def test_base_format_and_detailed_input_defaults_match_the_server_state(rte_runtime,monkeypatch):
    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    rows=_curve_rows(derive_legacy_rte(base['payload']))
    did=review.save_draft(base['release_id'],'Newer RTE version',rows,'Reviewed newer reference',a.user_id)
    draft=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    review.publish_draft(did,a.user_id,draft['sha256'])
    releases=[r for r in s.list_releases() if r['status']=='published']
    base_id=base['release_id']
    first=rows[0]
    value=first['rte_pct']-.01
    raw_key=f"rte_editor_{base_id}_new_new_raw_{first['row']}"
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.session_state['rte_base_release']=base_id
    app.session_state[f'rte_structure_{base_id}']='Legacy detailed bands'
    app.session_state[raw_key]=value
    app.run()
    assert not app.exception and not app.error
    selected=app.selectbox(key='rte_base_release')
    assert selected.value==base_id
    assert selected.proto.default==[r['release_id'] for r in releases].index(base_id)>0
    structure=app.radio(key=f'rte_structure_{base_id}')
    assert structure.value=='Legacy detailed bands' and structure.proto.default==1
    assert app.number_input(key=raw_key).value==app.number_input(key=raw_key).proto.default==value
