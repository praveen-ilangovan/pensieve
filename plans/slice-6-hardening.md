# Slice 6 — hardening (architect-review pre-refactor)

> **Status:** ✅ done · **Date:** 2026-06-27 · Addressed the pre-refactor checklist from
> `plans/architect-review.md` before the assets/search phase. Six fixes, ordered.

## 1. [blocker] Blanket restore corrupts state
`restore_stream` cleared **every** child node's flag, resurrecting a thread that was removed
independently by `entity rm` → an orphan thread for a derived-gone entity. (A note removed
before a `stream rm` is already correct — `restore_stream` never touches note flags.)
- **Fix (derived):** `restore_stream` re-shows a child thread **only if its entity is still
  live** (≥1 live note) — restore the stream node *first*, then per child: if it's an
  entity-thread (`get_entity(child.id)`) with `count_for_entity == 0`, leave it removed.
- **`restore_entity`:** only re-show the thread if its **parent stream is visible** (else the
  thread would be live under a removed stream); it self-heals when the stream is restored.
- Needs a raw read: `get_node(id, *, include_deleted=True)` on the port + both adapters.

## 2. [high] Adapters never verified against the port
Add `tests/integrations/test_adapter_conformance.py`: one rich scenario run against **both**
UoW factories (in-memory + sqlite), asserting identical observable results — so the two
backends can't silently drift (esp. before assets adds a new FK table).

## 3. [high] Stale/wrong `entity rm` CLI help
Help still says it *purges notes*; it only **unlinks**. Fix the command help text.

## 4. [medium] `next_id` read-modify-write race
Rewrite `SqliteRepository.next_id` as a single atomic upsert:
`INSERT … ON CONFLICT DO UPDATE SET next = next + 1 RETURNING next` (serialized by SQLite's
write lock). In-memory adapter unchanged (single-process).

## 5. [low/med] Dead schema + doc drift
- `Edge` is declared/migrated but unused → mark **RESERVED** (entity-edges are on the
  roadmap), with a pointer comment.
- Banner the superseded docs (`handoff.md`, `verbs.md`) as historical; point to the live
  docs (`glossary.md`, `cli.md`, SKILL.md).
- Make the "flush before FK insert" rule explicit (it bites the new assets table otherwise).

## 6. Overlapping-removal eval coverage
Add scenarios to `evals/removal.py` (both orders, both axes) that pin the blocker fix:
entity-rm-then-stream-rm-then-restore, note-rm-then-stream-rm-then-restore.

## Progress log
- **All six addressed — ✅ done.**
  1. **Blocker fixed.** `restore_stream` re-shows a child thread only if its entity is live
     (`streams.py`); `restore_entity` re-shows the thread only if the parent stream is
     visible (`entities.py`). Added raw `get_node(id, include_deleted=True)` to the port +
     both adapters. Verified: the entity-rm→stream-rm→restore repro no longer resurrects an
     orphan thread; normal restore intact.
  2. **Adapter conformance** — `tests/integrations/test_adapter_conformance.py`: one
     capture→promote→unlink→soft-rm→restore scenario run against both backends, asserting
     identical snapshots (service views + direct port reads) at every step.
  3. **Stale `entity rm` help fixed** (`cli/main.py`) — now says *unlink*, not purge.
  4. **`next_id` atomic** — `SqliteRepository.next_id` is a single
     `INSERT … ON CONFLICT DO UPDATE SET next = next + 1 RETURNING next` (serialized by the
     SQLite write lock). In-memory unchanged.
  5. **Dead schema / docs** — `Edge` marked RESERVED (entity-edges roadmap); `handoff.md` +
     `verbs.md` bannered HISTORICAL → point at `cli.md`/SKILL/`glossary.md`; the
     flush-before-FK rule is now spelled out on `SqliteRepository`.
  6. **Overlapping-removal evals** — `evals/removal.py` scenarios F (entity-rm→stream-rm→
     restore: no orphan) + G (note removed before stream rm stays removed). Plus unit tests
     in `test_streams.py`.
- Suite **78 green**; evals **19/19 + 36/36**; lint/types clean.
- Not done (deferred to "later" per the review): de-dupe `_utcnow`, README note on the two
  MCP registrations, single-writer doc note (superseded by the atomic fix).
