"""Unit tests for multi-stream notes — one note, several homes (in-memory adapter)."""

import pytest

from pensieve.errors import NodeNotFound, NoteNotFound, PensieveError


def _stream_note_ids(services, stream):
    return {n["id"] for n in services.content.get_stream_view(stream)["notes"]}


def test_add_note_into_multiple_streams(services):
    services.streams.create_stream("Writing")
    services.streams.create_stream("Recs")
    note = services.content.add_note("writing", "AI-agents article", also=["recs"])

    assert note.id in _stream_note_ids(services, "writing")
    assert note.id in _stream_note_ids(services, "recs")  # one note, both homes
    with services.uow() as uow:
        homes = {n.id for n in uow.repo.nodes_for_note(note.id)}
    assert homes == {"writing", "recs"}


def test_add_note_dedupes_repeated_target(services):
    services.streams.create_stream("Recs")
    note = services.content.add_note("recs", "x", also=["recs"])  # recs twice
    with services.uow() as uow:
        assert [n.id for n in uow.repo.nodes_for_note(note.id)] == ["recs"]


def test_add_note_rejects_thread_target(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.entities.promote_entity("rafia", "recs")  # rafia is a thread now
    with pytest.raises(PensieveError):
        services.content.add_note("recs", "y", also=["rafia"])
    with pytest.raises(NodeNotFound):
        services.content.add_note("recs", "y", also=["ghost"])


def test_file_existing_note_into_another_stream(services):
    services.streams.create_stream("Writing")
    services.streams.create_stream("Recs")
    note = services.content.add_note("writing", "the article")

    services.content.file_note(note.id, "recs")
    assert note.id in _stream_note_ids(services, "recs")
    assert note.id in _stream_note_ids(services, "writing")  # still there

    services.content.file_note(note.id, "recs")  # idempotent — no error/dup
    with services.uow() as uow:
        assert len([n for n in uow.repo.nodes_for_note(note.id)]) == 2


def test_file_note_errors(services):
    services.streams.create_stream("Recs")
    note = services.content.add_note("recs", "x")
    with pytest.raises(NoteNotFound):
        services.content.file_note("note-99", "recs")
    with pytest.raises(NodeNotFound):
        services.content.file_note(note.id, "ghost")


def test_unfile_note_keeps_other_homes(services):
    services.streams.create_stream("Writing")
    services.streams.create_stream("Recs")
    note = services.content.add_note("writing", "the article", also=["recs"])

    services.content.unfile_note(note.id, "recs")
    assert note.id not in _stream_note_ids(services, "recs")
    assert note.id in _stream_note_ids(services, "writing")  # survives in its other home


def test_unfile_refuses_last_home(services):
    services.streams.create_stream("Recs")
    note = services.content.add_note("recs", "only here")
    with pytest.raises(PensieveError):  # would orphan it → use rm
        services.content.unfile_note(note.id, "recs")
    with pytest.raises(PensieveError):  # not filed there
        services.content.unfile_note(note.id, "writing")
