"""Apply the new evidence tables only to freshly created, isolated databases."""

import json
import sqlite3
from types import SimpleNamespace

from alembic import command
from alembic.config import Config

from calb_sizing_tool.services.ac_equipment_capability_service import EquipmentCapabilityRevisionService
from calb_sizing_tool.services.product_admin_service import ProductAdminService


def contents(path):
    with sqlite3.connect(path) as db:
        names = [row[0] for row in db.execute("select name from sqlite_master where type='table'")
                 if row[0] != "alembic_version" and not row[0].startswith("sqlite_")
                 and not row[0].startswith("ac_equipment_capability_")]
        return {name: sorted(json.dumps(row, default=str)
                             for row in db.execute('select * from "' + name + '"'))
                for name in names}


def test_capability_migration_preserves_every_old_table_and_roundtrips(tmp_path, monkeypatch):
    path = tmp_path / "isolated-equipment-migration.sqlite"
    url = "sqlite:///" + path.as_posix()
    monkeypatch.setenv("CALB_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "20261020_0012")
    ProductAdminService(url).create_dc_block(dict(block_code="EXISTING-DC", block_name="Existing",
                                               is_active=True, is_published=True))
    before = contents(path)
    command.upgrade(config, "20261021_0013")
    assert contents(path) == before
    registry = EquipmentCapabilityRevisionService(SimpleNamespace(username="synthetic", is_admin=True), url)
    revision_id = registry.create(dict(package_code="SYN-PCS", revision="1", kind="pcs",
        model="Synthetic", manufacturer="SYNTHETIC ONLY", source_ref="synthetic:only", conditions={},
        pcs=dict(ports=[dict(port_id="P1", dc_bus_group="B1")], dc_buses=[dict(dc_bus_group="B1")])),
        "synthetic:source")
    registry.transition(revision_id, "draft", "parameter_review", "synthetic:parameters")
    registry.transition(revision_id, "parameter_review", "candidate_only", "synthetic:review")
    assert registry.inspect(revision_id)["candidate_review_current"]
    assert contents(path) == before
    with sqlite3.connect(path) as db:
        assert db.execute("select version_num from alembic_version").fetchone()[0] == "20261021_0013"
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert list(db.execute("pragma foreign_key_check")) == []
        assert list(db.execute("pragma foreign_key_list(ac_equipment_capability_revision)")) == []
        fks = list(db.execute("pragma foreign_key_list(ac_equipment_capability_event)"))
        assert len(fks) == 1 and fks[0][2] == "ac_equipment_capability_revision" and fks[0][6] == "RESTRICT"
        assert db.execute("select count(*) from ac_equipment_capability_event").fetchone()[0] == 3
    command.downgrade(config, "20261020_0012")
    assert contents(path) == before
    with sqlite3.connect(path) as db:
        assert not db.execute("select name from sqlite_master where name like 'ac_equipment_capability_%'").fetchall()
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
    command.upgrade(config, "20261021_0013")
    assert contents(path) == before
    assert registry.list_revisions() == []
