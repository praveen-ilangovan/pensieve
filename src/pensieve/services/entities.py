"""
entities.py

Entity domain logic — the registry that lets the memory group itself. An entity is a
named thing notes refer to (person/org/topic); it lives as a lightweight tag target
until it recurs past the threshold and is **promoted** into its own thread (slice 5b,
chunk 3).

This module covers the registry + resolution helpers (chunk 1): create, get, list (with
counts), and fuzzy `find`. The agent does the *semantic* resolution; these are the
engine-side primitives it leans on (`list_entities` to load, `find_entities` to shortlist).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from ..database.models import Entity, Node
from ..errors import (  # re-exported for callers
    EntityExists,
    EntityNotFound,
    NodeNotFound,
    PensieveError,
)
from ..repository.base import UnitOfWork
from ..slug import slugify

__all__ = ["EntityExists", "EntityNotFound", "EntityService", "PensieveError"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EntityService:
    """Manage the entity registry, atop an injected unit-of-work factory."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def create_entity(
        self, name: str, kind: str, aliases: list[str] | None = None
    ) -> Entity:
        """Create a registry entry. Raises ``EntityExists`` if the slug is taken."""
        entity_id = slugify(name)
        with self._uow() as uow:
            if uow.repo.get_entity(entity_id) is not None:
                raise EntityExists(f"Entity '{entity_id}' already exists")
            now = _utcnow()
            entity = Entity(
                id=entity_id,
                name=name,
                kind=kind,
                aliases=aliases or [],
                created=now,
                updated=now,
            )
            uow.repo.add_entity(entity)
            uow.commit()
            return entity

    def get_entity(self, entity_id: str) -> Entity:
        with self._uow() as uow:
            entity = uow.repo.get_entity(entity_id)
            if entity is None:
                raise EntityNotFound(f"No entity '{entity_id}'")
            return entity

    def get_entity_view(self, entity_id: str) -> dict[str, Any]:
        """Recall: the entity + every **live** note that references it (promoted or not).
        An entity with no live notes has effectively vanished (derived) → ``EntityNotFound``."""
        with self._uow() as uow:
            entity = uow.repo.get_entity(entity_id)
            notes = uow.repo.notes_for_entity(entity_id) if entity is not None else []
            if entity is None or not notes:
                raise EntityNotFound(f"No entity '{entity_id}'")
            return {
                "id": entity.id,
                "name": entity.name,
                "kind": entity.kind,
                "aliases": entity.aliases,
                "count": len(notes),
                "promoted": entity.node_id is not None,
                "node_id": entity.node_id,
                "notes": [
                    {"id": n.id, "text": n.text, "date": n.created.isoformat()}
                    for n in notes
                ],
            }

    def list_entities(self) -> list[dict[str, Any]]:
        """The live registry with counts — what the agent loads to resolve against.
        Entities with no live note are derived-gone and omitted."""
        with self._uow() as uow:
            views = [self._view(uow, e) for e in uow.repo.list_entities()]
            return [v for v in views if v["count"] >= 1]

    def find_entities(self, query: str) -> list[dict[str, Any]]:
        """Fuzzy candidate shortlist (name/alias substring) with counts. Entities with no
        live note are omitted (derived-gone)."""
        with self._uow() as uow:
            views = [self._view(uow, e) for e in uow.repo.find_entities(query)]
            return [v for v in views if v["count"] >= 1]

    def promote_entity(self, entity_id: str, parent_stream: str) -> Node:
        """Promote an entity into its own **thread** under a stream: create the node,
        attach every note that references the entity (additive — they keep their stream
        attachments), and link the entity to its node.

        Raises ``EntityNotFound`` / ``NodeNotFound`` / ``PensieveError`` (already
        promoted, or the node id collides).
        """
        with self._uow() as uow:
            entity = uow.repo.get_entity(entity_id)
            if entity is None:
                raise EntityNotFound(f"No entity '{entity_id}'")
            if entity.node_id is not None:
                raise PensieveError(f"Entity '{entity_id}' is already promoted")
            if uow.repo.get_node(parent_stream) is None:
                raise NodeNotFound(f"No node '{parent_stream}'")
            if not uow.repo.notes_for_entity(entity_id):
                raise PensieveError(f"Entity '{entity_id}' has no notes to promote")
            if uow.repo.get_node(entity_id) is not None:
                raise PensieveError(f"A node '{entity_id}' already exists")

            now = _utcnow()
            node = Node(
                id=entity_id,
                label=entity.name,
                kind=entity.kind,
                parent_id=parent_stream,
                created=now,
                updated=now,
            )
            uow.repo.add_node(node)
            for note in uow.repo.notes_for_entity(entity_id):
                uow.repo.attach(note.id, entity_id)
            entity.node_id = entity_id
            entity.updated = now
            uow.repo.save_entity(entity)
            uow.commit()
            return node

    def edit_entity(
        self,
        entity_id: str,
        *,
        name: str | None = None,
        aliases: list[str] | None = None,
    ) -> Entity:
        """Rename an entity / replace its aliases. The **id is immutable**. If the entity
        is promoted, its thread node's label is kept in sync. Raises ``EntityNotFound``."""
        with self._uow() as uow:
            entity = uow.repo.get_entity(entity_id)
            if entity is None:
                raise EntityNotFound(f"No entity '{entity_id}'")
            now = _utcnow()
            if name is not None:
                entity.name = name
                if entity.node_id is not None:
                    node = uow.repo.get_node(entity.node_id)
                    if node is not None:
                        node.label = name
                        node.updated = now
                        uow.repo.save_node(node)
            if aliases is not None:
                entity.aliases = aliases
            entity.updated = now
            uow.repo.save_entity(entity)
            uow.commit()
            return entity

    def delete_entity(self, entity_id: str) -> None:
        """Remove an entity (and its thread, if promoted): **purge its notes** — soft-delete
        every note tagged with it — and soft-delete its thread node. Any *other* entity left
        with no live note vanishes too (derived, recursive). A genuinely entity-less note
        elsewhere is untouched. Reversible via ``restore_entity``. Raises ``EntityNotFound``."""
        with self._uow() as uow:
            entity = uow.repo.get_entity(
                entity_id
            )  # raw — entities carry no deleted_at
            if entity is None:
                raise EntityNotFound(f"No entity '{entity_id}'")
            now = _utcnow()
            for note_id in uow.repo.note_ids_for_entity(entity_id):
                uow.repo.set_note_deleted(note_id, now)
            if entity.node_id is not None:
                uow.repo.set_node_deleted(entity.node_id, now)
            uow.commit()

    def restore_entity(self, entity_id: str) -> None:
        """Reverse ``delete_entity``: un-delete the entity's notes and its thread node.
        Derived entities riding those notes reappear too. Raises ``EntityNotFound``."""
        with self._uow() as uow:
            entity = uow.repo.get_entity(entity_id)
            if entity is None:
                raise EntityNotFound(f"No entity '{entity_id}'")
            for note_id in uow.repo.note_ids_for_entity(entity_id):
                uow.repo.set_note_deleted(note_id, None)
            if entity.node_id is not None:
                uow.repo.set_node_deleted(entity.node_id, None)
            uow.commit()

    def _view(self, uow: UnitOfWork, entity: Entity) -> dict[str, Any]:
        count = uow.repo.count_for_entity(entity.id)
        threshold = get_settings().PROMOTION_THRESHOLD
        return {
            "id": entity.id,
            "name": entity.name,
            "kind": entity.kind,
            "aliases": entity.aliases,
            "count": count,
            "promoted": entity.node_id is not None,
            "promotable": entity.node_id is None and count >= threshold,
        }
