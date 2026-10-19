"""Local-only review UI; deliberately does not write legacy AC/SLD contracts."""
import json
import math
import streamlit as st
from calb_sizing_tool.ui._ui import render_static_table
from calb_sizing_tool.services.cabinet_ac_preview_service import build_cabinet_groups, build_candidates


def show(count,total_mwh,codes,target_mw,target_mwh,source_run_id):
    st.subheader('418 kWh Cabinets: Independent DC Group AC Review')
    st.info('Local concept review: 1–12 cabinets per independent DC group, with one PCS per group. Adjust the group count below; physical cabinet quantities and DC sizing results remain unchanged.')
    st.warning('Concept candidates only. PCS installed MW does not establish net POI output. Current, continuous power, ports, protection, environmental derating and P/Q capability require validation. This page does not save formal AC runs or feed the existing SLD, layout or report workflows. Historical AC records remain unchanged.')
    a,b,c,d=st.columns(4)
    a.metric('Physical Cabinets',str(count));b.metric('DC Nameplate Energy',f'{total_mwh:.3f} MWh')
    c.metric('POI Power Requirement',f'{target_mw:.3f} MW');d.metric('POI Energy Requirement',f'{target_mwh:.3f} MWh')
    key=f'cabinet_group_count_{source_run_id}_{count}'
    groups=int(st.number_input('Independent DC Group Count',min_value=math.ceil(count/12),max_value=count,
               value=math.ceil(count/12),step=1,key=key))
    try:
        plan=build_cabinet_groups(count,total_mwh,codes,groups)
        candidates=build_candidates(plan,target_mw)
    except ValueError as exc:
        st.error(str(exc));return
    st.caption(f'Independent groups: {groups}; cabinets per group: '+ ' / '.join(str(g['cabinet_count']) for g in plan['groups']))
    render_static_table([{'DC Group':f"G{g['group_index']}",'Physical Cabinet Range':f"C{g['cabinet_indices'][0]:02d}—C{g['cabinet_indices'][-1]:02d}",
               'Cabinets':g['cabinet_count'],'DC Nameplate (MWh)':f"{g['nameplate_mwh']:.3f}",'Assigned PCS':f"PCS{g['pcs_index']}"} for g in plan['groups']])
    st.caption('Up to eight group-connected PCS units form one AC Block in this review. This is independent of the legacy physical-cabinet grouping ratios. Tail blocks use actual PCS counts without adding fictitious units.')
    with st.expander('View All Concept Candidates and Installed-Power Gaps',expanded=False):
        render_static_table([{'Candidate':c['candidate_key'],'AC Blocks':len(c['ac_blocks']),'Total PCS Units':c['pcs_count'],
            'PCS Unit Rating (kW)':c['pcs_unit_kw'],'Installed PCS Power (MW)':f"{c['station_pcs_nameplate_mw']:.3f}",
            'Installed Power minus POI Requirement (MW)':f"{c['nameplate_delta_mw']:+.3f}",
            'Status':'Installed rating sufficient; capability unverified' if c['nameplate_meets_poi_number'] else 'Installed rating below requirement'} for c in candidates])
    def label(i):
        c=candidates[i]
        return f"{len(c['ac_blocks'])} AC Block(s) · {c['pcs_count']} × {c['pcs_unit_kw']} kW PCS · Installed {c['station_pcs_nameplate_mw']:.3f} MW"
    chosen=st.selectbox('Select an AC Candidate for Review',range(len(candidates)),format_func=label,
                        key=f'cabinet_candidate_{source_run_id}_{groups}')
    candidate=candidates[chosen]
    if not candidate['nameplate_meets_poi_number']:
        st.error('Selected PCS installed power is below the POI power requirement. This candidate cannot be treated as meeting the requirement.')
    render_static_table([{'AC Block':b['ac_block_index'],'DC Groups':', '.join('G'+str(i) for i in b['group_indices']),
               'Cabinets':b['cabinet_count'],'DC Nameplate (MWh)':f"{b['nameplate_mwh']:.3f}",
               'PCS Configuration':f"{b['pcs_count']} × {b['pcs_unit_kw']} kW",'Installed PCS Power (MW)':f"{b['pcs_nameplate_mw']:.3f}"} for b in candidate['ac_blocks']])
    payload=dict(source_dc_run_id=source_run_id,dc_group_plan=plan,candidate={k:v for k,v in candidate.items() if k!='_identity'},
                 document_status='local_concept_review',poi_energy_requirement_mwh=target_mwh)
    st.download_button('Download Concept Review (JSON)',json.dumps(payload,ensure_ascii=False,indent=2).encode('utf-8'),
                       file_name='CALB_Cabinet_AC_Concept_Review.json',mime='application/json')
