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

    from ..database.models import History, Node, Note


@runtime_checkable
class Repository(Protocol):
    """Storage-agnostic graph primitives. Adapters implement; services consume."""

    def get_node(self, node_id: str) -> Node | None: ...
    def add_node(self, node: Node) -> None: ...
    def save_node(self, node: Node) -> None: ...
    def list_streams(self) -> list[Node]: ...
    def add_note(self, note: Note) -> None: ...
    def notes_for(self, node_id: str) -> list[Note]:
        """A node's notes in chronological (insertion) order."""
        ...

    def add_history(self, history: History) -> None: ...
    def next_id(self, scope: str, kind: str, prefix: str) -> str:
        """Allocate the next non-reusing id (1-based), e.g. ``note-1``, ``c1``."""
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
