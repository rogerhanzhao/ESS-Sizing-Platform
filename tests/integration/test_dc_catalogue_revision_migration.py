import json
import sqlite3

from alembic import command
from alembic.config import Config

from calb_sizing_tool.services.product_admin_service import ProductAdminService


def contents(path):
    with sqlite3.connect(path) as db:
        names = [r[0] for r in db.execute("select name from sqlite_master where type='table'")
                 if r[0] != 'alembic_version' and not r[0].startswith('sqlite_')
                 and not r[0].startswith('dc_catalogue_revision')
                 and not r[0].startswith('dc_configuration_variant')
                 and not r[0].startswith('ac_equipment_capability')]
        return {name: sorted(json.dumps(r, default=str) for r in db.execute('select * from "'+name+'"'))
                for name in names}


def test_revision_migration_preserves_old_records_and_roundtrips(tmp_path, monkeypatch):
    path = tmp_path / 'migration.sqlite'
    url = 'sqlite:///' + path.as_posix()
    monkeypatch.setenv('CALB_DATABASE_URL', url)
    cfg = Config('alembic.ini')
    command.upgrade(cfg, '20261013_0010')
    ProductAdminService(url).create_dc_block(dict(block_code='OLD', block_name='Existing block',
                                               is_active=True, is_published=True))
    before = contents(path)
    command.upgrade(cfg, 'head')
    assert contents(path) == before
    with sqlite3.connect(path) as db:
        assert db.execute('select count(*) from dc_catalogue_revision').fetchone()[0] == 0
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
    command.downgrade(cfg, '20261013_0010')
    assert contents(path) == before
    command.upgrade(cfg, 'head')
    assert contents(path) == before
