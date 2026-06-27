"""Unit tests for EntityService — the registry, counts, fuzzy find (in-memory adapter)."""

import pytest

from pensieve.errors import EntityExists, EntityNotFound


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
