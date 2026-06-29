"""Integration tests for multi-stream notes against the real SQLite adapter — including the
idempotent attach (re-filing must not trip the attachments PK / FK)."""

from pathlib import Path

from pensieve.factory import content_service, stream_service


def _ids(stream):
    return {n["id"] for n in content_service().get_stream_view(stream)["notes"]}


def test_add_and_file_round_trip(integration_store: Path):
    stream_service().create_stream("Writing")
    stream_service().create_stream("Recs")
    content_service().add_note("writing", "AI-agents article", also=["recs"])  # note-1

    assert "note-1" in _ids("writing") and "note-1" in _ids("recs")

    # re-filing where it already lives must be a no-op, not an IntegrityError
    content_service().file_note("note-1", "recs")
    assert "note-1" in _ids("recs")


def test_unfile_keeps_other_home(integration_store: Path):
    stream_service().create_stream("Writing")
    stream_service().create_stream("Recs")
    content_service().add_note("writing", "article", also=["recs"])  # note-1
    content_service().unfile_note("note-1", "recs")
    assert "note-1" in _ids("writing") and "note-1" not in _ids("recs")
