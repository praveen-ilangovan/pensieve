"""Unit tests for StreamService (in-memory adapter — no real DB)."""

import pytest

from pensieve.errors import StreamExists
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
