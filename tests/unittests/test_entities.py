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
    # find/list surface only LIVE entities (≥1 live note), so give each a note
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs",
        "met rafia",
        entities=[{"name": "Rafia Naseem", "kind": "person", "aliases": ["The Reader Life"]}],
    )
    services.content.add_note(
        "recs", "met travis", entities=[{"name": "Travis King", "kind": "person"}]
    )

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

    # the thread's own view shows the tagged notes
    thread = services.content.get_stream_view("rafia")
    assert {n["id"] for n in thread["notes"]} == {n1.id, n2.id}

    # additive STORAGE: the notes are still attached to recs...
    with services.uow() as uow:
        assert {n.id for n in uow.repo.notes_for("recs")} == {n1.id, n2.id}
    # ...but the stream VIEW now hides them (covered by the rafia thread)
    assert services.content.get_stream_view("recs")["notes"] == []


def test_promote_errors(services):
    services.streams.create_stream("Recs")
    services.entities.create_entity("Rafia", "person")  # no notes yet

    with pytest.raises(EntityNotFound):
        services.entities.promote_entity("ghost", "recs")
    with pytest.raises(NodeNotFound):
        services.entities.promote_entity("rafia", "nope")  # missing stream
    with pytest.raises(PensieveError):
        services.entities.promote_entity("rafia", "recs")  # no notes to promote

    services.content.add_note("recs", "hi", entities=[{"id": "rafia"}])
    services.entities.promote_entity("rafia", "recs")
    with pytest.raises(PensieveError):
        services.entities.promote_entity("rafia", "recs")  # already promoted


def test_stream_view_loose_vs_covered(services):
    services.streams.create_stream("Recs")
    n1 = services.content.add_note(
        "recs", "rafia note", entities=[{"name": "Rafia", "kind": "person"}]
    )
    n2 = services.content.add_note("recs", "Recs is an app")  # untagged / stream-level
    n3 = services.content.add_note(
        "recs",
        "rafia and travis",
        entities=[{"name": "Rafia", "kind": "person"}, {"name": "Travis", "kind": "person"}],
    )
    services.entities.promote_entity("rafia", "recs")  # travis stays un-promoted

    recs = services.content.get_stream_view("recs")
    loose = {n["id"] for n in recs["notes"]}
    assert n1.id not in loose  # sole tag promoted → covered → hidden
    assert n2.id in loose  # untagged → loose
    assert n3.id in loose  # travis un-promoted → not fully covered → loose
    assert [c["id"] for c in recs["children"]] == ["rafia"]

    # the thread shows all of rafia's notes (a thread has no children → nothing covered)
    thread = services.content.get_stream_view("rafia")
    assert {n["id"] for n in thread["notes"]} == {n1.id, n3.id}


def test_cross_stream_promotion_does_not_hide_in_other_stream(services):
    services.streams.create_stream("Recs")
    services.streams.create_stream("Employment")
    services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    emp_note = services.content.add_note(
        "employment", "rafia asked about a role", entities=[{"id": "rafia"}]
    )
    services.entities.promote_entity("rafia", "recs")  # thread under recs, not employment

    # the employment note isn't covered by an employment thread → still loose there
    emp = services.content.get_stream_view("employment")
    assert emp_note.id in {n["id"] for n in emp["notes"]}


def test_tagging_promoted_entity_attaches_to_thread(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "first", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.entities.promote_entity("rafia", "recs")

    # a NEW note tagging the (now promoted) entity lands under her thread automatically
    n = services.content.add_note("recs", "newer", entities=[{"id": "rafia"}])
    assert n.id in {x["id"] for x in services.content.get_stream_view("rafia")["notes"]}


def test_edit_entity_syncs_thread_label(services):
    services.streams.create_stream("Recs")
    services.content.add_note("recs", "x", entities=[{"name": "Rafia", "kind": "person"}])
    services.entities.promote_entity("rafia", "recs")

    services.entities.edit_entity("rafia", name="Rafia Naseem", aliases=["RN"])

    e = services.entities.get_entity("rafia")
    assert e.id == "rafia"  # id immutable
    assert e.name == "Rafia Naseem"
    assert e.aliases == ["RN"]
    # the promoted thread's label is kept in sync
    assert services.streams.get_stream("rafia").label == "Rafia Naseem"

    with pytest.raises(EntityNotFound):
        services.entities.edit_entity("ghost", name="x")


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


def test_delete_entity_purges_notes_and_derived_entities(services):
    services.streams.create_stream("Recs")
    n_plain = services.content.add_note("recs", "plain note")  # no entities
    services.content.add_note(
        "recs",
        "rafia and travis",
        entities=[
            {"name": "Rafia", "kind": "person"},
            {"name": "Travis", "kind": "person"},
        ],
    )

    services.entities.delete_entity("rafia")

    # the shared note is purged → travis (riding only it) is derived-gone too
    assert services.entities.list_entities() == []
    # the entity-less stream note survives
    recs = services.content.get_stream_view("recs")
    assert [n["id"] for n in recs["notes"]] == [n_plain.id]

    with pytest.raises(EntityNotFound):
        services.entities.delete_entity("ghost")


def test_delete_entity_with_thread_then_restore(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.content.add_note(
        "recs",
        "rafia and travis",
        entities=[
            {"id": "rafia"},
            {"name": "Travis", "kind": "person"},
        ],
    )
    services.entities.promote_entity("rafia", "recs")

    services.entities.delete_entity("rafia")
    assert services.streams.get_stream("rafia") is None  # thread node gone
    assert services.entities.list_entities() == []  # travis rode only purged notes

    services.entities.restore_entity("rafia")
    assert services.streams.get_stream("rafia") is not None  # thread back
    assert {e["id"] for e in services.entities.list_entities()} == {"rafia", "travis"}

    with pytest.raises(EntityNotFound):
        services.entities.restore_entity("ghost")


def test_removed_entity_recall_raises(services):
    services.streams.create_stream("Recs")
    n = services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.content.delete_note(n.id)  # rafia loses its only live note

    with pytest.raises(EntityNotFound):
        services.entities.get_entity_view("rafia")  # derived-gone


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
