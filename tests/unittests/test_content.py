"""Unit tests for ContentService — notes + id allocation (in-memory adapter)."""

import pytest

from pensieve.errors import NodeNotFound, PensieveError
from pensieve.repository.memory import InMemoryUnitOfWork, MemoryState
from pensieve.services.streams import StreamService


def test_add_note_allocates_ids_and_bumps_version(services):
    services.streams.create_stream("Recs", "Build Recs")  # created at version 1

    n1 = services.content.add_note("recs", "talking to 4 curators")
    n2 = services.content.add_note("recs", "Rafia postponed call -> Tue")

    assert (n1.id, n2.id) == ("note-1", "note-2")
    assert (n1.commit_id, n2.commit_id) == ("c1", "c2")
    assert n1.node_id == "recs"

    node = next(n for n in services.streams.list_streams() if n.id == "recs")
    assert node.version == 3  # 1 (create) -> 2 -> 3


def test_commit_ids_global_note_ids_per_node(services):
    services.streams.create_stream("Recs")
    services.streams.create_stream("Employment")

    a = services.content.add_note("recs", "x")
    b = services.content.add_note("employment", "y")
    c = services.content.add_note("recs", "z")

    # commit ids are global + non-reusing
    assert [a.commit_id, b.commit_id, c.commit_id] == ["c1", "c2", "c3"]
    # note ids restart per node
    assert (a.id, b.id, c.id) == ("note-1", "note-1", "note-2")


def test_add_note_missing_node_raises(services):
    with pytest.raises(NodeNotFound):
        services.content.add_note("nope", "x")


def test_invalid_flavor_rejected(services):
    services.streams.create_stream("Recs")
    with pytest.raises(PensieveError):
        services.content.add_note("recs", "x", flavor="bogus")


def test_flavor_and_supersedes_stored(services):
    services.streams.create_stream("Recs")

    n1 = services.content.add_note("recs", "ship feature A", flavor="decision")
    n2 = services.content.add_note(
        "recs", "actually B", flavor="decision", supersedes=n1.id
    )

    assert n1.flavor == "decision"
    assert n2.supersedes == "note-1"


def test_history_recorded_per_note(services):
    services.streams.create_stream("Recs")
    services.content.add_note("recs", "hello", session_id="sess-1")

    history = [h for h in services.state.history if h.node_id == "recs"]
    assert len(history) == 1
    row = history[0]
    assert row.commit_id == "c1"
    assert row.version == 2
    assert row.session == "sess-1"
    assert row.changes == [{"op": "add_note", "note": "note-1"}]


def test_get_stream_view_shape_and_order(services):
    services.streams.create_stream("Recs", "Build Recs")
    services.content.add_note("recs", "talking to 4 curators")
    services.content.add_note("recs", "Rafia postponed call -> Tue", flavor="outcome")

    view = services.content.get_stream_view("recs")

    assert view["id"] == "recs"
    assert view["label"] == "Recs"
    assert view["kind"] == "subject"
    assert view["purpose"] == "Build Recs"
    assert view["version"] == 3
    assert view["todos"] == [] and view["children"] == []

    assert [n["id"] for n in view["notes"]] == ["note-1", "note-2"]
    assert view["notes"][0]["text"] == "talking to 4 curators"
    assert view["notes"][1]["flavor"] == "outcome"
    assert view["notes"][0]["flavor"] is None


def test_get_stream_view_empty_notes(services):
    services.streams.create_stream("Recs")
    view = services.content.get_stream_view("recs")
    assert view["notes"] == []


def test_get_stream_view_missing_node_raises(services):
    with pytest.raises(NodeNotFound):
        services.content.get_stream_view("nope")


def test_provenance_recorded_on_commit(services):
    services.streams.create_stream("Recs")
    services.content.add_note("recs", "hi", actor="cli", interface="cli")

    row = services.state.history[-1]
    assert row.actor == "cli"
    assert row.interface == "cli"


def test_uncommitted_work_does_not_persist():
    """A transaction that mutates but never commits must not leak into the store."""
    state = MemoryState()
    streams = StreamService(lambda: InMemoryUnitOfWork(state))
    streams.create_stream("Recs")

    with InMemoryUnitOfWork(state) as uow:
        node = uow.repo.get_node("recs")
        assert node is not None
        node.version = 999
        uow.repo.save_node(node)
        # no uow.commit()

    assert streams.list_streams()[0].version == 1
