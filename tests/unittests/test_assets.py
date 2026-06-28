"""Unit tests for AssetService — by-reference pointers, kind inference, derived visibility.

Filesystem-dependent cases use the ``tmp_path`` fixture (real dirs/files) so inference is
deterministic and never depends on the machine's actual home/cwd.
"""

from pathlib import Path

import pytest

from pensieve.errors import AssetNotFound, NodeNotFound, NoteNotFound
from pensieve.services.assets import infer_kind, local_missing


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "recs"
    (repo / ".git").mkdir(parents=True)
    return repo


def test_infer_kind(tmp_path: Path):
    repo = _make_repo(tmp_path)
    plain_dir = tmp_path / "docs"
    plain_dir.mkdir()
    a_file = tmp_path / "notes.txt"
    a_file.write_text("x")
    an_image = tmp_path / "diagram.png"
    an_image.write_bytes(b"x")

    assert infer_kind(str(repo)) == "repo"
    assert infer_kind(str(plain_dir)) == "dir"
    assert infer_kind(str(a_file)) == "file"
    assert infer_kind(str(an_image)) == "image"
    assert infer_kind(str(tmp_path / "missing.txt")) == "file"  # missing → file
    assert infer_kind("https://recs.app/docs") == "url"
    assert infer_kind("https://x.com/a.png?v=2") == "image"


def test_local_missing(tmp_path: Path):
    a_file = tmp_path / "f.txt"
    a_file.write_text("x")
    assert local_missing(str(a_file), "file") is False
    assert local_missing(str(tmp_path / "nope"), "file") is True
    assert local_missing("https://x.com", "url") is False  # urls never "missing"


def test_add_to_stream_and_note_and_list(services, tmp_path: Path):
    services.streams.create_stream("Recs")
    n = services.content.add_note("recs", "met rafia")
    repo = _make_repo(tmp_path)

    a1 = services.assets.add_asset("recs", str(repo), hint="read CLAUDE.md first")
    a2 = services.assets.add_asset(n.id, "https://rafia.dev", kind="url")
    assert (a1.id, a2.id) == ("asset-1", "asset-2")  # global ids
    assert a1.node_id == "recs" and a1.note_id is None
    assert a2.note_id == n.id and a2.node_id is None

    recs = services.assets.list_assets("recs")
    assert [a["id"] for a in recs] == ["asset-1"]
    assert recs[0]["hint"] == "read CLAUDE.md first"
    assert recs[0]["kind"] == "repo"  # inferred from the real .git dir
    assert [a["id"] for a in services.assets.list_assets(n.id)] == ["asset-2"]


def test_add_to_missing_target_raises(services):
    with pytest.raises(NodeNotFound):
        services.assets.add_asset("nope", "/x")
    with pytest.raises(NoteNotFound):
        services.assets.add_asset("note-99", "/x")


def test_remove_asset(services):
    services.streams.create_stream("Recs")
    services.assets.add_asset("recs", "/x", kind="file")
    services.assets.remove_asset("asset-1")
    assert services.assets.list_assets("recs") == []
    with pytest.raises(AssetNotFound):
        services.assets.remove_asset("asset-1")


def test_asset_surfaces_in_stream_view(services):
    services.streams.create_stream("Recs")
    services.assets.add_asset("recs", "/code/recs", hint="start here", kind="repo")
    view = services.content.get_stream_view("recs")
    assert [a["location"] for a in view["assets"]] == ["/code/recs"]


def test_note_asset_appears_in_stream_view(services):
    # the #1 regression: a note's asset MUST be reachable from get_stream_view (not just
    # via list_assets(note-N)) — else note-level assets are write-only.
    services.streams.create_stream("Recs")
    n = services.content.add_note("recs", "see the mockup")
    services.assets.add_asset(n.id, "https://x.com/mock.png", kind="image")

    view = services.content.get_stream_view("recs")
    note = next(x for x in view["notes"] if x["id"] == n.id)
    assert [a["location"] for a in note["assets"]] == ["https://x.com/mock.png"]


def test_view_flags_remote_and_missing(services, tmp_path: Path):
    services.streams.create_stream("Recs")
    real = tmp_path / "f.txt"
    real.write_text("x")
    services.assets.add_asset("recs", str(real), kind="file")  # asset-1 local, present
    services.assets.add_asset("recs", str(tmp_path / "gone"), kind="file")  # asset-2 missing
    services.assets.add_asset("recs", "https://x.com", kind="url")  # asset-3 remote

    by_id = {a["id"]: a for a in services.assets.list_assets("recs")}
    assert by_id["asset-1"] == {**by_id["asset-1"], "remote": False, "missing": False}
    assert by_id["asset-2"]["missing"] is True and by_id["asset-2"]["remote"] is False
    assert by_id["asset-3"]["remote"] is True and by_id["asset-3"]["missing"] is False


def test_asset_visibility_is_derived_from_owner(services):
    # an asset on a stream hides when the stream is removed, and returns on restore —
    # no asset-level soft-delete; visibility derives from the owner.
    services.streams.create_stream("Recs")
    services.assets.add_asset("recs", "/code/recs", kind="repo")

    services.streams.delete_stream("recs")
    with pytest.raises(NodeNotFound):
        services.assets.list_assets("recs")  # owner gone → not reachable

    services.streams.restore_stream("recs")
    assert [a["id"] for a in services.assets.list_assets("recs")] == ["asset-1"]


def test_note_asset_surfaces_in_entity_recall(services):
    services.streams.create_stream("Recs")
    n = services.content.add_note(
        "recs", "met rafia", entities=[{"name": "Rafia", "kind": "person"}]
    )
    services.assets.add_asset(n.id, "https://rafia.dev", kind="url")

    view = services.entities.get_entity_view("rafia")
    assert view["assets"] == []  # not promoted → no identity-level assets of its own
    note = next(x for x in view["notes"] if x["id"] == n.id)
    assert [a["location"] for a in note["assets"]] == ["https://rafia.dev"]  # per-note
