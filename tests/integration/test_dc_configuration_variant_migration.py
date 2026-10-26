import json
import sqlite3

from alembic import command
from alembic.config import Config

from calb_sizing_tool.services.product_admin_service import ProductAdminService


def contents(path):
    with sqlite3.connect(path) as db:
        names = [r[0] for r in db.execute("select name from sqlite_master where type='table'")
                 if r[0] != 'alembic_version' and not r[0].startswith('sqlite_')
                 and not r[0].startswith('dc_configuration_variant')]
        return {name: sorted(json.dumps(r, default=str) for r in db.execute('select * from "' + name + '"'))
                for name in names}


def test_variant_migration_preserves_catalogue_and_roundtrips(tmp_path, monkeypatch):
    path = tmp_path / 'variant-migration.sqlite'
    url = 'sqlite:///' + path.as_posix()
    monkeypatch.setenv('CALB_DATABASE_URL', url)
    cfg = Config('alembic.ini')
    command.upgrade(cfg, '20261020_0011')
    ProductAdminService(url).create_dc_block(dict(block_code='EXISTING', block_name='Existing active block',
                                               is_active=True, is_published=True))
    before = contents(path)
    command.upgrade(cfg, '20261020_0012')
    assert contents(path) == before
    with sqlite3.connect(path) as db:
        assert db.execute('select count(*) from dc_configuration_variant').fetchone()[0] == 0
        assert db.execute('select count(*) from dc_configuration_variant_event').fetchone()[0] == 0
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        fks = list(db.execute('pragma foreign_key_list(dc_configuration_variant)'))
        assert len(fks) == 4
        assert {row[6] for row in fks} == {'RESTRICT'}
    command.downgrade(cfg, '20261020_0011')
    assert contents(path) == before
    command.upgrade(cfg, '20261020_0012')
    assert contents(path) == before
