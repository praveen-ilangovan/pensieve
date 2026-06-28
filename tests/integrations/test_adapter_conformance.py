"""
Adapter conformance — the in-memory and SQLite backends must be *behaviorally identical*
through the `Repository`/`UnitOfWork` port. We run one rich scenario (capture, tag, promote,
soft remove/unlink, restore — incl. the overlapping-removal corner) against **both**
adapters and assert the observable results match exactly. This is the guard against silent
drift between the two backends (e.g. a liveness filter added to one and not the other),
especially before new tables/FKs land.
"""

from __future__ import annotations

from types import SimpleNamespace

from pensieve.errors import EntityNotFound, NodeNotFound
from pensieve.repository.memory import InMemoryUnitOfWork, MemoryState
from pensieve.repository.sqlite import SqliteUnitOfWork
from pensieve.services.assets import AssetService
from pensieve.services.content import ContentService
from pensieve.services.entities import EntityService
from pensieve.services.streams import StreamService


def _bundle(uow_factory) -> SimpleNamespace:
    return SimpleNamespace(
        streams=StreamService(uow_factory),
        content=ContentService(uow_factory),
        entities=EntityService(uow_factory),
        assets=AssetService(uow_factory),
        uow=uow_factory,
    )


def _snapshot(b: SimpleNamespace) -> tuple:
    """A timestamp-free, comparable view of everything observable — service views + direct
    port reads (the methods most likely to drift between adapters)."""
    streams = [(s.id, s.label) for s in b.streams.list_streams()]
    entities = sorted(
        (e["id"], e["kind"], e["count"], e["promoted"], e["promotable"])
        for e in b.entities.list_entities()
    )

    views: dict[str, object] = {}
    for sid in ("recs", "employment", "rafia"):
        try:
            v = b.content.get_stream_view(sid)
        except NodeNotFound:
            views[sid] = "GONE"
        else:
            views[sid] = (
                [c["id"] for c in v["children"]],
                sorted(
                    (n["id"], tuple(sorted(a["id"] for a in n["assets"])))
                    for n in v["notes"]
                ),
                sorted(a["id"] for a in v["assets"]),  # node's own
            )

    recall: dict[str, object] = {}
    for eid in ("rafia", "travis"):
        try:
            rv = b.entities.get_entity_view(eid)
        except EntityNotFound:
            recall[eid] = "GONE"
        else:
            recall[eid] = (
                rv["count"],
                rv["promoted"],
                sorted(
                    (n["id"], tuple(sorted(a["id"] for a in n["assets"])))
                    for n in rv["notes"]
                ),
                sorted(a["id"] for a in rv["assets"]),  # thread's own
            )

    with b.uow() as uow:
        ports = (
            sorted(n.id for n in uow.repo.notes_for("recs")),
            sorted(n.id for n in uow.repo.find_nodes("r")),
            sorted(c.id for c in uow.repo.children_of("recs", include_deleted=True)),
            {eid: uow.repo.count_for_entity(eid) for eid in ("rafia", "travis")},
            {eid: sorted(uow.repo.tags_for_note(eid)) for eid in ("note-1", "note-3")},
            sorted(a.id for a in uow.repo.assets_for_node("recs")),
            sorted(a.id for a in uow.repo.assets_for_note("note-2")),
        )
    return (streams, entities, views, recall, ports)


def _scenario(b: SimpleNamespace) -> list[tuple]:
    """Same calls, same order — must yield the same snapshots on either backend."""
    snaps: list[tuple] = []
    b.streams.create_stream("Recs", "Build Recs")
    b.streams.create_stream("Employment", "Career")
    b.content.add_note("recs", "plain note")  # note-1
    b.content.add_note("recs", "met Rafia", entities=[{"name": "Rafia", "kind": "person"}])  # note-2
    b.content.add_note(
        "recs",
        "Rafia and Travis",
        entities=[{"id": "rafia"}, {"name": "Travis", "kind": "person"}],
    )  # note-3
    b.content.add_note("employment", "Rafia asked about a role", entities=[{"id": "rafia"}])  # note-4
    b.assets.add_asset("recs", "~/code/recs", hint="read CLAUDE.md first")  # node-level
    b.assets.add_asset("note-2", "https://rafia.dev", kind="url")  # note-level
    snaps.append(_snapshot(b))  # after capture

    b.entities.promote_entity("rafia", "recs")
    snaps.append(_snapshot(b))  # after promotion

    b.entities.delete_entity("travis")  # unlink (shared note survives under rafia)
    snaps.append(_snapshot(b))

    b.content.delete_note("note-1")  # soft remove a plain note
    snaps.append(_snapshot(b))

    b.streams.delete_stream("recs")  # cross-stream: rafia survives via employment
    snaps.append(_snapshot(b))

    b.streams.restore_stream("recs")  # must not resurrect travis's dead thread state
    b.entities.restore_entity("travis")
    b.content.restore_note("note-1")
    snaps.append(_snapshot(b))  # fully restored

    return snaps


def test_memory_and_sqlite_adapters_agree(integration_store):
    state = MemoryState()
    memory = _scenario(_bundle(lambda: InMemoryUnitOfWork(state)))
    sqlite = _scenario(_bundle(SqliteUnitOfWork))

    assert len(memory) == len(sqlite)
    for i, (m, s) in enumerate(zip(memory, sqlite)):
        assert m == s, f"adapters diverged at step {i}:\n memory={m}\n sqlite={s}"
