"""Unit tests for StreamService (in-memory adapter — no real DB)."""

import pytest

from pensieve.errors import NodeNotFound, StreamExists
from pensieve.services.streams import slugify


def test_slugify():
    assert slugify("My Cool Stream!") == "my-cool-stream"
    assert slugify("recs") == "recs"


def test_create_and_list(services):
    node = services.streams.create_stream("My Career", purpose="Grow toward VP")
    assert node.id == "my-career"
    assert node.kind == "subject"
    assert node.parent_id is None
    assert node.version == 1

    rows = services.streams.list_streams()
    assert [n.id for n in rows] == ["my-career"]
    assert rows[0].properties["purpose"] == "Grow toward VP"


def test_streams_ordered_by_label(services):
    services.streams.create_stream("Writing")
    services.streams.create_stream("Employment")
    services.streams.create_stream("Recs")

    assert [n.id for n in services.streams.list_streams()] == [
        "employment",
        "recs",
        "writing",
    ]


def test_duplicate_stream_rejected(services):
    services.streams.create_stream("Recs")
    with pytest.raises(StreamExists):
        services.streams.create_stream("Recs")


def test_get_stream(services):
    services.streams.create_stream("Recs", "Build Recs")
    node = services.streams.get_stream("recs")
    assert node is not None
    assert node.id == "recs"
    assert services.streams.get_stream("nope") is None


def test_edit_stream_keeps_id(services):
    services.streams.create_stream("Recs", "old purpose")
    services.streams.edit_stream("recs", name="Recommendations", purpose="new purpose")

    node = services.streams.get_stream("recs")
    assert node.id == "recs"  # id immutable
    assert node.label == "Recommendations"
    assert node.properties["purpose"] == "new purpose"

    with pytest.raises(NodeNotFound):
        services.streams.edit_stream("nope", name="x")


def test_delete_stream_soft_and_cascades_threads(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.entities.promote_entity("rafia", "recs")  # thread under recs

    services.streams.delete_stream("recs")

    # stream + its thread vanish from normal reads; entity is derived-gone
    assert services.streams.list_streams() == []
    assert services.streams.get_stream("recs") is None
    assert services.streams.get_stream("rafia") is None
    assert services.entities.list_entities() == []

    with pytest.raises(NodeNotFound):
        services.streams.delete_stream("nope")


def test_restore_stream_brings_back_stream_and_threads(services):
    services.streams.create_stream("Recs")
    services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.entities.promote_entity("rafia", "recs")
    services.streams.delete_stream("recs")

    services.streams.restore_stream("recs")

    assert [n.id for n in services.streams.list_streams()] == ["recs"]
    assert services.streams.get_stream("rafia") is not None  # thread restored
    assert [e["id"] for e in services.entities.list_entities()] == ["rafia"]

    with pytest.raises(NodeNotFound):
        services.streams.restore_stream("nope")


def test_delete_stream_keeps_cross_stream_note_live(services):
    services.streams.create_stream("Recs")
    services.streams.create_stream("Employment")
    services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.content.add_note(
        "employment", "rafia asked about a role", entities=[{"id": "rafia"}]
    )

    services.streams.delete_stream("recs")

    # rafia survives via the employment note (cross-stream) → still 1 live note there
    rafia = services.entities.get_entity_view("rafia")
    assert [n["text"] for n in rafia["notes"]] == ["rafia asked about a role"]
