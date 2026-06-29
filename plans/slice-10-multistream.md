# Slice 10 — multi-stream notes (one note, several homes)

> **Status:** ✅ built (local-verified; not yet pushed) · **Date:** 2026-06-29

## Why this slice (reviewer context — the problem space)

A note often belongs to **more than one stream**. Live example: an article on "how I built
the AI agents for Recs" is genuinely about **Writing** *and* **Recs** — but today `add_note`
files a note into exactly one stream, so it had to be captured **twice**. For a system whose
whole pitch is *coherence* (resolve-don't-duplicate), that's a real wart, and it's actively
affecting daily use.

The storage already supports it — notes↔nodes is a true many-to-many (`attach`); it's how a
promoted entity's note lives under both its stream and its thread. **What's missing is the
surface**: a way to file a note into several streams. This slice adds it. No schema change —
this is service + surface only. It also nudges the model toward "streams as views over one
note set," which is the right long-term direction.

## Design

### Semantics
- A note can be attached to **several streams**; it appears (loose, unless covered by a
  promoted entity *in that stream*) in each one's view — existing thin-view logic already
  handles this, and `search`/`recent` already de-dupe a multi-homed note.
- **Streams only** for these ops (like `add_note`): a note reaches a *thread* by tagging its
  entity, never by direct filing.
- **No orphaning:** `unfile` refuses to remove a note's **last** home (use `note rm` instead).

### Service (`ContentService`)
- `add_note(node_id, …, also: Sequence[str] = ())` — capture into the primary stream **and**
  each stream in `also`, in one transaction. Every target validated as an existing stream.
- `file_note(note_id, stream_id)` — attach an **existing** live note to another stream.
  Raises `NoteNotFound` / `NodeNotFound`; `PensieveError` if the target is a thread.
- `unfile_note(note_id, stream_id)` — detach from a stream. Raises if not attached there;
  `PensieveError` if it's the note's only live home.
- Reuses the existing repo primitives (`attach`/`detach`/`nodes_for_note`) — **no new repo
  methods, no migration.**

### Surface
- **CLI:** `pensieve note add <text> -s recs -s writing` (repeatable `-s`) ·
  `pensieve note file <note> -s <stream>` · `pensieve note unfile <note> -s <stream>`.
  `show <stream>` already renders a multi-homed note in each stream.
- **MCP:** `add_note(stream, text, …, also=None)` (backward-compatible — extra streams) ·
  `file_note(note, stream)` · `unfile_note(note, stream)`.
- **SKILL — capture step:** "if a note is genuinely about more than one stream, file it into
  **all** of them (one note, several homes) — never duplicate. Most notes still belong to
  one; multi-home only when it truly spans."

> **Naming call:** I went with **`file` / `unfile`** ("file it under Recs") for the
> note↔stream verbs — distinct from `entity link/unlink` (note↔entity). Trivial to rename if
> you'd prefer `add-to`/`remove-from` or similar.

## Testing
- Unit (memory) + integration (sqlite): `add` with `also` → note in N streams, shows in each;
  `file` an existing note → appears in the new stream, still in the old; `unfile` → gone from
  one, kept in the other; `unfile` last home → refused; `file`/`unfile` to a thread → refused;
  missing note/stream → errors. Cross-check `nodes_for_note`.
- Conformance: extend the scenario with a `file_note` step (deterministic — both adapters).
- MCP parity: `file_note`/`unfile_note` present + `add_note also=` smoke.
- Eval: capture/fetch — a note filed into two streams surfaces in both views.

## Build order
1. Service `add_note(also=)` + `file_note` + `unfile_note` (+ stream/thread/orphan guards).
2. CLI `note add -s…-s`, `note file`, `note unfile`.
3. MCP `add_note also=`, `file_note`, `unfile_note` + SKILL capture note.
4. Tests (unit, sqlite, conformance, MCP, eval) + lint + commit. Then live-test, then push.

## Open / deferred
- "Streams as saved queries/views over the note set" (the radical end-state) — this slice is
  the incremental step; full reframe is later, if ever.

## Progress log
- **Built — ✅.** No schema change. `ContentService.add_note(also=)` (capture into N streams,
  one transaction, deduped), `file_note`/`unfile_note` (+ `_require_stream` guard; unfile
  refuses the last home), reusing `attach`/`detach`/`nodes_for_note`. Made the sqlite
  `attach` **idempotent** so re-filing is safe. CLI `note add -s…-s`, `note file`,
  `note unfile`; MCP `add_note(also=)`, `file_note`, `unfile_note`; SKILL capture step now
  says "one note, several homes; never duplicate."
- Tests: unit `test_multistream.py` (multi-add, dedupe, thread/ghost rejects, file
  idempotent, unfile keeps-other / refuses-last) + sqlite `test_multistream_sqlite.py`
  (FK + idempotent re-file) + conformance (added a `file_note` step) + MCP parity/smoke +
  eval §11. Suite **122 green**; evals **28/28 + 43/43**; lint/types clean. CLI-verified.
