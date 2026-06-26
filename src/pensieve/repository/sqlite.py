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

from ..database.models import Counter, History, Node, Note
from ..database.session import get_engine, init_db
from .base import Repository


class SqliteRepository:
    """Graph primitives over a SQLModel `Session` (one open transaction)."""

    def __init__(self, session: Session) -> None:
        self._session = session

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

    def add_note(self, note: Note) -> None:
        self._session.add(note)

    def notes_for(self, node_id: str) -> list[Note]:
        statement = select(Note).where(Note.node_id == node_id).order_by(col(Note.date))
        return list(self._session.exec(statement))

    def add_history(self, history: History) -> None:
        self._session.add(history)

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
