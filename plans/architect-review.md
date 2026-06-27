# Pensieve — Architect Review (pre-assets/search phase)

> **Reviewer pass:** read-only, full-repo. Source, tests, evals, migrations, SKILL, docs, plans.
> **Baseline health at review time:** `pytest` 75/75 green; `evals.capture_fetch` 19/19; `evals.removal` 30/30.
> **Date:** 2026-06-27. **Scope:** code + plans + docs, before the assets / `search_notes` / recency work.

---

## Executive summary

Pensieve is in **good shape** and genuinely well-architected for a personal project. The
ports/adapters boundary is real and honored: services depend only on `repository.base`,
the SQLite adapter is the *only* place that imports `Session`, and the in-memory adapter is
a real second backend that the entire unit suite runs against. The derived-entity model
(an entity is "live" iff it has ≥1 live note via a live link) is implemented coherently and
consistently across both adapters and is well-covered by the removal eval. CLI/MCP/SKILL
vocabulary parity is strong and there are explicit tests that storage terms (`node`) do not
leak to users. Migrations form a clean 0001→0006 chain with a sensible legacy-adoption path.

The **5 things that matter most** before the next phase:

1. **Restore is a blanket "un-delete", not an inverse of a specific `rm`** — overlapping
   removals corrupt state on restore. Verified bug: `stream rm` + `entity rm` of a promoted
   entity, then `stream restore`, **resurrects an orphan thread node** for an entity that is
   correctly derived-gone (`services/streams.py:103`, `services/entities.py:188`). This is a
   real data-integrity issue, not theoretical. **Fix before assets** (assets will multiply
   the restore surface). [blocker]
2. **The `Repository` Protocol port is silently out of sync with the adapters** — the port
   declares methods that don't exist (`delete_note` in `base.py:61` exists in adapters but
   the port also implies behaviors the adapters don't enforce) and, more importantly, the
   port is **not the thing the adapters are checked against**. There is no test that either
   adapter actually satisfies `Repository`, and they have **diverged in subtle liveness
   semantics**. [high]
3. **`Edge` is dead code carried in the live schema** — declared, migrated, FK'd, indexed,
   never read or written. It's on the roadmap (entity-edges) but right now it's pure
   surface area / confusion. Decide: keep with a clear "reserved" marker, or drop. [low,
   but decide now]
4. **Counters never reset on restore/cascade and `next_id` has a read-modify-write race** —
   benign for a single-user local store today, but the once-per-process migration guard +
   shared counter assume single-writer; worth an explicit note before any concurrency. [medium]
5. **Docs are split between "current" and "superseded/aspirational"** and several (handoff,
   core_concept, spec_*) describe a *pre-build* design (todos, flavor, supersede, diff
   envelope, history log) that the shipped engine does not implement. A newcomer (or the
   agent) reading them will be misled. [medium]

Nothing here blocks shipping what exists. Item 1 is the only thing I'd insist on fixing
before building new features on top of remove/restore.

---

## 1. Architecture & layering

### GOOD — preserve these
- **The port boundary is genuinely enforced.** `services/*` import only from
  `repository.base`, `database.models`, `errors`, `slug`, `config`. No service imports
  `Session`, `select`, or `sqlite`. Verified by grep. `repository/sqlite.py:14-15` is the
  sole importer of `Session`/`select`. This is the single best thing about the codebase —
  do not regress it in the refactor.
- **The in-memory adapter is a real backend, not a mock.** It honors the transaction
  boundary (works on a `copy()`, applies on `commit()`; `repository/memory.py:44-52,
  237-257`) and returns **clones** so a service mutating a fetched row can't leak
  uncommitted state (`memory.py:27-29`). The entire unit suite runs through it. This is
  what makes the "swap storage = new adapter" claim true rather than aspirational.
- **The composition root is a single file** (`factory.py`) — storage choice lives in
  exactly one place, and CLI/MCP/evals all build from it.
- **`expire_on_commit=False`** (`sqlite.py:228`) with a clear rationale in the docstring is
  the right call given services read rows back after the UoW closes.

### Findings

