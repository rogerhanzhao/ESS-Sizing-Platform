"""Native input fields and existing HTML tables, without Arrow editors."""
import streamlit as st
from calb_sizing_tool.services.rte_matrix_service import NODES
from calb_sizing_tool.services.rte_review_service import _curve_rows


def render_test_inputs(initial,key):
    anchors=(initial.get('rte_rule') or {}).get('test_anchors',[])
    existing={(a['rate'],a['soh_pct']):a for a in anchors}
    source_labels={'test':'Entered test value','engineering_override':'Entered engineering value'}
    source_choices=list(source_labels)
    source_key=key+'_source_kind'
    source_current=st.session_state.get(source_key,source_choices[0])
    kind=st.selectbox('Input source for new or changed values',source_choices,
                      index=source_choices.index(source_current) if source_current in source_choices else 0,
                      format_func=source_labels.__getitem__,key=source_key,
                      help='Source type records the administrator’s classification of the entered value.')
    header=st.columns([1,2,2,2])
    for col,label in zip(header,['SOH (%)','0.5P RTE (%)','0.33P RTE (%)','0.25P RTE (%)']):col.caption(label)
    result=[]
    for h in NODES:
        cols=st.columns([1,2,2,2]);cols[0].caption(f'{h:g}%')
        for col,rate in zip(cols[1:],(.5,.33,.25)):
            old=existing.get((rate,h))
            field_key=f'{key}_tests_{rate}_{h}'
            v=col.number_input(f'{rate:g}P at SOH {h:g}%',min_value=.0001,max_value=100.,
                value=st.session_state.get(field_key,float(old['rte_pct']) if old else None),step=.01,format='%.2f',
                placeholder='No input',label_visibility='collapsed',key=field_key)
            if v is not None:
                result.append(dict(rate=rate,soh_pct=h,rte_pct=v,
                                   source_kind=old['source_kind'] if old and v==old['rte_pct'] else kind))
    st.caption('Leave a cell empty when no test or engineering value is available. Clear a value to remove that input; zero is not an empty cell.')
    return result


def render_detailed_rte_rows(initial,key):
    rows=_curve_rows(initial)
    with st.expander('Original band inputs',expanded=False):
        for rate in (.25,.33,.5):
            st.caption(f'{rate:g}C — raw DC RTE percentages')
            fields=st.columns(3)
            for i,row in enumerate(r for r in rows if r['rate']==rate):
                field_key=f"{key}_raw_{row['row']}"
                row['rte_pct']=fields[i%3].number_input(
                    f"SOH minimum {row['soh_min_pct']:g}% · row {i+1}",
                    min_value=.0001,max_value=100.,value=st.session_state.get(field_key,float(row['rte_pct'])),step=.01,
                    format='%.2f',key=field_key)
    return rows
