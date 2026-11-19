"""Read-only source/runtime status wording and admin navigation boundaries."""
from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest
from test_supplier_degradation_library import library

from calb_sizing_tool.ui.supplier_degradation_preview import _source_runtime_use


def _context(*, default=False, matching=True, corrupt=False):
    release=dict(release_id='published-release',version_label='Reviewed runtime package',
                 status='corrupt' if corrupt else 'published')
    if not corrupt:
        release['payload']={'source_sha256':'source-sha' if matching else 'another-source'}
    return dict(releases=[release],binding=(dict(release_id='published-release',family_key='soc20.mean') if default else None))


def test_source_status_is_derived_from_current_and_published_runtime_references():
    source={'source_sha256':'source-sha'}
    assert 'Default uses this source: Reviewed runtime package' in _source_runtime_use(source,_context(default=True))
    assert '20%' in _source_runtime_use(source,_context(default=True))
    assert 'Used by 1 published version.' in _source_runtime_use(source,_context())
    assert 'Not the default source' in _source_runtime_use(source,_context())
    assert 'No published curve version' in _source_runtime_use(source,_context(matching=False))
    assert 'integrity review' in _source_runtime_use(source,_context(default=True,corrupt=True))
    assert 'unavailable' in _source_runtime_use(source,None)
    context=_context(default=True)
    context['releases'][0]['version_label']='SOC20-screenshot-RTE-review-20261118'
    message=_source_runtime_use(source,context)
    assert '18 Nov 2026 · RTE in 5% SOH bands' in message
    assert 'SOC20-screenshot-RTE-review-20261118' not in message


def test_project_curve_choices_use_admin_names_and_order_without_changing_identity(monkeypatch):
    from calb_sizing_tool.ui import curve_release_controls
    from calb_sizing_tool.ui.curve_labels import curve_version_label
    from test_curve_release import _choice_app

    names = ('SOC20-screenshot-RTE-review-20261118',
             'SOC20-local-review-20261118-r2', 'Approved supplier data v4')
    releases = [dict(release_id=f'version-{i}', version_label=name,
                     payload_sha256=f'unchanged-hash-{i}', status='published',
                     payload={'curves': [dict(soc_pct=soc, basis=series,
                                             power_rate=.25, cycles_per_day=1)
                              for soc in (50, 20) for series in ('lower_limit', 'mean')]})
                for i, name in enumerate(names)]
    binding = dict(release_id='version-0', family_key='soc20.mean',
                   payload_sha256='unchanged-hash-0', revision=3)

    class Service:
        def __init__(self, db_url=None): pass
        def list_releases(self): return deepcopy(releases)
        def get_default(self): return deepcopy(binding)

    monkeypatch.setattr(curve_release_controls, 'CurveReleaseService', Service)
    app = AppTest.from_function(_choice_app, default_timeout=30).run()
    assert not app.exception and not app.error
    choice = app.selectbox(key='dc_inputs.curve_selection_token')
    expected = []
    for release in releases:
        for soc in (20, 50):
            for series in ('Mean', 'Lower limit'):
                prefix = 'Standard' if release['release_id']=='version-0' and soc==20 and series=='Mean' else 'Special case'
                expected.append(f"{prefix} · {curve_version_label(release)} · Source SOC {soc}% · {series}")
    assert choice.options == expected
    assert all('screenshot' not in value for value in choice.options)
    choice.select('version-1|soc50.lower_limit').run()
    assert not app.exception and not app.error
    selection = app.session_state['inputs']['curve_selection']
    assert selection == dict(release_id='version-1', family_key='soc50.lower_limit',
                             payload_sha256='unchanged-hash-1', selection_mode='special')


def _legacy_data_app():
    from calb_sizing_tool.ui.admin_portal_view import _section_dc_sizing_data
    _section_dc_sizing_data()


