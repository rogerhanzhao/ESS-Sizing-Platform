"""Cabinet SLD controls within the existing saved-AC -> SLD page flow."""
from __future__ import annotations
import streamlit as st
from calb_sizing_tool.services.cabinet_ac_preview_service import validate_cabinet_contract
from calb_sizing_tool.services.cabinet_sld_service import (
    PLUGIN_ID, generate_cabinet_sld, restore_cabinet_sld, input_signature, saved_cabinet_sld_block,
    matching_saved_cabinet_alternative,
    select_cabinet_sld_sheet,
)
from calb_sizing_tool.ui._ui import render_pipeline_next_steps, render_static_table


def _publish(bundle):
    st.session_state['sld_artifacts'] = bundle
    st.session_state['sld_pipeline_meta'] = dict(bundle.metadata)


def show_cabinet_sld(output, *, parent_run_id, workspace, is_guest, auth_user, authoritative):
    try:
        validate_cabinet_contract(output.get('cabinet_group_contract'), allocated=True)
    except ValueError as exc:
        st.error(f'Cabinet SLD input is invalid: {exc}. Recalculate AC Sizing.')
        return
    ac_run_id = None if is_guest else workspace.get('ac_run_id')
    if not is_guest:
        if not authoritative:
            st.warning('Save and select the cabinet AC alternative before generating a traceable SLD.')
            render_pipeline_next_steps('Single Line Diagram', is_guest=False)
            return
        from calb_sizing_tool.infra.db.session import session_scope
        from calb_sizing_tool.services.access_control_service import AccessControlService
        if auth_user is None:
            st.error('Sign in again before generating cabinet drawings.')
            return
        try:
            with session_scope() as session:
                if not AccessControlService(session, auth_user).load_dc_run_bundle(parent_run_id):
                    st.error('The source DC result is unavailable.')
                    return
        except PermissionError:
            st.error('You do not have access to this source DC result.')
            return
        except Exception:
            st.error('The source DC result could not be read. Retry before generating drawings.')
            return
        if not ac_run_id:
            try:
                matching = matching_saved_cabinet_alternative(output, parent_run_id=parent_run_id)
            except Exception:
                st.error('Saved AC alternatives could not be read. Retry before generating drawings.')
                return
            if matching:
                from calb_sizing_tool.state.workspace_state import set_active_ac_run
                set_active_ac_run(matching)
                st.rerun()
            st.warning('No unique saved AC alternative matches this restored configuration. Select its AC alternative in Workbench or save AC Sizing before generating cabinet drawings.')
            render_pipeline_next_steps('Single Line Diagram', is_guest=False)
            return
    plan = output['cabinet_group_contract']
    st.subheader('Cabinet Single Line Diagram')
    st.caption('One concept sheet per AC Block, based on the saved cabinet and PCS connections.')
    st.warning('CONCEPT / NOT FOR CONSTRUCTION. One independent cabinet group feeds one PCS. '
               'PCS electrical limits, isolation/protection, transformer vector group, earthing and MV interface '
               'require engineering confirmation. PCS nameplate power does not establish net POI delivery.')
    blocks = sorted({g['ac_block_index'] for g in plan['groups']})
    saved_block = None
    if not is_guest:
        try:
            saved_block = saved_cabinet_sld_block(output, parent_run_id=parent_run_id, ac_run_id=ac_run_id)
        except Exception:
            st.warning('Saved SLD information could not be read. Generation remains available; retry the read before assuming no drawing exists.')
    selected = st.selectbox('AC Block to preview', blocks, index=blocks.index(saved_block) if saved_block in blocks else 0,
        format_func=lambda value: f'AC Block {value}', key=f'cabinet_sld_block_{ac_run_id or parent_run_id}')
    st.caption(f"{plan['physical_cabinet_count']} physical cabinets / {len(plan['groups'])} independent groups / "
               f"{len(blocks)} AC Blocks. The package contains one separate sheet for each AC Block.")
    signature = input_signature(output, selected, parent_run_id, ac_run_id)
    bundle = st.session_state.get('sld_artifacts')
    if not (getattr(bundle, 'plugin_id', None) == PLUGIN_ID and bundle.metadata.get('signature') == signature):
        selected_bundle = None
        if getattr(bundle, 'plugin_id', None) == PLUGIN_ID:
            selected_bundle, failures = select_cabinet_sld_sheet(bundle, output, selected_block=selected,
                parent_run_id=parent_run_id, ac_run_id=ac_run_id)
            for failure in failures:
                st.warning(failure)
        bundle = selected_bundle
        st.session_state.pop('sld_artifacts', None)
        st.session_state.pop('sld_pipeline_meta', None)
        if bundle is None and not is_guest:
            try:
                bundle, failures = restore_cabinet_sld(output, selected_block=selected,
                    parent_run_id=parent_run_id, ac_run_id=ac_run_id)
                for failure in failures:
                    st.warning(failure)
            except Exception:
                st.warning('Saved cabinet SLD could not be restored. Retry or regenerate this selected alternative.')
        if bundle:
            _publish(bundle)
    if st.button('Generate Cabinet SLD', type='primary', key='generate_cabinet_sld'):
        try:
            bundle = generate_cabinet_sld(output, selected_block=selected,
                parent_run_id=parent_run_id, ac_run_id=ac_run_id,
                register=not is_guest, actor=getattr(auth_user, 'username', None))
        except Exception as exc:
            st.error(f'Cabinet SLD generation failed: {exc}')
            return
        _publish(bundle)
        st.success('Cabinet concept SLD generated and saved to the selected AC alternative.' if not is_guest
                   else 'Cabinet concept SLD generated for this guest session only.')
    if bundle:
        payloads = {a['artifact_kind']: a for a in bundle.artifacts}
        st.subheader('Preview')
        zoom = st.slider('Zoom (%)', 50, 200, 100, 10, key='cabinet_sld_zoom')
        png = payloads.get('sld_png')
        svg = payloads.get('sld_svg')
        if png:
            st.image(png['content'], width=int(1200 * zoom / 100))
        elif svg:
            width = int(1200 * zoom / 100)
            inline_svg = svg['content'].decode().replace('<svg ', '<svg style="width:100%;height:auto;" ', 1)
            st.components.v1.html(f'<div style="width:{width}px;">{inline_svg}</div>',
                                 height=int(width * 1188 / 1680) + 30, scrolling=True)
        with st.expander('Readiness and scope'):
            for warning in bundle.metadata.get('warnings', []):
                st.write(warning)
            st.caption('Transformer LV allocation is conceptual unless OEM feeder/winding assignment is explicitly confirmed. '
                       'This drawing is not a physical site arrangement or final protection design.')
        with st.expander('Cabinet / PCS connection schedule'):
            render_static_table([{'AC Block': g['ac_block_index'], 'PCS': g['pcs_index'], 'DC group': g['group_index'],
                'Cabinets': ', '.join(map(str,g['cabinet_indices'])), 'DC nameplate (MWh)': f"{g['nameplate_mwh']:.3f}"}
                for g in plan['groups']])
        st.subheader('Downloads')
        for kind,label in [('sld_svg','Download Cabinet SLD SVG'),('sld_png','Download Cabinet SLD PNG'),
                           ('cabinet_sld_package_zip','Download All Cabinet SLD Sheets'),
                           ('sld_readiness_manifest_json','Download Cabinet SLD Manifest')]:
            item=payloads.get(kind)
            if item:
                st.download_button(label,item['content'],file_name=item['file_name'],mime=item['media_type'],key=f'cabinet_download_{kind}')
        st.caption(f'Previewing AC Block {selected} from the saved package. Switching sheets does not regenerate drawings.'
                   if bundle.metadata.get('artifacts_registered') else
                   f'Previewing AC Block {selected} for this guest session only. Switching sheets does not regenerate drawings.')
    render_pipeline_next_steps('Single Line Diagram', is_guest=is_guest)
