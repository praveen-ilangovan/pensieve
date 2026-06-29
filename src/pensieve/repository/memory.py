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

from ..database.models import Asset, Entity, Node, Note
from .base import Repository

_M = TypeVar("_M", Node, Note, Entity, Asset)


def _clone(obj: _M) -> _M:
    """A detached copy, free of any backend instrumentation."""
    return type(obj)(**obj.model_dump())


def _asset_haystack(asset: Asset) -> str:
    """The searchable text of an asset — its metadata, never its contents (read-on-demand)."""
    return " ".join(x for x in (asset.hint, asset.label, asset.location) if x).lower()


@dataclass
class MemoryState:
    """The committed store, shared across `UnitOfWork` instances (the 'database')."""

    nodes: dict[str, Node] = field(default_factory=dict)
    notes: dict[str, Note] = field(default_factory=dict)
    attachments: set[tuple[str, str]] = field(default_factory=set)  # (note_id, node_id)
    entities: dict[str, Entity] = field(default_factory=dict)
    # (note_id, entity_id) -> deleted_at (None = active link; a value = soft-unlinked)
    tags: dict[tuple[str, str], object | None] = field(default_factory=dict)
    assets: dict[str, Asset] = field(default_factory=dict)
    counters: dict[tuple[str, str], int] = field(default_factory=dict)

    def copy(self) -> MemoryState:
        return MemoryState(
            nodes=dict(self.nodes),
            notes=dict(self.notes),
            attachments=set(self.attachments),
            entities=dict(self.entities),
            tags=dict(self.tags),
            assets=dict(self.assets),
            counters=dict(self.counters),
        )


