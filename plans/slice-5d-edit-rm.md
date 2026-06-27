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

## rm = soft-delete (recoverable; `forget` = future hard-delete)
- Add `deleted_at: datetime | None` to **nodes**, **notes**, **entities** (null = active).
  `rm` sets it; **every read filters `deleted_at IS NULL`** so a deleted thing "isn't
  considered" after — but it's still there, restorable. A future `forget` truly deletes.
- **Restore:** `pensieve <noun> restore <id>` (clears `deleted_at`).
- **`note rm`** becomes **soft** too (it currently hard-deletes) — consistency.
- Reads to filter (the ripple): `get_node`, `get_note`, `get_entity`, `list_streams`,
  `children_of`, `find_nodes`, `notes_for`, `notes_for_entity`, `count_for_entity`,
  `list_entities`, `find_entities`. Covered-recompute then falls out: a note whose
  covering entity is deleted becomes loose again (its `get_entity` → None).
- Migration `0005` (add `deleted_at` ×3).

### The one open decision — cascade on `stream rm`
- **(A) cascade (lean):** soft-delete the stream **+ its threads + its notes** (the
  subtree). Clean — restore brings it all back; no orphans (a thread whose stream is gone).
- **(B) shallow:** soft-delete only the stream node; its notes/threads linger (hidden
  stream, but findable threads) → orphan-ish.
- `entity rm <id>`: soft-delete the **entity + its thread node**; **notes stay** (they
  belong to the stream too) — they just lose their covering thread and return to the
  stream's loose view.

## Build order
1. **edit** — service + CLI (replace stubs) + tests. *(do now)*
2. **soft-delete** — `deleted_at` + migration `0005` + filter all reads + `rm` (cascade per
   decision) + `restore` + convert `note rm`; CLI + tests + eval.

## Progress log
- **edit — ✅ done.** `StreamService.edit_stream` (label/purpose) + `EntityService.
  edit_entity` (name/aliases, syncs the thread node's label when promoted); both keep the
  **id immutable**. CLI stubs `stream edit` / `entity edit` wired. Tests (unit + CLI);
  stub test now covers only `rm`. Suite **62 green**.
- **soft-delete (rm) — next**, pending the cascade decision below.
