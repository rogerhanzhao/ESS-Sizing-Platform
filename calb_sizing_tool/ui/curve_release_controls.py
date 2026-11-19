"""Curve choices on the existing DC and administrator pages."""
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from calb_sizing_tool.services.curve_release_service import CurveReleaseService
from calb_sizing_tool.ui.curve_labels import (
    family_label, curve_version_label, sorted_family_keys, rte_basis_label,
)


def render_curve_choice(dc_inputs, db_url=None):
    service = CurveReleaseService(db_url)
    try:
        releases = [r for r in service.list_releases() if r['status']=='published']
        default = service.get_default()
    except SQLAlchemyError as exc:
        # An old unmigrated database must be migrated explicitly, not treated
        # as a missing default for a new release.
        st.error('Curve version storage is unavailable. Run database migrations before sizing.')
        st.stop()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    options = {f"{r['release_id']}|{key}":(r,key) for r in releases for key in sorted_family_keys(r['payload'])}
    if not options and not dc_inputs.get('curve_selection'):
        return None  # Existing deployments without a published release retain legacy behavior.
    if default is None:
        options = {'legacy':None, **options}
    saved = dc_inputs.get('curve_selection') or default
    preferred = f"{saved['release_id']}|{saved['family_key']}" if saved else 'legacy'
    key = 'dc_inputs.curve_selection_token'
    if key not in st.session_state:
        st.session_state[key] = preferred
    if st.session_state[key] not in options:
        st.warning('The saved curve version is unavailable or retired. Select a published basis before recalculating; historical results remain unchanged.')
        options = {'unavailable':None, **options}
        st.session_state[key] = 'unavailable'
    def label(token):
        if token == 'legacy':
            return 'Legacy database / Excel basis'
        if token == 'unavailable':
            return 'Saved version unavailable — select a published basis'
        r, family = options[token]
        standard = default and token == f"{default['release_id']}|{default['family_key']}"
        return f"{'Standard · ' if standard else 'Special case · '}{curve_version_label(r)} · {family_label(family)}"
    token = st.selectbox('Degradation data basis', list(options),
                         index=list(options).index(st.session_state[key]), format_func=label, key=key,
                         help='Changes apply to the next Run Sizing only. They do not modify other cases or the system default.')
    if token == 'unavailable':
        st.error('Choose an available curve basis to run sizing.')
        return {'unavailable':True}
    if token == 'legacy':
        dc_inputs['curve_selection'] = None
        return None
    release, family = options[token]
    mode = 'default' if default and token==f"{default['release_id']}|{default['family_key']}" else 'special'
    selection = dict(release_id=release['release_id'], family_key=family,
                     payload_sha256=release['payload_sha256'], selection_mode=mode)
    dc_inputs['curve_selection'] = selection
    st.caption('Applies when you click Run Sizing. Existing results keep their original basis. '
               'Source SOC is not DOD. Missing source years are rejected; the existing explicitly paired RTE version is retained.')
    return selection


def load_curve_admin_context(db_url=None):
    service = CurveReleaseService(db_url)
    return dict(releases=service.list_releases(), binding=service.get_binding())


def render_curve_current_default(db_url=None, *, context=None):
    context = load_curve_admin_context(db_url) if context is None else context
    default = context['binding']
    st.markdown('**Current sizing default**')
    if not default:
        st.info('No standard curve default is set.')
        return
    release = next((r for r in context['releases'] if r['release_id'] == default['release_id']), None)
    if not release or release['status'] != 'published':
        st.error('The current default is unavailable. Choose a published version below to restore it.')
        return
    if default['family_key'] not in sorted_family_keys(release['payload']):
        st.error('The current default condition is unavailable. Choose a valid condition below to restore it.')
        return
    with st.container(border=True):
        st.write(f"**Curve version:** {curve_version_label(release)}")
        st.write(f"**Condition:** {family_label(default['family_key'])}")
        st.write(f"**RTE basis:** {rte_basis_label(release['payload'])}")
        st.caption('CALB 314Ah-A · Used when no version has been selected. Existing selections and saved results stay unchanged.')


