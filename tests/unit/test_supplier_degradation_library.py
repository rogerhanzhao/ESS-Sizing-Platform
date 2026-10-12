import csv
from io import BytesIO, StringIO
import json
from zipfile import ZipFile

import pytest
from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from calb_sizing_tool.infra.db.base import Base
from calb_sizing_tool.infra.db.models import AuditLog, SupplierDegradationImport, SohProfile, DegradationCurve
from calb_sizing_tool.infra.db.session import create_engine_for_url, session_scope
from calb_sizing_tool.services.auth_service import AuthService
from calb_sizing_tool.services.supplier_degradation_library_service import SupplierDegradationLibraryService, review_attachment
from test_supplier_degradation_preview import workbook_bytes


@pytest.fixture
def library(tmp_path):
    url = f"sqlite:///{(tmp_path / 'candidates.sqlite').as_posix()}"
    engine = create_engine_for_url(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    user = AuthService(url).create_user(username="review-admin", password="test-only", role_codes=["admin"])
    return SupplierDegradationLibraryService(url), user


def test_atomic_idempotent_import_reopen_and_no_active_soh_changes(library):
    service, user = library
    data = workbook_bytes()
    row, created = service.save_candidate(data, "supplier.xlsx", "Review v1", user.user_id)
    assert created and row['status'] == 'candidate'
    again, created = service.save_candidate(data, "renamed.xlsx", "Different name", user.user_id)
    assert not created and again['import_id'] == row['import_id']
    assert again['version_label'] == "Review v1"
    reopened = SupplierDegradationLibraryService(service.db_url)
    summary, dataset, original = reopened.load_version(row['import_id'], user.user_id)
    assert original == data
    assert summary['missing_points'] == 2
    assert next(c for c in dataset.curves if c.basis == 'lower_limit').retention_pct == (100, 93, None)
    with session_scope(service.db_url) as session:
        assert len(session.scalars(select(AuditLog).where(AuditLog.action == 'import_candidate')).all()) == 1
        assert session.query(SohProfile).count() == session.query(DegradationCurve).count() == 0


def test_invalid_source_leaves_no_candidate_or_import_audit(library):
    service, user = library
    with pytest.raises(ValueError):
        service.save_candidate(workbook_bytes(lower_exceeds=True), 'supplier.xlsx', 'invalid', user.user_id)
    assert service.list_versions(user.user_id) == []
    with session_scope(service.db_url) as session:
        assert session.query(AuditLog).filter_by(action='import_candidate').count() == 0


def test_non_admin_cannot_save_read_or_export_source(library):
    service, admin = library
    normal = AuthService(service.db_url).create_user(username='normal', password='test', role_codes=['normal_user'])
    row, _ = service.save_candidate(workbook_bytes(), 'supplier.xlsx', 'v1', admin.user_id)
    for action in [lambda: service.list_versions(normal.user_id),
                   lambda: service.load_version(row['import_id'], normal.user_id),
                   lambda: service.save_candidate(workbook_bytes(), 'supplier.xlsx', 'v2', normal.user_id)]:
        with pytest.raises(PermissionError):
            action()


def test_exports_reconcile_values_units_missing_cells_and_series(library):
    service, user = library
    row, _ = service.save_candidate(workbook_bytes(), 'supplier.xlsx', 'v1', user.user_id)
    metadata, dataset, _ = service.load_version(row['import_id'], user.user_id)
    with ZipFile(BytesIO(review_attachment(dataset, metadata=metadata))) as archive:
        assert set(archive.namelist()) == {'annual_retention.csv', 'source_points.csv', 'duty_review.csv', 'README.json'}
        points = list(csv.DictReader(StringIO(archive.read('source_points.csv').decode('utf-8-sig'))))
        assert len(points) == 6
        assert {p['source_series'] for p in points} == {'mean', 'lower_limit'}
        lower = [p for p in points if p['source_series'] == 'lower_limit']
        assert [p['retention_pct'] for p in lower] == ['100.0', '93.0', '']
        assert lower[-1]['source_cell'] == 'C7' and lower[-1]['value_status'] == 'missing'
        assert 'N/A' in archive.read('annual_retention.csv').decode('utf-8-sig')
        assert json.loads(archive.read('README.json'))['source_sha256'] == dataset.source_sha256
    with ZipFile(BytesIO(review_attachment(dataset, [dataset.curves[0]]))) as archive:
        assert json.loads(archive.read('README.json'))['exported_curves'] == 1


def test_source_checksum_failure_is_explicit(library):
    service, user = library
    row, _ = service.save_candidate(workbook_bytes(), 'supplier.xlsx', 'v1', user.user_id)
    with session_scope(service.db_url) as session:
        session.get(SupplierDegradationImport, row['import_id']).source_bytes = b'corrupt'
    with pytest.raises(ValueError, match='checksum'):
        service.load_version(row['import_id'], user.user_id)


def _app():
    from calb_sizing_tool.ui.supplier_degradation_preview import render_supplier_degradation_preview
    render_supplier_degradation_preview()


def test_page_save_then_reopen_in_new_session_without_upload(library, monkeypatch):
    import streamlit as st
    service, user = library
    monkeypatch.setenv('CALB_DATABASE_URL', service.db_url)
    data = workbook_bytes()

    class Upload:
        name = 'supplier.xlsx'
        size = len(data)

        def getvalue(self):
            return data

    monkeypatch.setattr(st, 'file_uploader', lambda *a, **k: Upload())
    auth = dict(user_id=user.user_id, username=user.username, display_name=None, roles=['admin'])
    app = AppTest.from_function(_app, default_timeout=30)
    app.session_state['auth_context'] = auth
    app.run()
    assert not app.exception
    app.button(key='supplier_curve_save').click().run()
    assert not app.exception
    version = service.list_versions(user.user_id)[0]
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **k: None)
    fresh = AppTest.from_function(_app, default_timeout=30)
    fresh.session_state['auth_context'] = auth
    fresh.run()
    fresh.selectbox(key='supplier_curve_review_source').select(version['import_id']).run()
    assert not fresh.exception
    assert any('Saved candidate' in x.value for x in fresh.success)
    labels = [x.label for x in fresh.get('download_button')]
    assert 'Download original supplier workbook' in labels
    assert 'Download all curves and review tables (ZIP)' in labels
    assert any('93.00%' in x.value and 'N/A' in x.value for x in fresh.markdown)
