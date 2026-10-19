import io
from pathlib import Path

import pytest

from tests.test_cabinet_report_data import saved_cabinet
from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import Project, SizingRun, ArtifactRegistry
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.ac_run_service import persist_ac_run
from calb_sizing_tool.services.artifact_service import resolve_artifact_path
from calb_sizing_tool.services.cabinet_sld_service import generate_cabinet_sld
from calb_sizing_tool.services.cabinet_arrangement_service import generate_cabinet_arrangement
from calb_sizing_tool.services.cabinet_report_service import (
    prepare_cabinet_report, generate_cabinet_technical_report, restore_cabinet_technical_report, CabinetReportNotReady,
)
from calb_sizing_tool.reporting.brand_profiles import CALB_BRAND, GUOXIA_BRAND


@pytest.fixture
def documents(saved_cabinet, tmp_path, monkeypatch):
    dc, output = saved_cabinet
    url = f"sqlite:///{(tmp_path / 'reports.sqlite').as_posix()}"
    monkeypatch.setenv('CALB_OUTPUTS_DIR', str(tmp_path / 'outputs'))
    with session_scope(url) as session:
        Base.metadata.create_all(session.get_bind())
        session.add(Project(project_id='p', project_code='P', project_name='Test'))
        session.flush()
        session.add(SizingRun(sizing_run_id=dc.run_id, project_id='p', run_type='dc_pipeline', status='succeeded'))
    child = persist_ac_run(dc_run_id=dc.run_id, ac_inputs={}, ac_output=output, db_url=url).run_id
    generate_cabinet_sld(output, selected_block=2, parent_run_id=dc.run_id, ac_run_id=child, register=True, db_url=url)
    generate_cabinet_arrangement(output, selected_block=1, parent_run_id=dc.run_id,
        ac_run_id=child, register=True, db_url=url)
    return dc, output, child, url


def test_report_uses_both_complete_packages_regardless_of_preview_choice(documents):
    dc, output, child, url = documents
    sources = prepare_cabinet_report(dc, output, ac_run_id=child, db_url=url)
    assert [p['ac_block_index'] for p in sources.diagram_pages] == [1, 2]
    assert b'C001' in sources.diagram_pages[0]['sld_svg'] and b'C048' in sources.diagram_pages[1]['sld_svg']
    assert b'C001' in sources.diagram_pages[0]['layout_svg'] and b'C048' in sources.diagram_pages[1]['layout_svg']
    assert sources.report_data['annual_rows'][4]['poi_usable_energy_mwh'] == 16.1627717136958
    refreshed = {**output, 'source_ac_run_id': 'new UI token'}
    assert prepare_cabinet_report(dc, refreshed, ac_run_id=child, db_url=url).fingerprint == sources.fingerprint


def test_report_is_saved_on_exact_child_and_restored_with_brand_and_hash_checks(documents):
    dc, output, child, url = documents
    content, filename, signature = generate_cabinet_technical_report(dc, output, ac_run_id=child,
        brand=CALB_BRAND, db_url=url)
    assert content.startswith(b'PK') and filename.endswith('.concept.docx')
    sources = prepare_cabinet_report(dc, output, ac_run_id=child, db_url=url)
    assert restore_cabinet_technical_report(sources, CALB_BRAND, db_url=url) == (content, filename, signature)
    assert restore_cabinet_technical_report(sources, GUOXIA_BRAND, db_url=url) is None
    with session_scope(url) as session:
        reports = session.query(ArtifactRegistry).filter(ArtifactRegistry.artifact_kind.like('cabinet_report_%')).all()
        assert len(reports) == 2 and all(row.sizing_run_id == child for row in reports)
        file = resolve_artifact_path(next(row.file_path for row in reports if row.artifact_kind.endswith('_docx')))
    file.write_bytes(b'changed report')
    with pytest.raises(CabinetReportNotReady, match='changed'):
        restore_cabinet_technical_report(sources, CALB_BRAND, db_url=url)


def test_missing_arrangement_cannot_fall_back_to_old_parent_or_session(documents, monkeypatch):
    dc, output, child, url = documents
    from calb_sizing_tool.services import cabinet_arrangement_service as arrangement
    monkeypatch.setattr(arrangement, 'restore_cabinet_arrangement', lambda *args, **kwargs: (None, []))
    with pytest.raises(CabinetReportNotReady, match='Generate the cabinet arrangement'):
        prepare_cabinet_report(dc, output, ac_run_id=child, db_url=url)


def test_changed_saved_package_and_wrong_child_are_rejected(documents):
    dc, output, child, url = documents
    with pytest.raises(ValueError, match='does not belong'):
        prepare_cabinet_report(dc, output, ac_run_id='another-child', db_url=url)
    with session_scope(url) as session:
        row = session.query(ArtifactRegistry).filter_by(sizing_run_id=child,
            artifact_kind='cabinet_arrangement_package_zip').one()
        file = resolve_artifact_path(row.file_path)
    file.write_bytes(b'not a zip')
    with pytest.raises(CabinetReportNotReady, match='could not be verified'):
        prepare_cabinet_report(dc, output, ac_run_id=child, db_url=url)


