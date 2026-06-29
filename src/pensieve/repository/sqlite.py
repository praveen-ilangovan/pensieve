"""
sqlite.py

The SQLite/SQLModel adapter — the **only** module that knows about `Session`, the
engine, or SQLModel queries. Implements the `Repository`/`UnitOfWork` port from
`base.py`. ``expire_on_commit=False`` so objects returned to services stay usable
after the transaction closes (services never re-touch the session).
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType

from sqlalchemy import String, cast, func, or_, text
from sqlmodel import Session, col, select

from ..database.models import Asset, Attachment, Entity, Node, Note, Tag
from ..database.session import get_engine, init_db
from .base import Repository


class SqliteRepository:
    """Storage primitives over a SQLModel `Session` (one open transaction).

    **FK ordering rule:** models carry no ORM relationships (dumb data holders), so the
    unit-of-work won't order an inserted link row after the rows it references. Any method
    that inserts a row with a foreign key (``attach``, ``tag_note`` — and any future
    link table such as assets) MUST ``self._session.flush()`` first so the FK targets
    exist; otherwise SQLite (``foreign_keys=ON``) raises IntegrityError.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # nodes ----------------------------------------------------------------
    def get_node(self, node_id: str, *, include_deleted: bool = False) -> Node | None:
        node = self._session.get(Node, node_id)
        if node is None or (node.deleted_at is not None and not include_deleted):
            return None
        return node

    def add_node(self, node: Node) -> None:
        self._session.add(node)

    def save_node(self, node: Node) -> None:
        self._session.add(node)

    def set_node_deleted(self, node_id: str, when: object) -> bool:
        node = self._session.get(Node, node_id)  # raw (may be deleted) — for rm/restore
        if node is None:
            return False
        node.deleted_at = when  # type: ignore[assignment]
        self._session.add(node)
        return True

    def list_streams(self) -> list[Node]:
        statement = (
            select(Node)
            .where(col(Node.parent_id).is_(None))
            .where(col(Node.deleted_at).is_(None))
            .order_by(col(Node.label))
        )
        return list(self._session.exec(statement))

    def children_of(self, node_id: str, *, include_deleted: bool = False) -> list[Node]:
        statement = select(Node).where(Node.parent_id == node_id)
        if not include_deleted:
            statement = statement.where(col(Node.deleted_at).is_(None))
        return list(self._session.exec(statement.order_by(col(Node.label))))

    def find_nodes(self, query: str) -> list[Node]:
        like = f"%{query.strip()}%"
        statement = (
            select(Node)
            .where(or_(col(Node.label).ilike(like), col(Node.id).ilike(like)))
            .where(col(Node.deleted_at).is_(None))
            .order_by(col(Node.label))
        )
        return list(self._session.exec(statement))

    # notes ----------------------------------------------------------------
    def add_note(self, note: Note) -> None:
        self._session.add(note)
        self._fts_sync(note)

    def _fts_sync(self, note: Note) -> None:
        # keep the FTS index in step with the note's text (single source of truth = notes).
        self._session.execute(
            text("DELETE FROM notes_fts WHERE note_id = :id"), {"id": note.id}
        )
        self._session.execute(
            text("INSERT INTO notes_fts (note_id, text) VALUES (:id, :t)"),
            {"id": note.id, "t": note.text},
        )

    def get_note(self, note_id: str) -> Note | None:
        note = self._session.get(Note, note_id)
        return note if note is not None and note.deleted_at is None else None

    def save_note(self, note: Note) -> None:
        self._session.add(note)
        self._fts_sync(note)  # text may have changed

    def set_note_deleted(self, note_id: str, when: object) -> bool:
        note = self._session.get(Note, note_id)  # raw (may be deleted) — for rm/restore
        if note is None:
            return False
        note.deleted_at = when  # type: ignore[assignment]
        self._session.add(note)
        return True

    def delete_note(self, note_id: str) -> None:
        for att in self._session.exec(
            select(Attachment).where(Attachment.note_id == note_id)
        ):
            self._session.delete(att)
        for tag in self._session.exec(select(Tag).where(Tag.note_id == note_id)):
            self._session.delete(tag)
        note = self._session.get(Note, note_id)
        if note is not None:
            self._session.delete(note)
        self._session.execute(
            text("DELETE FROM notes_fts WHERE note_id = :id"), {"id": note_id}
        )

    def notes_for(self, node_id: str) -> list[Note]:
        # the node is visible (caller navigated to it) → its non-deleted notes are live
        statement = (
            select(Note)
            .join(Attachment, col(Attachment.note_id) == col(Note.id))
            .where(Attachment.node_id == node_id)
            .where(col(Note.deleted_at).is_(None))
            .order_by(col(Note.created))
        )
        return list(self._session.exec(statement))

    def nodes_for_note(self, note_id: str) -> list[Node]:
        statement = (
            select(Node)
            .join(Attachment, col(Attachment.node_id) == col(Node.id))
            .where(Attachment.note_id == note_id)
            .where(col(Node.deleted_at).is_(None))
            .order_by(col(Node.label))
        )
        return list(self._session.exec(statement))

    def recent_notes(self, since: datetime | None, limit: int) -> list[Note]:
        statement = (
            select(Note)
            .join(Attachment, col(Attachment.note_id) == col(Note.id))
            .join(Node, col(Node.id) == col(Attachment.node_id))
            .where(col(Note.deleted_at).is_(None))
            .where(col(Node.deleted_at).is_(None))
        )
        if since is not None:
            statement = statement.where(col(Note.updated) >= since)
        statement = statement.order_by(
            col(Note.updated).desc(), col(Note.created).desc(), col(Note.id).desc()
        )
        # a multi-homed note joins once per visible home → dedupe, preserving rank order
        seen: set[str] = set()
        out: list[Note] = []
        for note in self._session.exec(statement):
            if note.id in seen:
                continue
            seen.add(note.id)
            out.append(note)
            if len(out) >= limit:
                break
        return out

    # search ---------------------------------------------------------------
    def search_notes(self, terms: list[str], limit: int) -> list[Note]:
        if not terms:
            return []
        # OR the terms, each quoted as a phrase so punctuation/operators can't break MATCH
        match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
        rows = self._session.execute(
            text(
                "SELECT notes_fts.note_id FROM notes_fts "
                "JOIN notes n ON n.id = notes_fts.note_id "
                "WHERE notes_fts MATCH :m AND n.deleted_at IS NULL "
                "AND EXISTS (SELECT 1 FROM attachments a JOIN nodes nd "
                "            ON nd.id = a.node_id "
                "            WHERE a.note_id = n.id AND nd.deleted_at IS NULL) "
                "ORDER BY bm25(notes_fts) LIMIT :lim"
            ),
            {"m": match, "lim": limit},
        ).all()
        notes = [self._session.get(Note, r[0]) for r in rows]
        return [n for n in notes if n is not None]

    def search_assets(self, terms: list[str], limit: int) -> list[Asset]:
        if not terms:
            return []

        def field_match(term: str):  # any of hint/label/location contains the term
            pat = f"%{term}%"
            return or_(
                func.lower(func.coalesce(Asset.hint, "")).like(pat),
                func.lower(func.coalesce(Asset.label, "")).like(pat),
                func.lower(Asset.location).like(pat),
            )

        statement = (
            select(Asset)
            .where(or_(*[field_match(t) for t in terms]))
            .order_by(col(Asset.created).desc())
        )
        out: list[Asset] = []
        for asset in self._session.exec(statement):
            if self._asset_owner_live(asset):
                out.append(asset)
                if len(out) >= limit:
                    break
        return out

    def _asset_owner_live(self, asset: Asset) -> bool:
        if asset.node_id is not None:
            return self.get_node(asset.node_id) is not None
        if asset.note_id is not None:
            return self._note_is_live(asset.note_id)
        return False

    def _note_is_live(self, note_id: str) -> bool:
        note = self._session.get(Note, note_id)
        if note is None or note.deleted_at is not None:
            return False
        home = self._session.exec(
            select(Attachment)
            .join(Node, col(Node.id) == col(Attachment.node_id))
            .where(Attachment.note_id == note_id)
            .where(col(Node.deleted_at).is_(None))
            .limit(1)
        ).first()
        return home is not None

    # attachments ----------------------------------------------------------
    def attach(self, note_id: str, node_id: str) -> None:
        # Models carry no ORM relationships (dumb data holders), so the unit-of-work
        # won't order this row after the note/node it references — flush them first so
        # the FK targets exist (covers add_note->attach and create-node->attach).
        self._session.flush()
        if self._session.get(Attachment, (note_id, node_id)) is None:  # idempotent
            self._session.add(Attachment(note_id=note_id, node_id=node_id))

    def detach(self, note_id: str, node_id: str) -> None:
        att = self._session.get(Attachment, (note_id, node_id))
        if att is not None:
            self._session.delete(att)

    # entities -------------------------------------------------------------
    def add_entity(self, entity: Entity) -> None:
        self._session.add(entity)

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._session.get(Entity, entity_id)

    def save_entity(self, entity: Entity) -> None:
        self._session.add(entity)

    def list_entities(self) -> list[Entity]:
        return list(self._session.exec(select(Entity).order_by(col(Entity.name))))

    def find_entities(self, query: str) -> list[Entity]:
        like = f"%{query.strip()}%"
        statement = select(Entity).where(
            or_(
                col(Entity.name).ilike(like),
                col(Entity.id).ilike(like),
                cast(col(Entity.aliases), String).ilike(like),
            )
        )
        return list(self._session.exec(statement))

    # tags -----------------------------------------------------------------
    def tag_note(self, note_id: str, entity_id: str) -> None:
        self._session.flush()  # ensure note + entity rows exist before the FK row
        tag = self._session.get(Tag, (note_id, entity_id))
        if tag is None:
            self._session.add(Tag(note_id=note_id, entity_id=entity_id))
        elif tag.deleted_at is not None:  # revive a soft-unlinked link
            tag.deleted_at = None
            self._session.add(tag)

    def untag_note(self, note_id: str, entity_id: str) -> None:
        tag = self._session.get(Tag, (note_id, entity_id))
        if tag is not None:
            self._session.delete(tag)

    def set_tags_deleted_for_entity(self, entity_id: str, when: object) -> None:
        for tag in self._session.exec(select(Tag).where(Tag.entity_id == entity_id)):
            tag.deleted_at = when  # type: ignore[assignment]
            self._session.add(tag)

    def tags_for_note(self, note_id: str) -> list[str]:
        statement = (
            select(Tag.entity_id)
            .where(Tag.note_id == note_id)
            .where(col(Tag.deleted_at).is_(None))
        )
        return list(self._session.exec(statement))

    def notes_for_entity(self, entity_id: str) -> list[Note]:
        # live = active link AND note not deleted AND attached to a visible node
        statement = (
            select(Note)
            .join(Tag, col(Tag.note_id) == col(Note.id))
            .join(Attachment, col(Attachment.note_id) == col(Note.id))
            .join(Node, col(Node.id) == col(Attachment.node_id))
            .where(Tag.entity_id == entity_id)
            .where(col(Tag.deleted_at).is_(None))
            .where(col(Note.deleted_at).is_(None))
            .where(col(Node.deleted_at).is_(None))
            .distinct()
            .order_by(col(Note.created))
        )
        return list(self._session.exec(statement))

    def count_for_entity(self, entity_id: str) -> int:
        statement = (
            select(func.count(func.distinct(col(Note.id))))
            .select_from(Tag)
            .join(Note, col(Note.id) == col(Tag.note_id))
            .join(Attachment, col(Attachment.note_id) == col(Note.id))
            .join(Node, col(Node.id) == col(Attachment.node_id))
            .where(Tag.entity_id == entity_id)
            .where(col(Tag.deleted_at).is_(None))
            .where(col(Note.deleted_at).is_(None))
            .where(col(Node.deleted_at).is_(None))
        )
        return int(self._session.exec(statement).one())

    # assets ---------------------------------------------------------------
    def add_asset(self, asset: Asset) -> None:
        self._session.flush()  # owner FK (note_id/node_id) must exist first
        self._session.add(asset)

    def get_asset(self, asset_id: str) -> Asset | None:
        return self._session.get(Asset, asset_id)

    def remove_asset(self, asset_id: str) -> None:
        asset = self._session.get(Asset, asset_id)
        if asset is not None:
            self._session.delete(asset)

    def assets_for_node(self, node_id: str) -> list[Asset]:
        statement = (
            select(Asset).where(Asset.node_id == node_id).order_by(col(Asset.created))
        )
        return list(self._session.exec(statement))

    def assets_for_note(self, note_id: str) -> list[Asset]:
        statement = (
            select(Asset).where(Asset.note_id == note_id).order_by(col(Asset.created))
        )
        return list(self._session.exec(statement))

    def next_id(self, scope: str, kind: str, prefix: str) -> str:
        # Atomic allocate-and-increment in a single statement: SQLite runs the upsert under
        # its write lock, so two concurrent writers (e.g. CLI + MCP on one store) serialize
        # and can't hand out the same id. RETURNING gives back the new value.
        row = self._session.execute(
            text(
                "INSERT INTO counters (scope, kind, next) VALUES (:scope, :kind, 1) "
                "ON CONFLICT(scope, kind) DO UPDATE SET next = next + 1 "
                "RETURNING next"
            ),
            {"scope": scope, "kind": kind},
        ).one()
        return f"{prefix}{row[0]}"


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