**[high] The adapters are not verified against the port, and have diverged.**
`base.py` defines `Repository` as a `@runtime_checkable Protocol`, but nothing asserts
`isinstance(SqliteRepository(...), Repository)` or that `InMemoryRepository` conforms.
Because `Protocol` conformance here is structural and never checked, the two adapters can
(and do) drift. Concretely, `notes_for_entity`/`count_for_entity` compute "live" with the
**same intent** in both but via **different mechanisms**: SQLite joins `Attachment`+`Node`
and filters `Node.deleted_at` (`sqlite.py:178-206`); memory uses a hand-written
`_note_live` helper that requires a *visible attachment* (`memory.py:66-73, 205-220`). They
agree today (I probed several cases), but there is no test pinning them to agreement, so a
future change to one will silently desync — and unit tests (memory) and integration tests
(sqlite) won't both catch it.
*Why it matters:* the whole decoupling story rests on behavioral equivalence; right now
equivalence is asserted by neither types nor tests.
*Fix:* add a single **adapter-conformance test** parametrized over both UoW factories that
exercises the liveness-bearing primitives (`notes_for`, `notes_for_entity`,
`count_for_entity`, `tags_for_note`, `set_tags_deleted_for_entity`, restore round-trips) and
asserts identical results. Add `assert isinstance(repo, Repository)` as a cheap smoke check.

**[medium] The port doc-comments over-promise vs. the adapters.**
`base.py:37-39` says `set_node_deleted` does a "raw lookup (acts on already-deleted rows
too)" — correct. But `base.py:91-95` (`set_tags_deleted_for_entity`) and `base.py:56-59`
do not document the **idempotency/over-restore** hazard that `restore_*` relies on (see
§3). The port is the contract; it should state that `when=None` re-links **every** tag
(not "every tag this rm touched"), because that asymmetry is the root of the restore bug.
*Fix:* tighten the port docstrings to state the blanket semantics explicitly, then fix the
services to not rely on blanket restore (§3).

**[low] `runtime_checkable` Protocol gives a false sense of safety.** It only checks method
*names* at runtime, not signatures. Either lean on it (add the isinstance smoke test) or
drop `@runtime_checkable` to avoid implying more than it delivers.

**[low] `factory.py` builds a new service per call.** Each `content_service()` etc. returns
a fresh instance. Harmless (services are stateless wrappers over a UoW factory) and CLI/MCP
both do this, but note the pattern: a single MCP tool invocation that builds two services
(e.g. `show` in the CLI calls `content_service()` then `entity_service()`) runs them in
**separate transactions/sessions**. Fine for reads; be careful if any future flow needs
two services in one atomic unit.

---

## 2. Data model coherence

### GOOD — preserve
- **The derived-entity model is clean and consistent.** "Entity is live iff ≥1 live note
  via a live link" is implemented identically in spirit in both adapters and is the
  backbone of the removal model. `count_for_entity`/`notes_for_entity` correctly require
  note-not-deleted **and** active tag **and** visible node home. The removal eval
  (`evals/removal.py`) exercises the cross-stream and cascade cases thoroughly.
- **Soft-delete + soft-unlink are well-separated:** nodes/notes carry `deleted_at`
  (`models.py:42,68`); tags carry their own `deleted_at` (`models.py:111`) for the
  unlink-don't-delete semantics; entities carry **no** `deleted_at` (they're derived) —
  this is the right call and the code comments call it out (`entities.py:183-185`).
- **Migration chain is intact.** 0001→0002→0003→0004→0005→0006, each `down_revision`
  correctly chained; `0003_remodel` honestly documents the note **reset** (clear-and-
  rebuild) and even sweeps stale counters (`0003:execute DELETE FROM counters...`). The
  legacy-adoption path (`migrate.py:48-53`: stamp baseline if `nodes` exists without
  `alembic_version`, then upgrade) is correct and tested
  (`test_migrations.py:test_legacy_store_is_adopted_and_upgraded`).
- **`render_as_batch=True`** in `env.py` is the right SQLite ALTER strategy and is used
  consistently in the migrations.

### Findings

**[low] `Edge` is fully dead.** Declared (`models.py:45-54`), created/indexed in
`0001`, never imported by either adapter or any service (verified: the only non-migration
reference is the class definition). The roadmap reserves it for entity-edges (item in the
backlog), which is a legitimate reason to keep it — but right now it's schema and code that
*looks* live. *Fix (decide now):* either (a) add a one-line `# RESERVED — not yet used; see
roadmap "Entity-to-entity edges"` on the class and leave it, or (b) drop it and re-add when
the feature lands. I lean (a) since it's already migrated and dropping/re-adding churns the
chain. Do **not** leave it un-annotated.

