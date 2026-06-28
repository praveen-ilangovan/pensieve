"""
Deterministic **removal** evaluator — the bottom-up delete/restore model as a runnable
regression gate. Removal is *not* top-down: "remove a stream" means *let go of its notes*,
then everything standing only on those notes falls away on its own. Notes are the atoms;
streams contain them, entities/threads merely *reference* them.

The rules under test:
  * `note rm`   — soft-hide a note (reversible); an entity at zero live notes derives away.
  * `stream rm` — let go of the stream's notes; a note also homed in another stream stays
                  live there, so cross-stream entities survive; pure ones derive away.
  * `entity rm` — **unlink**, never delete a note: a shared note survives under its other
                  subject; a note left subject-less becomes a plain note; the entity (and
                  its thread, if promoted) derives away. `restore` re-links.

Each scenario runs on its own throwaway store from the same seed, so they're independent.

Run:  poetry run python -m evals.removal   (or `make eval`)
Exit: 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from evals.capture_fetch import Checks

# ---- the canonical seed -------------------------------------------------------
# recs:        N1 (plain)         N2 (rafia)        N3 (rafia, travis)
# employment:  N4 (travis)        N5 (rafia)
# => rafia x3 (N2,N3,N5), travis x2 (N3,N4)


def _seed() -> dict[str, str]:
    from pensieve.factory import content_service, stream_service

    streams, content = stream_service(), content_service()
    streams.create_stream("Recs", "Build Recs")
    streams.create_stream("Employment", "Career")
    n1 = content.add_note("recs", "Recs launches in May", actor="eval")
    n2 = content.add_note(
        "recs",
        "met Rafia, a curator",
        actor="eval",
        entities=[{"name": "Rafia", "kind": "person"}],
    )
    n3 = content.add_note(
        "recs",
        "Rafia and Travis demoed",
        actor="eval",
        entities=[{"id": "rafia"}, {"name": "Travis", "kind": "person"}],
    )
    n4 = content.add_note(
        "employment",
        "Travis joined the team",
        actor="eval",
        entities=[{"id": "travis"}],
    )
    n5 = content.add_note(
        "employment",
        "Rafia asked about a role",
        actor="eval",
        entities=[{"id": "rafia"}],
    )
    return {"n1": n1.id, "n2": n2.id, "n3": n3.id, "n4": n4.id, "n5": n5.id}


# ---- small read helpers (always through a fresh service = durable round-trip) --
def _count(entity_id: str) -> int:
    """Live note count for an entity; 0 if it has derived away (absent from registry)."""
    from pensieve.factory import entity_service

    for e in entity_service().list_entities():
        if e["id"] == entity_id:
            return int(e["count"])
    return 0


def _live_entities() -> list[str]:
    from pensieve.factory import entity_service

    return sorted(e["id"] for e in entity_service().list_entities())


def _stream_ids() -> list[str]:
    from pensieve.factory import stream_service

    return sorted(s.id for s in stream_service().list_streams())


def _recall_texts(entity_id: str) -> list[str]:
    from pensieve.factory import entity_service

    return [n["text"] for n in entity_service().get_entity_view(entity_id)["notes"]]


def _loose_ids(node_id: str) -> set[str]:
    from pensieve.factory import content_service

    return {n["id"] for n in content_service().get_stream_view(node_id)["notes"]}


# ---- scenarios ----------------------------------------------------------------
def _scenario_A(checks: Checks) -> None:
    """stream rm recs — its notes go; cross-stream entities survive via employment."""
    from pensieve.factory import stream_service

    ids = _seed()
    stream_service().delete_stream("recs")
    checks.eq("A: recs is gone from the list", "recs" in _stream_ids(), False)
    checks.eq("A: rafia survives via employment (x1)", _count("rafia"), 1)
    checks.eq("A: travis survives via employment (x1)", _count("travis"), 1)
    checks.eq("A: both entities still live", _live_entities(), ["rafia", "travis"])
    stream_service().restore_stream("recs")
    checks.eq("A: restore recs → rafia back to x3", _count("rafia"), 3)
    checks.eq("A: restore recs → travis back to x2", _count("travis"), 2)
    checks.eq(
        "A: restore recs → N1..N3 live again",
        _loose_ids("recs"),
        set(ids[k] for k in ("n1", "n2", "n3")),
    )


def _scenario_B(checks: Checks) -> None:
    """stream rm employment — recs notes keep both entities alive."""
    from pensieve.factory import stream_service

    _seed()
    stream_service().delete_stream("employment")
    checks.eq("B: rafia keeps her recs notes (x2)", _count("rafia"), 2)
    checks.eq("B: travis keeps his recs note (x1)", _count("travis"), 1)
    checks.eq("B: both entities still live", _live_entities(), ["rafia", "travis"])


def _scenario_C(checks: Checks) -> None:
    """entity rm travis — UNLINK, never delete: the shared note stays (under rafia)."""
    from pensieve.factory import entity_service

    ids = _seed()
    entity_service().delete_entity("travis")
    checks.eq("C: travis derives away", "travis" in _live_entities(), False)
    checks.eq("C: rafia is untouched (x3)", _count("rafia"), 3)
    # the regression we set out to fix: removing travis must NOT lose the shared note.
    checks.eq(
        "C: the shared note survives under rafia",
        "Rafia and Travis demoed" in _recall_texts("rafia"),
        True,
    )
    # no note was deleted — all five are still in their streams (recs:3, employment:2)
    checks.eq(
        "C: recs keeps all 3 notes",
        _loose_ids("recs"),
        set(ids[k] for k in ("n1", "n2", "n3")),
    )
    checks.eq(
        "C: employment keeps both notes",
        _loose_ids("employment"),
        set(ids[k] for k in ("n4", "n5")),
    )
    entity_service().restore_entity("travis")
    checks.eq("C: restore travis → re-linked (x2)", _count("travis"), 2)
    checks.eq(
        "C: restore travis → both entities live", _live_entities(), ["rafia", "travis"]
    )


def _scenario_D(checks: Checks) -> None:
    """The cascade: note rm N5, then stream rm recs → rafia hits zero and vanishes."""
    from pensieve.errors import EntityNotFound
    from pensieve.factory import content_service, entity_service, stream_service

    ids = _seed()
    content_service().delete_note(ids["n5"])
    checks.eq("D: after note rm N5, rafia x2", _count("rafia"), 2)

    stream_service().delete_stream("recs")
    checks.eq(
        "D: stream rm recs drives rafia to zero → vanishes",
        "rafia" in _live_entities(),
        False,
    )
    checks.eq("D: travis stands on its employment note (x1)", _count("travis"), 1)
    checks.raises(
        "D: recall of the vanished rafia raises EntityNotFound",
        EntityNotFound,
        lambda: entity_service().get_entity_view("rafia"),
    )

    stream_service().restore_stream("recs")
    checks.eq(
        "D: restore recs → rafia back to x2 (N5 still removed)", _count("rafia"), 2
    )
    content_service().restore_note(ids["n5"])
    checks.eq("D: restore N5 → rafia back to x3", _count("rafia"), 3)


def _scenario_E(checks: Checks) -> None:
    """entity rm on a PROMOTED entity — thread drops, notes survive, restore re-promotes."""
    from pensieve.factory import content_service, entity_service

    _seed()
    entity_service().promote_entity("rafia", "recs")  # rafia x3 → thread under recs
    checks.eq(
        "E: rafia is promoted to a thread under recs",
        [c["id"] for c in content_service().get_stream_view("recs")["children"]],
        ["rafia"],
    )

    entity_service().delete_entity("rafia")
    checks.eq(
        "E: rafia (and its thread) derives away", "rafia" in _live_entities(), False
    )
    checks.eq(
        "E: the thread is dropped from the stream",
        content_service().get_stream_view("recs")["children"],
        [],
    )
    checks.eq("E: travis survives the shared note (x2)", _count("travis"), 2)
    checks.eq(
        "E: no note deleted — recs still shows N1..N3", len(_loose_ids("recs")), 3
    )

    entity_service().restore_entity("rafia")
    checks.eq("E: restore re-links rafia (x3)", _count("rafia"), 3)
    checks.eq(
        "E: restore re-promotes the thread",
        [c["id"] for c in content_service().get_stream_view("recs")["children"]],
        ["rafia"],
    )


def _scenario_F(checks: Checks) -> None:
    """OVERLAPPING removals — restore must reverse only its own delete, not blanket-revive.
    entity rm a promoted entity, THEN stream rm, THEN stream restore: the dead entity's
    thread must NOT come back (the architect-review blocker)."""
    from pensieve.factory import content_service, entity_service, stream_service

    _seed()
    entity_service().promote_entity("rafia", "recs")
    entity_service().delete_entity("rafia")  # thread dropped, rafia derives away
    stream_service().delete_stream("recs")
    stream_service().restore_stream("recs")  # must NOT resurrect rafia's thread

    checks.eq(
        "F: stream restore does not resurrect the dead entity's thread",
        content_service().get_stream_view("recs")["children"],
        [],
    )
    checks.eq("F: the dead entity stays gone", "rafia" in _live_entities(), False)
    # travis (never removed, shared note) is back with the stream
    checks.eq("F: an untouched entity returns with the stream", _count("travis"), 2)


def _scenario_G(checks: Checks) -> None:
    """A note removed BEFORE a stream rm stays removed after the stream is restored
    (restore_stream never touches note flags)."""
    from pensieve.factory import content_service, stream_service

    ids = _seed()
    content_service().delete_note(ids["n1"])  # plain note, removed independently
    stream_service().delete_stream("recs")
    stream_service().restore_stream("recs")

    checks.eq(
        "G: independently-removed note stays removed after stream restore",
        ids["n1"] in _loose_ids("recs"),
        False,
    )
    checks.eq(
        "G: the stream's other notes come back",
        {ids["n2"], ids["n3"]} <= _loose_ids("recs"),
        True,
    )
    content_service().restore_note(ids["n1"])
    checks.eq(
        "G: explicitly restoring the note brings it back",
        ids["n1"] in _loose_ids("recs"),
        True,
    )


def _assets_on(target: str) -> object:
    """Asset ids attached to a target, or GONE if the owner isn't reachable (derived)."""
    from pensieve.errors import NodeNotFound, NoteNotFound
    from pensieve.factory import asset_service

    try:
        return sorted(a["id"] for a in asset_service().list_assets(target))
    except (NodeNotFound, NoteNotFound):
        return "GONE"


