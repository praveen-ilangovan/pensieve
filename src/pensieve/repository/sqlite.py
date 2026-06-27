"""
sqlite.py

The SQLite/SQLModel adapter — the **only** module that knows about `Session`, the
engine, or SQLModel queries. Implements the `Repository`/`UnitOfWork` port from
`base.py`. ``expire_on_commit=False`` so objects returned to services stay usable
after the transaction closes (services never re-touch the session).
"""

from __future__ import annotations

from types import TracebackType

from sqlmodel import Session, col, select

from ..database.models import Attachment, Counter, Node, Note
from ..database.session import get_engine, init_db
from .base import Repository


class SqliteRepository:
    """Storage primitives over a SQLModel `Session` (one open transaction)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # nodes ----------------------------------------------------------------
    def get_node(self, node_id: str) -> Node | None:
        return self._session.get(Node, node_id)

    def add_node(self, node: Node) -> None:
        self._session.add(node)

    def save_node(self, node: Node) -> None:
        self._session.add(node)

    def list_streams(self) -> list[Node]:
        statement = (
            select(Node).where(col(Node.parent_id).is_(None)).order_by(col(Node.label))
        )
        return list(self._session.exec(statement))

    # notes ----------------------------------------------------------------
    def add_note(self, note: Note) -> None:
        self._session.add(note)

    def get_note(self, note_id: str) -> Note | None:
        return self._session.get(Note, note_id)

    def save_note(self, note: Note) -> None:
        self._session.add(note)

    def delete_note(self, note_id: str) -> None:
        for att in self._session.exec(
            select(Attachment).where(Attachment.note_id == note_id)
        ):
            self._session.delete(att)
        note = self._session.get(Note, note_id)
        if note is not None:
            self._session.delete(note)

    def notes_for(self, node_id: str) -> list[Note]:
        statement = (
            select(Note)
            .join(Attachment, col(Attachment.note_id) == col(Note.id))
            .where(Attachment.node_id == node_id)
            .order_by(col(Note.created))
        )
        return list(self._session.exec(statement))

    # attachments ----------------------------------------------------------
    def attach(self, note_id: str, node_id: str) -> None:
        # Models carry no ORM relationships (dumb data holders), so the unit-of-work
        # won't order this row after the note/node it references — flush them first so
        # the FK targets exist (covers add_note->attach and create-node->attach).
        self._session.flush()
        self._session.add(Attachment(note_id=note_id, node_id=node_id))

    def detach(self, note_id: str, node_id: str) -> None:
        att = self._session.get(Attachment, (note_id, node_id))
        if att is not None:
            self._session.delete(att)

    def next_id(self, scope: str, kind: str, prefix: str) -> str:
        counter = self._session.get(Counter, (scope, kind))
        if counter is None:
            counter = Counter(scope=scope, kind=kind, next=0)
        n = counter.next + 1
        counter.next = n
        self._session.add(counter)
        return f"{prefix}{n}"


class SqliteUnitOfWork:
    """A transaction over the configured SQLite store. Ensures the schema on enter."""

    repo: Repository

    def __init__(self) -> None:
        self._session: Session | None = None

    def __enter__(self) -> SqliteUnitOfWork:
        init_db()
        self._session = Session(get_engine(), expire_on_commit=False)
        self.repo = SqliteRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        if exc_type is not None:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()
