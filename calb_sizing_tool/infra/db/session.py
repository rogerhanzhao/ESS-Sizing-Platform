from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_SQLITE_PATH = Path("var/calb_sizing.sqlite")


def get_database_url() -> str:
    env_url = os.environ.get("CALB_DATABASE_URL") or os.environ.get("CALB_DB_URL")
    if env_url:
        return env_url
    return f"sqlite:///{DEFAULT_SQLITE_PATH.resolve().as_posix()}"


def normalize_database_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return database_url

    database = url.database
    if not database or database == ":memory:":
        return database_url

    db_path = Path(database)
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(url.set(database=db_path.as_posix()))


def create_engine_for_url(database_url: str | None = None, *, echo: bool = False) -> Engine:
    url = normalize_database_url(database_url or get_database_url())
    connect_args = {"check_same_thread": False} if url.startswith("sqlite:") else {}
    engine = create_engine(url, future=True, echo=echo, connect_args=connect_args)
    if url.startswith("sqlite:"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return engine


def create_session_factory(database_url: str | None = None, *, echo: bool = False) -> sessionmaker[Session]:
    engine = create_engine_for_url(database_url, echo=echo)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope(database_url: str | None = None, *, echo: bool = False) -> Iterator[Session]:
    factory = create_session_factory(database_url, echo=echo)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
