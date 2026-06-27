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
from ..database.models import Entity
from ..errors import EntityExists, EntityNotFound  # re-exported for callers
from ..repository.base import UnitOfWork
from ..slug import slugify

__all__ = ["EntityNotFound", "EntityExists", "EntityService"]


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

    def list_entities(self) -> list[dict[str, Any]]:
        """The whole registry with counts — what the agent loads to resolve against."""
        with self._uow() as uow:
            return [self._view(uow, e) for e in uow.repo.list_entities()]

    def find_entities(self, query: str) -> list[dict[str, Any]]:
        """Fuzzy candidate shortlist (name/alias substring) with counts."""
        with self._uow() as uow:
            return [self._view(uow, e) for e in uow.repo.find_entities(query)]

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
