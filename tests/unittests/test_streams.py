"""Unit tests for the streams service (isolated temp store per test)."""

import pytest

from pensieve.services import streams


def test_slugify():
    assert streams.slugify("My Cool Stream!") == "my-cool-stream"
    assert streams.slugify("recs") == "recs"


def test_create_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("PENSIEVE_HOME", str(tmp_path))

    node = streams.create_stream("My Career", purpose="Grow toward VP")
    assert node.id == "my-career"
    assert node.kind == "subject"
    assert node.parent_id is None
    assert node.version == 1

    rows = streams.list_streams()
    assert [n.id for n in rows] == ["my-career"]
    assert rows[0].properties["purpose"] == "Grow toward VP"


def test_duplicate_stream_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PENSIEVE_HOME", str(tmp_path))

    streams.create_stream("Recs")
    with pytest.raises(streams.StreamExists):
        streams.create_stream("Recs")
