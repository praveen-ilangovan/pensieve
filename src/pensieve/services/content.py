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

from ..database.models import Entity, Note
from ..errors import (
    EntityNotFound,
    NodeNotFound,
    NoteNotFound,
    PensieveError,
)  # re-exported for callers
from ..repository.base import UnitOfWork
from ..slug import slugify

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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
            if uow.repo.get_node(node_id) is None:
                raise NodeNotFound(f"No node '{node_id}'")
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
        """Truly remove a note (and its attachments). Raises ``NoteNotFound``."""
        with self._uow() as uow:
            if uow.repo.get_note(note_id) is None:
                raise NoteNotFound(f"No note '{note_id}'")
            uow.repo.delete_note(note_id)
            uow.commit()

    def get_stream_view(self, node_id: str) -> dict[str, Any]:
        """The node's **thin view**: identity + purpose + its notes (chronological).

        ``children`` is present but empty (filled by a later slice). Raises
        ``NodeNotFound`` if the node is missing.
        """
        with self._uow() as uow:
            node = uow.repo.get_node(node_id)
            if node is None:
                raise NodeNotFound(f"No node '{node_id}'")
            notes = uow.repo.notes_for(node_id)
            return {
                "id": node.id,
                "label": node.label,
                "kind": node.kind,
                "purpose": str(node.properties.get("purpose") or ""),
                "notes": [
                    {"id": n.id, "text": n.text, "date": n.created.isoformat()}
                    for n in notes
                ],
                "children": [],
            }
