from copy import deepcopy
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.adapters.excel_loader_adapter import load_dc_excel_bundle_from_path
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models.curve_release import CurveRelease
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.schemas.case import SizingCaseInput
from calb_sizing_tool.services.auth_service import AuthService
from calb_sizing_tool.services.curve_release_service import (
    BASIS_KEY, CurveReleaseService, attach_curve_basis, curve_display_meta, digest,
)
from calb_sizing_tool.services.dc_pipeline_service import run_dc_pipeline
from calb_sizing_tool.services.master_data_service import MasterDataService
from calb_sizing_tool.services.run_persistence_service import persist_dc_run
from calb_sizing_tool.services.run_restore_service import load_dc_run_bundle
from calb_sizing_tool.services.supplier_degradation_library_service import SupplierDegradationLibraryService


def source_bytes(socs=(20,50)):
    wb = Workbook()
    wb.remove(wb.active)
    for name, lower in [('Degradation-均值',False),('Degradation-下限值',True)]:
        ws = wb.create_sheet(name)
        for n,soc in enumerate(socs):
            start=2+n*10
            ws.cell(start,1,'SOC');ws.cell(start,3,soc/100).number_format='0%'
            ws.cell(start+1,1,'Power Rate')
            for i,(rate,freq) in enumerate(( (r,f) for r in (.25,.33,.5) for f in (1,1.5,2)),3):
                ws.cell(start+1,i,rate);ws.cell(start+2,i,freq)
                for y in range(4):
                    ws.cell(start+3+y,2,y)
                    value=1 if y==0 else 1-.02*y-(.01 if lower else 0)-(soc-20)*.0001
                    ws.cell(start+3+y,i,value).number_format='0.00%'
    out=BytesIO();wb.save(out);wb.close();return out.getvalue()


@pytest.fixture
def runtime(tmp_path,sample_excel_path):
    url=f"sqlite:///{(tmp_path/'curves.sqlite').as_posix()}"
    engine=create_engine_for_url(url);Base.metadata.create_all(engine);engine.dispose()
    actor=AuthService(url).create_user(username='curve-admin',password='test',role_codes=['admin'])
    bundle=load_dc_excel_bundle_from_path(sample_excel_path)
    MasterDataService(url).migrate_soh_rte_from_excel_bundle(bundle,version_tag='test',source_ref='test')
    source,_=SupplierDegradationLibraryService(url).save_candidate(source_bytes(),'source.xlsx','source-v1',actor.user_id)
    service=CurveReleaseService(url)
    release=service.publish(source['import_id'],'review-v1','Local test / same approved cell basis',actor.user_id)
    service.set_default(release['release_id'],'soc20.mean',actor.user_id,0)
    return service,actor,bundle,release


def test_publishing_does_not_replace_master_data_and_rte_is_frozen(runtime):
    s,a,b,r=runtime
    before=MasterDataService(s.db_url).build_soh_rte_dataframes()
    for key in ('df_rte_profile','df_rte_curve'):
        frozen=pd.DataFrame(r['payload']['rte_profiles' if key=='df_rte_profile' else 'rte_bands'])
        pd.testing.assert_frame_equal(before[key],frozen,check_dtype=False)
    bundle,basis=s.prepare(b,s.get_default(),life_years=3,cycles_per_year=365)
    assert basis['source_series']=='mean' and basis['source_soc_pct']==20
    assert bundle is not b
    after=MasterDataService(s.db_url).build_soh_rte_dataframes()
    for key in before:pd.testing.assert_frame_equal(before[key],after[key])


def test_fractional_source_frequency_preserved_in_selection_and_report_meta(runtime):
    s,a,b,r=runtime
    bundle,basis=s.prepare(b,s.get_default(),life_years=2,cycles_per_year=540)
    case=SizingCaseInput(poi_power_req_mw=1,poi_energy_req_mwh=4,project_life_years=2,poi_guarantee_year=2,cycles_per_year=540)
    snapshot=attach_curve_basis(run_dc_pipeline(case,bundle),basis)
    assert snapshot.stage3.meta.chosen_soh_cycles_per_year==547
    assert curve_display_meta(snapshot)['chosen_soh_cycles_per_year']==547.5
    assert snapshot.summary[BASIS_KEY]['source_cycles_per_day']==1.5


def test_missing_year_is_rejected_without_lighter_frequency_substitution(runtime):
    s,a,b,r=runtime
    with pytest.raises(ValueError,match='full 4-year'):
        s.prepare(b,s.get_default(),life_years=4,cycles_per_year=365)


