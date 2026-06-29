# Slice 8 — search (recall over note content **and** pointers)

> **Status:** ✅ built (local-verified; not yet pushed) · **Date:** 2026-06-29

## Why this slice (reviewer context — the problem space)

Pensieve's whole purpose is **cross-session recall**, but today recall is **navigational
only**: you can find things by *name* — `list_streams`, `get_stream`, `find_entities`
(name/alias over streams/threads/entities). There is **no way to search what the memory
actually says.**

So the most natural recall question fails: *"what did we decide about pricing?"* when no
stream or entity is literally named "pricing." The only way to answer it now is to pull whole
streams and scan the prose by eye — worse as the store grows. This was the **#1 gap** in the
first feature review ("retrieval is the whole game, and it's the thinnest part").

**The recall surface is two things, not one: note *prose* and *pointers* (asset hints/labels/
locations).** A real incident proved it — slice-8 itself was discoverable only via an asset
*hint* ("side-projects… memory-stick"), not via any note. Content search alone would be *half*
the gap. So this slice does **both**:
- **`search` over note text** — FTS5, stemmed, ranked.
- **`search` over asset metadata** — hint/label/location (never file contents — read-on-demand
  stands, [[pensieve-assets-read-on-demand]]).

Search is squarely in scope for an **information lake** ([[pensieve-information-lake-principle]]):
it serves *recall*, not workflow/PM. It's also one half of a future auto-hydrate — the other
half is the **recency** path; search alone doesn't yet unlock session-start hydration.

**Why FTS5 + porter (not `LIKE`) for notes:** match *language*, not substrings. FTS5 with a
`porter` stemmer makes "pricing" recall a note that says "we **priced** it" — real recall
`LIKE` can't do — plus bm25 ranking + snippets. We accept FTS5's costs (a virtual-table
migration + sync + query sanitization) for that quality. (Porter is English-only and
over-stems occasionally — acceptable.) Asset metadata is short and few, so it's a plain
substring match — no FTS needed there.

> Note: note search is **engine-specific** (ranking/stemming live in SQLite), so it is **not**
> held to in-memory/SQLite equality. See "Testing" — a conscious carve-out, not drift.

## Design

### Surface
- **CLI:** `pensieve search <query>` — distinct from `find` (`find` = name/label/alias over
  streams/threads/entities; `search` = full content over **notes + pointers**). Renders two
  sections (notes, assets).
- **MCP:** `search(query)` → `{ notes: [...], assets: [...], truncated: bool, ... }`.

### Semantics
- **Terms are OR-ed** (recall over precision) — a multi-word query surfaces strong partial
  matches; bm25 floats full matches to the top. (AND only if precision ever becomes a need.)
- **Notes:** FTS5 `MATCH` over text, **bm25-ranked**, **live notes only** (not soft-deleted
  **and** attached to a visible node). Each hit → `{id, text, snippet, date, streams:[live
  homes id+label], entities:[tagged ids]}`.
- **Assets:** case-insensitive substring of any term in **hint / label / location**, filtered
  to **live owners** (the owning note/node is visible). Each hit → the `asset_view`
  (`id, kind, location, hint, label, remote, missing`) + its owner (`{id, label}`). Ordered
  newest-first.
- **Top-K cap** (default 20 each); when truncated, say so (`truncated: true`, and the CLI
  prints "showing top 20 of N") — **no silent caps**.
- Empty/blank query → empty result.

### FTS5 mechanics (notes)
- **Standalone** FTS5 table `notes_fts(note_id UNINDEXED, text)` — committed (string PKs make
  external-content rowid alignment fiddly; duplicated text is trivial at this scale).
- Tokenizer: **`unicode61` + `porter`**.
- **Sync** (single source of truth = `notes`; FTS is just a text index):
  - `add_note` → insert; `update_note` → update.
  - soft delete / restore → **no FTS change** (liveness filtered at query time by joining
    matched ids to live notes). Only a future hard `forget` deletes the FTS row.
