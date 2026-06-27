"""
Deterministic capture/fetch evaluator — the slice-4 acceptance scenario as a runnable
regression gate. Spins up a throwaway store and drives the **engine** through the three
capture *outcomes* + fetch, asserting results.

Scope (be honest about what this proves): the engine has no "proposal" — `create_stream`
/`add_note` are mechanical ops. So this script plays a *scripted agent* that always makes
the right target choice, proving the engine **supports** each path and that content
round-trips. Whether a real agent **chooses** right (against the live MCP) is the
agent-in-the-loop eval — a separate, staged harness, not this script.

Run:  poetry run python -m evals.capture_fetch   (or `make eval`)
Exit: 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable


class Checks:
    """A tiny pass/fail collector with a printed report and an exit code."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.passed = 0
        self.failed = 0

    def eq(self, desc: str, got: object, want: object) -> None:
        ok = got == want
        self._record(ok, desc, None if ok else f"got {got!r}, want {want!r}")

    def raises(self, desc: str, exc: type[Exception], fn: Callable[[], object]) -> None:
        try:
            fn()
            self._record(False, desc, f"no {exc.__name__} raised")
        except exc:
            self._record(True, desc, None)
        except Exception as other:  # noqa: BLE001
            self._record(
                False, desc, f"raised {type(other).__name__}, want {exc.__name__}"
            )

    def _record(self, ok: bool, desc: str, detail: str | None) -> None:
        mark = "✓" if ok else "✗"
        self.lines.append(f"  {mark} {desc}" + (f"  — {detail}" if detail else ""))
        if ok:
            self.passed += 1
        else:
            self.failed += 1


def run_checks() -> Checks:
    """Run the scenario against the currently-configured store. Returns the results."""
    from pensieve.errors import NodeNotFound
    from pensieve.factory import content_service, stream_service

    streams = stream_service()
    content = content_service()
    checks = Checks()

    # 1. empty to begin
    checks.eq("empty store has no streams", [s.id for s in streams.list_streams()], [])

    # 2. create a few streams, list them (ordered by label)
    streams.create_stream("Recs", "Build and grow Recs")
    streams.create_stream("Employment", "Navigate my career")
    checks.eq(
        "streams listed after create",
        [s.id for s in streams.list_streams()],
        ["employment", "recs"],
    )

    # 3. the three capture outcomes (scripted agent makes the target choice)
    streams.create_stream("Writing", "The 'I used to think' essays")
    a = content.add_note(
        "writing", "drafted the first essay outline", actor="eval"
    )  # new
    b = content.add_note(
        "recs", "we are talking to 4 curators", actor="eval"
    )  # existing
    c = content.add_note(
        "employment", "I am working for Nothing", actor="eval"
    )  # explicit
    d = content.add_note("recs", "rafia is one of the curators", actor="eval")

    # note ids are GLOBAL + non-reusing now (not per-node)
    checks.eq(
        "global sequential note ids",
        [a.id, b.id, c.id, d.id],
        ["note-1", "note-2", "note-3", "note-4"],
    )
    checks.eq("provenance recorded on the note", a.actor, "eval")

    # 4. FETCH through a *fresh* service — the cross-session round-trip.
    view = content_service().get_stream_view("recs")
    checks.eq("fetch: purpose round-trips", view["purpose"], "Build and grow Recs")
    checks.eq(
        "fetch: notes round-trip in order",
        [n["text"] for n in view["notes"]],
        ["we are talking to 4 curators", "rafia is one of the curators"],
    )

    # 5. update (fix a mistake) rewrites in place; delete removes.
    content.update_note(d.id, "Rafia and Travis are curators", actor="eval")
    checks.eq(
        "update rewrites in place",
        [n["text"] for n in content_service().get_stream_view("recs")["notes"]],
        ["we are talking to 4 curators", "Rafia and Travis are curators"],
    )
    content.delete_note(b.id)
    checks.eq(
        "delete removes the note",
        [n["text"] for n in content_service().get_stream_view("recs")["notes"]],
        ["Rafia and Travis are curators"],
    )

    # 6. ENTITIES — resolution + dedup + count (the self-organising bit).
    from pensieve.factory import entity_service

    entities = entity_service()
    content.add_note(
        "recs", "Rafia emailed", entities=[{"name": "Rafia Naseem", "kind": "person"}]
    )
    content.add_note(
        "recs", "Rafia called", entities=[{"name": "Rafia Naseem", "kind": "person"}]
    )
    reg = [e for e in entities.list_entities() if e["id"] == "rafia-naseem"]
    checks.eq("entity resolved once (no duplicate)", len(reg), 1)
    checks.eq("entity note count", reg[0]["count"] if reg else None, 2)
    checks.eq("promotable at threshold", reg[0]["promotable"] if reg else None, True)

    # 7. PROMOTION — thread under the stream + its notes attached.
    node = entities.promote_entity("rafia-naseem", "recs")
    checks.eq("promoted to a thread under the stream", node.parent_id, "recs")
    view = entity_service().get_entity_view("rafia-naseem")
    checks.eq("entity is now a thread", view["promoted"], True)
    checks.eq(
        "recall returns the entity's notes",
        [n["text"] for n in view["notes"]],
        ["Rafia emailed", "Rafia called"],
    )

    # a new note tagging the promoted entity lands under the thread automatically.
    content.add_note("recs", "Rafia confirmed", entities=[{"id": "rafia-naseem"}])
    thread = content_service().get_stream_view("rafia-naseem")
    checks.eq(
        "new tagged note lands under the thread",
        "Rafia confirmed" in [n["text"] for n in thread["notes"]],
        True,
    )

    # fetching a missing stream raises (engine vocabulary; CLI/MCP translate it)
    checks.raises(
        "fetch missing stream raises NodeNotFound",
        NodeNotFound,
        lambda: content_service().get_stream_view("nope"),
    )

    return checks


def main() -> int:
    store = tempfile.mkdtemp(prefix="pensieve-eval-")
    os.environ["PENSIEVE_HOME"] = store
    os.environ["PENSIEVE_PROMOTION_THRESHOLD"] = "2"  # so the eval can reach it quickly

    from pensieve.database.session import reset_engines

    reset_engines()  # bind a fresh engine to the throwaway store

    print("Capture/Fetch evaluator (deterministic, engine-level)")
    print(f"  store: {store}\n")
    try:
        checks = run_checks()
    finally:
        shutil.rmtree(store, ignore_errors=True)

    for line in checks.lines:
        print(line)
    total = checks.passed + checks.failed
    print(f"\n{checks.passed}/{total} checks passed")
    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