def _preferred_condition(keys, default):
    preferred = default['family_key'] if default else 'soc20.mean'
    return preferred if preferred in keys else ('soc20.mean' if 'soc20.mean' in keys else keys[0])


def render_curve_admin(actor, db_url=None, *, context=None):
    from calb_sizing_tool.services.supplier_degradation_library_service import SupplierDegradationLibraryService
    from calb_sizing_tool.ui._ui import render_static_table
    service = CurveReleaseService(db_url)
    with st.expander('Curve versions — apply, roll back and stop', expanded=False):
        st.caption('Apply or roll back: choose an available version and condition below, then click Apply as sizing default. '
                   'You can keep earlier versions available for rollback. Stop a version only when it should no longer be used for new calculations.')
        try:
            context = load_curve_admin_context(db_url) if context is None else context
            releases, default = context['releases'], context['binding']
            published = {r['release_id']: r for r in releases if r['status'] == 'published'}
            status_labels = {'published': 'Available for new runs', 'retired': 'Stopped for new runs',
                             'corrupt': 'Unavailable · integrity check failed'}
            if releases:
                render_static_table([{
                    'Curve version': curve_version_label(r),
                    'Status': status_labels.get(r['status'], r['status']),
                    'Standard default': family_label(default['family_key'])
                        if default and r['release_id'] == default['release_id'] else '—',
                } for r in releases])
            else:
                st.caption('No curve versions have been published.')
            if published:
                st.markdown('**Apply or roll back the sizing default**')
                revision_key = 'review_curve_default_revision'
                version_key = 'curve_default_version'
                condition_key = 'curve_default_condition'
                reviewed_version_key = 'review_curve_default_version'
                if st.button('Refresh default settings', key='curve_default_refresh'):
                    for key in (revision_key, version_key, condition_key, reviewed_version_key):
                        st.session_state.pop(key, None)
                revision = default['revision'] if default else 0
                # Missing version widget means the previous form was left, not
                # that its review token may be refreshed on a candidate change.
                if revision_key not in st.session_state or version_key not in st.session_state:
                    st.session_state[revision_key] = revision
                    st.session_state[version_key] = (default['release_id']
                        if default and default['release_id'] in published else next(iter(published)))
                    st.session_state.pop(condition_key, None)
                    st.session_state.pop(reviewed_version_key, None)
                version_ids = list(published)
                previous_version = st.session_state[version_key]
                if previous_version not in published:
                    version_ids.insert(0, previous_version)
                version = st.selectbox('Published curve version', version_ids,
                    index=version_ids.index(previous_version), key=version_key,
                    format_func=lambda k: curve_version_label(published[k]) if k in published
                        else 'Unavailable selection — refresh settings')
                candidate = published.get(version)
                keys = sorted_family_keys(candidate['payload']) if candidate else ['unavailable']
                if (st.session_state.get(reviewed_version_key) != version
                        or st.session_state.get(condition_key) not in keys):
                    st.session_state[condition_key] = _preferred_condition(keys, default)
                    st.session_state[reviewed_version_key] = version
                stale = st.session_state[revision_key] != revision or candidate is None
                if stale:
                    st.error('Default settings changed during review. Refresh default settings and review again before applying.')
                with st.form('curve_default_form'):
                    condition = st.selectbox('Proposed default condition', keys,
                        index=keys.index(st.session_state[condition_key]), key=condition_key,
                        format_func=lambda k: family_label(k) if k != 'unavailable' else 'Unavailable condition')
                    st.caption('This is a proposed selection. It takes effect only after you apply it; saved results are not changed. '
                               'Existing cases keep their selected basis; change that selection before recalculating if needed.')
                    if st.form_submit_button('Apply as sizing default', disabled=stale) and not stale:
                        service.set_default(version, condition, actor, st.session_state[revision_key])
                        st.session_state.pop(revision_key, None)
                        st.success('Sizing default updated. Existing selections and saved results are unchanged.')
                        st.rerun()
            with st.expander('Publish a complete version from a source workbook', expanded=False):
                versions = SupplierDegradationLibraryService(db_url).list_versions(actor)
                if not versions:
                    st.caption('Save a source workbook first.')
                else:
                    st.caption('Create a new SOH/RTE version from a saved workbook and an RTE basis. Publication does not change the sizing default.')
                    with st.form('curve_publish_form'):
                        source_ids = [v['import_id'] for v in versions]
                        source_current = st.session_state.get('curve_publish_source', source_ids[0])
                        if source_current not in source_ids:
                            source_current = source_ids[0]
                            st.session_state['curve_publish_source'] = source_current
                        source = st.selectbox('Source workbook', source_ids,
                            index=source_ids.index(source_current), key='curve_publish_source',
                            format_func=lambda k: next(v['version_label'] for v in versions if v['import_id'] == k))
                        label = st.text_input('Curve version name',
                            value=st.session_state.get('curve_publish_name', ''), key='curve_publish_name',
                            placeholder='CALB314-SOH-RTE-v2',
                            help='Name this revision. SOC and series are selected separately.')
                        rte_options = {'master': 'Original reference RTE', **{
                            r['release_id']: f"{curve_version_label(r)} · {rte_basis_label(r['payload'])}"
                            for r in published.values()}}
                        rte_current = default['release_id'] if default and default['release_id'] in rte_options else 'master'
                        rte_current = st.session_state.get('curve_publish_rte_source', rte_current)
                        if rte_current not in rte_options:
                            rte_current = 'master'
                            st.session_state['curve_publish_rte_source'] = rte_current
                        rte_source = st.selectbox('RTE basis', list(rte_options),
                            index=list(rte_options).index(rte_current), key='curve_publish_rte_source',
                            format_func=lambda k: rte_options[k])
                        note = st.text_area('Change reason and applicability',
                            value=st.session_state.get('curve_publish_note', ''), key='curve_publish_note',
                            help='Record the applicable product and why this SOH/RTE pairing is suitable.')
                        if st.form_submit_button('Publish complete source-based version'):
                            service.publish(source, label, note, actor,
                                rte_release_id=None if rte_source == 'master' else rte_source)
                            st.success('Curve version published and available for selection. The sizing default is unchanged.')
                            st.rerun()
            if published:
                with st.expander('Stop a version for new runs', expanded=False):
                    st.caption('Historical results are retained. Stopping blocks new calculations using this version, including recalculation of saved cases. '
                               'Stopped versions cannot be re-enabled on this page; keep a previous version available if it may be needed for rollback.')
                    retire_ids = list(published)
                    retire_current = st.session_state.get('curve_retire_version', retire_ids[0])
                    if retire_current not in published:
                        retire_current = retire_ids[0]
                        st.session_state['curve_retire_version'] = retire_current
                    retired = st.selectbox('Curve version to stop', list(published), key='curve_retire_version',
                        index=retire_ids.index(retire_current),
                        format_func=lambda k: curve_version_label(published[k]))
                    is_current_default = bool(default and default['release_id'] == retired)
                    if is_current_default:
                        st.info('This is the current default. Apply another available version as the sizing default before stopping it.')
                    if st.button('Stop selected version for new runs', key='curve_retire_submit', disabled=is_current_default):
                        service.retire(retired, actor)
                        st.success('This version is no longer available for new runs. Historical results are retained.')
                        st.rerun()
            if releases:
                with st.expander('Version records and review history', expanded=False):
                    st.caption('Stored names and review notes are historical records; current availability is shown above.')
                    for r in releases:
                        st.write(f"**{curve_version_label(r)}**")
                        st.caption(f"Stored version name: {r['version_label']}")
                        st.caption(f"Version ID: {r['release_id']}")
                        if r.get('payload'):
                            st.caption(f"RTE record: {r['payload']['rte_version']}")
                        st.write(r['review_note'])
        except (ValueError, PermissionError, SQLAlchemyError) as exc:
            st.error(str(exc))
