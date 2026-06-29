"""
content.py

Content domain logic — notes (the information in the lake). Pure domain/use-case layer
atop the `UnitOfWork` port.

Notes are **append-only information**: `add_note` records a new piece of information and
attaches it to a node. `update_note` edits a note in place (only to fix a genuine
mistake — a world-change is a *new* note). `delete_note` truly removes one. Note ids are
**global** (`note-1`, `note-2`, …); a note is multi-homed via attachments.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from ..database.models import Asset, Entity, Note
from ..errors import (
    EntityNotFound,
    NodeNotFound,
    NoteNotFound,
    PensieveError,
)  # re-exported for callers
from ..repository.base import UnitOfWork
from ..slug import slugify
from .assets import asset_view as _asset_view

__all__ = [
    "ContentService",
    "EntityNotFound",
    "NodeNotFound",
    "NoteNotFound",
    "PensieveError",
]

# An entity reference from the agent: either {"id": "<existing>"} or
# {"name": str, "kind": str, "aliases"?: list[str]} to resolve-or-create.
EntitySpec = dict[str, Any]


# default top-K per search section; truncation is always surfaced, never silent
_SEARCH_LIMIT = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _search_terms(query: str) -> list[str]:
    """A query → a bag of lowercased terms (OR-ed downstream; recall over precision)."""
    return [t for t in query.lower().split() if t]


def _snippet(text: str, terms: list[str], width: int = 200) -> str:
    """A short window of the note text centred on the first matching term."""
    if len(text) <= width:
        return text
    low = text.lower()
    hits = [low.find(t) for t in terms if t in low]
    pos = min(hits) if hits else 0
    start = max(0, pos - width // 3)
    end = min(len(text), start + width)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


class ContentService:
    """Add, edit, remove, and read notes — atop an injected unit-of-work factory."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def add_note(
        self,
        node_id: str,
        text: str,
        *,
        entities: Sequence[EntitySpec] | None = None,
        actor: str | None = None,
        interface: str | None = None,
    ) -> Note:
        """Record a new piece of information, attach it to a node, and tag the entities
        it references (resolved/created from ``entities``).

        Raises ``NodeNotFound`` if the node is missing, ``EntityNotFound`` if an entity
        referenced by id doesn't exist.
        """
        with self._uow() as uow:
            node = uow.repo.get_node(node_id)
            if node is None:
                raise NodeNotFound(f"No node '{node_id}'")
            if node.parent_id is not None:
                raise PensieveError(
                    f"'{node_id}' is a thread, not a stream — capture to a stream; "
                    "notes reach a thread by tagging its entity."
                )
            note_id = uow.repo.next_id("_note", "note", "note-")
            now = _utcnow()
            note = Note(
                id=note_id,
                text=text,
                created=now,
                updated=now,
                actor=actor,
                interface=interface,
            )
            uow.repo.add_note(note)
            uow.repo.attach(note_id, node_id)
            for spec in entities or ():
                self._tag(uow, note_id, self._resolve_entity(uow, spec, now))
            uow.commit()
            return note

    def tag_note(self, note_id: str, entities: Sequence[EntitySpec]) -> list[str]:
        """Tag an existing note with entities (resolve/create). Returns the entity ids.

        Raises ``NoteNotFound`` / ``EntityNotFound``.
        """
        with self._uow() as uow:
            if uow.repo.get_note(note_id) is None:
                raise NoteNotFound(f"No note '{note_id}'")
            now = _utcnow()
            ids = []
            for spec in entities:
                entity_id = self._resolve_entity(uow, spec, now)
                self._tag(uow, note_id, entity_id)
                ids.append(entity_id)
            uow.commit()
            return ids

    def untag_note(self, note_id: str, entity_id: str) -> None:
        """Remove an entity tag from a note — for correcting a mis-tag. If the entity is
        promoted, also detach the note from its thread (the inverse of tagging). Raises
        ``NoteNotFound``; a tag that isn't there is a no-op.
        """
        with self._uow() as uow:
            if uow.repo.get_note(note_id) is None:
                raise NoteNotFound(f"No note '{note_id}'")
            uow.repo.untag_note(note_id, entity_id)
            entity = uow.repo.get_entity(entity_id)
            if entity is not None and entity.node_id is not None:
                uow.repo.detach(note_id, entity.node_id)
            uow.commit()

    def _tag(self, uow: UnitOfWork, note_id: str, entity_id: str) -> None:
        """Tag a note with an entity; if the entity is already promoted, also attach the
        note to its thread node (so it shows under the thread immediately)."""
        uow.repo.tag_note(note_id, entity_id)
        entity = uow.repo.get_entity(entity_id)
        if entity is not None and entity.node_id is not None:
            uow.repo.attach(note_id, entity.node_id)

    def _resolve_entity(self, uow: UnitOfWork, spec: EntitySpec, now: datetime) -> str:
        """Resolve a spec to an entity id: ``{id}`` (must exist) or ``{name, kind}``
        (resolve-or-create by slug, merging any new aliases)."""
        if "id" in spec:
            entity_id = str(spec["id"])
            if uow.repo.get_entity(entity_id) is None:
                raise EntityNotFound(f"No entity '{entity_id}'")
            return entity_id

        name = str(spec["name"])
        entity_id = slugify(name)
        aliases = list(spec.get("aliases", []))
        existing = uow.repo.get_entity(entity_id)
        if existing is None:
            uow.repo.add_entity(
                Entity(
                    id=entity_id,
                    name=name,
                    kind=str(spec.get("kind", "topic")),
                    aliases=aliases,
                    created=now,
                    updated=now,
                )
            )
        elif aliases:  # grow aliases as we learn them
            merged = list(dict.fromkeys([*existing.aliases, *aliases]))
            if merged != existing.aliases:
                existing.aliases = merged
                existing.updated = now
                uow.repo.save_entity(existing)
        return entity_id

    def update_note(
        self,
        note_id: str,
        text: str,
        *,
        actor: str | None = None,
        interface: str | None = None,
    ) -> Note:
        """Rewrite a note's text in place (for fixing a genuine mistake).

        Raises ``NoteNotFound`` if the note is missing.
        """
        with self._uow() as uow:
            note = uow.repo.get_note(note_id)
            if note is None:
                raise NoteNotFound(f"No note '{note_id}'")
            note.text = text
            note.updated = _utcnow()
            if actor is not None:
                note.actor = actor
            if interface is not None:
                note.interface = interface
            uow.repo.save_note(note)
            uow.commit()
            return note

    def delete_note(self, note_id: str) -> None:
        """**Soft-delete** a note — it stops being live, any entity that loses its last
        live note disappears (derived), and it can be brought back with ``restore_note``.
        (A genuinely stream-level note with no entities simply leaves that stream's view.)
        Raises ``NoteNotFound``."""
        with self._uow() as uow:
            if uow.repo.get_note(note_id) is None:  # already-deleted reads as absent
                raise NoteNotFound(f"No note '{note_id}'")
            uow.repo.set_note_deleted(note_id, _utcnow())
            uow.commit()

    def restore_note(self, note_id: str) -> None:
        """Un-delete a soft-deleted note (raw lookup — it's hidden from normal reads).
        Its entities reappear if it was their last note. Raises ``NoteNotFound``."""
        with self._uow() as uow:
            if not uow.repo.set_note_deleted(note_id, None):
                raise NoteNotFound(f"No note '{note_id}'")
            uow.commit()

    def get_stream_view(self, node_id: str) -> dict[str, Any]:
        """The node's **thin view**: identity + purpose + child **threads** + its **loose**
        notes (those *not* covered by a thread under this node — see ``_covered``).

        Storage is unchanged (notes stay attached); this only filters what's rendered, so
        a stream stays a glance as its entities promote. Raises ``NodeNotFound``.
        """
        with self._uow() as uow:
            node = uow.repo.get_node(node_id)
            if node is None:
                raise NodeNotFound(f"No node '{node_id}'")
            children = uow.repo.children_of(node_id)
            child_ids = {c.id for c in children}
            loose = [
                n
                for n in uow.repo.notes_for(node_id)
                if not self._covered(uow, n.id, child_ids)
            ]
            return {
                "id": node.id,
                "label": node.label,
                "kind": node.kind,
                "purpose": str(node.properties.get("purpose") or ""),
                "assets": [_asset_view(a) for a in uow.repo.assets_for_node(node_id)],
                "notes": [
                    {
                        "id": n.id,
                        "text": n.text,
                        "date": n.created.isoformat(),
                        "assets": [
                            _asset_view(a) for a in uow.repo.assets_for_note(n.id)
                        ],
                    }
                    for n in loose
                ],
                "children": [
                    {
                        "id": c.id,
                        "label": c.label,
                        "kind": c.kind,
                        "count": len(uow.repo.notes_for(c.id)),
                    }
                    for c in children
                ],
            }

    def search(self, query: str, *, limit: int = _SEARCH_LIMIT) -> dict[str, Any]:
        """Recall over **content**: note prose (stemmed, ranked) + asset pointers
        (hint/label/location). Live results only; the engine never follows a pointer. Each
        section is capped at ``limit`` with a ``*_truncated`` flag — never a silent cap."""
        empty = {
            "query": query,
            "notes": [],
            "assets": [],
            "notes_truncated": False,
            "assets_truncated": False,
        }
        terms = _search_terms(query)
        if not terms:
            return empty
        with self._uow() as uow:
            raw_notes = uow.repo.search_notes(
                terms, limit + 1
            )  # +1 to detect truncation
            raw_assets = uow.repo.search_assets(terms, limit + 1)
            return {
                "query": query,
                "notes": [
                    self._search_note_view(uow, n, terms) for n in raw_notes[:limit]
                ],
                "assets": [self._search_asset_view(a) for a in raw_assets[:limit]],
                "notes_truncated": len(raw_notes) > limit,
                "assets_truncated": len(raw_assets) > limit,
            }

    def _search_note_view(
        self, uow: UnitOfWork, note: Note, terms: list[str]
    ) -> dict[str, Any]:
        homes = uow.repo.nodes_for_note(note.id)
        return {
            "id": note.id,
            "text": note.text,
            "snippet": _snippet(note.text, terms),
            "date": note.created.isoformat(),
            "streams": [{"id": h.id, "label": h.label} for h in homes],
            "entities": uow.repo.tags_for_note(note.id),
        }

    def _search_asset_view(self, asset: Asset) -> dict[str, Any]:
        view = _asset_view(asset)  # id/kind/location/hint/label/remote/missing
        view["owner"] = asset.node_id or asset.note_id
        view["owner_kind"] = "node" if asset.node_id else "note"
        return view

    def _covered(self, uow: UnitOfWork, note_id: str, child_ids: set[str]) -> bool:
        """A note is *covered* (hidden from this node's loose list) iff it has ≥1 tag and
        **every** tagged entity is promoted to a thread under this node."""
        tags = uow.repo.tags_for_note(note_id)
        if not tags:
            return False
        for entity_id in tags:
            entity = uow.repo.get_entity(entity_id)
            if entity is None or entity.node_id not in child_ids:
                return False
        return True