def _recall_assets(entity_id: str) -> object:
    """All asset ids surfaced in an entity's recall — its thread's own plus its *live* notes'
    (per-note) assets, or GONE."""
    from pensieve.errors import EntityNotFound
    from pensieve.factory import entity_service

    try:
        view = entity_service().get_entity_view(entity_id)
        ids = [a["id"] for a in view["assets"]]
        for n in view["notes"]:
            ids += [a["id"] for a in n["assets"]]
        return sorted(ids)
    except EntityNotFound:
        return "GONE"


def _scenario_H(checks: Checks) -> None:
    """Assets are by-reference and derive visibility from their owner — they hide when the
    owner is removed and return on restore; an asset on a shared note survives `entity rm`."""
    from pensieve.factory import asset_service, entity_service, stream_service

    ids = _seed()
    asset_service().add_asset("recs", "/code/recs", kind="repo")  # asset-1 (node)
    asset_service().add_asset(
        ids["n3"], "https://demo.recs", kind="url"
    )  # asset-2 (shared note)

    checks.eq("H: asset on stream is listed", _assets_on("recs"), ["asset-1"])
    # the shared note's asset surfaces in rafia's recall (n3 is one of her live notes)
    checks.eq(
        "H: shared note's asset shows in entity recall",
        _recall_assets("rafia"),
        ["asset-2"],
    )

    entity_service().delete_entity("travis")  # unlink; note n3 survives (rafia)
    checks.eq(
        "H: shared note's asset survives entity rm",
        _recall_assets("rafia"),
        ["asset-2"],
    )

    stream_service().delete_stream("recs")  # owner gone → assets hide (derived)
    checks.eq("H: stream asset hides with its owner", _assets_on("recs"), "GONE")
    # n3 is now non-live (its only home is removed) → its asset drops out of recall
    checks.eq(
        "H: note asset hides when its note goes non-live", _recall_assets("rafia"), []
    )

    stream_service().restore_stream("recs")
    checks.eq("H: stream asset returns on restore", _assets_on("recs"), ["asset-1"])
    checks.eq("H: note asset returns on restore", _recall_assets("rafia"), ["asset-2"])


def run_checks() -> Checks:
    checks = Checks()
    for scenario in (
        _scenario_A,
        _scenario_B,
        _scenario_C,
        _scenario_D,
        _scenario_E,
        _scenario_F,
        _scenario_G,
        _scenario_H,
    ):
        _run_isolated(scenario, checks)
    return checks


def _run_isolated(scenario, checks: Checks) -> None:
    """Run one scenario against its own fresh throwaway store."""
    from pensieve.database.session import reset_engines

    store = tempfile.mkdtemp(prefix="pensieve-eval-rm-")
    os.environ["PENSIEVE_HOME"] = store
    os.environ["PENSIEVE_PROMOTION_THRESHOLD"] = "2"
    reset_engines()
    try:
        scenario(checks)
    finally:
        shutil.rmtree(store, ignore_errors=True)


def main() -> int:
    print("Removal evaluator (deterministic, bottom-up delete/restore)\n")
    checks = run_checks()
    for line in checks.lines:
        print(line)
    total = checks.passed + checks.failed
    print(f"\n{checks.passed}/{total} checks passed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