@pytest.mark.parametrize('populated',[False,True])
def test_legacy_reference_maintenance_does_not_claim_to_switch_runtime_default(monkeypatch,populated):
    from calb_sizing_tool.services import master_data_service
    counts={name:int(populated) for name in ('soh_profile','soh_curve_point','rte_profile','rte_curve_band')}
    class StubService:
        def get_soh_rte_counts(self):return deepcopy(counts)
    monkeypatch.setattr(master_data_service,'MasterDataService',StubService)
    app=AppTest.from_function(_legacy_data_app,default_timeout=30).run()
    assert not app.exception
    text=' '.join(v.value for collection in (app.caption,app.info,app.success) for v in collection)
    assert 'Legacy SOH / RTE reference tables' in text
    assert 'do not change published curve versions' in text
    assert 'Degradation' in text
    assert 'DC sizing uses the saved database curves' not in text
    assert app.button(key='btn_migrate_soh_rte').label=='Replace legacy SoH / RTE tables from Excel'
    if populated:
        assert app.button(key='btn_clear_soh_rte').label=='Clear legacy SoH / RTE reference tables'


def _reference_rte_app():
    from calb_sizing_tool.ui.admin_portal_view import _section_rte
    _section_rte(None,dict(rte_curves=[],cells=[]))


def test_reference_rte_page_points_to_runtime_review_in_degradation():
    app=AppTest.from_function(_reference_rte_app,default_timeout=30).run()
    assert not app.exception
    assert any('Degradation → Revise RTE' in v.value for v in app.info)
    assert any('does not mean the published curve version has no RTE data' in v.value for v in app.info)
    assert any('Active / Published flags do not change a published curve version' in v.value for v in app.caption)


def test_source_preview_keeps_default_summary_first_and_management_after_saved_source(library,monkeypatch):
    import streamlit as st
    from calb_sizing_tool.ui import curve_release_controls, rte_review_controls
    from test_supplier_degradation_library import _app
    from test_supplier_degradation_preview import workbook_bytes

    service,user=library
    source,_=service.save_candidate(workbook_bytes(),'supplier.xlsx','Imported source name',user.user_id)
    monkeypatch.setenv('CALB_DATABASE_URL',service.db_url)
    context=_context(default=True)
    context['releases'][0]['payload']['source_sha256']=source['source_sha256']
    calls=[]
    def load_context(db_url=None):
        calls.append('load')
        return context
    def summary(db_url=None,*,context=None):
        calls.append('summary')
        st.caption('Current default summary marker')
    def rte(actor,db_url=None):
        calls.append('rte')
        st.caption('RTE revision marker')
    def management(actor,db_url=None,*,context=None):
        calls.append('management')
        st.caption('Published version management marker')
    monkeypatch.setattr(curve_release_controls,'load_curve_admin_context',load_context)
    monkeypatch.setattr(curve_release_controls,'render_curve_current_default',summary)
    monkeypatch.setattr(curve_release_controls,'render_curve_admin',management)
    monkeypatch.setattr(rte_review_controls,'render_rte_review',rte)
    app=AppTest.from_function(_app,default_timeout=30)
    app.session_state['auth_context']=dict(user_id=user.user_id,username=user.username,display_name=None,roles=['admin'])
    app.run()
    assert not app.exception
    assert calls==['load','summary','rte','management']
    assert any('Source saved: Imported source name' in v.value for v in app.success)
    assert any('Default uses this source: Reviewed runtime package' in v.value for v in app.info)
    captions=[v.value for v in app.caption]
    assert captions.index('Current default summary marker')<next(i for i,v in enumerate(captions) if 'Source preview · View only' in v)
    assert next(i for i,v in enumerate(captions) if 'View only: source-series' in v)<captions.index('RTE revision marker')
    assert captions.index('RTE revision marker')<captions.index('Published version management marker')
    visible=' '.join(v.value for collection in (app.caption,app.info,app.success,app.markdown) for v in collection)
    assert 'Not active in sizing' not in visible
    assert 'not applied to sizing' not in visible
    assert 'Filters and exports do not change the sizing default' in visible
    assert any(v.label=='Imported workbooks (1)' for v in app.expander)
    assert not next(v for v in app.expander if v.label=='Source workbooks — preview and import').proto.expanded