def test_higher_frequency_cannot_fall_back_to_lighter_ordinary_duty(runtime):
    s,a,b,r=runtime
    with pytest.raises(ValueError,match='exceeds this published family maximum'):
        s.prepare(b,s.get_default(),life_years=1,cycles_per_year=1095)


def test_unapproved_reference_workbook_is_rejected(runtime):
    s,a,b,r=runtime
    with pytest.raises(ValueError,match='reference workbook differs'):
        s.prepare(b,s.get_default(),life_years=1,cycles_per_year=365,verify_reference=True)


def test_changing_default_does_not_change_prepared_run_or_explicit_case(runtime):
    s,a,b,r=runtime
    selected=s.get_default()
    bundle,basis=s.prepare(b,selected,life_years=2,cycles_per_year=365)
    s.set_default(r['release_id'],'soc50.lower_limit',a.user_id,selected['revision'])
    again,old_basis=s.prepare(b,selected,life_years=2,cycles_per_year=365)
    assert basis==old_basis
    pd.testing.assert_frame_equal(bundle.df_soh_curve,again.df_soh_curve)
    new,new_basis=s.prepare(b,None,life_years=2,cycles_per_year=365)
    assert new_basis['family_key']=='soc50.lower_limit'
    assert new_basis['package_sha256']!=basis['package_sha256']


def test_concurrent_default_revision_and_retirement_guards(runtime):
    s,a,b,r=runtime
    with pytest.raises(ValueError,match='Default changed'):
        s.set_default(r['release_id'],'soc50.mean',a.user_id,0)
    with pytest.raises(ValueError,match='Switch the default'):
        s.retire(r['release_id'],a.user_id)


def test_non_admin_cannot_publish_or_switch(runtime):
    s,a,b,r=runtime
    user=AuthService(s.db_url).create_user(username='ordinary',password='test',role_codes=['normal_user'])
    with pytest.raises(PermissionError):s.set_default(r['release_id'],'soc50.mean',user.user_id,1)
    with pytest.raises(PermissionError):s.publish(r['source_import_id'] if 'source_import_id' in r else 'any','v2','note',user.user_id)


def test_corrupt_release_and_forged_selection_fail_closed(runtime):
    s,a,b,r=runtime
    selection=s.get_default();selection['payload_sha256']='bad'
    with pytest.raises(ValueError,match='hash changed'):s.prepare(b,selection,life_years=1,cycles_per_year=365)
    with session_scope(s.db_url) as db:db.get(CurveRelease,r['release_id']).payload_sha256='bad'
    with pytest.raises(ValueError,match='checksum'):s.get_default()
    assert s.list_releases()[0]['status']=='corrupt'
    assert s.get_binding()['revision']==1


def test_incomplete_selection_is_a_clear_validation_error(runtime):
    s,a,b,r=runtime
    with pytest.raises(ValueError,match='Incomplete versioned'):
        s.prepare(b,{'release_id':r['release_id']},life_years=1,cycles_per_year=365)


def test_save_restore_uses_immutable_package_even_after_default_changes(runtime):
    s,a,b,r=runtime
    selection=s.get_default();selection={k:v for k,v in selection.items() if k!='revision'}
    bundle,basis=s.prepare(b,selection,life_years=2,cycles_per_year=540)
    case=SizingCaseInput(project_name='Curve roundtrip',poi_power_req_mw=1,poi_energy_req_mwh=4,project_life_years=2,cycles_per_year=540,curve_selection=selection)
    snapshot=attach_curve_basis(run_dc_pipeline(case,bundle),basis)
    saved=persist_dc_run(case,snapshot,db_url=s.db_url,actor=a.username)
    s.set_default(r['release_id'],'soc50.lower_limit',a.user_id,1)
    restored=load_dc_run_bundle(saved['run_id'],db_url=s.db_url)
    assert restored.snapshot.summary[BASIS_KEY]==snapshot.summary[BASIS_KEY]
    assert restored.input_snapshot.payload[BASIS_KEY]['package_sha256']==basis['package_sha256']


def test_cannot_save_version_label_over_legacy_result(runtime):
    s,a,b,r=runtime
    selection={k:v for k,v in s.get_default().items() if k!='revision'}
    case=SizingCaseInput(poi_power_req_mw=1,poi_energy_req_mwh=4,project_life_years=2,curve_selection=selection)
    snapshot=run_dc_pipeline(case,b)
    with pytest.raises(ValueError,match='actual run curve package'):
        persist_dc_run(case,snapshot,db_url=s.db_url)


