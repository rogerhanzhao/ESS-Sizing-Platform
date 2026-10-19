"""Saved cabinet technical proposal in the existing Report Export page."""
import streamlit as st

from calb_sizing_tool.reporting.brand_profiles import BRAND_PROFILES
from calb_sizing_tool.services.cabinet_report_service import (
    prepare_cabinet_report, generate_cabinet_technical_report, restore_cabinet_technical_report,
    CabinetReportNotReady,
)
from calb_sizing_tool.ui.cabinet_document_context import cabinet_document_context
from calb_sizing_tool.state.workspace_state import navigate_now


def _render_reference_panels(data, alternative_label):
    """Keep the existing report-page references and product attachment sections."""
    with st.expander('Run references and data sources', expanded=False):
        a, b = st.columns(2)
        with a:
            st.caption('Project')
            st.write(data.get('project_name') or '—')
        with b:
            st.caption('Case')
            st.write(data.get('case_name') or '—')
        if alternative_label:
            st.caption(f'AC Alternative {alternative_label}')
        st.success('Saved DC and AC results are linked to the selected configuration.')
        st.caption('All SLD and arrangement sheets are read from its verified drawing packages.')

    from calb_sizing_tool.ui.report_export_view import _load_product_assets_for_block
    products = data.get('dc_products') or []
    attachments = [(product, _load_product_assets_for_block(product.get('block_code')))
                   for product in products]
    with st.expander('Standard Product Information', expanded=any(assets for _, assets in attachments)):
        if not attachments:
            st.info('No product assets registered for this DC block.')
        for product, assets in attachments:
            st.caption(f"DC Block: {product.get('block_name') or product.get('block_code') or '—'}")
            if not assets:
                st.info('No product assets registered for this DC block. '
                        'Add datasheets and product images in Product & Database → Product Assets.')
            for asset in assets:
                st.markdown(f"**{asset['kind'].replace('_', ' ').title()}** — {asset['title']}")
                if asset.get('file_name'):
                    st.caption(asset['file_name'])
                if asset.get('caption'):
                    st.write(asset['caption'])


def show_cabinet_report(output, *, parent_run_id, workspace, auth_user, authoritative, installation_basis=None):
    context = cabinet_document_context(output, parent_run_id=parent_run_id, workspace=workspace,
        is_guest=False, auth_user=auth_user, authoritative=authoritative)
    if context is None:
        return
    child, dc_bundle = context
    from calb_sizing_tool.services.ac_run_service import ac_alternative_label
    try:
        alternative_label = ac_alternative_label(parent_run_id, child)
    except Exception:
        st.error('The selected AC alternative name could not be read. Retry before exporting.')
        return
    # Use the existing template state across container and cabinet configurations.
    template = st.selectbox('Report Template', list(BRAND_PROFILES), index=0, key='report_template_brand')
    brand = BRAND_PROFILES[template]
    try:
        sources = prepare_cabinet_report(dc_bundle, output, ac_run_id=child, installation_basis=installation_basis,
            ac_alternative_label=alternative_label)
    except (CabinetReportNotReady, ValueError) as exc:
        st.info(str(exc))
        a, b = st.columns(2)
        if a.button('Go to Single Line Diagram', key='cabinet_report_go_sld'):
            navigate_now('Single Line Diagram')
        if b.button('Go to Typical AC Block Arrangement', key='cabinet_report_go_arrangement'):
            navigate_now('Typical AC Block Arrangement')
        st.button('Retry retrieving the figures', key='cabinet_report_retry_sources')
        return
    except Exception:
        st.error('The saved cabinet report sources could not be read. Retry before exporting.')
        return
    data = sources.report_data
    st.subheader('Selected Run Summary')
    c1, c2, c3 = st.columns(3)
    c1.metric('POI Power Requirement', f"{data['poi_power_mw']:.3f} MW")
    c2.metric('POI Energy Requirement', f"{data['poi_energy_mwh']:.3f} MWh")
    c3.metric('Installed DC Nameplate', f"{data['dc_total_mwh']:.3f} MWh")
    st.caption(f"{data['physical_cabinet_count']} cabinets / {len(sources.diagram_pages)} AC Blocks / "
               f"{len(data['annual_rows'])} saved annual records. All AC Block figures are included; preview selection does not limit the report.")
    st.subheader('Report Content')
    r1, r2, r3, r4 = st.columns(4)
    r1.success('✓  DC Sizing')
    r2.success('✓  AC Sizing')
    r3.success('✓  SLD Image')
    r4.success('✓  Typical AC Block Arrangement (Concept Only)')
    with st.expander('Report contents', expanded=False):
        st.write('Project design basis; DC equipment; POI energy and SOH curves; annual performance table; '
                 'AC allocation; all SLD and arrangement sheets; installation evidence and engineering interfaces.')
    st.warning('CONCEPT / NOT FOR CONSTRUCTION. The report records modelled energy performance and equipment '
               'grouping. It does not establish a net POI power guarantee or an approved installation design.')
    st.divider()
    _render_reference_panels(data, alternative_label)
    st.divider()
    st.subheader('Downloads')
    try:
        report = restore_cabinet_technical_report(sources, brand)
    except CabinetReportNotReady as exc:
        st.error(str(exc))
        st.button('Retry retrieving the report', key='cabinet_report_retry_saved')
        return
    except Exception:
        st.error('The saved report could not be read. Retry before downloading.')
        st.button('Retry retrieving the report', key='cabinet_report_retry_saved')
        return
    # Match the original Report Export flow: prepare bytes on page entry and
    # offer the download directly. Only a genuine cache miss writes a report.
    if report is None:
        try:
            with st.spinner('Preparing the combined report...'):
                report = generate_cabinet_technical_report(dc_bundle, output, ac_run_id=child, brand=brand,
                    actor=getattr(auth_user, 'username', None), installation_basis=installation_basis,
                    ac_alternative_label=alternative_label)
        except Exception as exc:
            st.error(f'Combined report preparation failed: {exc}')
            st.button('Retry preparing the report', key='cabinet_report_retry_prepare')
            return
    if report:
        data, filename, _ = report
        st.download_button('Download Technical Proposal', data, file_name=filename,
            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            type='primary', on_click='ignore', key='download_cabinet_report')
        st.caption('Concept technical proposal. Body pages are portrait; complete engineering figure sheets are A3 landscape.')
