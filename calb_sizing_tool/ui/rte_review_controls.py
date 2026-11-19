"""Administrator RTE working copies on the existing Degradation page."""
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from calb_sizing_tool.services.curve_release_service import CurveReleaseService
from calb_sizing_tool.services.rte_review_service import (
    RteReviewService, _curve_rows, derive_legacy_rte, edited_rte_payload,
)
from calb_sizing_tool.ui.curve_labels import curve_version_label, rte_basis_label
from calb_sizing_tool.ui._ui import render_static_table
from calb_sizing_tool.ui.rte_input_forms import render_test_inputs, render_detailed_rte_rows
from calb_sizing_tool.ui.rte_annual_preview import render_annual_rte_review_preview
from calb_sizing_tool.services.rte_matrix_service import build_screenshot_package, matrix_rows


def render_rte_review(actor,db_url=None):
    with st.expander('Revise RTE',expanded=False):
        st.caption('Edit the RTE inputs, review the relevant operating conditions, save the complete draft, then publish once. '
                   'All conditions in the version are retained; individual preview approvals are not recorded.')
        try:
            releases=CurveReleaseService(db_url).list_releases()
            releases={r['release_id']:r for r in releases if r['status']=='published'}
            if not releases:
                st.caption('Publish a verified SOH curve version first, then review its RTE reference table here.')
                return
            service=RteReviewService(db_url)
            drafts=service.list_drafts(actor)
            pending=st.session_state.pop('rte_pending_draft',None)
            choices=['new']+[d['draft_id'] for d in drafts if d['status']=='draft']
            if pending in choices:st.session_state['rte_draft_choice']=pending
            if st.session_state.get('rte_draft_choice','new') not in choices:st.session_state['rte_draft_choice']='new'
            token=st.selectbox('Working draft',choices,key='rte_draft_choice',
                index=choices.index(st.session_state.get('rte_draft_choice','new')),
                format_func=lambda k:'New draft' if k=='new' else
                    f"Draft {choices.index(k)} — {curve_version_label(next(d for d in drafts if d['draft_id']==k))}")
            draft=next((d for d in drafts if d['draft_id']==token),None)
            review_key='rte_reviewed_draft'
            if draft:
                reviewed=dict(draft_id=token,sha256=draft['sha256'],
                              version_label=draft['version_label'],review_note=draft['review_note'])
                previous=st.session_state.get(review_key)
                if previous and previous['draft_id']==token and previous!=reviewed:
                    st.error('This RTE working draft changed during review. Reload it and review the current inputs before saving or publishing.')
                    if st.button('Reload draft',key='rte_reload_draft'):
                        st.session_state[review_key]=reviewed
                        st.rerun()
                    return
                st.session_state[review_key]=reviewed
            else:
                st.session_state.pop(review_key,None)
            if draft:
                base_id=draft['base_release_id']
                # A base can be retired after the draft was started; its
                # immutable data are still available for review/publication.
                base=CurveReleaseService(db_url).get_release(base_id)
                initial=draft['payload']
                label=draft['version_label'];reason=draft['review_note']
                st.caption('Editing a saved draft. Published values stay unchanged.')
            else:
                base_choices=list(releases)
                base_current=st.session_state.get('rte_base_release',base_choices[0])
                base_id=st.selectbox('Base curve version',base_choices,key='rte_base_release',
                                     index=base_choices.index(base_current) if base_current in base_choices else 0,
                                     format_func=lambda k:curve_version_label(releases[k]))
                base=releases[base_id]
                initial=base['payload'] if base['payload'].get('rte_rule') else derive_legacy_rte(base['payload'])
                label=curve_version_label(base)+' – RTE revision';reason=''
            with st.expander('Version details',expanded=False):
                st.caption('Published base name: '+base['version_label'])
                st.caption('RTE basis: '+rte_basis_label(initial))
                if initial.get('rte_version'):st.caption('RTE version reference: '+initial['rte_version'])
            model=(initial.get('rte_rule') or {}).get('model')
            structures=['Screenshot five-percent SOH bands','Legacy detailed bands']
            structure_key=f'rte_structure_{base_id}'
            structure_current=st.session_state.get(structure_key,structures[0])
            screenshot = model=='screenshot_5pct' if draft else st.radio(
                'RTE table format',structures,
                index=structures.index(structure_current) if structure_current in structures else 0,
                format_func=lambda value:{'Screenshot five-percent SOH bands':'SOH bands (5%)',
                                          'Legacy detailed bands':'Original detailed bands'}[value],
                key=structure_key)=='Screenshot five-percent SOH bands'
            key=f"rte_editor_{base_id}_{token}_{draft['sha256'] if draft else 'new'}"
            matrix_config=None
            st.subheader('RTE inputs')
            if screenshot:
                st.caption('Optional test or engineering values at the listed SOH nodes. SOH is capacity retention; these rows are not source SOC conditions.')
                anchors=render_test_inputs(initial,key)
                proposed=build_screenshot_package(base['payload'],anchors)
                matrix_config=dict(test_anchors=anchors)
                rows=_curve_rows(proposed)
                st.subheader('Calculated RTE reference table')
                st.caption('Entered values are retained. Other cells are filled by the reference model and are not test results.')
                render_static_table([{k:f'{v:.2f}' if isinstance(v,(int,float)) else v
                                      for k,v in row.items()} for row in matrix_rows(proposed)])
            else:
                st.caption('Review or edit the original RTE band values below.')
                rows=render_detailed_rte_rows(initial,key)
            name_key=f'rte_name_{base_id}_{token}'
            note_key=f'rte_reason_{base_id}_{token}'
            name=st.text_input('New version name',value=st.session_state.get(name_key,label),key=name_key)
            note=st.text_area('Review note / applicability',value=st.session_state.get(note_key,reason),key=note_key)
            if not screenshot:proposed=edited_rte_payload(base['payload'],rows,note)
            with st.expander('Calculation method and applicability',expanded=False):
                st.write('Source SOC is the supplier workbook’s operating-condition label. It does not establish a constant standby SOC and is not DOD. SOH is capacity retention relative to BOL.')
                st.write('Mean and Lower limit identify the source curve series; neither label alone establishes a performance guarantee.')
                st.write('Original rate rule: RTE(0.5C) = RTE(0.25C) − 1.6 × [RTE(0.25C) − RTE(0.33C)]. The recorded epsilon note has no verified executable branch and is not used to invent an additional formula.')
                st.write('The supplied P labels are retained in the five-percent table. Their pairing with existing runtime profiles does not prove that every definition of P and C is equivalent.')
                if screenshot:
                    st.write(proposed['rte_rule']['matching'])
                    st.write(proposed['rte_rule']['preparation'])
                    origins={'test':'Entered test value','engineering_override':'Entered engineering value',
                             'legacy_model':'Legacy model reference','interpolated':'Interpolated value',
                             'legacy_model_calibrated':'Calibrated legacy model','rate_derived':'Derived from rate model',
                             'legacy_low_soh_fallback':'Legacy low-SOH fallback'}
                    explanation=pd.DataFrame(proposed['rte_rule']['calculation_rows'])
                    for column in ('soh_pct', 'rte_pct'):
                        explanation[column]=explanation[column].map(lambda value:f'{value:.2f}')
                    explanation['origin']=explanation['origin'].map(lambda value:origins.get(value,value))
                    render_static_table(explanation.rename(columns={'rate':'Source rate label','soh_pct':'SOH (%)',
                        'rte_pct':'DC RTE (%)','origin':'Value source','calculation':'Calculation'}))
                st.caption('Below 60% SOH, the separate original-model fallback is retained. It is not new supplier test evidence. Entered classifications are supplied by the administrator; calculated reference values do not by themselves establish a supplier guarantee.')
            binding=CurveReleaseService(db_url).get_binding()
            preferred=binding['family_key'] if binding else 'soc20.mean'
            render_annual_rte_review_preview(proposed,f'{base_id}_{token}',preferred)
            st.markdown('**Save and publish the complete version**')
            if st.button('Save complete draft',key='rte_save_draft'):
                draft_id=service.save_draft(base_id,name,rows,note,actor,
                    draft_id=draft['draft_id'] if draft else None,expected_sha=draft['sha256'] if draft else None,
                    matrix_config=matrix_config)
                st.session_state.pop(review_key,None)
                st.session_state['rte_pending_draft']=draft_id;st.rerun()
            unchanged=False
            if draft:
                unchanged=(name==draft['version_label'] and note==draft['review_note']
                           and rows==_curve_rows(draft['payload']))
                if screenshot:
                    # Equal numeric values can still carry new test evidence.
                    # Publication must include the saved sources as well as values.
                    order=lambda a:(a['rate'],a['soh_pct'])
                    unchanged = unchanged and sorted(anchors,key=order) == sorted(
                        draft['payload']['rte_rule'].get('test_anchors', []),key=order)
                if not unchanged:st.info('Save current edits before publishing. Publication uses the saved draft only.')
            else:
                st.caption('Save the complete draft first to enable publication.')
            if st.button('Publish complete curve version',disabled=not unchanged,key='rte_publish_draft'):
                service.publish_draft(draft['draft_id'],actor,draft['sha256'])
                st.success('Complete curve version published. Open Curve versions — apply, roll back and stop to apply it as the sizing default if required.')
                st.rerun()
            st.caption('Publishing creates a new SOH + RTE version with the same SOH data. It does not switch the default or change previous runs.')
            st.caption('Saving, publishing and applying a default do not run SIZING. Click Run Sizing on the project page to calculate.')
        except (ValueError,PermissionError,SQLAlchemyError) as exc:
            st.error(str(exc))
