from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from test_curve_release import runtime
from test_rte_review import rte_runtime, _admin_rte_app
from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package
from calb_sizing_tool.services.rte_review_service import _curve_rows, annual_rte_preview
from calb_sizing_tool.ui import rte_annual_preview
from calb_sizing_tool.ui.rte_annual_preview import annual_rte_display_rows


def _point(rate,cycles,year,soh,rte,low=False):
    return dict(rate=rate,cycles_day=cycles,year=year,soh_pct=soh,
                dc_rte_pct=rte,legacy_low_soh_fallback=low)


@pytest.fixture
def preview_rows():
    # Deliberately unordered years and distinct operating groups make an
    # accidental combined table or cross-group gap fill observable.
    return [
        _point(.25,1,2,92.123456,93.087654),
        _point(.5,2,3,59.87654,90.123456,True),
        _point(.25,.5,1,97.54321,93.111111),
        _point(.25,1.5,2,90.45678,92.99999),
        _point(.25,1,0,100.,94.),
        _point(.5,2,0,100.,92.56),
        _point(.25,.5,0,100.,94.),
        _point(.25,1,1,94.999999,93.71727773247174),
        _point(.5,2,1,98.12345,92.345678),
        _point(.25,1.5,0,100.,94.),
    ]


def test_annual_display_formats_two_decimals_without_changing_source_precision(preview_rows):
    original=deepcopy(preview_rows)
    rows=annual_rte_display_rows(preview_rows,.25,1)
    assert rows==[
        {'Year':0,'SOH (%)':'100.00','DC RTE (%)':'94.00'},
        {'Year':1,'SOH (%)':'95.00','DC RTE (%)':'93.72'},
        {'Year':2,'SOH (%)':'92.12','DC RTE (%)':'93.09'},
    ]
    assert preview_rows==original
    boundary=next(row for row in preview_rows if row['rate']==.25 and row['cycles_day']==1 and row['year']==1)
    assert boundary['soh_pct']==94.999999
    assert boundary['dc_rte_pct']==93.71727773247174


def test_annual_display_marks_missing_years_without_filling_or_extending_the_tail(preview_rows):
    data=deepcopy(preview_rows)+[_point(.5,2,8,None,None)]
    original=deepcopy(data)
    rows=annual_rte_display_rows(data,.5,2)
    assert [row['Year'] for row in rows]==[0,1,2,3]
    assert rows[2]['SOH (%)']==rows[2]['DC RTE (%)']=='N/A'
    assert rows[0]['Basis']==rows[1]['Basis']=='SOH band'
    assert rows[3]['Basis']=='Low-SOH reference'
    assert rows[3]['SOH (%)']=='59.88'
    assert data==original
    assert annual_rte_display_rows(data,.33,1)==[]


def _annual_preview_app():
    import streamlit as st
    from calb_sizing_tool.ui.rte_annual_preview import render_annual_rte_preview
    render_annual_rte_preview(st.session_state['annual_preview_input'],'annual_probe')


def _capture_tables(monkeypatch):
    captured=[]
    original=rte_annual_preview.render_static_table
    def capture(data,*args,**kwargs):
        rows=data.to_dict(orient='records') if hasattr(data,'to_dict') else data
        captured.append(deepcopy(rows))
        return original(data,*args,**kwargs)
    monkeypatch.setattr(rte_annual_preview,'render_static_table',capture)
    return captured


