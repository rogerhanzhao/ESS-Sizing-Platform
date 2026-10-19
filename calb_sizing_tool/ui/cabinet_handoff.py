"""Render the persisted cabinet interface on existing downstream pages."""
import json
import streamlit as st
from calb_sizing_tool.ui._ui import render_static_table, render_pipeline_next_steps
from calb_sizing_tool.state.auth_state import get_auth_context
from calb_sizing_tool.services.cabinet_ac_preview_service import validate_cabinet_contract


def render_cabinet_handoff(output, page):
    if output.get('dc_unit_kind') != 'independent_cabinet_group':
        summary = st.session_state.get('dc_result_summary') or {}
        if output and summary.get('cabinet_count', 0) > 0 and not summary.get('container_count', 0):
            st.warning('This cabinet-only AC result uses the legacy DC Block interface. Recalculate AC Sizing to save independent cabinet groups before generating drawings or reports.')
            return True
        return False
    plan = output.get('cabinet_group_contract')
    try:
        validate_cabinet_contract(plan, allocated=True)
    except ValueError as exc:
        st.error(f'Saved cabinet interface is invalid: {exc}. Recalculate AC Sizing before exporting.')
        return True
    st.subheader('Independent cabinet group schedule')
    st.caption('Saved AC configuration. Group numbers identify independent DC busbars, not 20ft containers.')
    render_static_table([{
        'AC Block': g['ac_block_index'], 'PCS within AC Block': g['pcs_index'],
        'DC group': g['group_index'], 'Cabinets': g['cabinet_count'],
        'Cabinet numbers': ', '.join(str(n) for n in g['cabinet_indices']),
        'DC nameplate (MWh)': f"{g['nameplate_mwh']:.3f}",
    } for g in plan['groups']])
    st.warning('Cabinet-specific physical layout and formal report rendering are not yet available. Generate the cabinet concept SLD on the Single Line Diagram page. '
               'The container renderer is disabled for this configuration. Equipment electrical limits, '
               'cabinet footprints and site clearances require confirmation before issuing drawings.')
    st.download_button('Download saved cabinet interface', json.dumps(plan, indent=2),
                       file_name='cabinet_group_interface.json', mime='application/json',
                       key=f'cabinet_interface_{page}')
    auth = get_auth_context()
    render_pipeline_next_steps(page, is_guest=bool(auth and auth.is_guest))
    return True
