# Slice 9 — recency (what changed lately) → the other half of auto-hydrate

> **Status:** ✅ built (local-verified; not yet pushed) · **Date:** 2026-06-29

## Why this slice (reviewer context — the problem space)

Recall has two of its three modes now: **by name** (`list_streams`/`find_entities`) and
**by content** (`search`, slice 8). The missing one is **by time** — *"what's happened
lately?"* / *"what changed since I was last here?"*

That gap is what makes session bootstrap manual today: a fresh agent has to be *told* where
to look. There's no way to ask the memory for its recent activity. This is also the reason
the slice-8 review flagged that "search alone doesn't unlock auto-hydrate" — **search finds
what's *relevant*; recency finds what's *recent*.** You need both to reconstruct working
context at the start of a session.

So this slice adds a **time-ordered feed across the whole memory**: `recent(since?, limit?)`
— the live notes most recently added or edited, newest-first, each with its stream context.
It's the engine primitive **auto-hydrate** will consume ("on session start, pull what's
recent + search what's relevant"). Auto-hydrate as an *automatic* behaviour is a thin
follow-on in the skill; this slice ships the capability + a manual `recent` surface.

Squarely in scope for an information lake ([[pensieve-information-lake-principle]]): it's
recall, not workflow. No FTS, no new table — deterministic, so it stays **inside** adapter
conformance (unlike `search_notes`).

## Design

### Semantics
- **Cross-stream** feed of **live** notes (not soft-deleted **and** attached to a visible
  node) — the same liveness rule as everywhere.
- Ordered **newest-first by `updated`** (which equals `created` for a fresh note and bumps on
  an edit — so the feed surfaces both new notes and genuine edits), tie-broken by `created`
  then `id` for determinism.
- **`since`** (optional): only notes with `updated >= since`. Omitted → most-recent overall.
- **`limit`** (default 20) + a `truncated` flag — no silent caps (same discipline as search).
- Each hit returns the note + context: `{id, text, snippet?, date, updated, streams:[live
  homes id+label], entities:[tagged ids]}` — enough to reconstruct "what's been happening."

> Decision: this is a **cross-stream feed**, not a sort option on `get_stream`. Hydrate is a
> whole-memory question ("what changed *anywhere*"); per-stream newest-first ordering on
> `get_stream` is a minor, separate nicety — deferred unless wanted.

### Repository (port + both adapters — conformance-equal)
- `recent_notes(since: datetime | None, limit: int) -> list[Note]` — live notes, `updated`
  desc, optional `since`, capped. Deterministic; SQLite and in-memory must agree → covered by
  the conformance test.

### Service
- `ContentService.recent(*, since=None, limit=20) -> {notes, truncated}` — runs the repo
  query, assembles context (stream homes + tagged entities), applies top-K + truncation.
  Parses `since` from an ISO date/datetime string at the surface layer (CLI/MCP), passing a
  `datetime` into the service.

### Surface
- **CLI:** `pensieve recent [--since YYYY-MM-DD] [--limit N]` — newest-first feed.
- **MCP:** `recent(since=None, limit=20)` — for "what changed / catch me up." Docstring frames
  it as the time axis next to `search` (content) and `find_entities` (names).
- **SKILL:** a short **RESUME / HYDRATE** note — at the start of a resumed session, combine
  `recent` (what changed) + `search`/`get_stream` (what's relevant) to rebuild context; keep
  it a light, deliberate move, not a crawl.

## Testing
- **Unit (in-memory)** + **integration (sqlite)**: newest-first order, `since` filter, edited
  note floats up (updated bump), live-only (removed note/stream excluded), top-K + truncation.
- **Conformance**: add `recent_notes` to the snapshot (deterministic — both adapters agree).
- **MCP parity**: `recent` present + a stdio smoke.
- **Eval**: extend `evals/capture_fetch.py` — capture a few notes, `recent` returns them
  newest-first; an edit re-floats; a removed one drops out; `since` narrows.

## Build order
1. Repo `recent_notes` (port + sqlite + memory) + conformance extension.
2. `ContentService.recent` (+ ISO `since` parsing helper) + view assembly.
3. CLI `recent` + MCP `recent` + SKILL RESUME/HYDRATE note.
4. Tests (unit, sqlite, conformance, MCP, eval) + lint + commit. Then live-test, then push.

## Open / deferred
- **Auto-hydrate as an automatic behaviour** (agent calls `recent`+`search` on session start
  without prompting) — a follow-on; this slice gives the primitive + manual surface.
- Newest-first / `since` ordering option on `get_stream` — minor; defer unless wanted.
- Counting non-text "activity" (new tags/assets/promotion bumping recency) — out of scope;
  `updated` tracks the note's own text. Revisit if the feed feels stale.
- Relative `since` ("7d", "yesterday") — v1 takes an ISO date/datetime; relative parsing later.

## Progress log
- **Built — ✅.** Repo `recent_notes(since, limit)` (port + sqlite + memory) — live notes,
  `updated` desc (then created, id), optional `since`, deduped/capped; **conformance-equal**
  (added to the snapshot, ordered). `ContentService.recent` (+ `parse_since` ISO→naive-UTC
  helper, tz handled) → `{notes, truncated}` with stream homes + tagged entities. CLI
  `pensieve recent [--since] [--limit]`; MCP `recent`; SKILL gained a "what changed" line + a
  **RESUME/HYDRATE** note (combine `recent` + `search`/`get_stream`).
- Tests: unit `test_recency.py` (newest-first, edit-refloat, live-only, `since`, truncation,
  `parse_since` incl. tz + bad input), integration `test_recency_sqlite.py` (order, removed
  note/stream excluded, edit-refloat), conformance + MCP parity/smoke. Eval: capture/fetch
  §10 (newest-first, edit-refloat, `since` far-future empty).
- Standalone lens confirmed: `search`/`get_stream`/`find` orderings untouched.
- Suite **112 green**; evals **27/27 + 43/43**; lint/types clean. CLI-verified.
