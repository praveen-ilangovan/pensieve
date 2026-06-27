"""
Integration tests for the domain services against the **real SQLite adapter**.

Builds each service with `SqliteUnitOfWork` against the `integration_store` fixture, and
reads back through a *fresh* service instance to prove durable persistence.
"""

from pathlib import Path

import pytest

from pensieve.errors import EntityExists, NodeNotFound, NoteNotFound, StreamExists
from pensieve.repository.sqlite import SqliteUnitOfWork
from pensieve.services.content import ContentService
from pensieve.services.entities import EntityService
from pensieve.services.streams import StreamService


class TestStreamServiceIntegration:
    def test_create_and_list_persist(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs", "Build Recs")

        rows = StreamService(SqliteUnitOfWork).list_streams()
        assert [n.id for n in rows] == ["recs"]
        assert rows[0].properties["purpose"] == "Build Recs"

    def test_duplicate_rejected(self, integration_store: Path):
        streams = StreamService(SqliteUnitOfWork)
        streams.create_stream("Recs")
        with pytest.raises(StreamExists):
            streams.create_stream("Recs")


class TestContentServiceIntegration:
    def test_add_then_fetch_round_trip(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs", "Build Recs")
        content = ContentService(SqliteUnitOfWork)

        n1 = content.add_note(
            "recs", "talking to 4 curators", actor="claude-code", interface="mcp"
        )
        n2 = content.add_note("recs", "rafia is one of them")
        assert (n1.id, n2.id) == ("note-1", "note-2")  # global ids

        # durable across a fresh service
        view = ContentService(SqliteUnitOfWork).get_stream_view("recs")
        assert view["purpose"] == "Build Recs"
        assert [n["text"] for n in view["notes"]] == [
            "talking to 4 curators",
            "rafia is one of them",
        ]

    def test_provenance_persists_on_the_note(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs")
        note = ContentService(SqliteUnitOfWork).add_note(
            "recs", "hi", actor="claude-code", interface="mcp"
        )

        from sqlmodel import select

        from pensieve.database.models import Note
        from pensieve.database.session import get_session

        with get_session() as s:
            stored = s.exec(select(Note).where(Note.id == note.id)).one()
        assert stored.actor == "claude-code"
        assert stored.interface == "mcp"

    def test_update_and_delete(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs")
        content = ContentService(SqliteUnitOfWork)
        note = content.add_note("recs", "meeting Tuesday")

        content.update_note(note.id, "meeting Wednesday")
        view = ContentService(SqliteUnitOfWork).get_stream_view("recs")
        assert [n["text"] for n in view["notes"]] == ["meeting Wednesday"]

        content.delete_note(note.id)
        assert ContentService(SqliteUnitOfWork).get_stream_view("recs")["notes"] == []

    def test_delete_tagged_note_no_fk_error(self, integration_store: Path):
        # deleting a tagged note must not trip the tags FK (real SQLite, foreign_keys=ON)
        StreamService(SqliteUnitOfWork).create_stream("Recs")
        content = ContentService(SqliteUnitOfWork)
        note = content.add_note(
            "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
        )
        content.delete_note(note.id)  # would raise IntegrityError if tags weren't cleaned

        rafia = next(
            e for e in EntityService(SqliteUnitOfWork).list_entities()
            if e["id"] == "rafia"
        )
        assert rafia["count"] == 0

    def test_errors(self, integration_store: Path):
        content = ContentService(SqliteUnitOfWork)
        with pytest.raises(NodeNotFound):
            content.add_note("nope", "x")
        with pytest.raises(NoteNotFound):
            content.update_note("note-99", "x")
        with pytest.raises(NoteNotFound):
            content.delete_note("note-99")


class TestEntityServiceIntegration:
    def test_create_find_and_count(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs")
        entities = EntityService(SqliteUnitOfWork)
        content = ContentService(SqliteUnitOfWork)

        entities.create_entity("Rafia Naseem", "person", aliases=["The Reader Life"])
        with pytest.raises(EntityExists):
            entities.create_entity("Rafia Naseem", "person")

        # fuzzy find over name + alias (real SQLite LIKE)
        assert [e["id"] for e in entities.find_entities("rafia")] == ["rafia-naseem"]
        assert [e["id"] for e in entities.find_entities("reader")] == ["rafia-naseem"]

        # tag a note via the repo, count reflects it (durable across a fresh service)
        note = content.add_note("recs", "met rafia")
        with SqliteUnitOfWork() as uow:
            uow.repo.tag_note(note.id, "rafia-naseem")
            uow.commit()

        rafia = next(
            e for e in EntityService(SqliteUnitOfWork).list_entities()
            if e["id"] == "rafia-naseem"
        )
        assert rafia["count"] == 1
        assert rafia["promoted"] is False

    def test_promote_round_trip(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs")
        content = ContentService(SqliteUnitOfWork)
        content.add_note("recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}])
        content.add_note("recs", "rafia again", entities=[{"id": "rafia"}])

        node = EntityService(SqliteUnitOfWork).promote_entity("rafia", "recs")
        assert node.parent_id == "recs"

        # durable: a fresh service sees the thread + its notes, and the promoted flag
        thread = ContentService(SqliteUnitOfWork).get_stream_view("rafia")
        assert [n["text"] for n in thread["notes"]] == ["met rafia", "rafia again"]
        rafia = next(
            e for e in EntityService(SqliteUnitOfWork).list_entities()
            if e["id"] == "rafia"
        )
        assert rafia["promoted"] is True
