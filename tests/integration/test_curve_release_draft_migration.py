import sqlite3
from alembic import command
from alembic.config import Config


def test_rte_draft_migration_preserves_existing_curve_packages(tmp_path,monkeypatch):
    p=tmp_path/'rte.sqlite';monkeypatch.setenv('CALB_DATABASE_URL',f'sqlite:///{p.as_posix()}')
    cfg=Config('alembic.ini');command.upgrade(cfg,'20261118_0014')
    def contents():
        with sqlite3.connect(p) as c:
            return {t:c.execute('select * from "'+t+'"').fetchall() for (t,) in c.execute("select name from sqlite_master where type='table'") if t not in ('alembic_version','curve_release_draft') and not t.startswith('sqlite_')}
    before=contents();command.upgrade(cfg,'20261118_0015');assert contents()==before
    with sqlite3.connect(p) as c:assert c.execute('select count(*) from curve_release_draft').fetchone()[0]==0
    command.downgrade(cfg,'20261118_0014');assert contents()==before
