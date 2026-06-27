"""
Unit-test fixtures — no real database.

Services are exercised against the in-memory adapter (`repository.memory`), our
unit-level double for the storage port. Same services, zero SQLite — so these tests
stay fast and also guard the decoupling (a service reaching past the port would break).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pensieve.repository.memory import InMemoryUnitOfWork, MemoryState
from pensieve.services.content import ContentService
from pensieve.services.entities import EntityService
from pensieve.services.streams import StreamService


@pytest.fixture
def services() -> SimpleNamespace:
    """A Stream/Content/Entity service trio sharing one in-memory store.

    Returns a namespace: ``services.streams``, ``services.content``,
    ``services.entities``, ``services.state`` (the raw `MemoryState`), and
    ``services.uow`` (a factory, for tagging/attaching directly in tests).
    """
    state = MemoryState()

    def uow_factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(state)

    return SimpleNamespace(
        streams=StreamService(uow_factory),
        content=ContentService(uow_factory),
        entities=EntityService(uow_factory),
        state=state,
        uow=uow_factory,
    )
