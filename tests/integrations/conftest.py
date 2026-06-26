"""
Integration-test fixtures — the real SQLite store.

`integration_store` points `PENSIEVE_HOME` at a dedicated, wiped-fresh local store
(`.local/integration`) — never the real `~/.pensieve`. `_isolate_engines` clears the
cached engines around each test so every test binds a fresh engine to that store.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from pensieve.database import session as db_session

INTEGRATION_STORE = Path(".local/integration")


@pytest.fixture(autouse=True)
def _isolate_engines() -> Iterator[None]:
    db_session.reset_engines()
    yield
    db_session.reset_engines()


@pytest.fixture
def integration_store(monkeypatch: pytest.MonkeyPatch) -> Path:
    store = INTEGRATION_STORE.resolve()
    if store.exists():
        shutil.rmtree(store)
    store.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PENSIEVE_HOME", str(store))
    return store
