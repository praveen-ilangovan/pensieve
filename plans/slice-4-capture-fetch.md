# Slice 4 — Capture & Fetch (the heart)

> **Status:** planned · **Date:** 2026-06-26 · **Depends on:** slices 1–3 (CLI + MCP +
> install), `docs/verbs.md` (ops + R1–R9 + §3b promotion), `docs/glossary.md` (model).
> **The make-or-break slice:** the first time content lands under a stream and round-trips
> across sessions. Streams alone are empty shells; this is what makes them mean something.

---

## 1. Goal & the demo (acceptance)

A user can **add content to Pensieve in one session and pull it back in another**, with the
agent doing all the structural work and the user only approving.

**Acceptance scenario (must pass end-to-end, two separate sessions):**

1. **Session A** — user: *"add this to pensieve: we're talking to 4 curators — Rafia,
   Travis, Violet, Raja. Rafia postponed her call, now Tuesday."*
   - Agent loads the stream index, **proposes** the `recs` stream, user approves.
   - Agent writes notes onto `recs` (incl. *"Rafia postponed call → Tue 2026-06-30"*,
     relative date pinned per R6).
2. **Session B (fresh, zero prior context)** — user: *"what's in recs?"*
   - Agent fetches the `recs` thin view and shows those notes back, dates intact.

If both legs work against `~/.pensieve` (global) and `.local/manual` (dev), the slice ships.

---

## 2. Scope

**In (this slice):**
- **Capture** as a user verb (*"add this to pensieve [under X]"*) → agent proposes
  placement → user approves → content persisted as **note(s) on the chosen stream node**.
- **Fetch** as a user verb (*"what's in pensieve / in recs"*) → the stream **thin view**
  (identity + purpose + its notes), readable in a different session.
- The three primitive ops the above need: `add_note`, `get_stream` (thin view),
  `list_streams` (the routing index — already exists).
- Vertical surface, same discipline as slices 1–3: **services + CLI + MCP + tests**, plus
  a **minimal** capture/fetch pass in the Claude skill.
- A **deterministic evaluator** (throwaway DB) that scripts the acceptance scenario
  end-to-end through the engine (empty → create → list → add_note onto new/existing/
  specified stream → fetch) and asserts outcomes — the **regression gate**. *(It proves
  the engine **supports** each path; the agent-in-the-loop eval against the live MCP —
  proving the agent **chooses** right — is a staged follow-on, not this slice.)*

**Out (explicit non-goals — each is its own later slice):**
- **Promotion / per-entity counters** (verbs.md §3b). Needs entity tagging + a reference
  tally → separate slice. *(Correction: the existing `Counter` table is id allocation, not
  reference counts — see §6.)* Capture here just appends notes; everything stays a note.
- **Contained nodes ("threads")** — notes hang on the **stream node itself**; no child
  nodes yet (lazy, per R5).