**[low] `Counter` table is single-purpose but generically shaped.** Only `(_note, note)`
is ever used post-0003. The `(scope, kind, prefix)` generality in `next_id` is vestigial
from the per-node-counter era. Not worth changing, but worth a comment that the only live
scope is `_note`.

**[low] `Node.schema_version` / `Node.version` are written but never read.** `version` is
set to 1 and never incremented after the `history`/commit-log was dropped in 0003;
`schema_version` is constant. They're harmless but are dead fields that imply an
optimistic-concurrency / versioning story that no longer exists. Either wire `version` into
edits (bump on `save_node`) or annotate them as reserved.

**[low] id/slug collision between entities and nodes is load-bearing and mostly handled.**
Promotion deliberately makes the thread node id == entity id (`entities.py:130`,
guarded by `entities.py:126` "a node already exists"). But `create_stream`/`create_entity`
both slugify independently and could mint the same slug in either order. E.g. a stream
"Rafia" and an entity "Rafia" both want `rafia`; if the stream exists, promoting the entity
will fail with "a node 'rafia' already exists" — acceptable, but the error surfaces late
(at promote time) rather than at entity-create time. Worth a note in the SKILL that entity
and stream/thread ids share a namespace.

---

## 3. Correctness & risks

### [blocker] Restore is a blanket un-delete, so overlapping removals corrupt on restore.
**Verified reproduction** (probe, `PROMOTION_THRESHOLD=1`):
1. `create_stream("recs")`, add a note tagging Rafia, `promote_entity("rafia","recs")` →
   thread node `rafia` lives under `recs`.
2. `delete_stream("recs")` → soft-deletes `recs` **and child `rafia`** (`streams.py:98-100`).
3. `delete_entity("rafia")` → soft-unlinks all tags + soft-deletes node `rafia`
   (`entities.py:188-190`).
4. `restore_stream("recs")` → restores `recs` **and all children including `rafia`**
   (`streams.py:110-111`), via raw `set_node_deleted(child.id, None)`.

**Result:** node `rafia` is visible again and appears as a child thread of `recs`
(`get_stream_view("recs")["children"] == ["rafia"]`), but the entity is correctly
derived-gone (tags still soft-unlinked, `list_entities() == []`). **An orphan thread node
with no live entity is now rendered in the stream view.** Restore resurrected a row that a
*different, still-in-effect* removal had deleted.

*Root cause:* `restore_stream`/`restore_note`/`restore_entity` all do an unconditional
`set_node_deleted(..., None)` / `set_tags_deleted_for_entity(..., None)` regardless of *why*
the row was deleted or whether another removal still owns its deletion. There's no notion of
"restore only what *this* rm deleted."
*Why it matters:* this is silent state corruption that a user can hit with a normal
sequence ("remove this stream… also stop tracking Rafia… actually bring the stream back").
It will get worse with assets (more cascade fan-out) and is exactly the kind of thing the
removal eval is supposed to guard but doesn't (the eval only tests *non-overlapping*
removals).
*Fix options (pick one):*
- **Tombstone the deletion cause.** Record *which operation* soft-deleted each row (a
  deletion-batch id, or a `deleted_by` discriminator), and restore only rows whose latest
  deletion matches the operation being undone. Most correct, most work.
- **Derive thread liveness from the entity, not a separate `deleted_at`.** A promoted
  thread node's liveness could be *derived* from its entity's link-liveness (like the
  entity itself is), so there's no independent node flag to desync. This collapses the
  whole class of bug for promoted threads. Recommended direction; aligns with the existing
  "derived" philosophy.
- **At minimum, guard the render:** in `get_stream_view`, drop child threads whose backing
  entity is derived-gone. Cheap band-aid, doesn't fix the underlying double-ownership.
*Add an eval scenario* for overlapping removals + restore order permutations.

### [high] `restore_entity` re-links *every* tag, including ones removed for a different reason.
`set_tags_deleted_for_entity(entity_id, None)` (`entities.py:200`) revives **all** soft-
unlinked tags for the entity. If a tag was soft-unlinked by a *prior* `entity rm` that was
intentionally not restored, or (future) by any other path, restore over-revives. Today the
only producer of soft-unlinked tags is `entity rm` itself, so the blast radius is limited —
but it's the same blanket-restore design flaw as the blocker, on the tag axis. *Fix:* same
tombstone/scoping approach; or document that entity restore is "revive the last rm" only.

