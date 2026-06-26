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

    # 3. Case A — content fits NO existing stream -> it becomes a new stream.
    #    (scripted agent: nothing matched, so create then add)
    streams.create_stream("Writing", "The 'I used to think' essays")
    a = content.add_note("writing", "drafted the first essay outline", actor="eval")
    checks.eq("A (new stream): note id", a.id, "note-1")

    # 4. Case B — content routes to an EXISTING stream.
    b = content.add_note("recs", "we are talking to 4 curators", actor="eval")
    checks.eq("B (existing stream): note id", b.id, "note-1")

    # 5. Case C — explicit target stream.
    c = content.add_note("employment", "I am working for Nothing", actor="eval")
    checks.eq("C (explicit stream): note id", c.id, "note-1")

    # a second note on recs — exercises per-node note ids + ordering
    content.add_note("recs", "rafia is one of the curators", actor="eval")

    # note ids are per-node; commit ids are global + non-reusing
    checks.eq(
        "global commit ids",
        [a.commit_id, b.commit_id, c.commit_id],
        ["c1", "c2", "c3"],
    )

    # 6. FETCH through a *fresh* service — the cross-session round-trip.
    view = content_service().get_stream_view("recs")
    checks.eq("fetch: purpose round-trips", view["purpose"], "Build and grow Recs")
    checks.eq(
        "fetch: notes round-trip in order",
        [n["text"] for n in view["notes"]],
        ["we are talking to 4 curators", "rafia is one of the curators"],
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
