from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_db_migration_roundtrip(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "alembic_roundtrip.sqlite"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("CALB_DATABASE_URL", db_url)

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    tables = sorted(inspect(engine).get_table_names())
    assert "parameter_definition" in tables
    assert "sizing_run" in tables
    assert "user_account" in tables
    assert "product_asset" in tables
    product_dc_columns = {column["name"] for column in inspect(engine).get_columns("product_dc_block")}
    assert "block_form" in product_dc_columns

    command.downgrade(cfg, "base")
    engine = create_engine(db_url)
    assert "parameter_definition" not in inspect(engine).get_table_names()

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    assert "artifact_registry" in inspect(engine).get_table_names()
    assert "product_asset" in inspect(engine).get_table_names()
