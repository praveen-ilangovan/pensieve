"""
session.py

SQLite engine + session management. Sync (SQLite, single-file store). The engine is
cached per database URL, so tests pointing `PENSIEVE_HOME` at a temp dir each get an
isolated engine. Standard pragmas (WAL, foreign_keys, busy_timeout) are applied on
every connection.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from ..config import get_settings

# Importing models registers them on SQLModel.metadata (needed by create_all).
from . import models as _models  # noqa: F401

_engines: dict[str, Engine] = {}


def _install_pragmas(engine: Engine, busy_timeout_ms: int) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn: object, _record: object) -> None:
        cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cur.close()


def get_engine() -> Engine:
    """The SQLite engine for the configured store (created + cached on first use)."""
    settings = get_settings()
    url = settings.db_url
    engine = _engines.get(url)
    if engine is None:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, echo=settings.ECHO)
        _install_pragmas(engine, settings.BUSY_TIMEOUT_MS)
        _engines[url] = engine
    return engine


def init_db() -> None:
    """Create all tables (idempotent)."""
    SQLModel.metadata.create_all(get_engine())


def reset_engines() -> None:
    """Dispose and clear all cached engines (used by tests for isolation)."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session bound to the configured engine."""
    with Session(get_engine()) as session:
        yield session
