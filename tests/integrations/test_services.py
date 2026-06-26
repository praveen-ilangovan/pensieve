"""
Integration tests for the domain services against the **real SQLite adapter**.

Mirrors recs-app's service integration style (a test class per service, exercising the
real store). Builds each service with `SqliteUnitOfWork` against the `integration_store`
fixture, and reads back through a *fresh* service instance to prove durable persistence —
the thing the in-memory unit tests can't.
"""

from pathlib import Path

import pytest

from pensieve.errors import NodeNotFound, StreamExists
from pensieve.repository.sqlite import SqliteUnitOfWork
from pensieve.services.content import ContentService
from pensieve.services.streams import StreamService


class TestStreamServiceIntegration:
    def test_create_and_list_persist(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs", "Build Recs")

        # a fresh service instance reads it back from the real store
        rows = StreamService(SqliteUnitOfWork).list_streams()
        assert [n.id for n in rows] == ["recs"]
        assert rows[0].properties["purpose"] == "Build Recs"

    def test_duplicate_rejected(self, integration_store: Path):
        streams = StreamService(SqliteUnitOfWork)
        streams.create_stream("Recs")
        with pytest.raises(StreamExists):
            streams.create_stream("Recs")


class TestContentServiceIntegration:
    def test_add_note_round_trip_and_durable_version(self, integration_store: Path):
        StreamService(SqliteUnitOfWork).create_stream("Recs", "Build Recs")
        content = ContentService(SqliteUnitOfWork)

        n1 = content.add_note("recs", "talking to 4 curators")
        n2 = content.add_note(
            "recs", "Rafia postponed call -> Tue 2026-06-30", flavor="outcome"
        )

        assert (n1.id, n2.id) == ("note-1", "note-2")
        assert (n1.commit_id, n2.commit_id) == ("c1", "c2")
        assert n2.flavor == "outcome"

        # durable across a fresh service: the version bumps survived the commits
        node = next(
            n for n in StreamService(SqliteUnitOfWork).list_streams() if n.id == "recs"
        )
        assert node.version == 3  # create + two notes

    def test_add_note_missing_node(self, integration_store: Path):
        with pytest.raises(NodeNotFound):
            ContentService(SqliteUnitOfWork).add_note("nope", "x")

    def test_capture_then_fetch_thin_view(self, integration_store: Path):
        """Capture in one service, fetch the thin view through a fresh one — the
        cross-session round-trip in miniature."""
        StreamService(SqliteUnitOfWork).create_stream("Recs", "Build Recs")
        content = ContentService(SqliteUnitOfWork)
        content.add_note("recs", "talking to 4 curators")
        content.add_note("recs", "Rafia postponed call -> Tue 2026-06-30")

        view = ContentService(SqliteUnitOfWork).get_stream_view("recs")
        assert view["id"] == "recs"
        assert view["purpose"] == "Build Recs"
        assert [n["text"] for n in view["notes"]] == [
            "talking to 4 curators",
            "Rafia postponed call -> Tue 2026-06-30",
        ]