def test_report_alternative_label_is_resolved_from_the_real_saved_child(documents):
    import copy
    dc, output, child, url = documents
    other = copy.deepcopy(output)
    other.update(pcs_kw=2500, pcs_per_block=2, block_size_mw=5, total_ac_mw=10)
    for row in other['ac_block_rows']: row['pcs_kw'] = 2500
    sibling = persist_ac_run(dc_run_id=dc.run_id, ac_inputs={}, ac_output=other, db_url=url).run_id
    assert sibling != child
    sources = prepare_cabinet_report(dc, output, ac_run_id=child, db_url=url)
    assert sources.report_data['ac_alternative_label'] == 'A'
    with pytest.raises(ValueError, match='label conflicts'):
        prepare_cabinet_report(dc, output, ac_run_id=child, db_url=url, ac_alternative_label='B')


@pytest.fixture
def saved_report_cache(documents):
    """A real report cache on the selected child, separate from its drawings."""
    import json

    dc, output, child, url = documents
    generate_cabinet_technical_report(dc, output, ac_run_id=child, brand=CALB_BRAND, db_url=url)
    # Re-read the source packages after the report has been saved; cache tests
    # must not substitute a different source or alter the confirmed drawings.
    sources = prepare_cabinet_report(dc, output, ac_run_id=child, db_url=url)
    with session_scope(url) as session:
        rows = session.query(ArtifactRegistry).filter_by(sizing_run_id=child).all()
        manifest_path = resolve_artifact_path(next(row.file_path for row in rows
            if row.artifact_kind == 'cabinet_report_calb_manifest'))
        report_path = resolve_artifact_path(next(row.file_path for row in rows
            if row.artifact_kind == 'cabinet_report_calb_docx'))
        drawing_packages = {row.artifact_kind: resolve_artifact_path(row.file_path).read_bytes()
            for row in rows if row.artifact_kind in {'cabinet_sld_package_zip', 'cabinet_arrangement_package_zip'}}
    manifest = json.loads(manifest_path.read_bytes())
    return sources, url, manifest_path, report_path, manifest, drawing_packages


def _write_cache_manifest(path, manifest):
    import json
    path.write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')


@pytest.mark.parametrize('field,conflicting_value', [
    ('plugin_id', 'unrelated_report_plugin'),
    ('source_run_id', 'another-dc-parent'),
    ('source_ac_run_id', 'another-ac-alternative'),
    ('brand', GUOXIA_BRAND.key),
])
def test_bound_report_cache_conflicts_are_not_treated_as_a_cache_miss(saved_report_cache, field, conflicting_value):
    sources, url, manifest_path, report_path, manifest, drawing_packages = saved_report_cache
    original_report = report_path.read_bytes()
    manifest[field] = conflicting_value
    _write_cache_manifest(manifest_path, manifest)
    with pytest.raises(CabinetReportNotReady):
        restore_cabinet_technical_report(sources, CALB_BRAND, db_url=url)
    # A reader must fail closed, preserving the evidence instead of replacing
    # another publisher's/alternative's artifact through automatic preparation.
    assert report_path.read_bytes() == original_report
    with session_scope(url) as session:
        rows = session.query(ArtifactRegistry).filter_by(sizing_run_id=sources.ac_run_id).all()
        for row in rows:
            if row.artifact_kind in drawing_packages:
                assert resolve_artifact_path(row.file_path).read_bytes() == drawing_packages[row.artifact_kind]


@pytest.mark.parametrize('corruption', ['missing_signature', 'empty_signature', 'manifest_not_object'])
def test_structurally_invalid_report_manifest_is_not_a_normal_cache_miss(saved_report_cache, corruption):
    sources, url, manifest_path, _, manifest, _ = saved_report_cache
    if corruption == 'missing_signature':
        del manifest['signature']
    elif corruption == 'empty_signature':
        manifest['signature'] = ''
    elif corruption == 'manifest_not_object':
        manifest = [manifest]
    _write_cache_manifest(manifest_path, manifest)
    with pytest.raises(CabinetReportNotReady):
        restore_cabinet_technical_report(sources, CALB_BRAND, db_url=url)


def test_intact_same_source_report_with_a_valid_stale_signature_can_be_prepared_again(saved_report_cache):
    sources, url, manifest_path, report_path, manifest, _ = saved_report_cache
    # A syntactically valid old signature can represent an earlier generator
    # version. Its complete binding and content hash must still be intact.
    manifest['signature'] = '0' * 64
    original_report = report_path.read_bytes()
    _write_cache_manifest(manifest_path, manifest)
    assert restore_cabinet_technical_report(sources, CALB_BRAND, db_url=url) is None
    assert report_path.read_bytes() == original_report


def test_stale_signature_cannot_hide_a_damaged_report_hash(saved_report_cache):
    sources, url, manifest_path, report_path, manifest, _ = saved_report_cache
    manifest['signature'] = '0' * 64
    _write_cache_manifest(manifest_path, manifest)
    report_path.write_bytes(b'damaged cached document with an expired source signature')
    with pytest.raises(CabinetReportNotReady):
        restore_cabinet_technical_report(sources, CALB_BRAND, db_url=url)
