"""
memory.py

An in-memory adapter for the same `Repository`/`UnitOfWork` port — a second, fully
working storage backend with **no SQLite involved**. It exists for two reasons:

1. it makes the decoupling concrete (one port, two adapters), and
2. it's a fast, dependency-free double for unit-testing service/domain logic.

It honours the transaction boundary: each `UnitOfWork` works on a shallow copy and
applies it to the shared store only on `commit()`. Reads return **clones** (via
`model_dump`) so a service mutating a fetched row can't leak uncommitted changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType
from typing import TypeVar

from ..database.models import Node, Note
from .base import Repository

_M = TypeVar("_M", Node, Note)


def _clone(obj: _M) -> _M:
    """A detached copy, free of any backend instrumentation."""
    return type(obj)(**obj.model_dump())


@dataclass
class MemoryState:
    """The committed store, shared across `UnitOfWork` instances (the 'database')."""

    nodes: dict[str, Node] = field(default_factory=dict)
    notes: dict[str, Note] = field(default_factory=dict)
    attachments: set[tuple[str, str]] = field(default_factory=set)  # (note_id, node_id)
    counters: dict[tuple[str, str], int] = field(default_factory=dict)

    def copy(self) -> MemoryState:
        return MemoryState(
            nodes=dict(self.nodes),
            notes=dict(self.notes),
            attachments=set(self.attachments),
            counters=dict(self.counters),
        )


class InMemoryRepository:
    """Storage primitives over a `MemoryState` working copy."""

    def __init__(self, state: MemoryState) -> None:
        self._state = state

    # nodes ----------------------------------------------------------------
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

    # notes ----------------------------------------------------------------
    def add_note(self, note: Note) -> None:
        self._state.notes[note.id] = note

    def get_note(self, note_id: str) -> Note | None:
        note = self._state.notes.get(note_id)
        return _clone(note) if note is not None else None

    def save_note(self, note: Note) -> None:
        self._state.notes[note.id] = note

    def delete_note(self, note_id: str) -> None:
        self._state.notes.pop(note_id, None)
        self._state.attachments = {
            a for a in self._state.attachments if a[0] != note_id
        }

    def notes_for(self, node_id: str) -> list[Note]:
        ids = [nid for (nid, target) in self._state.attachments if target == node_id]
        notes = [self._state.notes[i] for i in ids if i in self._state.notes]
        return [_clone(n) for n in sorted(notes, key=lambda n: n.created)]

    # attachments ----------------------------------------------------------
    def attach(self, note_id: str, node_id: str) -> None:
        self._state.attachments.add((note_id, node_id))

    def detach(self, note_id: str, node_id: str) -> None:
        self._state.attachments.discard((note_id, node_id))

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
        self._base.attachments = self._work.attachments
        self._base.counters = self._work.counters
