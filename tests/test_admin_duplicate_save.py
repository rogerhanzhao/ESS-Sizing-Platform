import pytest
from sqlalchemy.exc import IntegrityError

from calb_sizing_tool.ui import admin_portal_view


def test_unique_conflict_shows_recovery_without_sql(monkeypatch):
    messages=[]
    monkeypatch.setattr(admin_portal_view.st,'error',messages.append)
    with admin_portal_view._friendly_duplicate_save():
        raise IntegrityError('INSERT SECRET SQL',{},Exception('UNIQUE constraint failed: product_cell.cell_code'))
    assert len(messages)==1
    assert 'already exists' in messages[0]
    assert 'SQL' not in messages[0]


def test_other_integrity_errors_are_not_mislabeled_as_duplicate():
    with pytest.raises(IntegrityError):
        with admin_portal_view._friendly_duplicate_save():
            raise IntegrityError('insert',{},Exception('NOT NULL constraint failed'))
