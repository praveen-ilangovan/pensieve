# Slice 5d — edit + rm (soft-delete)

> **Status:** planned · **Date:** 2026-06-27 · Wires the CLI stubs (`stream edit/rm`,
> `entity edit/rm`) to real behaviour. Two halves: **edit** (easy) and **rm = soft-delete**
> (rippunier).

## edit (easy) — rename / repurpose; **id is immutable**
- `stream edit <id> [--name] [-p purpose]` → update the node's label / `purpose` property.
- `entity edit <id> [--name] [--alias …]` → update the entity's name / aliases; if it's
  promoted, also update its thread node's label to match.
- The **id (slug) never changes** — notes/threads/tags reference it. Only display
  fields change.
- Service: `StreamService.edit_stream`, `EntityService.edit_entity`. CLI replaces the two
  edit stubs. (MCP edit deferred — agents rename rarely.)

## rm = soft-delete, note-centric & recursive (the settled model)
**Notes and entities justify each other.** `rm` removes notes (directly or via a
container) and **entities are derived — alive iff they still have ≥1 live note.** So:

- **`rm note N`** → soft-delete N. Any entity that loses its **last** note → vanishes
  (derived). A genuinely **stream-level note (no entities) stays** — it's the stream's own.
- **`rm entity` / `rm thread E`** → **purge E's notes** (soft-delete every note tagged E)
  + soft-delete E's thread node. Other entities riding those notes that are now orphaned →
  vanish too (recursive). E itself → 0 notes → vanishes.
- **`rm stream S`** → soft-delete S + its threads; its notes go non-live transitively
  (a note is **live** iff not-deleted **and** still attached to a visible node). A note
  also in `employment` stays live there → its entities survive. Pure-`recs` entities → 0
  live notes → vanish. (This is how cross-stream "Rafia in two streams" survives.)
- **Soft + recoverable:** `restore` brings the notes back → entities reappear (derived).
  Future `forget` = real delete.

### Model
- `deleted_at: datetime | None` on **nodes** and **notes** (NOT entities — derived).
- A note is **live** = `deleted_at IS NULL` **and** attached to a visible node.
- An **entity is visible** = it has ≥1 live note (`get_entity`/`list`/`find` filter on it).
- Reads filter accordingly; migration `0005` adds `deleted_at` ×2.
- **`restore`:** `pensieve <noun> restore <id>` un-deletes (stream → clears its + threads'
  flags, notes relive transitively; note/entity → clears the relevant flags).

## Build order
1. **edit** — service + CLI (replace stubs) + tests. *(do now)*
2. **soft-delete** — `deleted_at` + migration `0005` + filter all reads + `rm` (cascade per
   decision) + `restore` + convert `note rm`; CLI + tests + eval.

## Progress log
- **edit — ✅ done.** `StreamService.edit_stream` (label/purpose) + `EntityService.
  edit_entity` (name/aliases, syncs the thread node's label when promoted); both keep the
  **id immutable**. CLI stubs `stream edit` / `entity edit` wired. Tests (unit + CLI);
  stub test now covers only `rm`. Suite **62 green**.
- **soft-delete (rm) — ✅ done.** `deleted_at` on nodes+notes (migration `0005`);
  liveness derived (a note is live iff not-deleted **and** attached to a visible node;
  an entity is live iff ≥1 live note). Repo reads filter on it; `notes_for_entity` /
  `count_for_entity` count only live notes (Tag→Note→Attachment→Node join); added
  `set_node_deleted` / `set_note_deleted` / `note_ids_for_entity` + `children_of(include_deleted=)`
  to both adapters + the port. Services: `note rm/restore` (soft), `stream rm/restore`
  (cascade threads; notes go non-live transitively → cross-stream notes survive),
  `entity rm/restore` (purge tagged notes + thread; other entities derived-recursive);
  `EntityService.list/find/get_entity_view` hide derived-gone entities. CLI: `stream rm |
  restore`, `note rm | restore`, `entity rm | restore` wired (stubs + `_not_implemented`
  gone). Tests: unit (streams/entities/content soft-delete + cascade + cross-stream) +
  CLI round-trips; migration test asserts `deleted_at`. Suite **70 green**; eval **28/28**
  (added §9 soft-delete/restore). MCP rm/restore exposure still deferred.
- **rm model corrected → bottom-up + `entity rm` = unlink — ✅ done.** The relationship
  is *note owns entity* (a note can exist subject-less; an entity can't exist without a
  note). So removal is **bottom-up**: containers (streams) own notes; entities/threads
  only *reference* them. `stream rm` / `note rm` already did this. Fixed `entity rm` from
  "purge its notes" (which destroyed a note shared with another subject) to **unlink from
  every note** — a note is never deleted; a shared note survives under its other subject;
  the entity (and its thread) derives away. Reversible: added `deleted_at` on the **tag**
  link (migration `0006`), `tag_note` revives a soft-unlinked link, `entity rm/restore`
  ride `set_tags_deleted_for_entity`; `tags_for_note`/`notes_for_entity`/`count_for_entity`
  count only live links. Dropped `note_ids_for_entity`. Memory adapter `tags` is now a
  dict `(note,entity)->deleted_at`. New **`evals/removal.py`** (30 checks, scenarios A–E:
  stream rm cross-stream survival, entity rm unlink keeps shared note, the cascade to
  derived-vanish, promoted-entity rm). `make eval` runs both evals. Suite **73 green**;
  capture/fetch + removal evals green.