- **Query sanitization:** split into terms, quote each as a phrase, **OR** them
  (`"pricing" OR "deck"`) — punctuation/operators can't break or inject into `MATCH`.
- Migration `0008`: create `notes_fts` + **backfill** existing notes.

### Repository (port + adapters)
- `search_notes(query) -> list[Note]` (live, bm25-ranked, capped).
  - **SQLite:** sanitized FTS `MATCH` joined to the live-note filter, `ORDER BY bm25`.
  - **In-memory:** case-insensitive substring (any term), recency order — a good-enough
    double for service-plumbing tests (NOT held to FTS semantics).
- `search_assets(query) -> list[Asset]` (substring over hint/label/location, live-owner,
  capped) — same logic in both adapters (this one *is* conformance-equal).

### Service
- `ContentService.search(query) -> {notes, assets, truncated, totals}` — runs both repo
  searches, keeps live results, assembles context (note homes + entities + snippet; asset
  owner), applies the top-K caps and the truncation flag.

## Testing
- **SQLite integration** (the real note behaviour): stemming ("priced" matches "pricing"),
  bm25 ordering, liveness filtering (removed-stream / soft-deleted excluded), sanitization
  (punctuation doesn't crash), backfill after migration, top-K truncation flag.
- **Unit (in-memory)**: service plumbing — OR semantics, live-filter, context, empty query,
  asset hint/label/location matching + live-owner filter.
- **Conformance**: `search_assets` included (deterministic); `search_notes` **excluded by
  design** with an inline comment (engine-specific).
- **MCP parity**: `search` present + a stdio smoke query.
- **Eval**: extend `evals/capture_fetch.py` (or `evals/search.py`) — capture notes + an asset
  hint, then a stemmed query returns the right note, an asset-hint query returns the pointer,
  and a removed note/owner drops out.

## Build order
1. Migration `0008` (`notes_fts` standalone + backfill).
2. Repo `search_notes` (sqlite FTS + memory substring) + `search_assets` (both) + sanitizer +
   caps.
3. `ContentService.search` (live filter + context + snippet + top-K + truncation).
4. CLI `search` (two sections) + MCP `search` + SKILL FETCH/RECALL note ("search = content +
   pointers; find = names").
5. Tests (sqlite integration, unit, MCP, eval) + lint + commit. Then live-test, then push.

## Open / deferred
- Unified single ranked list across notes+assets (instead of two sections) — later; two
  sections are clearer for v1.
- Stemmed/FTS search over asset metadata, or searching entity names in `search` — later.
- Phrase/boolean operators exposed to the user — no; keep the query a bag-of-terms for v1.
- Recency path (for auto-hydrate) — separate slice; search is the other half.

## Progress log
- **Built — ✅.** Migration `0008` (standalone `notes_fts` FTS5, `porter unicode61`,
  backfill). Repo: `search_notes` (sqlite FTS5/bm25, live-filtered via EXISTS-visible-home;
  memory substring/recency double), `search_assets` (substring over hint/label/location,
  live-owner — conformance-equal), `nodes_for_note`; FTS kept in sync in
  `add_note`/`save_note`/`delete_note`. `ContentService.search` → `{notes, assets, *_truncated}`
  with OR terms, top-K=20 + truncation flags, snippets, note homes + tagged entities, asset
  owner. CLI `pensieve search`, MCP `search`, SKILL FETCH/RECALL note ("search = content;
  find = names").
- Tests: unit `test_search.py` (memory plumbing — OR, liveness, context, asset hint,
  truncation), integration `test_search_sqlite.py` (porter stemming, removed-note/stream
  exclusion, edit-reindex, query sanitization, truncation), conformance extended with
  `search_assets` (note search excluded by design, commented), MCP parity + stdio smoke.
  Eval: capture/fetch §9 (stemmed note match + asset-hint match + no-match).
- Decisions honored from review: OR terms; standalone FTS; top-K + truncation; asset search
  by metadata (hint/label/location), never contents.
- Suite **101 green**; evals **23/23 + 43/43**; lint/types clean. CLI-verified (stemming +
  asset-hint).
