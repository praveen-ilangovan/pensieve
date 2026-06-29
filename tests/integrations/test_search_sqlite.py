"""Integration tests for search against the **real SQLite/FTS5 adapter** — the behaviour
that's engine-specific (porter stemming, liveness filtering, truncation) and so lives only
here, not in the cross-adapter conformance test.
"""

from pathlib import Path

from pensieve.factory import asset_service, content_service, stream_service


def test_search_stems_note_content(integration_store: Path):
    stream_service().create_stream("Recs")
    content_service().add_note("recs", "we priced the deck at five dollars")  # note-1

    # porter stemming: "pricing" → "price" → recalls "priced" (LIKE never could)
    res = content_service().search("pricing")
    assert [n["id"] for n in res["notes"]] == ["note-1"]
    assert res["notes"][0]["streams"] == [{"id": "recs", "label": "Recs"}]


def test_search_excludes_removed_notes_and_streams(integration_store: Path):
    stream_service().create_stream("Recs")
    stream_service().create_stream("Old")
    content_service().add_note("recs", "pricing alpha")  # note-1 (live)
    content_service().add_note("recs", "pricing beta")  # note-2 (soft-removed below)
    content_service().add_note("old", "pricing gamma")  # note-3 (stream removed below)
    content_service().delete_note("note-2")
    stream_service().delete_stream("old")

    res = content_service().search("pricing")
    assert {n["id"] for n in res["notes"]} == {"note-1"}


def test_search_assets_and_truncation(integration_store: Path):
    stream_service().create_stream("Recs")
    asset_service().add_asset("recs", "/x", hint="deployment guide", kind="file")
    for i in range(21):
        content_service().add_note("recs", f"deploy note {i}")

    res = content_service().search("deploy")
    assert len(res["notes"]) == 20 and res["notes_truncated"] is True  # capped + flagged
    assert [a["id"] for a in res["assets"]] == ["asset-1"]  # hint matched


def test_search_edited_note_text_is_reindexed(integration_store: Path):
    stream_service().create_stream("Recs")
    content_service().add_note("recs", "original wording")  # note-1
    content_service().update_note("note-1", "now mentions pricing")

    assert [n["id"] for n in content_service().search("pricing")["notes"]] == ["note-1"]
    assert content_service().search("original")["notes"] == []  # old text gone from index


def test_search_punctuation_does_not_crash(integration_store: Path):
    stream_service().create_stream("Recs")
    content_service().add_note("recs", "pricing decisions")
    # quotes / FTS operators in the query must be neutralised, not break MATCH
    res = content_service().search('pricing" OR notes MATCH "x')
    assert res["notes"][0]["id"] == "note-1"
