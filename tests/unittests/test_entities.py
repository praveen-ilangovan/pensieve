"""Unit tests for EntityService — the registry, counts, fuzzy find (in-memory adapter)."""

import pytest

from pensieve.errors import EntityExists, EntityNotFound, NodeNotFound, PensieveError


def _tag(services, note_id: str, entity_id: str) -> None:
    """Tag a note directly via the repo (capture-time tagging lands in chunk 2)."""
    with services.uow() as uow:
        uow.repo.tag_note(note_id, entity_id)
        uow.commit()


def test_create_get_and_duplicate(services):
    e = services.entities.create_entity(
        "Rafia Naseem", "person", aliases=["Rafia", "her"]
    )
    assert e.id == "rafia-naseem"
    assert e.kind == "person"

    got = services.entities.get_entity("rafia-naseem")
    assert got.name == "Rafia Naseem"

    with pytest.raises(EntityExists):
        services.entities.create_entity("Rafia Naseem", "person")
    with pytest.raises(EntityNotFound):
        services.entities.get_entity("nope")


def test_list_with_counts_and_promotable(services, monkeypatch):
    monkeypatch.setenv("PENSIEVE_PROMOTION_THRESHOLD", "2")
    services.streams.create_stream("Recs")
    services.entities.create_entity("Rafia", "person")

    n1 = services.content.add_note("recs", "met rafia")
    n2 = services.content.add_note("recs", "rafia emailed")
    _tag(services, n1.id, "rafia")

    listed = {e["id"]: e for e in services.entities.list_entities()}
    assert listed["rafia"]["count"] == 1
    assert listed["rafia"]["promotable"] is False  # 1 < 2

    _tag(services, n2.id, "rafia")
    rafia = next(e for e in services.entities.list_entities() if e["id"] == "rafia")
    assert rafia["count"] == 2
    assert rafia["promotable"] is True  # 2 >= 2
    assert rafia["promoted"] is False


def test_find_by_name_and_alias(services):
    services.entities.create_entity("Rafia Naseem", "person", aliases=["The Reader Life"])
    services.entities.create_entity("Travis King", "person")

    assert [e["id"] for e in services.entities.find_entities("rafia")] == ["rafia-naseem"]
    # alias substring also matches
    assert [e["id"] for e in services.entities.find_entities("reader")] == [
        "rafia-naseem"
    ]
    assert [e["id"] for e in services.entities.find_entities("king")] == ["travis-king"]
    assert services.entities.find_entities("zzz") == []


def test_promote_creates_thread_and_attaches_notes(services):
    services.streams.create_stream("Recs")
    n1 = services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    n2 = services.content.add_note("recs", "rafia again", entities=[{"id": "rafia"}])

    node = services.entities.promote_entity("rafia", "recs")
    assert (node.id, node.parent_id, node.kind) == ("rafia", "recs", "person")

    rafia = next(e for e in services.entities.list_entities() if e["id"] == "rafia")
    assert rafia["promoted"] is True

    # the thread's own view shows the tagged notes (additive — still on recs too)
    thread = services.content.get_stream_view("rafia")
    assert {n["id"] for n in thread["notes"]} == {n1.id, n2.id}
    assert {n["id"] for n in services.content.get_stream_view("recs")["notes"]} == {
        n1.id,
        n2.id,
    }


def test_promote_errors(services):
    services.streams.create_stream("Recs")
    services.entities.create_entity("Rafia", "person")
    with pytest.raises(NodeNotFound):
        services.entities.promote_entity("rafia", "nope")  # missing stream
    with pytest.raises(EntityNotFound):
        services.entities.promote_entity("ghost", "recs")
    services.entities.promote_entity("rafia", "recs")
    with pytest.raises(PensieveError):
        services.entities.promote_entity("rafia", "recs")  # already promoted


def test_tagging_promoted_entity_attaches_to_thread(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "first", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.entities.promote_entity("rafia", "recs")

    # a NEW note tagging the (now promoted) entity lands under her thread automatically
    n = services.content.add_note("recs", "newer", entities=[{"id": "rafia"}])
    assert n.id in {x["id"] for x in services.content.get_stream_view("rafia")["notes"]}


def test_get_entity_view(services):
    services.streams.create_stream("Recs")
    services.content.add_note("recs", "a", entities=[{"name": "Rafia", "kind": "person"}])
    services.content.add_note("recs", "b", entities=[{"id": "rafia"}])

    view = services.entities.get_entity_view("rafia")
    assert view["count"] == 2
    assert view["promoted"] is False
    assert [n["text"] for n in view["notes"]] == ["a", "b"]

    with pytest.raises(EntityNotFound):
        services.entities.get_entity_view("ghost")


def test_notes_and_count_for_entity(services):
    services.streams.create_stream("Recs")
    services.entities.create_entity("Rafia", "person")
    a = services.content.add_note("recs", "note a")
    b = services.content.add_note("recs", "note b")
    _tag(services, a.id, "rafia")
    _tag(services, b.id, "rafia")

    with services.uow() as uow:
        assert uow.repo.count_for_entity("rafia") == 2
        assert {n.id for n in uow.repo.notes_for_entity("rafia")} == {a.id, b.id}
        assert set(uow.repo.tags_for_note(a.id)) == {"rafia"}