- **`apply_diff` + the diff envelope + dry-run preview** (verbs.md §1). Slice 4 calls the
  **primitive ops directly**; the approval gate here is *conversational* (agent states what
  it'll write, user says yes), not the `apply_diff(dry_run)` preview. Batching N ops into
  one atomic commit comes with `apply_diff`.
- **MCP resources (`stream://<id>`)** — fetch is a **tool** (`get_stream`) this slice,
  matching the existing tool pattern; migrating reads to resource URIs is a follow-on.
- **Todos** — notes only this slice (`add_todo` is a symmetrical fast-follow).
- **Edit ops** (`complete_todo`, supersede handling, `reparent`) — schema supports
  `supersedes`, but capture v1 only appends.

---

## 3. Architecture (where it plugs in)

Unchanged path, one new service module:

```
agent ── MCP (mcp_server.py) ──┐
                               ├─► services.content ─► models (Note/History/Counter) ─► SQLite
user ── CLI (cli/main.py) ─────┘   services.streams (get_stream/list_streams for routing)
```

The **agent judges** (route, propose, get approval); the **engine mutates** (allocates ids,
writes the note + history row atomically). No direct DB access from CLI/MCP — both go through
services, as today.

---

## 4. Engine work

### 4a. ID allocation — wire up the `Counter` table (first use)

The `Counter` table exists (`scope`, `kind`, `next`) but nothing uses it yet. `Note.commit_id`
is **non-nullable**, so we must mint ids. New helper in `services/` (e.g. `services/ids.py`
or inside `content.py`):

```python
def next_id(session, scope: str, kind: str, prefix: str) -> str:
    """Atomically allocate the next non-reusing id, e.g. note-1, c1."""
    # SELECT counter row FOR scope/kind (create at next=0 if absent); n = next; next += 1;
    # return f"{prefix}{n}".  Runs inside the caller's transaction.
```

- commit id: `scope="_commit", kind="commit"` → `c<n>`
- note id: `scope=<node_id>, kind="note"` → `note-<n>`

WAL + `busy_timeout` pragmas are already installed; single-writer SQLite makes the
read-modify-write safe within one transaction.

### 4b. `services/content.py` (new)

```python
def add_note(node_id, text, *, flavor=None, supersedes=None, session_id=None,
             summary=None) -> Note:
    """Append a note to a node (the stream), as one atomic commit:
       1. assert node exists (raise NodeNotFound otherwise)
       2. commit_id = next_id(_commit/commit, 'c'); note_id = next_id(node/note, 'note')
       3. insert Note(node_id, note_id, text, flavor, supersedes, date=utcnow, commit_id)
       4. write History row (commit_id, version=node.version+1, session=session_id, summary)
       5. bump node.version, node.updated
       all in one transaction."""

def get_stream_view(node_id) -> dict:
    """The thin view: identity + notes (+ forward-compat empty children/todos).
       { id, label, kind, purpose, notes: [{id, text, flavor, date}],
         todos: [], children: [] }  # todos/children populated by later slices
       Raise NodeNotFound if missing."""
```

- `flavor` validated against `decision | outcome | observation` (or None).
- Reuse `streams.PensieveError`; add `NodeNotFound(PensieveError)`.

### 4c. `services/streams.py` (touch)

- Add `get_stream(node_id) -> Node | None` (lookup used by routing/fetch). `list_streams`
  already gives the routing index.

---

## 5. CLI (`cli/main.py`)

```
pensieve add <text> --stream <id> [--flavor decision|outcome|observation]
    → services.content.add_note → "✓ added note-N to <stream>"
    → error if stream missing (exit 1), mirroring `create`'s StreamExists handling

pensieve show <stream>
    → services.content.get_stream_view → render: header (label · purpose) then notes
      newest-last, each "note-N [flavor] <text>  (date)"; "(empty)" if none
```

*(`show` is the CLI face of fetch; keep the name `show`.)*

---

## 6. MCP (`mcp_server.py`)

Two new tools (reuse services, like slice 2):

```python
@mcp.tool()
def add_note(stream: str, text: str, flavor: str | None = None) -> dict:
    """Append a note to a stream. Use only after the user has approved placement.
       'stream' is the stream id (from list_streams). 'flavor' optional."""

@mcp.tool()
def get_stream(stream: str) -> dict:
    """Fetch a stream's thin view: identity, purpose, and its notes. Use for 'what's
       in <stream>' / resuming."""
```

- `list_streams` (exists) is the **routing index** the agent loads before proposing.
- Tool docstrings must steer the flow: *load index → propose → on approval add_note*;
  *get_stream to recall*. (The judgment lives in the skill, §7.)

> **Note on reference counts:** when the promotion slice lands, `add_note` is the natural
> place to also bump the per-entity tally (§3b) — but that needs the agent to pass the
> entities it referenced, which is out of scope here. Don't fake it now.

---

## 7. Skill (`adapters/claude/SKILL.md`) — minimal capture/fetch pass

Add behavior (not the full playbook reframe — that's a separate fold from `verbs.md`):

- **"add this to pensieve [under X]"** →
  1. call `list_streams` (the index);
  2. **propose** placement: an existing stream if one fits; **a new stream** (confirm
     name + one-line purpose, then `create_stream`) if none do; honor an explicit stream
     if named;
  3. on user approval, call `add_note` (pin relative dates to absolute, per R6);
  4. confirm what was written, briefly.
- **"what's in pensieve / in <stream>"** → `get_stream`, render the thin view tightly.
- Keep the friction discipline: propose once, don't interrogate; everything stays a note
  (no promotion talk yet).

> Flag in the skill that this is the **first capture/fetch pass**; the full R1–R9 + §3b
> playbook fold (and the pre-graph PLAYBOOK.md reframe) follows.

---

## 8. Tests (mirror existing layout)

**`tests/unittests/test_content.py`** (new):
- `add_note` allocates `note-1`, `note-2`, … per node; bumps `node.version`; writes a
  History row with the commit id.
- commit ids are global + non-reusing (`c1`, `c2` across different nodes).
- `add_note` on a missing node → `NodeNotFound`.
- invalid `flavor` rejected.
- `get_stream_view` returns notes in order with ids/dates; `(empty)` shape when none.

**`tests/integrations/test_cli.py`** (extend): `create` → `add` → `show` round-trip; `add`
to a missing stream exits non-zero.

**`tests/integrations/test_mcp.py`** (extend): `add_note` then `get_stream` returns it;
`get_stream` on a missing stream errors cleanly.

Round-trip across sessions is inherent (same SQLite file) — the integration tests prove it
by reading in a fresh service call. Keep ruff + mypy clean; all green before commit.

---

## 9. Build order (vertical sub-steps)

1. `next_id` helper + `NodeNotFound` + `content.add_note` + unit tests. *(engine core)*
2. `content.get_stream_view` + `streams.get_stream` + unit tests.
3. CLI `add` / `show` + CLI integration test.
4. MCP `add_note` / `get_stream` + MCP integration test.
5. Deterministic evaluator — scripts the §1 scenario through the engine on a throwaway DB.
6. Skill capture/fetch pass.
7. Live verify the §1 demo across two sessions (dev store + global), then commit/push.
   - ✅ **`install.sh` dependency drift fixed** (found in chunk 4): when the venv already
     exists on the right Python, the script now **re-syncs deps in place**
     (`pipx runpip pensieve install -q -e .`) instead of skipping — so new deps (e.g.
     `alembic`) are picked up without recreating the venv (keeps the no-recreate
     optimization; falls back to `--force` recreate if the re-sync fails). Syntax-checked;
     full exercise happens on the chunk-7 reinstall.

---

## 10. Open questions (resolve as they block)

- **One capture = one note or many?** The example is 2 notes. This slice does one note per
  `add_note` call (one commit each); true multi-note-in-one-commit waits for `apply_diff`.
  Acceptable for the demo?
- **History granularity** — write a History row per `add_note` now, or defer provenance
  until `apply_diff`? Leaning **write it now** (cheap, and the schema wants `commit_id`).
- **Thin-view rendering** — how terse? Start minimal (notes only); enrich when todos /
  children exist.
- **Reference counting is a separate later slice**  (entity tagging + tally + promotion
  trigger; none needed for the round-trip demo). Slice 4 adds **no** counter state, so
  there is nothing structural to remove when it lands — only captured note data in the
  dev store, which we clear + re-capture. **Decision to make then, flagged now:** the
  per-entity tally should be **derived/recomputable from notes' entity tags**, not an
  incrementally-maintained live counter — so it can't drift, and pre-promotion notes are
  *backfillable* rather than poison. Don't design an incremental counter that makes
  Slice 4 data unusable.

---

## 11. Progress log

> Updated as we build (this is the resume anchor — no separate handoff).

- **Chunk 1 — engine core (`next_id` + `NodeNotFound` + `content.add_note`)** — ✅ done.
  `services/content.py` + `tests/unittests/test_content.py` (6 tests). Wired the `counters`
  table for the first time (1-based: `c1…` global commits, `note-1…` per node); each
  `add_note` is one atomic commit (note + history row + version bump). Suite 12 green,
  ruff + mypy clean.
- **Refactor (pre-chunk-2) — repository layer (light) + Unit of Work** — ✅ done.
  Introduced the storage **port** (`repository/base.py`: `Repository` + `UnitOfWork`) with
  **two adapters**: `repository/sqlite.py` (the only module that imports `Session`/engine)
  and `repository/memory.py` (in-memory; doubles as the test fake, honours commit/rollback
  via copy-on-enter). Services are now injected classes — `StreamService` / `ContentService`
  taking a `uow_factory`, with **zero** SQL/Session imports; shared errors moved to
  `errors.py`; composition root in `factory.py`. Call sites (CLI, MCP, quick_run) build via
  the factory. New `test_services_in_memory.py` (3 tests) **proves the decoupling** — the
  same services run with no SQLite. Suite **15 green**, ruff + mypy clean, CLI smoke ✓.
  *(Decision: light over full hexagonal — SQLModel models stay as entities; light is a
  strict prefix of full, upgradeable if we ever move to a graph DB. See chat + §10.)*
- **Chunk 2 — read side (`get_stream` + `get_stream_view`)** — ✅ done. Added `notes_for`
  to the port + both adapters (chronological), `StreamService.get_stream`, and
  `ContentService.get_stream_view` (thin view: identity + purpose + notes; `todos`/
  `children` present-but-empty for later slices; raises `NodeNotFound`). Unit tests on the
  fake (view shape/order/empty/missing, `get_stream`) + an integration **capture→fetch**
  round-trip through a fresh service. Suite **23 green**, ruff + mypy clean.
- **Chunk 3 — CLI op surface (`add` / `show`)** — ✅ done. `pensieve add <text> -s <stream>
  [-f flavor]` and `pensieve show <stream>` (renders identity · purpose + notes, `(empty)`
  when none); both exit 1 on a missing stream. CLI integration tests: add→show round-trip,
  empty view, missing-stream errors. Suite **27 green**, ruff + mypy clean, smoke ✓.
  *(Naming locked: CLI/MCP speak **ops** (`add`/`add_note`); `capture`/`fetch` are **flows**
  that live only in the skill — see new `verbs.md §0a "Flows vs ops"`.)*
  - **Help polish:** cleaner one-line command summaries, per-command `Example:` lines, a
    `Flavor` enum so `--flavor` shows `[decision|outcome|observation]` + validates at the
    CLI boundary, one-line "Typical flow" epilog (Typer collapses multi-line epilogs).
  - **Vocabulary fix:** CLI translates internal `NodeNotFound("No node …")` → user-facing
    **`No stream '<id>'`** (presentation layer hides the graph term `node`; service keeps
    it). Tests assert "node" never leaks. Same translation to apply at the MCP layer.
- **Migrations infrastructure (Alembic) — introduced before chunk 4** — ✅ done.
  Schema is now **owned by Alembic** (mirrors recs-app). Migrations live *inside* the
  package (`src/pensieve/migrations/`) so they ship with the pipx install; `env.py` pulls
  the URL from `PENSIEVE_HOME` and uses `render_as_batch=True` (SQLite ALTERs). New
  `database/migrate.py` runs `upgrade head` **programmatically from `init_db`** (guarded
  once-per-store-per-process) → the installed CLI/MCP **self-migrate** on first use, no
  manual step. **Legacy stores** (pre-migration `create_all` DBs, e.g. the existing
  `~/.pensieve`) are detected (`nodes` exists, no `alembic_version`), **stamped at
  `0001_initial`, then upgraded** — data preserved, never wiped. Migrations: `0001_initial`
  (full schema) + `0002_provenance`. `create_all` removed from the runtime path; mako
  template patched to `import sqlmodel`. Makefile: `make migrate` / `make migration m=…`.
  Tests: fresh-store migrates to head; legacy-store adopted+upgraded with data intact.
  *(Decision: proper migrations now rather than an ad-hoc column guard — schema will keep
  changing; nothing saved by delaying. User call.)*
- **Chunk 4 — MCP tools (`add_note` / `get_stream`) + commit provenance** — ✅ done.
  MCP now exposes the full op set: `list_streams`, `create_stream`, `add_note`,
  `get_stream`. `add_note` records **provenance**: `actor` = the MCP **client name from
  `initialize`** (e.g. `claude-code`) + `interface="mcp"`; the CLI tags `actor="cli"`.
  Provenance lives on the **commit** (`History`); `Note.commit_id` links the chain.
  Friendly-vocabulary translation extended to MCP (`NodeNotFound` → `No stream '<id>'`,
  no `node` leak). Tool docstrings steer the agent (do the routing/approval, then call
  `add_note`). Tests: MCP stdio roundtrip (create→add→get), **client-recorded-as-actor**,
  friendly missing-stream error. Suite **32 green**, ruff + mypy clean.
  *(Heads-up: a stale global pipx install predates the `alembic` dep — reinstall via
  `./install.sh` / `pipx reinstall`, or use `poetry run pensieve`, before bare `pensieve`.)*
- **Chunk 4 add-on — commit provenance (`actor` + `interface`)** — ✅ folded into chunk 4
  (above) and the `0002_provenance` migration. Provenance
  lives on the **commit** (`History`), not per-note (`Note.commit_id` already links the
  chain). Add `actor` + `interface` to `History`: CLI tags `actor="cli"`; MCP tags the
  **client name from `initialize`** (e.g. `claude-code`) — the agent-agnostic "who created
  it" captured automatically. Keep it to these 1–2 fields now; the commit is the stable
  home as it gets richer later (agent version, model, confidence…). Note ids stay
  **per-node** (commit ids global) — confirmed intentional.
- **Chunk 5 — deterministic evaluator** — ✅ done. `evals/capture_fetch.py` (+ `make eval`):
  spins up a throwaway store and drives the engine through the §1 scenario — empty →
  create streams → list → the three capture *outcomes* (new / existing / explicit stream)
  → fetch round-trip via a fresh service → missing-stream raises. Prints ✓/✗ per check,
  exits non-zero on failure (regression gate). Honest scoping in the docstring: it proves
  the engine **supports** each path (scripted-agent target choice); the agent-in-the-loop
  eval (does the agent **choose** right, vs live MCP) is the staged follow-on. Guarded
  from bit-rot by `tests/integrations/test_eval.py` (subprocess, asserts clean exit).
  **9/9 checks pass; suite 33 green.**
- **Chunk 6 — the skill (capture/fetch flows)** — ✅ done. `adapters/claude/SKILL.md`
  extended from list/create into the full brain layer: **capture** ("add this to
  pensieve" → filter durable state → `list_streams` → propose placement (existing / new /
  explicit) → approve → `add_note`, pinning relative dates) and **fetch** ("what's in
  <stream>" → `get_stream`, render tightly). Encodes the vocabulary rule (speak
  streams/notes, never node/edge/thread; translate leaked "node"→"stream"), the
  flows-vs-ops distinction (calling `add_note` ≠ capturing), friction discipline
  (propose once, surface ambiguity), and notes-only-for-now with a banner that R1–R9 +
  counter-promotion follow. *(Goes live after a reinstall — chunk 7.)*
- **Chunk 7 — live verify** — ✅ PASSED → **Slice 4 COMPLETE.** Reinstalled the global
  (the `install.sh` dep re-sync pulled in `alembic`); new skill + MCP tools loaded;
  `~/.pensieve` auto-migrated. Verified live across **three independent sessions**:
  capture proposed a new `recs` stream (approved → created + first note); a later session
  captured an email thread + WhatsApp exchange into **3 flavored notes** (filter held,
  flavors right, "next Tuesday"→`Jun 30` pinned, date conflict **surfaced not guessed**,
  routed into existing stream); a third fresh session recalled "what about Rafia" with
  full coherent cross-session recall. The core promise — capture in one session, fetch in
  another — works end-to-end with `actor=claude-code` provenance.
- **What live use surfaced → next slice.** Real data already exhibits the promotion
  signal: **Rafia recurs** across notes (her own status/activity) — exactly §3b's trigger;
  "what about Rafia" currently scans all of `recs` and filters, which a Rafia **node**
  would turn into a direct lookup. Mild **note accumulation** (two notes touch the same
  meeting/date) wants the **supersede/condense** edit layer. => **Next slice: counter-driven
  note→node promotion + edit ops** (the data is asking for it).
- **Test taxonomy — aligned to recs-app** — ✅ done. Split into per-layer conftests (no
  root conftest, like recs-app): `unittests/conftest.py` (a `services` fixture on the
  **in-memory adapter** — no DB) and `integrations/conftest.py` (`integration_store` +
  engine isolation). Unit service tests (`test_streams`/`test_content`) now run pure on the
  fake (**11 tests, 0.01s**); added `integrations/test_services.py` — both services against
  **real SQLite**, class-per-service like recs-app's `test_auth_service.py`, reading back
  through a fresh service to prove durable persistence (**7 integration tests, 0.58s**).
  Removed the redundant `test_services_in_memory.py`. Suite **18 green**. *(Tests are
  excluded from ruff/mypy by the project's pre-commit config — convention, not a gap.)*