def test_cannot_attach_new_version_to_result_calculated_with_old_points(runtime):
    s,a,b,r=runtime
    _,basis=s.prepare(b,s.get_default(),life_years=2,cycles_per_year=365)
    legacy=run_dc_pipeline(SizingCaseInput(poi_power_req_mw=1,poi_energy_req_mwh=4,project_life_years=2),b)
    with pytest.raises(ValueError,match='metadata|SOH points'):
        attach_curve_basis(legacy,basis)


def _choice_app():
    import streamlit as st
    from calb_sizing_tool.ui.curve_release_controls import render_curve_choice
    with st.form('dc'):
        selection=render_curve_choice(st.session_state.setdefault('inputs',{}))
        if st.form_submit_button('Run'):
            st.json(selection)


def test_original_form_default_and_manual_special_choice(runtime,monkeypatch):
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    app=AppTest.from_function(_choice_app,default_timeout=30).run()
    assert not app.exception
    assert app.selectbox(key='dc_inputs.curve_selection_token').value.endswith('|soc20.mean')
    app.selectbox(key='dc_inputs.curve_selection_token').select(r['release_id']+'|soc50.lower_limit')
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['inputs']['curve_selection']['family_key']=='soc50.lower_limit'


def _admin_app():
    import streamlit as st
    from calb_sizing_tool.ui.curve_release_controls import render_curve_admin
    render_curve_admin(st.session_state['review_actor'])


def _admin_current_default_app():
    import streamlit as st
    from calb_sizing_tool.ui.curve_release_controls import (
        load_curve_admin_context, render_curve_current_default, render_curve_admin,
    )
    context=load_curve_admin_context()
    render_curve_current_default(context=context)
    render_curve_admin(st.session_state['review_actor'],context=context)