### [medium] `next_id` read-modify-write is not concurrency-safe; counters never reset.
`next_id` (`sqlite.py:208-215`) does `get` → `+1` → `add`. Two concurrent writers (two
Claude sessions, or CLI + MCP) on the same store can both read `next=N` and both mint
`note-(N+1)` → PK collision on the second commit (one transaction fails — at least it
*fails* rather than silently dups, thanks to the PK, but it's an ungraceful error).
SQLite's default isolation + `busy_timeout` mitigates but doesn't eliminate this for the
read-then-write pattern. *Why it matters:* the install registers the MCP server **user-
scope** (every session) pointed at one `~/.pensieve`, and the CLI hits the same store — so
two-writer is a real configuration, not hypothetical. *Fix:* either accept single-writer
and **document it loudly**, or make id allocation atomic (`UPDATE counters SET next=next+1
... RETURNING next`, or a `BEGIN IMMEDIATE`). Low urgency (personal store) but record the
assumption now, before assets add more write paths.

### [medium] The once-per-process migration guard assumes the store doesn't change underneath.
`migrate.py:31,44-54` caches "this url was migrated" in a process-global `set`. Correct for
a long-lived MCP server. But: if a migration is added while an MCP server is running, the
server won't pick it up until restart (the guard short-circuits). Also, the guard is keyed
on `db_url`, and `get_settings()` is re-read per call, so an env change mid-process to a new
`PENSIEVE_HOME` correctly re-migrates the new url — good. The risk is only the "new
migration, old running server" case. *Fix:* fine as-is for a local tool; just note it
("restart the MCP server after upgrading Pensieve" — the install.sh editable-install story
makes code live but not this).

### [medium] FK ordering relies on manual `flush()` and is fragile.
Because models carry **no ORM relationships** (by design — "dumb data holders"), the UoW
won't order inserts; the adapter compensates with explicit `self._session.flush()` before
inserting FK rows in `attach` (`sqlite.py:114-119`) and `tag_note` (`sqlite.py:152`). This
works and is commented, but it's a **latent trap**: any new FK-bearing primitive (assets
will add one) must remember to flush, or it'll fail only against SQLite (with `foreign_keys=
ON`) and pass against the memory adapter — i.e. unit tests won't catch it. *Why it matters:*
the assets feature is next and will add a new association table. *Fix:* centralize the
"flush before FK insert" expectation (a helper, or a comment-checklist in `base.py` for
adapter authors), and ensure the conformance test (§1) exercises add-then-reference in one
UoW.

### [low] `get_stream_view` child `count` counts covered + uncovered notes.
`streams`/content `get_stream_view` reports `count: len(notes_for(c.id))` for each child
thread (`content.py:241`). That's the full attached count, which is the right number for a
thread (a thread covers nothing). Consistent — flagging only to confirm it's intentional:
the parent's *loose* list is filtered by `_covered`, but the child counts are raw. Fine.

### [low] `_covered` is correctly scoped to *this* node's children — verified.
`_covered` (`content.py:247-257`) hides a note from a stream's loose list only if **every**
tagged entity is promoted to a thread **under this node** (`entity.node_id in child_ids`).
The cross-stream test (`test_cross_stream_promotion_does_not_hide_in_other_stream`) confirms
a note isn't hidden in stream B just because its entity has a thread under stream A. Good,
no action.

### [low] `untag_note` detaches from the thread even when the note is multi-homed there.
`untag_note` (`content.py:110-122`) detaches the note from the promoted entity's thread
node. If the same note reached that thread by *two* tags (two entities both promoted to the
same parent — rare) or was independently attached, the detach is unconditional. Edge case;
the inverse-of-tag intent is right for the common path. Note it; don't fix yet.

---

## 4. Surface coherence (CLI ↔ MCP ↔ SKILL)

### GOOD — preserve
- **Parity is tested, not just asserted.** `test_mcp.py:EXPECTED_TOOLS` pins the exact MCP
  tool set ("nothing missing, nothing stray"). The CLI mirrors the same ops grouped by
  noun.
- **Storage terms are tested for non-leakage.** `test_cli.py:53,59` and
  `test_mcp.py:219` assert `"node" not in output`. Error translation in both surfaces maps
  `NodeNotFound` → "No stream '…'". This directly serves the user's stated "no leaked
  internal terms" preference.
- **The flows-vs-ops split is principled and documented** (`docs/verbs.md §0a`): `capture`/
  `fetch` live only in SKILL; the engine exposes only mechanical ops. The MCP tool is named
  `add_note` (not `capture`) deliberately. This is good discipline.

### Findings

**[medium] CLI verb vs MCP verb naming is inconsistent in a user-visible way.** CLI uses
`stream rm` / `note rm` / `entity rm` and `... restore`; MCP uses `remove_stream` /
`restore_stream`; SKILL speaks `remove`. The CLI `rm` vs MCP `remove_*` is a deliberate
Unix-CLI nod, but the docs (`cli.md`) and SKILL should make explicit that they're the same
op so the agent doesn't think `rm` and `remove_*` differ. Minor, but the user explicitly
values a coherent noun-verb surface. *Fix:* one line in `cli.md` mapping `rm`↔`remove_*`.

**[medium] CLI `entity rm` help text contradicts the implemented semantics.**
`cli/main.py:367-369` help says: *"Purges the notes about it; notes that were only about
this entity (and the entities riding only those notes) go too."* But `delete_entity`
**never deletes a note** (it unlinks) — this is the whole point of the redesign, correctly
implemented (`entities.py:176-191`) and correctly described in the MCP docstring
(`mcp_server.py:305-309`) and SKILL. The CLI help is **stale from a previous removal model**
and actively misleading. *Fix:* rewrite the CLI `entity rm` help to match (unlink, never
delete a note; reversible).

**[low] `find` CLI dedups promoted entities against node ids, but `--type entity` does not.**
`cli/main.py:124-128` skips an entity row if its id is already in `node_ids`, so a promoted
entity shows once (as its thread). With `-t entity` there's no node search to dedup against,
so it surfaces as an entity (tested, `test_find_dedups_promoted_entity`). Intentional and
fine; flagging for awareness.

---

## 5. Tests & evals

### GOOD — preserve
- **Two-layer test strategy is sound:** unit tests run services against the memory adapter
  (fast, guards decoupling); integration tests run the same services against real SQLite
  (durability), plus a real CLI runner and a **real MCP stdio subprocess** round-trip.
  That MCP subprocess test is excellent — it proves the actual agent-facing path.
- **The removal eval is a strong invariant pinner** for the bottom-up model: cross-stream
  survival (A,B), unlink-not-delete (C), the cascade (D), promoted-entity rm+restore (E).
- **The capture/fetch eval is honest about scope** (`evals/capture_fetch.py:8-13`): it
  states it's a *scripted agent*, not a test of whether a real agent chooses right. Good
  epistemic hygiene.

### Findings (gaps)

**[high] No test covers overlapping removal + restore** — the exact gap that hides the
blocker in §3. Every removal scenario in `evals/removal.py` and the service tests removes
*one axis at a time* and restores it in isolation. *Fix:* add scenarios: (stream rm + entity
rm) then restore in both orders; (note rm + entity rm) then restore note; restore-after-
partial-overlap. These will fail today against the blocker and should drive its fix.

**[medium] No adapter-conformance test** (see §1). The two adapters are tested
*independently* (memory via unit, sqlite via integration) but never *against each other*.

**[low] Restore-fidelity not asserted at the tag level.** `test_delete_entity_with_thread_
then_restore` checks count returns to 2, but doesn't assert that restore touched *only* the
tags this rm removed. Tie this to the §3/§1 fixes.

**[low] `_isolate_engines` + `reset_migration_cache`** are correctly used in integration
conftest, but the **evals** mutate `os.environ["PENSIEVE_HOME"]` globally and call
`reset_engines()` without restoring the prior env. Harmless for a throwaway process run,
but if anything ever imports an eval into a test process it'd leak env. Low risk.

**[low] No test pins `find_entities`/`list_entities` ordering** beyond name sort; fine.

---

## 6. Maintainability

### GOOD
- Docstrings are unusually good — most modules explain *why*, not just *what* (e.g.
  `base.py` header, `memory.py` clone rationale, the `flush()` comments). Preserve this
  standard.
- Errors are storage-agnostic and shared (`errors.py`); surfaces translate them. Clean.
- `slug.py` is tiny, correct, and shared by streams + entities (one slug law).

### Findings

**[medium] Docs are a mix of current and superseded/aspirational, without a clear "start
here".** `docs/handoff.md` (the file currently modified in git) still describes the
**pre-build** design: `todos`, `flavor`, `supersedes`, a `history`/commit-log,
`add_todo`/`complete_todo`/`promote_entry`/`redact` ops, a diff envelope. None of that is in
the shipped engine (0003 dropped history/todos/flavor/supersedes; there are no todo/edge
ops). `docs/verbs.md` likewise documents an op catalog (`create_node`, `add_edge`,
`reparent`, `promote_entry`, `redact`, `supersede`) that **does not match** the actual
service/MCP surface. `spec_diff_format.md`/`spec_stream_layout.md` are correctly marked
SUPERSEDED, but `verbs.md` and `handoff.md` are *not* marked stale and read as current.
*Why it matters:* these are the first things a newcomer (or a future you, or an agent asked
to extend Pensieve) will read, and they describe a system that isn't there. *Fix:* add a
banner to `verbs.md`/`handoff.md` ("describes the pre-build graph-op design; the shipped
surface is the MCP tools / CLI — see `cli.md` and SKILL"), or fold the still-true judgment
rules into the SKILL and archive the rest. `glossary.md` and `cli.md` *are* current — make
the doc map point there as the source of truth.

**[low] Duplicate `_utcnow()`** defined in `models.py:22`, `content.py:42`, `entities.py:34`
(and inline in `streams.py:82,97`). Trivial; consider one shared helper. Not urgent.

**[low] `SCHEMA_VERSION = 1` in `models.py:19`** is imported and stamped onto nodes but,
like `Node.schema_version`, never consulted. Dead-ish.

**[low] `.mcp.json` (repo, `poetry run pensieve-mcp`) vs `install.sh` (user-scope,
`$PIPX_BIN/pensieve-mcp`)** are two different registrations of the same server with
different store resolution. Intentional (repo = dev store via `.env`; user = `~/.pensieve`)
and documented in `install.sh` comments — but it's a subtlety worth one line in a README so
a future contributor doesn't "fix" the apparent duplication.

**[low] `get_settings()` builds a fresh `Settings` every call** (`config.py:54-56`) and is
called per-`_view` inside loops (`entities.py:207`). The `cached_property` on `db_path`/
`db_url` is per-instance, so a fresh instance per call re-reads env each time — correct for
test isolation, mildly wasteful in `list_entities` (one settings build per entity). Cache
the threshold lookup outside the loop. Micro.

---

## Prioritized pre-refactor checklist

### Fix BEFORE the next feature phase (assets / search)
1. **[blocker] Fix blanket-restore corruption** (§3). Pick the scoping approach (recommended:
   derive promoted-thread liveness from the entity rather than an independent `deleted_at`,
   or tombstone the deletion cause). Drives item 2.
2. **[high] Add an overlapping-removal + restore eval/test suite** (§5) — both orders,
   both axes — to lock the fix and prevent regression when assets add cascade paths.
3. **[high] Add an adapter-conformance test** parametrized over both UoW factories (§1),
   covering the liveness/restore primitives. Do this before assets adds a new FK table.
4. **[high] Fix the stale `entity rm` CLI help text** (§4) — it claims notes are purged; they
   are not.
5. **[medium] Centralize / document the "flush before FK insert" rule** (§3) so the new
   assets association table doesn't reintroduce the SQLite-only FK trap.
6. **[low–medium] Annotate or remove dead schema/fields:** `Edge` (mark RESERVED), `Counter`
   generality, `Node.version`/`schema_version`/`SCHEMA_VERSION` (§2, §6). Cheap clarity before
   piling on.

### Later / nice-to-have
- **[medium] Decide and document the single-writer assumption** (or make `next_id` atomic) (§3).
- **[medium] Doc hygiene:** banner the superseded/aspirational docs (`verbs.md`, `handoff.md`);
  point the doc map at `glossary.md` + `cli.md` + SKILL as current truth (§6).
- **[low] CLI↔MCP verb-naming note** (`rm` ↔ `remove_*`) in `cli.md` (§4).
- **[low] De-dupe `_utcnow`; cache threshold in `list_entities` loop** (§6).
- **[low] One-line README note** on the two MCP registrations / store resolution (§6).
- **[low] `untag_note` multi-home detach** edge case — revisit only if it bites (§3).

### Explicitly GOOD — do not regress during refactor
- The ports/adapters boundary (no SQL in services; sqlite is the only `Session` importer).
- The in-memory adapter as a real, transaction-honoring, cloning second backend.
- The derived-entity liveness model and the bottom-up removal semantics.
- CLI/MCP/SKILL parity + the no-leaked-`node` error translation (and its tests).
- The MCP stdio subprocess integration test.
- The migration chain + legacy-adoption path.
- The quality of module docstrings.
