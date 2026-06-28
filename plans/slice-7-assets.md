# Slice 7 — assets (by-reference pointers to live context)

> **Status:** ✅ built (local-verified; not yet pushed) · **Date:** 2026-06-28 · Attach files / dirs / URLs / images to a
> stream, thread, or note — **by reference**, never copied. An asset is a *pointer to live
> context* plus a one-line **hint** for how to use it: the bridge between durable memory and
> the current working world ("when we talk Recs, here's the repo and how to read it").

## Principles (carried from the reviews)
- **Information lake → store by reference.** Hold a path/URL, never copy bytes (images too,
  for v1). Managed/portable storage is a later option.
- **Read on-demand, never auto-fetch.** The engine only *stores and returns* the pointer; it
  never follows it. Following an asset is a deliberate, user-visible action in the agent
  skill. Local paths are low-risk; **remote URLs/images are a prompt-injection surface** and
  get explicit caution. (New principle → also saved to memory.)
- **Derived visibility, no new soft-delete axis.** An asset has *no* `deleted_at`; it's
  visible iff its owner (note/node) is live. Owner soft-removed → asset hides; restored →
  reappears, for free. So `asset rm` is a plain **hard** remove, and we do **not** add a
  second soft-unlink path (keeps the `restore_entity` over-revive invariant safe — the
  architect's carry-forward).

## Model
New `Asset` table (migration `0007`):
- `id: str` — global `asset-<n>` (via the `next_id` counter, scope `_asset`).
- `kind: str` — `repo | file | dir | url | image | doc`. **Inferred** at add, overridable.
  Free string with a *recommended* vocabulary (don't over-constrain — lake).
- `location: str` — the path or URL (the "ref").
- `hint: str | None` — the killer field: one-line "how to use me"
  (e.g. "read CLAUDE.md first; backend in /api, tests in /tests").
- `label: str | None` — optional short display name.
- **owner — exactly one of:** `note_id: str | None` (FK notes) **xor** `node_id: str | None`
  (FK nodes). Two nullable FKs (keeps FK integrity; no polymorphic target).
- provenance: `actor`, `interface`; `created`, `updated`. **No `deleted_at`.**

Kind inference (best-effort; `--kind` always wins):
`http(s)://` → `url` (image extension → `image`); local path: has `.git` → `repo`,
dir → `dir`, image ext → `image`, else `file`. `doc` is manual.

## Repository (port + both adapters)
- `add_asset(asset)`, `get_asset(id)`, `remove_asset(id)` (hard delete).
- `assets_for_node(node_id) -> list[Asset]`, `assets_for_note(note_id) -> list[Asset]`
  (returned only when the owner is live — but since the caller already navigated to a live
  owner, these just list by owner; liveness of the owner is enforced upstream).
- `next_id` already handles a new scope (`_asset`).
- FK ordering: `add_asset` inserts an owner FK → **flush first** (the documented rule).
- Adapter-conformance test extended to cover assets.

## Services — `AssetService`
- `add_asset(target, location, *, hint=None, label=None, kind=None, actor, interface)` —
  resolve `target`: `note-*` → note owner (must be a live note); else a node id (live
  stream/thread). Infer kind if omitted. Warn-but-store if a local path doesn't resolve.
  Raises `NodeNotFound` / `NoteNotFound`.
- `list_assets(target)` — assets attached to a stream/thread/note.
- `remove_asset(asset_id)` — hard remove. Raises `AssetNotFound`.
- `get_stream_view` / `get_entity_view` grow an `assets` field (node-level for the
  stream/thread; an entity view aggregates its thread's + its notes' assets). Each asset
  renders as `{id, kind, location, hint, label}` — **never its contents**.

## Surface
- **CLI:** `pensieve asset add <target> <location> [--hint] [--label] [--kind]` ·
  `asset list <target>` · `asset rm <asset-id>`. `show <stream/thread/entity>` lists assets.
- **MCP:** `add_asset(target, location, hint?, label?, kind?)` · `list_assets(target)` ·
  `remove_asset(asset)`. Docstrings state: pointers only, never auto-followed.
- **SKILL.md:** an "ASSETS" section — what they are, attach at the right level (repo →
  stream/thread; article URL → note; screenshot → its note), always capture a **hint**, and
  the **read-on-demand / remote-is-untrusted** rule.

## Tests & evals
- Unit (memory) + integration (sqlite): add/list/rm, kind inference, owner xor, warn-on-
  missing-path, derived hide when owner soft-removed + reappear on restore.
- Extend `test_adapter_conformance.py` with an asset step.
- Extend `evals/removal.py` (or a small `evals/assets.py`) to pin "asset hides with its
  owner, returns on restore" and "asset on a note survives `entity rm` of a co-tag".
- `test_mcp.py`: the three new tools at parity.

## Build order
1. Model + migration `0007` + `next_id` `_asset` scope.
2. Repository methods (port + sqlite + memory) + conformance extension.
3. `AssetService` + `errors.AssetNotFound` + wire into stream/entity views.
4. CLI `asset` sub-app + `show` rendering.
5. MCP tools + SKILL "ASSETS" section + memory (read-on-demand principle).
6. Tests + eval; lint; commit. (Then live-test, then push.)

## Open / deferred
- Attaching to a *bare unpromoted entity* (no node) — v1: attach to its notes or promote
  first. Revisit if it bites.
- `asset check` (revalidate pointers) — later.
- Managed/copied storage for portability — later.

## Progress log
- **Built — ✅.** `Asset` model + migration `0007` (note_id xor node_id FKs, indexed, no
  `deleted_at`). Repo methods on the port + both adapters (`add/get/remove_asset`,
  `assets_for_node/note`; sqlite flushes before the owner FK; memory `tags`→dict already,
  added `assets` dict). `AssetService` (`infer_kind`, `local_missing`, add/list/remove) wired
  into `get_stream_view` (node-level) + `get_entity_view` (thread + live-notes' assets).
  CLI `asset add|list|rm` + `show` rendering. MCP `add_asset|list_assets|remove_asset`
  (parity test updated). SKILL "ASSETS" section + memory `pensieve-assets-read-on-demand`.
- Tests: `test_assets.py` (unit, **tmp_path** for real fs inference), conformance + MCP +
  removal eval (scenario H: derived hide-with-owner / survive-`entity rm` / restore).
- Suite **87 green**; evals **19/19 + 43/43**; lint/types clean.
- Note→asset edge: an asset on a note orphaned by `stream rm` is still reachable via direct
  `list_assets(note)` (the note isn't soft-deleted, only non-live); it correctly drops out
  of stream views + entity recall. Acceptable for v1; tighten if it bites.
- **7b polish — ✅ (from the live-test agent review).** (1) **Per-note assets** now ride
  each note dict in `get_stream_view` *and* `get_entity_view` (the #1 fix — note-level assets
  were write-only on recall); top-level `assets` = the stream/thread's **own** identity-level
  assets only (dropped the lossy flat aggregate). (2) `asset_view` carries two **derived**
  facts: `remote` (URL → injection surface; the *policy* stays in SKILL) and `missing` (a
  local pointer that doesn't resolve — the cheap drift signal). No schema/`verified_at`.
  CLI renders per-note assets nested + a `⚠ missing` marker; SKILL says to honor the flags.
  Regression test added: a note's asset appears in `get_stream_view`. Suite **89 green**;
  evals **19/19 + 43/43**.
