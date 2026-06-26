# Pensieve — Spec 4: Engine Contract (storage, durability, config)

> **Status:** spec / pre-implementation · **Version:** v1-draft · **Date:** 2026-06-25
> **Depends on:** `glossary.md` (model) · `verbs.md` (ops) · `core_concept.md`

The **systems layer** the contract specs deliberately don't touch: how the engine
persists the canonical model, how commits stay atomic under crashes and
concurrency, and the operational details (config, ids, dates, errors). This is the
answer to the implementer review's central finding — *"clear at the contract layer,
silent at the systems layer, which is exactly where the data-loss risk lives."*

The decisive simplification: **storage is SQLite**, so atomicity, concurrency, and
crash-safety come from the database rather than hand-rolled file journaling.

---

## 1. Store & configuration

- **Root:** `$PENSIEVE_HOME` if set, else `~/.pensieve/` (expanded once at
  startup). DB file: `<root>/pensieve.db`.
- The store is **global and cwd-independent** — the same pensieve regardless of which
  repo you're in.
- A single file → trivially portable/backup-able (copy `pensieve.db`).
- **`PRAGMA journal_mode=WAL`** (concurrent readers + a serialized writer),
  **`PRAGMA foreign_keys=ON`**, a sane **`PRAGMA busy_timeout`** (e.g. 5000ms).
- **`PRAGMA user_version`** holds the schema version (mirrors `schema_version` in
  the model). Migrations branch on it; the stamp exists from day one so data
  written now is always migratable. Each migration **runs inside a transaction and
  bumps `user_version` as its last statement**, so a crashed migration rolls back
  wholesale — the same atomicity discipline as commits, applied to schema changes.

---

## 2. Schema (v1 target)

Indicative DDL — refined during build, but the shape is fixed. The canonical model
(`glossary.md`) is a **property graph**, so the schema is **generic**: one `nodes`
table (every kind), `edges`, and per-node contents (`todos`, `notes`) + `history`.
The engine assembles the URI-layer JSON (`spec_resource_uris.md`) from these.

```sql
-- every node: top-level ("stream") or contained ("thread"), any kind
CREATE TABLE nodes (
  id             TEXT PRIMARY KEY,                              -- agent-proposed kebab slug
  label          TEXT NOT NULL,
  kind           TEXT NOT NULL,                                 -- subject|person|org|place|event|asset
  parent_id      TEXT REFERENCES nodes(id) ON DELETE CASCADE,   -- NULL = top-level ("stream"); else the `contains` edge
  properties     TEXT NOT NULL DEFAULT '{}',                    -- JSON, kind-specific: purpose/status/when/location/role/sub_kind/suggested_reads…
  version        INTEGER NOT NULL,                              -- per-node; SOLE source of truth
  schema_version INTEGER NOT NULL,
  created        TEXT NOT NULL,
  updated        TEXT NOT NULL
);

-- typed relationships (NON-`contains`; containment is nodes.parent_id)
CREATE TABLE edges (
  from_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  to_id   TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  kind    TEXT NOT NULL,                                        -- located-in|requested-by|attended|participates-in|about|relates-to
  PRIMARY KEY (from_id, to_id, kind)
);

-- contents: todos = the mutable working set (only OPEN items live here;
-- complete/close DELETEs the row and records it in history)
CREATE TABLE todos (
  node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  id TEXT NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY (node_id, id)
);

-- contents: notes = the append-only log; flavor optional; supersedes links a reversal
CREATE TABLE notes (
  node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  id TEXT NOT NULL, text TEXT NOT NULL, flavor TEXT, supersedes TEXT,
  date TEXT NOT NULL, commit_id TEXT NOT NULL,
  PRIMARY KEY (node_id, id)
);

-- per-node commit log (provenance). One apply_diff may touch several nodes;
-- each affected node gets a row sharing the apply_diff's commit_id.
CREATE TABLE history (
  node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  commit_id TEXT NOT NULL, version INTEGER NOT NULL,
  session TEXT, date TEXT NOT NULL, summary TEXT, changes TEXT,  -- changes = JSON array
  PRIMARY KEY (node_id, commit_id)
);

-- non-reusing id counters (see §4)
CREATE TABLE counters (scope TEXT, kind TEXT, next INTEGER, PRIMARY KEY(scope,kind));

-- the registry is a derived VIEW over top-level nodes — can never drift
CREATE VIEW registry AS
  SELECT id, label, kind, json_extract(properties,'$.purpose') AS purpose, version, updated
  FROM nodes WHERE parent_id IS NULL;
```

> **Why generic, not per-field?** The pre-graph schema had a table per state-field
> (goals / open_loops / decisions / …). The graph collapses all of it into **nodes +
> contents**: goals/loops/actions → `todos`; decisions/insights → `notes` (+`flavor`);
> references → `asset` nodes; context → `person` nodes; the hierarchy → `parent_id`.
> Kind-specific data lives in the `properties` JSON, so **a new kind needs no schema
> change.**

