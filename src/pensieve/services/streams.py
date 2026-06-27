"""
streams.py

Stream domain logic. A "stream" is a top-level `subject` node (no parent). Pure
domain/use-case layer: it depends on the `UnitOfWork` port, never on a storage engine.
"""

from __future__ import annotations

from collections.abc import Callable

from ..database.models import SCHEMA_VERSION, Node
from ..errors import PensieveError, StreamExists  # re-exported for callers/tests
from ..repository.base import UnitOfWork
from ..slug import slugify  # re-exported for callers/tests

__all__ = ["PensieveError", "StreamExists", "StreamService", "slugify"]


class StreamService:
    """Create and list streams, atop an injected unit-of-work factory."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def create_stream(self, name: str, purpose: str = "") -> Node:
        """Create a top-level `subject` node (a stream). Raises if the id is taken."""
        node_id = slugify(name)
        with self._uow() as uow:
            if uow.repo.get_node(node_id) is not None:
                raise StreamExists(f"Stream '{node_id}' already exists")
            node = Node(
                id=node_id,
                label=name,
                kind="subject",
                parent_id=None,
                properties={"purpose": purpose},
                version=1,
                schema_version=SCHEMA_VERSION,
            )
            uow.repo.add_node(node)
            uow.commit()
            return node

    def list_streams(self) -> list[Node]:
        """All top-level nodes (streams), ordered by label."""
        with self._uow() as uow:
            return uow.repo.list_streams()

    def get_stream(self, node_id: str) -> Node | None:
        """A single node by id (None if absent)."""
        with self._uow() as uow:
            return uow.repo.get_node(node_id)
