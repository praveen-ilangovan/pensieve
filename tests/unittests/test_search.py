"""Unit tests for ContentService.search — OR semantics, liveness, context, asset pointers.

These run on the in-memory adapter (substring double), so they pin the *service plumbing*
— FTS-specific behaviour (stemming/ranking) is covered by the SQLite integration test.
"""


def test_search_or_terms_matches_notes(services):
    services.streams.create_stream("Recs")
    services.content.add_note("recs", "pricing for the new deck")  # note-1
    services.content.add_note("recs", "hiring a designer")  # note-2

    res = services.content.search("pricing designer")  # OR — either term matches
    assert {n["id"] for n in res["notes"]} == {"note-1", "note-2"}


def test_search_blank_query_is_empty(services):
    services.streams.create_stream("Recs")
    services.content.add_note("recs", "pricing")
    assert services.content.search("   ")["notes"] == []


def test_search_only_live_notes(services):
    services.streams.create_stream("Recs")
    services.streams.create_stream("Old")
    services.content.add_note("recs", "pricing here")  # note-1
    services.content.add_note("old", "pricing there")  # note-2
    services.content.delete_note("note-2")  # soft-removed → out of search

    res = services.content.search("pricing")
    assert {n["id"] for n in res["notes"]} == {"note-1"}


def test_search_note_view_carries_context(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "pricing deck", entities=[{"name": "Rafia", "kind": "person"}]
    )
    note = services.content.search("pricing")["notes"][0]
    assert note["streams"] == [{"id": "recs", "label": "Recs"}]
    assert note["entities"] == ["rafia"]
    assert "pricing" in note["snippet"]


def test_search_assets_by_hint_and_location(services):
    services.streams.create_stream("Recs")
    services.assets.add_asset("recs", "/code/recs", hint="deployment guide", kind="repo")

    by_hint = services.content.search("deploy")  # substring of "deployment"
    assert [a["id"] for a in by_hint["assets"]] == ["asset-1"]
    assert by_hint["assets"][0]["owner"] == "recs"
    assert by_hint["assets"][0]["owner_kind"] == "node"


def test_search_truncates_and_flags(services):
    services.streams.create_stream("Recs")
    for i in range(21):
        services.content.add_note("recs", f"pricing note {i}")

    res = services.content.search("pricing")
    assert len(res["notes"]) == 20
    assert res["notes_truncated"] is True
