"""Cabinet arrangements in the original Typical AC Block Arrangement page."""
import streamlit as st

from calb_diagrams.cabinet_sld import _validate_output
from calb_sizing_tool.services.cabinet_arrangement_service import (
    PLUGIN_ID, PACKAGE_KIND, MANIFEST_KIND, input_signature, generate_cabinet_arrangement,
    restore_cabinet_arrangement, select_cabinet_arrangement_sheet,
)
from calb_sizing_tool.ui.cabinet_document_context import cabinet_document_context
from calb_sizing_tool.ui._ui import render_pipeline_next_steps, render_static_table


def show_cabinet_arrangement(output, *, parent_run_id, workspace, is_guest, auth_user, authoritative,
                              installation_basis=None):
    try:
        plan, _, _ = _validate_output(output)
    except ValueError as exc:
        st.error(f'Cabinet arrangement input is invalid: {exc}. Recalculate AC Sizing.')
        return
    context = cabinet_document_context(output, parent_run_id=parent_run_id, workspace=workspace,
        is_guest=is_guest, auth_user=auth_user, authoritative=authoritative)
    if context is None:
        render_pipeline_next_steps('Typical AC Block Arrangement', is_guest=is_guest)
        return
    child, _ = context
    st.subheader('Cabinet AC Block Arrangement')
    st.caption('Actual cabinet groups and PCS assignments from the selected AC configuration.')
    st.warning('CONCEPT / NOT FOR CONSTRUCTION. Relative equipment positions only; not to scale. '
               'The drawing does not establish a site area, installation spacing or approved access route.')
    blocks = sorted({group['ac_block_index'] for group in plan['groups']})
    selected = st.selectbox('AC Block to preview', blocks, format_func=lambda value: f'AC Block {value}',
        key=f'cabinet_arrangement_block_{child or parent_run_id}')
    st.caption(f"{plan['physical_cabinet_count']} cabinets / {len(plan['groups'])} independent DC groups / "
               f'{len(blocks)} AC Blocks. All sheets are generated together.')
    signature = input_signature(output, parent_run_id, child, installation_basis)
    bundle = st.session_state.get('layout_artifacts')
    if not (getattr(bundle, 'plugin_id', None) == PLUGIN_ID and bundle.metadata.get('signature') == signature
            and bundle.metadata.get('selected_ac_block') == selected):
        previous = bundle
        bundle = None
        st.session_state.pop('layout_artifacts', None)
        if getattr(previous, 'plugin_id', None) == PLUGIN_ID:
            bundle, failures = select_cabinet_arrangement_sheet(previous, output, selected_block=selected,
                parent_run_id=parent_run_id, ac_run_id=child, installation_basis=installation_basis)
            for failure in failures:
                st.warning(failure)
        if bundle is None and not is_guest:
            try:
                bundle, failures = restore_cabinet_arrangement(output, selected_block=selected,
                    parent_run_id=parent_run_id, ac_run_id=child, installation_basis=installation_basis)
                for failure in failures:
                    st.warning(failure)
            except Exception:
                st.warning('The saved arrangement could not be restored. Retry before assuming no drawing exists.')
        if bundle:
            st.session_state['layout_artifacts'] = bundle
    if st.button('Generate Cabinet Arrangement', type='primary', key='generate_cabinet_arrangement'):
        try:
            bundle = generate_cabinet_arrangement(output, selected_block=selected, parent_run_id=parent_run_id,
                ac_run_id=child, register=not is_guest, actor=getattr(auth_user, 'username', None),
                installation_basis=installation_basis)
        except Exception as exc:
            st.error(f'Cabinet arrangement generation failed: {exc}')
            return
        st.session_state['layout_artifacts'] = bundle
        st.success('Cabinet arrangement saved to the selected AC alternative.' if not is_guest
                   else 'Cabinet arrangement generated for this guest session only.')
    if bundle:
        payloads = {a['artifact_kind']: a for a in bundle.artifacts}
        st.subheader('Concept Preview')
        if 'layout_png' in payloads:
            st.image(payloads['layout_png']['content'], use_container_width=True)
        else:
            svg = payloads['layout_svg']['content'].decode().replace('<svg ', '<svg style="width:100%;height:auto;" ', 1)
            st.components.v1.html(svg, height=850, scrolling=True)
        with st.expander('Equipment and group schedule'):
            render_static_table([{'AC Block': group['ac_block_index'], 'Group': group['group_index'],
                'PCS': group['pcs_index'], 'Cabinets': ', '.join(f'C{n:03d}' for n in group['cabinet_indices']),
                'DC nameplate (MWh)': f"{group['nameplate_mwh']:.3f}"} for group in plan['groups']])
        with st.expander('Installation evidence and remaining interfaces'):
            for warning in bundle.metadata.get('warnings', []):
                st.write(warning)
            st.caption('A fire-test specimen arrangement does not automatically establish a general installation minimum. '
                       'Use the applicable equipment manual, test conditions and project approval basis together.')
        st.subheader('Downloads')
        for kind, label in [('layout_svg', 'Download Cabinet Arrangement SVG'),
                            ('layout_png', 'Download Cabinet Arrangement PNG'),
                            (PACKAGE_KIND, 'Download All Cabinet Arrangement Sheets'),
                            (MANIFEST_KIND, 'Download Cabinet Arrangement Schedule')]:
            item = payloads.get(kind)
            if item:
                st.download_button(label, item['content'], file_name=item['file_name'], mime=item['media_type'],
                    key=f'cabinet_arrangement_download_{kind}')
        st.caption(f'Previewing AC Block {selected}. Switching sheets does not regenerate or save another drawing.')
    render_pipeline_next_steps('Typical AC Block Arrangement', is_guest=is_guest)
