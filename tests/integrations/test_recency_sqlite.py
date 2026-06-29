"""Integration tests for `recent` against the real SQLite adapter (time-ordered recall)."""

from pathlib import Path

from pensieve.factory import content_service, stream_service


def test_recent_newest_first(integration_store: Path):
    stream_service().create_stream("Recs")
    content_service().add_note("recs", "first")  # note-1
    content_service().add_note("recs", "second")  # note-2
    assert [n["id"] for n in content_service().recent()["notes"]] == ["note-2", "note-1"]


def test_recent_excludes_removed_notes_and_streams(integration_store: Path):
    stream_service().create_stream("Recs")
    stream_service().create_stream("Old")
    content_service().add_note("recs", "keep")  # note-1
    content_service().add_note("old", "gone-stream")  # note-2
    content_service().add_note("recs", "gone-note")  # note-3
    content_service().delete_note("note-3")
    stream_service().delete_stream("old")
    assert [n["id"] for n in content_service().recent()["notes"]] == ["note-1"]


def test_recent_refloats_an_edited_note(integration_store: Path):
    stream_service().create_stream("Recs")
    content_service().add_note("recs", "alpha")  # note-1
    content_service().add_note("recs", "beta")  # note-2
    content_service().update_note("note-1", "alpha edited")  # bumps updated
    assert content_service().recent()["notes"][0]["id"] == "note-1"
