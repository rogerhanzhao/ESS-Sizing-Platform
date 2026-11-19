from copy import deepcopy
import pytest
import pandas as pd
from streamlit.testing.v1 import AppTest
from test_curve_release import runtime
from test_rte_review import rte_runtime
from test_rte_review import _admin_rte_app
from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package,matrix_rows,NODES
from calb_sizing_tool.services.rte_review_service import _curve_rows
from calb_sizing_tool.infra.db.models import RteCurveBand, RteProfile
from calb_sizing_tool.infra.db.models.curve_release import CurveRelease
from calb_sizing_tool.infra.db.session import session_scope


def test_screenshot_grid_is_complete_and_no_inputs_are_claimed_as_measurements(rte_runtime):
    s,a,b,base,review=rte_runtime
    p=build_screenshot_package(base['payload'])
    assert len(matrix_rows(p))==9 and len(p['rte_bands'])==30
    assert p['curves']==base['payload']['curves']
    assert p['rte_rule']['test_anchors']==[]
    assert set(r['origin'] for r in p['rte_rule']['calculation_rows'])=={'legacy_model','legacy_low_soh_fallback'}
    bol=matrix_rows(p)[0]
    assert bol['0.25P RTE (%)']==94
    assert bol['0.33P RTE (%)']==pytest.approx(93.1)
    assert bol['0.5P RTE (%)']==pytest.approx(92.56)


def test_five_percent_initial_bins_never_improve_old_applied_rte(rte_runtime):
    s,a,b,base,review=rte_runtime
    p=build_screenshot_package(base['payload'])
    for profile in p['rte_profiles']:
        pid=profile['Profile_Id']
        old=pd.DataFrame([r for r in base['payload']['rte_bands'] if r['Profile_Id']==pid]).sort_values('Soh_Band_Min_Pct',ascending=False)
        old['Rte_Dc_Pct']=old.Rte_Dc_Pct.cummin()
        new=pd.DataFrame([r for r in p['rte_bands'] if r['Profile_Id']==pid]).sort_values('Soh_Band_Min_Pct',ascending=False)
        for h in [1.,.999999,.95,.949999,.9,.899999,.85,.8,.75,.7,.65,.6]:
            assert new[new.Soh_Band_Min_Pct<=h].Rte_Dc_Pct.iloc[0]<=old[old.Soh_Band_Min_Pct<=h].Rte_Dc_Pct.iloc[0]+1e-14


def test_test_points_lock_intermediate_nodes_interpolate_and_other_rate_derives(rte_runtime):
    s,a,b,base,review=rte_runtime
    anchors=[dict(rate=r,soh_pct=h,rte_pct=v) for r,h,v in [(.25,100,95.),(.25,90,93.),(.33,100,94.),(.33,90,92.)]]
    p=build_screenshot_package(base['payload'],anchors)
    rows=p['rte_rule']['calculation_rows']
    find=lambda rate,h:next(r for r in rows if r['rate']==rate and r['soh_pct']==h)
    assert find(.25,100)['rte_pct']==95
    assert find(.25,95)['rte_pct']==94
    assert find(.25,95)['origin']=='interpolated'
    assert find(.5,95)['rte_pct']==pytest.approx(92.4)
    assert find(.5,95)['origin']=='rate_derived'
    assert find(.25,85)['origin']=='legacy_model_calibrated'


def test_one_bol_input_calibrates_old_shape_without_claiming_lifetime_tests(rte_runtime):
    s,a,b,base,review=rte_runtime
    p=build_screenshot_package(base['payload'],[dict(rate=.5,soh_pct=100,rte_pct=92.3)])
    initial=build_screenshot_package(base['payload'])
    for row,old in zip(p['rte_rule']['calculation_rows'],initial['rte_rule']['calculation_rows']):
        if row['rate']==.5:
            assert row['rte_pct']==pytest.approx(old['rte_pct']-.26)
            if row['soh_pct'] not in (0,100):assert row['origin']=='legacy_model_calibrated'


def test_duplicate_or_non_node_inputs_are_rejected(rte_runtime):
    s,a,b,base,review=rte_runtime
    with pytest.raises(ValueError,match='Duplicate'):
        build_screenshot_package(base['payload'],[dict(rate=.5,soh_pct=100,rte_pct=92)]*2)
    with pytest.raises(ValueError,match='listed rate'):
        build_screenshot_package(base['payload'],[dict(rate=.5,soh_pct=97,rte_pct=92)])


def test_new_matrix_draft_roundtrip_and_publish_remain_explicit(rte_runtime):
    s,a,b,base,review=rte_runtime
    old_default=s.get_default();p=build_screenshot_package(base['payload'])
    did=review.save_draft(base['release_id'],'Screenshot RTE',_curve_rows(p),'Screenshot grid review',a.user_id,matrix_config={'test_anchors':[]})
    d=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    assert d['payload']['rte_rule']['model']=='screenshot_5pct'
    rid=review.publish_draft(did,a.user_id,d['sha256'])
    assert s.get_release(rid)['payload']['rte_bands']==p['rte_bands']
    assert s.get_default()==old_default


def test_editor_inputs_immediately_update_calculated_matrix_and_explanation(rte_runtime,monkeypatch):
    from calb_sizing_tool.ui import rte_review_controls
    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    captured=[]
    original=rte_review_controls.render_static_table
    def capture(data,*args,**kwargs):
        captured.append(deepcopy(data));return original(data,*args,**kwargs)
    monkeypatch.setattr(rte_review_controls,'render_static_table',capture)
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id;app.run()
    next(x for x in app.number_input if x.label=='0.25P at SOH 100%').set_value(95.)
    next(x for x in app.number_input if x.label=='0.33P at SOH 100%').set_value(94.)
    captured.clear();app.run()
    assert not app.exception and not app.error
    frames=[pd.DataFrame(data) for data in captured]
    matrix=next(f for f in frames if 'SOH interval' in f.columns)
    assert float(matrix.iloc[0]['0.25P RTE (%)'])==95
    assert float(matrix.iloc[0]['0.33P RTE (%)'])==94
    assert float(matrix.iloc[0]['0.5P RTE (%)'])==pytest.approx(93.4)
    explain=next(f for f in frames if 'Value source' in f.columns)
    assert 'Derived from rate model' in set(explain['Value source'])
    assert 'Calibrated legacy model' in set(explain['Value source'])


def test_new_soh_publication_can_pair_published_rte_without_live_legacy_tables(rte_runtime):
    s,a,b,base,review=rte_runtime
    p=build_screenshot_package(base['payload'])
    did=review.save_draft(base['release_id'],'new paired RTE',_curve_rows(p),'review',a.user_id,matrix_config={'test_anchors':[]})
    d=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    rid=review.publish_draft(did,a.user_id,d['sha256'])
    with session_scope(s.db_url) as db:
        source=db.get(CurveRelease,base['release_id']).source_import_id
        db.query(RteCurveBand).delete();db.query(RteProfile).delete()
    new=s.publish(source,'new SOH paired with selected RTE','Explicit pairing review',a.user_id,rte_release_id=rid)
    assert new['payload']['rte_bands']==p['rte_bands']
    assert new['payload']['rte_rule']['model']=='screenshot_5pct'
    assert new['payload']['rte_source_release_id']==rid
