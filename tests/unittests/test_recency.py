"""Unit tests for ContentService.recent — the time lens — and the `since` parser."""

from datetime import datetime

import pytest

from pensieve.services.content import parse_since


def test_parse_since():
    assert parse_since(None) is None
    assert parse_since("") is None
    assert parse_since("2026-06-01") == datetime(2026, 6, 1, 0, 0)
    # tz-aware → naive UTC (12:00+02:00 == 10:00 UTC)
    assert parse_since("2026-06-01T12:00:00+02:00") == datetime(2026, 6, 1, 10, 0)
    with pytest.raises(ValueError):
        parse_since("not-a-date")


def test_recent_newest_first(services):
    services.streams.create_stream("Recs")
    a = services.content.add_note("recs", "first")
    b = services.content.add_note("recs", "second")
    c = services.content.add_note("recs", "third")
    assert [n["id"] for n in services.content.recent()["notes"]] == [c.id, b.id, a.id]


def test_recent_refloats_an_edited_note(services):
    services.streams.create_stream("Recs")
    a = services.content.add_note("recs", "old")
    services.content.add_note("recs", "newer")
    services.content.update_note(a.id, "old, now edited")  # bumps updated
    assert services.content.recent()["notes"][0]["id"] == a.id


def test_recent_only_live_notes(services):
    services.streams.create_stream("Recs")
    a = services.content.add_note("recs", "keep")
    b = services.content.add_note("recs", "drop")
    services.content.delete_note(b.id)
    assert [n["id"] for n in services.content.recent()["notes"]] == [a.id]


def test_recent_since_filters(services):
    services.streams.create_stream("Recs")
    services.content.add_note("recs", "early")  # note-1
    b = services.content.add_note("recs", "late")  # note-2
    cutoff = b.created.replace(tzinfo=None)
    assert [n["id"] for n in services.content.recent(since=cutoff)["notes"]] == [b.id]


def test_recent_truncates_and_flags(services):
    services.streams.create_stream("Recs")
    for i in range(21):
        services.content.add_note("recs", f"note {i}")
    res = services.content.recent()
    assert len(res["notes"]) == 20 and res["truncated"] is True


def test_recent_view_carries_context(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "x", entities=[{"name": "Rafia", "kind": "person"}]
    )
    n = services.content.recent()["notes"][0]
    assert n["streams"] == [{"id": "recs", "label": "Recs"}]
    assert n["entities"] == ["rafia"]
    assert "updated" in n
