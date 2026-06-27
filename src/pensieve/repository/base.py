"""
base.py

The storage **port**: a `Repository` of low-level graph primitives, and a
`UnitOfWork` that owns one transaction. Services depend on *these protocols only* —
never on SQLite, SQLModel, or `Session`. Swapping storage = providing another adapter
(see `sqlite.py`, `memory.py`); the service/domain layer is untouched.

The `UnitOfWork` is what lets a service compose several repo calls into one atomic
commit (e.g. `add_note` = note + history + counter + version bump in a single commit):

    with uow_factory() as uow:
        node = uow.repo.get_node(node_id)
        ...
        uow.repo.add_note(note)
        uow.commit()              # nothing persists until this call
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from types import TracebackType

    from ..database.models import Entity, Node, Note


@runtime_checkable
class Repository(Protocol):
    """Storage-agnostic primitives. Adapters implement; services consume."""

    # nodes (streams / threads)
    def get_node(self, node_id: str, *, include_deleted: bool = False) -> Node | None:
        """A node by id. ``include_deleted`` returns it even if soft-deleted (for
        restore logic); by default soft-deleted nodes read as absent."""
        ...

    def add_node(self, node: Node) -> None: ...
    def save_node(self, node: Node) -> None: ...
    def set_node_deleted(self, node_id: str, when: object) -> bool:
        """Soft-delete (``when`` a datetime) or restore (``when`` None) a node — raw
        lookup (acts on already-deleted rows too). Returns whether the node existed."""
        ...

    def list_streams(self) -> list[Node]: ...
    def children_of(self, node_id: str, *, include_deleted: bool = False) -> list[Node]:
        """Child nodes (threads) directly under a node, ordered by label.
        ``include_deleted`` surfaces soft-deleted threads (for cascade/restore)."""
        ...

    def find_nodes(self, query: str) -> list[Node]:
        """Fuzzy/substring match over node label + id (streams and threads)."""
        ...

    # notes (standalone; multi-homed via attachments)
    def add_note(self, note: Note) -> None: ...
    def get_note(self, note_id: str) -> Note | None: ...
    def save_note(self, note: Note) -> None: ...
    def set_note_deleted(self, note_id: str, when: object) -> bool:
        """Soft-delete (``when`` a datetime) or restore (``when`` None) a note — raw
        lookup (acts on already-deleted rows too). Returns whether the note existed."""
        ...

    def delete_note(self, note_id: str) -> None:
        """Hard-delete a note and all its attachments (reserved for future ``forget``)."""
        ...

    def notes_for(self, node_id: str) -> list[Note]:
        """The notes attached to a node, in chronological order."""
        ...

    # attachments (note <-> node, many-to-many)
    def attach(self, note_id: str, node_id: str) -> None: ...
    def detach(self, note_id: str, node_id: str) -> None: ...

    # entities (the tag registry)
    def add_entity(self, entity: Entity) -> None: ...
    def get_entity(self, entity_id: str) -> Entity | None: ...
    def save_entity(self, entity: Entity) -> None: ...
    def list_entities(self) -> list[Entity]: ...
    def find_entities(self, query: str) -> list[Entity]:
        """Fuzzy/substring match over canonical name + aliases (candidate shortlist)."""
        ...

    # tags (note <-> entity links, many-to-many; soft-unlinkable)
    def tag_note(self, note_id: str, entity_id: str) -> None:
        """Link a note to an entity (reviving a soft-unlinked link if one exists)."""
        ...

    def untag_note(self, note_id: str, entity_id: str) -> None:
        """**Hard**-remove a link — for correcting a mis-tag (no restore needed)."""
        ...

    def set_tags_deleted_for_entity(self, entity_id: str, when: object) -> None:
        """Soft-unlink (``when`` a datetime) or re-link (``when`` None) **every** link to
        the entity — this is what ``entity rm`` / ``entity restore`` ride on. Notes are
        never touched (a note owns its entities, not the reverse)."""
        ...

    def tags_for_note(self, note_id: str) -> list[str]:
        """The entity ids a note **actively** links to (live links only)."""
        ...

    def notes_for_entity(self, entity_id: str) -> list[Note]:
        """The **live** notes actively linked to the entity, in chronological order."""
        ...

    def count_for_entity(self, entity_id: str) -> int:
        """Count of **live** notes actively linked to the entity (the promotion counter)."""
        ...

    def next_id(self, scope: str, kind: str, prefix: str) -> str:
        """Allocate the next non-reusing id (1-based), e.g. ``note-1``."""
        ...


class UnitOfWork(Protocol):
    """One transaction. ``repo`` is valid only inside the ``with`` block; changes
    persist only if ``commit()`` is called before exit."""

    repo: Repository

    def __enter__(self) -> UnitOfWork: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def commit(self) -> None: ...
