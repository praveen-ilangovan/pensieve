"""
memory.py

An in-memory adapter for the same `Repository`/`UnitOfWork` port — a second, fully
working storage backend with **no SQLite involved**. It exists for two reasons:

1. it makes the decoupling concrete (one port, two adapters), and
2. it's a fast, dependency-free double for unit-testing service/domain logic.

It honours the transaction boundary: each `UnitOfWork` works on a shallow copy and
applies it to the shared store only on `commit()` — so "forgot to commit" fails here
exactly as it would on SQLite. Reads return **clones** (via `model_dump`) so a service
mutating a fetched node can't leak uncommitted changes into the shared store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType
from typing import TypeVar

from ..database.models import History, Node, Note
from .base import Repository

_M = TypeVar("_M", Node, Note, History)


def _clone(obj: _M) -> _M:
    """A detached copy, free of any backend instrumentation."""
    return type(obj)(**obj.model_dump())


@dataclass
class MemoryState:
    """The committed store, shared across `UnitOfWork` instances (the 'database')."""

    nodes: dict[str, Node] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)
    history: list[History] = field(default_factory=list)
    counters: dict[tuple[str, str], int] = field(default_factory=dict)

    def copy(self) -> MemoryState:
        return MemoryState(
            nodes=dict(self.nodes),
            notes=list(self.notes),
            history=list(self.history),
            counters=dict(self.counters),
        )


class InMemoryRepository:
    """Graph primitives over a `MemoryState` working copy."""

    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def get_node(self, node_id: str) -> Node | None:
        node = self._state.nodes.get(node_id)
        return _clone(node) if node is not None else None

    def add_node(self, node: Node) -> None:
        self._state.nodes[node.id] = node

    def save_node(self, node: Node) -> None:
        self._state.nodes[node.id] = node

    def list_streams(self) -> list[Node]:
        streams = [n for n in self._state.nodes.values() if n.parent_id is None]
        return [_clone(n) for n in sorted(streams, key=lambda n: n.label)]

    def add_note(self, note: Note) -> None:
        self._state.notes.append(note)

    def notes_for(self, node_id: str) -> list[Note]:
        notes = [n for n in self._state.notes if n.node_id == node_id]
        return [_clone(n) for n in sorted(notes, key=lambda n: n.date)]

    def add_history(self, history: History) -> None:
        self._state.history.append(history)

    def next_id(self, scope: str, kind: str, prefix: str) -> str:
        n = self._state.counters.get((scope, kind), 0) + 1
        self._state.counters[(scope, kind)] = n
        return f"{prefix}{n}"


class InMemoryUnitOfWork:
    """A transaction over a shared `MemoryState`; applies on `commit()` only."""

    repo: Repository

    def __init__(self, state: MemoryState) -> None:
        self._base = state
        self._work: MemoryState | None = None

    def __enter__(self) -> InMemoryUnitOfWork:
        self._work = self._base.copy()
        self.repo = InMemoryRepository(self._work)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._work = None  # uncommitted work is simply discarded

    def commit(self) -> None:
        assert self._work is not None
        self._base.nodes = self._work.nodes
        self._base.notes = self._work.notes
        self._base.history = self._work.history
        self._base.counters = self._work.counters