**Required with `foreign_keys=ON`** (the DDL is indicative; these aren't optional):
- **FK + `ON DELETE CASCADE`** on `parent_id` (deleting a node removes its subtree)
  and from `edges` / `todos` / `notes` / `history` to `nodes(id)`.
- **Indexes** on `nodes(parent_id)` (children lookup), `edges(from_id)` /
  `edges(to_id)` (traversal + backlinks), and `history(node_id, commit_id)`.
- **Dup-detection:** PK/unique check for node ids, todo/note ids, and edges; a JSON
  membership check in code for array-valued properties (e.g. `suggested_reads`).

---

## 3. Atomic commit

**One `apply_diff` = one SQLite transaction** — it may touch several nodes, all
committed atomically:

```
BEGIN IMMEDIATE;                       -- take the write lock up front
  -- validate all ops (node/edge/todo/note target ids exist, kind/edge-kind valid,
  --   no dup) — abort on any failure
  -- allocate ids (see §4) within the txn
  -- apply node create / set-property / reparent, edges, todo add|complete,
  --   note appends (incl. supersedes), promote_entry, redact
  -- append one history row per affected node
  -- bump version + updated on each affected node
COMMIT;                                -- single durable, all-or-nothing point
```

- **Crash mid-commit** (kill -9, OOM, power loss): SQLite rolls the transaction
  back via the WAL; the store is left at the previous consistent version. No
  half-written stream, no orphaned log line. **No custom journaling needed.**
- **Validation failure**: the transaction never commits; `ok:false` + `errors`.
- **I/O/DB failure**: the transaction rolls back; surfaced as a hard failure
  (distinct from `errors`), store stays consistent.

---

## 4. ID allocation (crash-, race- & reuse-safe)

All engine-assigned ids are allocated **inside the commit transaction** (so they're
consistent under crashes and concurrency) **and from a non-reusing monotonic
counter** (so a freed id is never reissued).

- **Node ids** are **agent-proposed kebab slugs**; the engine validates uniqueness
  in `nodes` (rejects dupes). Not counter-allocated.
- **`commit_id`**: one `apply_diff` = one `commit_id` = `"c" + n`, `n` from a global
  `counters` row (scope `_commit`), read inside `BEGIN IMMEDIATE` (the write lock
  prevents two writers sharing a base). Each affected node's `version` bumps by 1.
- **Per-node content ids — `note-<n>` / `todo-<n>`**: `n` from a per-**node**
  `counters` row (scope = `node_id`, kind = `note`|`todo`), **incremented, never
  reset**:

  ```sql
  -- counters(scope, kind, next), PK(scope,kind)
  -- allocate: UPDATE counters SET next = next + 1 WHERE scope=? AND kind=? RETURNING next;
  ```

> **Why not `max(existing)+1`?** `todos` are **deleted** when completed/closed
> (only the open working set lives in the table). With `max`-over-live-rows, deleting
> `todo-5` then adding a new todo would **reissue `todo-5`** — colliding with the
> `todo-5` still referenced in old `history.changes`. The non-reusing counter keeps
> ids **stable handles** everywhere (the promise of glossary's id-addressing). Notes
> are append-only so they lack the hazard, but use the counter uniformly.

---

## 5. Concurrency

- **Two `capture` runs on the same store** (e.g. two terminal tabs): `BEGIN
  IMMEDIATE` + WAL serialize the writers. The second waits (up to `busy_timeout`)
  and then commits on top of the first's new version — no lost update.
- **`fetch` read during a `capture` write**: WAL gives the reader a consistent
  snapshot; no torn reads, no half-written state. (Plain files had exactly this
  hazard; the DB removes it.)
- Manual-trigger-only narrows the window further, but the guarantee doesn't depend
  on it.
- **`busy_timeout` exhaustion** (sustained contention beyond the timeout) surfaces
  `SQLITE_BUSY`. Classify this as a **retryable hard failure** (like an I/O error,
  not a validation error per spec_diff §6) — the transaction never committed, the
  store is consistent, and the caller may retry.

---

## 6. Operational details (resolving the implementer's ambiguities)

- **`date`** is a local `YYYY-MM-DD` for display; **ordering is by `version` /
  `commit_id` / `seq`, never by date** (multiple commits can share a day). Timezone
  = system-local at commit time.
- **`session`**: if the diff omits it, the engine synthesizes
  `<date>-<short-uuid>` so provenance is never null.
- **Reference paths** (`~/...`) are stored **verbatim**; the engine never expands or
  resolves them — that's the agent's job on demand (Spec 2 "pointer-only").
- **Registry never conflicts**: it's a `VIEW`, always consistent with `streams`.
  (No `reindex` needed — the failure mode it would fix can't occur.)

---

## 7. Render / sync (deferred — noted for boundaries)

Not v1. When built, these are **read-only projections** off the canonical store:
`pensieve export` → JSON/Markdown; push `pensieve.db` (or an export) to GitHub
for backup; Obsidian/Notion views. The round-trip contract (decision #16) applies
to the **data model**, not to filesystem/DB-level guarantees (ordering, atomicity)
— the engine owns those via `version`/`seq`, so a backend that can't preserve
append order is still correct as long as it round-trips the data + its ids.

> **WAL copy caveat.** In WAL mode the live DB has `-wal`/`-shm` sidecar files;
> a naive `cp pensieve.db` while frames are uncheckpointed copies a torn/stale
> snapshot. So "copy/push the pensieve" must go through a **checkpoint first**
> (`PRAGMA wal_checkpoint(TRUNCATE)`) or use SQLite's **backup API / `VACUUM
> INTO`** — never a bare file copy of a live DB.

---

## 8. Build order

`spec_engine_contract` (this transactional core) is built **first** — it's the
substrate every op runs through. Then: canonical model + diff engine → CLI
(exercises everything, easy to test) → MCP server (thin frontend) → Claude
`SKILL.md` shim last.
