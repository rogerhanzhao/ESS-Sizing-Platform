"""Access-checked cabinet sources for the existing downstream pages."""
import streamlit as st


def cabinet_document_context(output, *, parent_run_id, workspace, is_guest, auth_user, authoritative):
    """Return (actual AC child ID, saved DC bundle), or None after a friendly error."""
    if is_guest:
        return None, None
    if not authoritative:
        st.warning('Save and select the cabinet AC alternative before generating traceable documents.')
        return None
    if auth_user is None:
        st.error('Sign in again before generating cabinet documents.')
        return None
    from calb_sizing_tool.infra.db.session import session_scope
    from calb_sizing_tool.services.access_control_service import AccessControlService
    from calb_sizing_tool.services.cabinet_document_service import verify_cabinet_ac_source
    from calb_sizing_tool.services.cabinet_sld_service import matching_saved_cabinet_alternative
    try:
        with session_scope() as session:
            dc_bundle = AccessControlService(session, auth_user).load_dc_run_bundle(parent_run_id)
        if dc_bundle is None:
            st.error('The saved source DC result is unavailable.')
            return None
        child = workspace.get('ac_run_id')
        if not child:
            child = matching_saved_cabinet_alternative(output, parent_run_id=parent_run_id)
            if child:
                from calb_sizing_tool.state.workspace_state import set_active_ac_run
                set_active_ac_run(child)
                st.rerun()
            st.warning('Select the saved cabinet AC alternative in Workbench or save AC Sizing first.')
            return None
        verify_cabinet_ac_source(output, parent_run_id, child)
    except PermissionError:
        st.error('You do not have access to this source DC result.')
        return None
    except ValueError as exc:
        st.error(str(exc))
        return None
    except Exception:
        st.error('The saved cabinet configuration could not be read. Retry before creating documents.')
        return None
    return child, dc_bundle
