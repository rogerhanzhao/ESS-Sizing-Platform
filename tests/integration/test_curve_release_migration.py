import sqlite3
from alembic import command
from alembic.config import Config


def contents(path):
    with sqlite3.connect(path) as c:
        return {t: c.execute('select * from "'+t+'"').fetchall()
                for (t,) in c.execute("select name from sqlite_master where type='table'")
                if t!='alembic_version' and not t.startswith(('sqlite_','curve_'))}


def test_curve_migration_adds_empty_tables_without_changing_old_data(tmp_path,monkeypatch):
    path=tmp_path/'curves.sqlite'
    monkeypatch.setenv('CALB_DATABASE_URL',f'sqlite:///{path.as_posix()}')
    cfg=Config('alembic.ini');command.upgrade(cfg,'20261021_0013')
    before=contents(path)
    command.upgrade(cfg,'20261118_0014')
    assert contents(path)==before
    with sqlite3.connect(path) as c:
        assert c.execute('select count(*) from curve_release').fetchone()[0]==0
        assert c.execute('select count(*) from curve_default_binding').fetchone()[0]==0
        assert c.execute('pragma foreign_key_check').fetchall()==[]
    command.downgrade(cfg,'20261021_0013');assert contents(path)==before
    command.upgrade(cfg,'20261118_0014');assert contents(path)==before
