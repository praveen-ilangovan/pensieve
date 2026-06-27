"""Unit tests for ContentService — notes, attachments, provenance (in-memory adapter)."""

import pytest

from pensieve.errors import NodeNotFound, NoteNotFound
from pensieve.repository.memory import InMemoryUnitOfWork


def test_add_note_allocates_global_ids_and_attaches(services):
    services.streams.create_stream("Recs", "Build Recs")
    services.streams.create_stream("Employment")

    a = services.content.add_note("recs", "talking to 4 curators")
    b = services.content.add_note("employment", "I work at Nothing")
    c = services.content.add_note("recs", "rafia is one of the curators")

    # note ids are GLOBAL now (not per-node)
    assert (a.id, b.id, c.id) == ("note-1", "note-2", "note-3")

    # each note is attached to its stream
    recs = services.content.get_stream_view("recs")
    assert [n["id"] for n in recs["notes"]] == ["note-1", "note-3"]
    emp = services.content.get_stream_view("employment")
    assert [n["id"] for n in emp["notes"]] == ["note-2"]


def test_provenance_recorded_on_the_note(services):
    services.streams.create_stream("Recs")
    note = services.content.add_note("recs", "hi", actor="cli", interface="cli")

    stored = services.state.notes[note.id]
    assert stored.actor == "cli"
    assert stored.interface == "cli"
    assert stored.created == stored.updated  # untouched since creation


def test_add_note_missing_node_raises(services):
    with pytest.raises(NodeNotFound):
        services.content.add_note("nope", "x")


def test_update_note_rewrites_in_place(services):
    services.streams.create_stream("Recs")
    note = services.content.add_note("recs", "meeting Tuesday")

    services.content.update_note(note.id, "meeting Wednesday", actor="cli")

    view = services.content.get_stream_view("recs")
    assert [n["text"] for n in view["notes"]] == ["meeting Wednesday"]
    stored = services.state.notes[note.id]
    assert stored.updated >= stored.created


def test_update_missing_note_raises(services):
    with pytest.raises(NoteNotFound):
        services.content.update_note("note-99", "x")


def test_delete_note_removes_it_and_its_attachment(services):
    services.streams.create_stream("Recs")
    note = services.content.add_note("recs", "oops wrong note")

    services.content.delete_note(note.id)

    assert services.content.get_stream_view("recs")["notes"] == []
    assert note.id not in services.state.notes
    assert all(a[0] != note.id for a in services.state.attachments)


def test_delete_missing_note_raises(services):
    with pytest.raises(NoteNotFound):
        services.content.delete_note("note-99")


def test_get_stream_view_shape(services):
    services.streams.create_stream("Recs", "Build Recs")
    services.content.add_note("recs", "first")
    services.content.add_note("recs", "second")

    view = services.content.get_stream_view("recs")
    assert view["id"] == "recs"
    assert view["label"] == "Recs"
    assert view["kind"] == "subject"
    assert view["purpose"] == "Build Recs"
    assert view["children"] == []
    assert [n["text"] for n in view["notes"]] == ["first", "second"]
    assert "flavor" not in view["notes"][0]  # flavor is gone


def test_get_stream_view_missing_node_raises(services):
    with pytest.raises(NodeNotFound):
        services.content.get_stream_view("nope")


def test_note_can_be_multi_homed(services):
    """The core of the new model: one note attached to two nodes (used by promotion)."""
    services.streams.create_stream("Recs")
    services.streams.create_stream("Writing")
    note = services.content.add_note("recs", "shared across both")

    # attach the same note to a second node (what promotion does)
    with InMemoryUnitOfWork(services.state) as uow:
        uow.repo.attach(note.id, "writing")
        uow.commit()

    assert [n["id"] for n in services.content.get_stream_view("recs")["notes"]] == [
        note.id
    ]
    assert [n["id"] for n in services.content.get_stream_view("writing")["notes"]] == [
        note.id
    ]