class InMemoryRepository:
    """Storage primitives over a `MemoryState` working copy."""

    def __init__(self, state: MemoryState) -> None:
        self._state = state

    # liveness helpers -----------------------------------------------------
    def _node_visible(self, node_id: str) -> bool:
        node = self._state.nodes.get(node_id)
        return node is not None and node.deleted_at is None

    def _note_live(self, note_id: str) -> bool:
        note = self._state.notes.get(note_id)
        if note is None or note.deleted_at is not None:
            return False
        return any(
            nid == note_id and self._node_visible(target)
            for (nid, target) in self._state.attachments
        )

    # nodes ----------------------------------------------------------------
    def get_node(self, node_id: str, *, include_deleted: bool = False) -> Node | None:
        node = self._state.nodes.get(node_id)
        if node is None or (node.deleted_at is not None and not include_deleted):
            return None
        return _clone(node)

    def add_node(self, node: Node) -> None:
        self._state.nodes[node.id] = node

    def save_node(self, node: Node) -> None:
        self._state.nodes[node.id] = node

    def set_node_deleted(self, node_id: str, when: object) -> bool:
        node = self._state.nodes.get(node_id)  # raw (may be deleted) — for rm/restore
        if node is None:
            return False
        node.deleted_at = when  # type: ignore[assignment]
        return True

    def list_streams(self) -> list[Node]:
        streams = [
            n
            for n in self._state.nodes.values()
            if n.parent_id is None and n.deleted_at is None
        ]
        return [_clone(n) for n in sorted(streams, key=lambda n: n.label)]

    def children_of(self, node_id: str, *, include_deleted: bool = False) -> list[Node]:
        kids = [
            n
            for n in self._state.nodes.values()
            if n.parent_id == node_id and (include_deleted or n.deleted_at is None)
        ]
        return [_clone(n) for n in sorted(kids, key=lambda n: n.label)]

    def find_nodes(self, query: str) -> list[Node]:
        q = query.strip().lower()
        out = [
            n
            for n in self._state.nodes.values()
            if n.deleted_at is None and (q in n.label.lower() or q in n.id.lower())
        ]
        return [_clone(n) for n in sorted(out, key=lambda n: n.label)]

    # notes ----------------------------------------------------------------
    def add_note(self, note: Note) -> None:
        self._state.notes[note.id] = note

    def get_note(self, note_id: str) -> Note | None:
        note = self._state.notes.get(note_id)
        return _clone(note) if note is not None and note.deleted_at is None else None

    def save_note(self, note: Note) -> None:
        self._state.notes[note.id] = note

    def set_note_deleted(self, note_id: str, when: object) -> bool:
        note = self._state.notes.get(note_id)  # raw (may be deleted) — for rm/restore
        if note is None:
            return False
        note.deleted_at = when  # type: ignore[assignment]
        return True

    def delete_note(self, note_id: str) -> None:
        self._state.notes.pop(note_id, None)
        self._state.attachments = {
            a for a in self._state.attachments if a[0] != note_id
        }
        self._state.tags = {
            k: v for k, v in self._state.tags.items() if k[0] != note_id
        }

    def notes_for(self, node_id: str) -> list[Note]:
        # the node is visible (caller navigated to it) → its non-deleted notes are live
        ids = [nid for (nid, target) in self._state.attachments if target == node_id]
        notes = [
            self._state.notes[i]
            for i in ids
            if i in self._state.notes and self._state.notes[i].deleted_at is None
        ]
        return [_clone(n) for n in sorted(notes, key=lambda n: n.created)]

    def nodes_for_note(self, note_id: str) -> list[Node]:
        ids = [nid for (n, nid) in self._state.attachments if n == note_id]
        nodes = [
            self._state.nodes[i]
            for i in ids
            if i in self._state.nodes and self._state.nodes[i].deleted_at is None
        ]
        return [_clone(n) for n in sorted(nodes, key=lambda n: n.label)]

    # search ---------------------------------------------------------------
    def search_notes(self, terms: list[str], limit: int) -> list[Note]:
        # substring double (any term); FTS semantics live only in the SQLite adapter.
        if not terms:
            return []
        matched = [
            n
            for n in self._state.notes.values()
            if self._note_live(n.id) and any(t in n.text.lower() for t in terms)
        ]
        matched.sort(key=lambda n: n.created, reverse=True)
        return [_clone(n) for n in matched[:limit]]

    def search_assets(self, terms: list[str], limit: int) -> list[Asset]:
        if not terms:
            return []
        matched = [
            a
            for a in self._state.assets.values()
            if any(t in _asset_haystack(a) for t in terms)
        ]
        matched.sort(key=lambda a: a.created, reverse=True)
        out: list[Asset] = []
        for a in matched:
            if self._asset_owner_live(a):
                out.append(_clone(a))
                if len(out) >= limit:
                    break
        return out

    def _asset_owner_live(self, asset: Asset) -> bool:
        if asset.node_id is not None:
            return self._node_visible(asset.node_id)
        if asset.note_id is not None:
            return self._note_live(asset.note_id)
        return False

    # attachments ----------------------------------------------------------
    def attach(self, note_id: str, node_id: str) -> None:
        self._state.attachments.add((note_id, node_id))

    def detach(self, note_id: str, node_id: str) -> None:
        self._state.attachments.discard((note_id, node_id))

    # entities -------------------------------------------------------------
    def add_entity(self, entity: Entity) -> None:
        self._state.entities[entity.id] = entity

    def get_entity(self, entity_id: str) -> Entity | None:
        ent = self._state.entities.get(entity_id)
        return _clone(ent) if ent is not None else None

    def save_entity(self, entity: Entity) -> None:
        self._state.entities[entity.id] = entity

    def list_entities(self) -> list[Entity]:
        ents = sorted(self._state.entities.values(), key=lambda e: e.name)
        return [_clone(e) for e in ents]

    def find_entities(self, query: str) -> list[Entity]:
        q = query.strip().lower()
        out = []
        for e in self._state.entities.values():
            haystack = [e.name.lower(), e.id.lower(), *(a.lower() for a in e.aliases)]
            if any(q in h for h in haystack):
                out.append(_clone(e))
        return out

    # tags -----------------------------------------------------------------
    def tag_note(self, note_id: str, entity_id: str) -> None:
        self._state.tags[(note_id, entity_id)] = None  # (re)activate the link

    def untag_note(self, note_id: str, entity_id: str) -> None:
        self._state.tags.pop((note_id, entity_id), None)  # hard remove (mis-tag fix)

    def set_tags_deleted_for_entity(self, entity_id: str, when: object) -> None:
        for key in list(self._state.tags):
            if key[1] == entity_id:
                self._state.tags[key] = when

    def tags_for_note(self, note_id: str) -> list[str]:
        return [
            eid
            for (nid, eid), deleted in self._state.tags.items()
            if nid == note_id and deleted is None
        ]

    def notes_for_entity(self, entity_id: str) -> list[Note]:
        # live = active link AND note not deleted AND attached to a visible node
        ids = [
            nid
            for (nid, eid), deleted in self._state.tags.items()
            if eid == entity_id and deleted is None and self._note_live(nid)
        ]
        notes = [self._state.notes[i] for i in ids if i in self._state.notes]
        return [_clone(n) for n in sorted(notes, key=lambda n: n.created)]

    def count_for_entity(self, entity_id: str) -> int:
        return sum(
            1
            for (nid, eid), deleted in self._state.tags.items()
            if eid == entity_id and deleted is None and self._note_live(nid)
        )

    # assets ---------------------------------------------------------------
    def add_asset(self, asset: Asset) -> None:
        self._state.assets[asset.id] = asset

    def get_asset(self, asset_id: str) -> Asset | None:
        asset = self._state.assets.get(asset_id)
        return _clone(asset) if asset is not None else None

    def remove_asset(self, asset_id: str) -> None:
        self._state.assets.pop(asset_id, None)

    def assets_for_node(self, node_id: str) -> list[Asset]:
        out = [a for a in self._state.assets.values() if a.node_id == node_id]
        return [_clone(a) for a in sorted(out, key=lambda a: a.created)]

    def assets_for_note(self, note_id: str) -> list[Asset]:
        out = [a for a in self._state.assets.values() if a.note_id == note_id]
        return [_clone(a) for a in sorted(out, key=lambda a: a.created)]

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
        self._base.entities = self._work.entities
        self._base.tags = self._work.tags
        self._base.assets = self._work.assets
        self._base.counters = self._work.counters
