"""
Integration tests for the domain services against the **real SQLite adapter**.

Builds each service with `SqliteUnitOfWork` against the `integration_store` fixture, and
reads back through a *fresh* service instance to prove durable persistence.
"""

from pathlib import Path

import pytest

from pensieve.errors import NodeNotFound, NoteNotFound, StreamExists
from pensieve.repository.sqlite import SqliteUnitOfWork
from pensieve.services.content import ContentService
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

    def test_errors(self, integration_store: Path):
        content = ContentService(SqliteUnitOfWork)
        with pytest.raises(NodeNotFound):
            content.add_note("nope", "x")
        with pytest.raises(NoteNotFound):
            content.update_note("note-99", "x")
        with pytest.raises(NoteNotFound):
            content.delete_note("note-99")