def test_admin_default_control_starts_at_actual_current_default(runtime,monkeypatch):
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    app=AppTest.from_function(_admin_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception
    assert app.selectbox(key='curve_default_version').value==r['release_id']
    assert app.selectbox(key='curve_default_condition').value=='soc20.mean'
    assert app.button(key='curve_retire_submit').disabled
    assert any('current default' in message.value for message in app.info)
    assert s.get_default()['release_id']==r['release_id']


def test_publish_form_retains_chosen_rte_and_text_without_publishing(runtime,monkeypatch):
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    original_default=s.get_default()
    original_releases=s.list_releases()
    app=AppTest.from_function(_admin_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception and not app.error
    assert app.selectbox(key='curve_publish_rte_source').value==r['release_id']
    assert app.selectbox(key='curve_publish_rte_source').proto.default==1

    app.selectbox(key='curve_publish_rte_source').select('master')
    app.text_input(key='curve_publish_name').set_value('Proposed reference revision')
    app.text_area(key='curve_publish_note').set_value('Pending review only; no publication requested.')
    app.run()
    assert not app.exception and not app.error
    assert app.selectbox(key='curve_publish_rte_source').value=='master'
    assert app.selectbox(key='curve_publish_rte_source').proto.default==0
    assert app.text_input(key='curve_publish_name').value=='Proposed reference revision'
    assert app.text_input(key='curve_publish_name').proto.default=='Proposed reference revision'
    assert app.text_area(key='curve_publish_note').value=='Pending review only; no publication requested.'
    assert app.text_area(key='curve_publish_note').proto.default=='Pending review only; no publication requested.'
    assert app.session_state['curve_publish_rte_source']=='master'
    assert s.get_default()==original_default
    assert s.list_releases()==original_releases


def test_admin_default_stale_form_requires_refresh_before_applying(runtime,monkeypatch):
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    app=AppTest.from_function(_admin_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception
    app.selectbox(key='curve_default_condition').select('soc50.mean')

    # A second administrator changes the default after the first has reviewed
    # revision 1. The open form must retain that reviewed revision for its write.
    s.set_default(r['release_id'],'soc50.lower_limit',a.user_id,1)
    current=s.get_default()
    assert current['revision']==2
    next(v for v in app.button if v.label=='Apply as sizing default').click().run()
    assert not app.exception
    assert app.error
    assert s.get_default()==current
    assert next(v for v in app.button if v.label=='Apply as sizing default').disabled

    # Refresh is explicit: only then may the administrator review and apply a
    # new choice against revision 2.
    app.button(key='curve_default_refresh').click().run()
    assert not app.exception
    assert not next(v for v in app.button if v.label=='Apply as sizing default').disabled
    app.selectbox(key='curve_default_condition').select('soc50.mean')
    next(v for v in app.button if v.label=='Apply as sizing default').click().run()
    assert not app.exception and not app.error
    updated=s.get_default()
    assert updated['revision']==3
    assert updated['family_key']=='soc50.mean'


def _admin_navigation_app():
    import streamlit as st
    from calb_sizing_tool.ui.curve_release_controls import render_curve_admin
    page=st.radio('Review page',['Admin','Sizing'],key='review_test_page')
    if page=='Admin':
        render_curve_admin(st.session_state['review_actor'])


def test_returning_to_admin_reopens_current_default_without_false_conflict(runtime,monkeypatch):
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    s.set_default(r['release_id'],'soc50.lower_limit',a.user_id,1)
    app=AppTest.from_function(_admin_navigation_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception and not app.error
    assert app.selectbox(key='curve_default_version').value==r['release_id']
    assert app.selectbox(key='curve_default_condition').value=='soc50.lower_limit'
    assert app.selectbox(key='curve_default_condition').proto.default==3

    # Navigating away omits the real widget, so Streamlit itself clears its
    # state while retaining the non-widget reviewed revision.
    app.radio(key='review_test_page').set_value('Sizing').run()
    assert not app.exception
    assert 'curve_default_version' not in app.session_state
    assert 'curve_default_condition' not in app.session_state
    assert app.session_state['review_curve_default_revision']==2
    s.set_default(r['release_id'],'soc50.mean',a.user_id,2)

    app.radio(key='review_test_page').set_value('Admin').run()
    assert not app.exception and not app.error
    assert app.selectbox(key='curve_default_version').value==r['release_id']
    assert app.selectbox(key='curve_default_condition').value=='soc50.mean'
    assert app.selectbox(key='curve_default_condition').proto.default==2
    assert app.session_state['review_curve_default_revision']==3
    assert not next(v for v in app.button if v.label=='Apply as sizing default').disabled


def test_changing_proposed_version_uses_only_its_conditions_and_keeps_actual_default(runtime,monkeypatch):
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    source,_=SupplierDegradationLibraryService(s.db_url).save_candidate(
        source_bytes(socs=(100,)),'different-conditions.xlsx','source-SOC100-only',a.user_id)
    second=s.publish(source['import_id'],'Separate conditions v2','Different operating conditions',a.user_id)
    original=s.get_default()
    app=AppTest.from_function(_admin_current_default_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception and not app.error
    # The newest published version is not automatically the sizing default.
    assert app.selectbox(key='curve_default_version').value==r['release_id']
    assert app.selectbox(key='curve_default_condition').value=='soc20.mean'

    app.selectbox(key='curve_default_version').select(second['release_id']).run()
    assert not app.exception and not app.error
    condition=app.selectbox(key='curve_default_condition')
    assert condition.value=='soc100.mean'
    assert len(condition.options)==2
    assert condition.proto.default==0
    assert s.get_default()==original
    assert app.session_state['review_curve_default_revision']==original['revision']
    assert any(m.value=='**Condition:** Source SOC 20% · Mean' for m in app.markdown)

    # Switching a proposed version must not adopt a concurrent DB revision.
    s.set_default(r['release_id'],'soc50.lower_limit',a.user_id,original['revision'])
    concurrent=s.get_default()
    app.selectbox(key='curve_default_version').select(r['release_id']).run()
    assert not app.exception
    assert app.error
    assert app.session_state['review_curve_default_revision']==original['revision']
    assert next(v for v in app.button if v.label=='Apply as sizing default').disabled
    assert s.get_default()==concurrent


def test_current_default_summary_does_not_follow_a_pending_condition(runtime,monkeypatch):
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    original=s.get_default()
    app=AppTest.from_function(_admin_current_default_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception and not app.error

    app.selectbox(key='curve_default_condition').select('soc50.lower_limit').run()
    assert not app.exception and not app.error
    assert app.selectbox(key='curve_default_condition').value=='soc50.lower_limit'
    assert any(m.value=='**Condition:** Source SOC 20% · Mean' for m in app.markdown)
    assert not any(m.value=='**Condition:** Source SOC 50% · Lower limit' for m in app.markdown)
    assert s.get_default()==original


def test_malformed_default_condition_keeps_admin_recovery_available(runtime,monkeypatch):
    from calb_sizing_tool.ui import curve_release_controls
    s,a,b,r=runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    original=s.get_default()
    load_context=curve_release_controls.load_curve_admin_context
    def broken_context(db_url=None):
        context=load_context(db_url)
        context['binding']=dict(context['binding'],family_key='broken')
        return context
    monkeypatch.setattr(curve_release_controls,'load_curve_admin_context',broken_context)
    app=AppTest.from_function(_admin_current_default_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.run()
    assert not app.exception
    assert any('current default condition is unavailable' in error.value for error in app.error)
    assert app.selectbox(key='curve_default_version').value==r['release_id']
    assert app.selectbox(key='curve_default_condition').value=='soc20.mean'
    assert not next(v for v in app.button if v.label=='Apply as sizing default').disabled

    app.selectbox(key='curve_default_condition').select('soc50.mean').run()
    assert not app.exception
    assert app.selectbox(key='curve_default_condition').value=='soc50.mean'
    assert not next(v for v in app.button if v.label=='Apply as sizing default').disabled
    assert s.get_default()==original


def test_curve_ui_labels_sort_conditions_numerically_with_mean_first():
    from calb_sizing_tool.ui.curve_labels import sorted_family_keys, family_label
    payload={'curves':[dict(soc_pct=soc,basis=series,power_rate=.25,cycles_per_day=1)
        for soc in (100,20,50) for series in ('lower_limit','mean')]}
    assert sorted_family_keys(payload)==[
        'soc20.mean','soc20.lower_limit','soc50.mean','soc50.lower_limit',
        'soc100.mean','soc100.lower_limit']
    assert family_label('soc20.mean')=='Source SOC 20% · Mean'


@pytest.mark.parametrize('stored,expected',[
    ('SOC20-screenshot-RTE-review-20261118','18 Nov 2026 · RTE in 5% SOH bands'),
    ('SOC20-local-review-20261118-r2','18 Nov 2026 · Original RTE bands (r2)'),
    ('SOC20-local-review-20261118','18 Nov 2026 · Initial review'),
    ('Customer SOC20 custom revision','Customer SOC20 custom revision'),
])
def test_curve_ui_display_names_preserve_stored_identity_and_unmapped_names(stored,expected):
    from calb_sizing_tool.ui.curve_labels import curve_version_label
    release=dict(version_label=stored,release_id='fixed-identity')
    original=deepcopy(release)
    assert curve_version_label(release)==expected
    assert release==original


def test_high_effective_rate_is_not_approved_by_nearest_source(runtime):
    s,a,b,r=runtime
    bundle,basis=s.prepare(b,s.get_default(),life_years=2,cycles_per_year=365)
    case=SizingCaseInput(poi_power_req_mw=4,poi_energy_req_mwh=1,project_life_years=2)
    with pytest.raises(ValueError,match='C-rate exceeds'):
        attach_curve_basis(run_dc_pipeline(case,bundle),basis)


def _curve_choice_result_app():
    import streamlit as st
    from calb_sizing_tool.ui.curve_release_controls import render_curve_choice
    st.session_state['choice_result']=render_curve_choice(st.session_state.setdefault('inputs',{}))


def _stub_curve_library(monkeypatch,releases):
    from calb_sizing_tool.ui import curve_release_controls
    class StubService:
        def __init__(self,db_url=None):pass
        def list_releases(self):return releases
        def get_default(self):return None
    monkeypatch.setattr(curve_release_controls,'CurveReleaseService',StubService)


def test_retired_saved_choice_requires_explicit_legacy_selection_when_no_releases_remain(monkeypatch):
    _stub_curve_library(monkeypatch,[dict(release_id='retired-version',status='retired')])
    saved=dict(release_id='retired-version',family_key='soc20.mean',payload_sha256='old-hash')
    app=AppTest.from_function(_curve_choice_result_app,default_timeout=30)
    app.session_state['inputs']={'curve_selection':saved}
    app.run()
    assert not app.exception
    assert app.session_state['choice_result']=={'unavailable':True}
    assert app.warning and app.error
    assert app.session_state['inputs']['curve_selection']==saved
    assert app.selectbox(key='dc_inputs.curve_selection_token').value=='unavailable'

    app.selectbox(key='dc_inputs.curve_selection_token').select('legacy').run()
    assert not app.exception and not app.error
    assert app.session_state['choice_result'] is None
    assert app.session_state['inputs']['curve_selection'] is None


def test_empty_initial_curve_library_preserves_legacy_without_blocking(monkeypatch):
    _stub_curve_library(monkeypatch,[])
    app=AppTest.from_function(_curve_choice_result_app,default_timeout=30).run()
    assert not app.exception and not app.error and not app.warning
    assert app.session_state['choice_result'] is None
    assert not app.selectbox