def test_annual_preview_selects_one_group_and_corrects_an_unavailable_frequency(preview_rows,monkeypatch):
    original=deepcopy(preview_rows)
    captured=_capture_tables(monkeypatch)
    app=AppTest.from_function(_annual_preview_app,default_timeout=30)
    app.session_state['annual_preview_input']=deepcopy(preview_rows)
    app.run()
    assert not app.exception and not app.error
    assert app.selectbox(key='annual_probe_rate').value==.25
    cycles=app.selectbox(key='annual_probe_cycles')
    assert cycles.value==1 and cycles.proto.default==1
    assert captured[-1]==annual_rte_display_rows(original,.25,1)

    captured.clear()
    app.selectbox(key='annual_probe_cycles').set_value(1.5).run()
    assert not app.exception and not app.error
    assert app.selectbox(key='annual_probe_cycles').proto.default==2
    assert captured[-1]==annual_rte_display_rows(original,.25,1.5)
    assert [row['Year'] for row in captured[-1]]==[0,1,2]
    assert captured[-1][1]['SOH (%)']=='N/A'

    # The prior 1.5/day is absent at 0.5P; use its actual 2/day group.
    captured.clear()
    app.selectbox(key='annual_probe_rate').set_value(.5).run()
    assert not app.exception and not app.error
    assert app.selectbox(key='annual_probe_rate').proto.default==1
    cycles=app.selectbox(key='annual_probe_cycles')
    assert cycles.value==2 and cycles.proto.default==0
    assert captured[-1]==annual_rte_display_rows(original,.5,2)
    assert [row['Year'] for row in captured[-1]]==[0,1,2,3]

    # On return, 2/day is absent and the preferred 1/day is available again.
    captured.clear()
    app.selectbox(key='annual_probe_rate').set_value(.25).run()
    assert not app.exception and not app.error
    assert app.selectbox(key='annual_probe_cycles').value==1
    assert app.selectbox(key='annual_probe_cycles').proto.default==1
    assert captured[-1]==annual_rte_display_rows(original,.25,1)
    assert app.session_state['annual_preview_input']==original


def test_saved_draft_preview_choices_do_not_change_its_values_hash_or_publication_state(rte_runtime,monkeypatch):
    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    proposed=build_screenshot_package(base['payload'])
    did=review.save_draft(base['release_id'],'Read-only annual preview',_curve_rows(proposed),
                         'Review a single operating group without changing its inputs',a.user_id,
                         matrix_config={'test_anchors':[]})
    original=next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)
    original_default=s.get_default()
    captured=_capture_tables(monkeypatch)
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.session_state['rte_draft_choice']=did
    app.run()
    assert not app.exception and not app.error
    assert not app.button(key='rte_publish_draft').disabled
    next(item for item in app.selectbox if item.label=='Source rate label').set_value(.5).run()
    captured.clear()
    next(item for item in app.selectbox if item.label=='Cycles/day').set_value(2).run()
    assert not app.exception and not app.error
    assert captured[-1]==annual_rte_display_rows(annual_rte_preview(original['payload'],'soc20.mean'),.5,2)
    assert not app.button(key='rte_publish_draft').disabled
    assert not any('Save current edits before publishing' in item.value for item in app.info)
    assert next(d for d in review.list_drafts(a.user_id) if d['draft_id']==did)==original
    assert s.get_default()==original_default


def test_operating_condition_preview_keeps_the_latest_unsaved_rte_inputs(rte_runtime,monkeypatch):
    s,a,b,base,review=rte_runtime
    monkeypatch.setenv('CALB_DATABASE_URL',s.db_url)
    original_releases=s.list_releases()
    original_drafts=review.list_drafts(a.user_id)
    original_default=s.get_default()
    captured=_capture_tables(monkeypatch)
    app=AppTest.from_function(_admin_rte_app,default_timeout=30)
    app.session_state['review_actor']=a.user_id
    app.session_state['rte_base_release']=base['release_id']
    app.run()
    assert not app.exception and not app.error

    raw=95.678901
    next(item for item in app.number_input if item.label=='0.25P at SOH 100%').set_value(raw).run()
    assert not app.exception and not app.error
    assert captured[-1][0]['DC RTE (%)']=='95.68'

    captured.clear()
    family_key=f"rte_family_{base['release_id']}_new"
    app.selectbox(key=family_key).set_value('soc50.mean').run()
    cycles_key=f"rte_annual_{base['release_id']}_new_soc50.mean_cycles"
    app.selectbox(key=cycles_key).set_value(2).run()
    assert not app.exception and not app.error
    assert captured[-1][0]['DC RTE (%)']=='95.68'
    assert next(item for item in app.number_input if item.label=='0.25P at SOH 100%').value==raw
    assert app.button(key='rte_publish_draft').disabled
    assert s.list_releases()==original_releases
    assert review.list_drafts(a.user_id)==original_drafts
    assert s.get_default()==original_default
