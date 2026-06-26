# Pensieve — Core Concept

> **Status:** design / pre-implementation · **Version:** v0.6 · **Date:** 2026-06-27
>
> This document captures both the *design* and the *reasoning that produced it* —
> deliberately, because the journey is as interesting as the destination.

---

## 1. One line

**Pensieve is a manually-triggered, multi-stream cognitive-state system.** It
routes a working session into persistent *domain* streams on the way out, and
gives an agent *lazy, on-demand* access to chosen streams on the way in.

It is **not** chat history. It is **not** a notes app. It is a **routing system**
that converts conversation into structured, persistent cognitive state across the
several domains a person actually works in.

A useful one-line framing: **version-controlled, domain-partitioned working
memory for humans + agents.** It borrows from Git (diffs and commits), from
knowledge graphs (streams as domains), and from the agent ecosystem (MCP as the
interface).

---

## 2. Where it comes from

Pensieve is the natural evolution of two small skills already in daily use:

- **`wrap-up`** — at the end of a session, write a summary, *keyed to the current
  repo and the day*.
- **`hydrate`** — at the start of a session, load the latest summary *for the
  current repo*.

These work, but they bake in two assumptions that don't match how work actually
happens. Pensieve breaks both:

| `wrap-up` / `hydrate` assumption | Pensieve |
| --- | --- |
| Memory is **keyed to a repo** | Memory is keyed to a **domain** (a "stream") that may span many repos, or none |
| A session collapses into **one flat dated blob** | A session **fans out** into multiple streams, routed by meaning |
| Reading **dumps the whole summary** into context | Reading is **lazy** — load a thin index, fetch detail on demand |

The heartbeat is identical to the originals: **manual write at the end, manual
read at the start.** Everything else generalizes.

---

## 3. Core principles

1. **Always user-triggered.** No continuous extraction, no background daemon, no
   "smart" auto-capture. The user invokes it. This is a deliberate preference,
   not a limitation to fix later.
2. **Multi-stream, not session-based.** A person works across several domains at
   once. Memory must too.
3. **Routing, not storage.** The value is in *where information goes*, not that
   it's saved.
4. **Streams are deliberate.** A stream is created only by explicit user choice
   (or repeated, confirmed cross-session relevance). Prefer **fewer, stronger
   streams** over many thin ones. Anti-fragmentation is a first-class rule.
5. **Lazy by default.** Fetching gives the agent *access*, not a context dump.
6. **Judgment and mutation are separated.** The agent decides; the engine
   commits. (See architecture.)
7. **Friction at the end is the make-or-break.** Everything hinges on the moment
   the user runs `capture`. If it's long, repetitive, or interrogative, they stop
   doing it and the elegance is worthless. **Questions are the exception;
   approval is one glance.** Friction must scale with *uncertainty*, not be a
   fixed ritual.
8. **Prevent entropy, but plan to repair it.** Deliberate stream creation slows
   drift; it doesn't stop it. The data model must never *block* later
   refactoring (split / merge / rename), even though the refactoring UX is
   deferred.

---

## 4. Core abstractions

### 🧵 Stream

A **Stream** is a user-approved, persistent domain of work. Examples: `recs` (an
app in growth mode), `employment`, `writing`, `architecture-learning`.

> **⚠️ Graph reframe (post-v0.5).** The model described in §4–§6 below is the
> *earlier per-stream framing*. It has since been **generalized into a property
> graph** — the canonical model now lives in **`glossary.md`** (nodes · edges ·
> properties · kinds) and **`verbs.md`** (ops). Mapping: a stream → a top-level
> `subject` node; goals/loops/actions → `todo` contents; decisions/insights →
> `note`s (+`flavor`); references → `asset` child-nodes; context → `person`
> child-nodes; the hierarchy → a `contains` edge (`parent_id`). The sections below
> are kept for the *narrative*; **build from glossary + verbs.**

A stream has **two halves**:

1. **Durable references** — pointers the backend resolves *on demand*: repo
   paths, `CLAUDE.md`, files, links. (e.g. `recs` points at its repo + its
   `CLAUDE.md` + growth-strategy notes.)
2. **Evolving state** — a `purpose` (the enduring north-star, identity-level),
   plus a live projection of `current_focus`, `goals`, `open_loops`,
   `next_actions` and `suggested_reads`; append-only `decisions`, `insights`, and
   a compressed `history`; and a **`context`** bucket of tracked ongoing threads
   (each a mini-stream: a mutable one-line `status` + an append-only `updates[]`).
   The `context` bucket is the "you just know" memory — e.g. the current state of
   each person you're mid-thread with — surfaced as one-line statuses at fetch,
   with the full thread fetched only on demand.

> **`purpose` vs `goals`.** `purpose` is *why the stream exists* (enduring; rarely
> changes). `goals` are *what you're currently chasing* within it (transient).
> "Growth" is a **goal** of `recs`, never its purpose. The word "goal" lives only
> in the transient projection — where intuition already puts it.

A stream:

- is **explicitly created**, never auto-generated;
- **accumulates** long-term context across sessions;
- is updated **only** via an approved diff;
- has a **stable id, separate from its display name** — so a rename is free and
  refactoring is never blocked at the data layer;
- gives **engine-assigned ids** to projection items (`goal-`, `loop-`, `act-`) and
  log entries (`dec-`, `ins-`), so the diff closes/updates them **by id, not by
  re-matching free text**.

#### Fetching hints (`suggested_reads`)

Lazy loading has a real failure mode: the agent *doesn't fetch when it should*
and acts dumber than expected. To counter this without forcing context, the thin
`state` layer carries a short list of **likely next reads** — pointers the agent
is nudged (not forced) to follow:

```yaml
current_focus: growth experiments
open_loops: onboarding funnel unclear
suggested_reads:
  - stream://recs/notes              # recent notes
  - stream://recs/children           # people / assets / sub-efforts
```

### ⚡ The diff (unit of update)

The agent never edits stream files directly. At the end of a session it produces
a **diff** — a structured proposal of what changed, routed per-stream. The engine
**validates and applies** it. This narrow contract is the entire interface
between brain and engine:

> **The agent produces a diff; the engine validates and applies it.**

#### Git for streams (the logical model — resolves the parked fork)

We had a parked question: should a stream be an **event-sourced log** or a
**mutable state file**? The Git framing answers it — *both, at the right
granularity:*

- **Stream state = a mutable projection** (the "working tree"): the current
  `purpose` / `focus` / `goals` / `open_loops` / etc., always up to date.
- **Each committed diff = a commit**, retained in an **append-only history log**
  with **provenance** (which session produced it).

The diff-log *is* the event log — at **commit** granularity, not per-keystroke.
That buys auditability, provenance, and replay **without** the cost and
complexity of full event-sourcing. It also keeps later **merge/split**
refactoring tractable, because every change has a traceable origin.

> **Storage.** This is the *logical* model. Physically, v1 stores it in **SQLite**
> (see `spec_engine_contract.md`): the projection in tables, the logs as
> append-only rows, and **each commit as one SQLite transaction** — which is what
> makes the multi-part commit genuinely atomic and crash-safe, for free, rather
> than via hand-rolled file journaling. The agent never sees storage; it only sees
> the canonical model through the URI/diff contract.

---

## 5. The two flows (the whole product)

### ① `capture` — end of session (write)

`capture` is **one command run as two internal phases**. Splitting it keeps each
LLM pass simple and independently inspectable — instead of betting the whole
system on a single heroic pass that must understand *and* route *and* diff at
once.

**Phase A — "what happened?"** (no stream knowledge required)
- Read the session and produce a **session digest**: a set of **atomic signals**
  — decisions, tasks, shifts, insights, open questions.
- This is generic and portable. (These signals are the "events" of earlier
  drafts — given their correct home as a *transport* artifact between A and B,
  not as a storage model.)

**Phase B — "where does it go?"** (the only stream-aware part)
1. Load the registry of existing streams (identities/summaries only — cheap).
2. **Route** each signal from the digest to one or more streams.
3. Surface **routing ambiguities** — *only when confidence is low*: "this could
   be `recs` *or* `employment` — which? or both?"
4. **Propose new streams** only when something clearly doesn't fit *and* looks
   persistent — user confirms.
5. Handle the **unrouted case**: signals that fit no stream and don't warrant one
   are **surfaced at approval** ("3 signals didn't route — new stream / attach /
   drop?"), never silently dropped and never auto-filed into an inbox.
6. On approval, emit a diff; the engine **commits** structured updates to each
   affected stream.

**Friction discipline.** Best-effort routing happens silently; **questions are
the exception, not the ritual**, asked only when ambiguity or new-stream
confidence crosses a threshold. The gate is always a **one-glance diff
approval** — not an interrogation. (See principle 7.)

### ② `fetch` — start of session (read)

- Pull **1–2 named streams**, **lazily**: load only the thin top layer (goal,
  current focus, open loops, next actions) plus the *list* of available
  references **and `suggested_reads`** — **not** the full history or the
  referenced files.
- The agent fetches deeper pieces **on demand** when the conversation needs them
  ("read `recs`'s `CLAUDE.md`", "show the decision log"), nudged by
  `suggested_reads` toward what's most likely relevant.

> The point of lazy fetching: the agent has *access* to the streams and refers
> to them on demand. It should **not** be force-fed the entire context up front.

---

## 6. Architecture — the layers

Cleanly separated layers, each split into a **universal** part and an **agent-
specific** part.

```
        ┌─────────────────────────────────────┐
        │  SKILL (agent-specific brain)         │
        │  read transcript → split/route → diff │
        └───────────────┬─────────────────────┘
                        │  (talks MCP)
        ┌───────────────▼─────────────────────┐
        │  MCP SERVER  (agent-facing frontend)  │  ── also: CLI frontend
        └───────────────┬─────────────────────┘
                        │  (function calls)
        ┌───────────────▼─────────────────────┐
        │  CORE ENGINE (library)                │
        │  canonical model · diff-apply         │
        │  · versioning · validation            │
        └───────────────┬─────────────────────┘
                        │  (private store)
        ┌───────────────▼─────────────────────┐
        │  SQLite  (pensieve.db — atomic commits) │
        └───────────────────────────────────────┘

   render / sync (deferred): export JSON·Markdown·Obsidian, push to GitHub
```

### Engine — the reader/writer of streams

The **core is a library**, not "an MCP server." MCP is *one frontend* over it.

- **Core library:** owns the canonical model, enforces structure, creates/reads/
  writes streams, applies diffs, handles versioning and validation. Knows
  *nothing* about conversations.
- **Store:** **v1 = SQLite** (`pensieve.db`), private to the engine — atomicity,
  concurrency and crash-safety come from the DB (see `spec_engine_contract.md`).
- **Render / sync** (export to JSON/Markdown/Obsidian, push to GitHub) is a
  **deferred, read-only** layer *off* the canonical store — not a storage backend.
- **MCP server frontend** — the agent-agnostic surface (see §7).
- **CLI frontend** — for debugging, scripting, and agents that don't speak MCP.

Why a library core rather than engine-as-MCP: CLI and MCP reuse the same logic;
storage stays private behind the engine; the diff engine is unit-testable without
a protocol.

### MCP fits the model exactly

Lazy fetching + on-demand addressing map directly onto MCP's two primitives:

- **Resources = lazy fetch.** Each addressable piece of a stream is a URI fetched
  only when needed:
  - `stream://recs` — the thin view (the whole node, one fetch)
  - `stream://recs/children` — its contained nodes (people, sub-efforts, assets)
  - `stream://recs/notes`, `stream://recs/history` — deep detail
- **Tools = actions.** `list_streams`, `create_stream`, `apply_diff`.

The addressing scheme we need for "refer on demand" *is* just MCP resource URIs.
The abstraction wants to be MCP.

### Brain — the agentic layer

The skill is the **brain**: it reads the transcript, summarizes, splits, routes,
asks the user the ambiguity/new-stream questions, and emits the diff. It is the
only layer that ever sees the conversation.

---

## 7. Portability — universal vs. agent-specific

`SKILL.md` is **Claude-specific** (Anthropic's Agent Skills format). But its
*content* — the routing/split/diff workflow — is portable prose. So we apply the
same split-the-reusable-from-the-wrapper trick used on the engine:

```
brain/PLAYBOOK.md        ← agnostic. The workflow as plain prose;
                            also names the MCP tools/resources to call.
adapters/
  claude/SKILL.md        ← thin Claude shim (frontmatter + "follow PLAYBOOK.md")
  cursor/.cursorrules     ← (future) same playbook, Cursor's wiring
  generic/PROMPT.md       ← (future) paste-into-system-prompt version
```

Each adapter does only the two genuinely non-portable things:

1. **Transcript access** — how *this* agent reads the current session (the engine
   never sees the conversation, so this can't live in the engine).
2. **MCP wiring** — pointing the agent at the Pensieve MCP server.

The full picture:

| Layer | Universal | Agent / specific |
| --- | --- | --- |
| Engine | core library, SQLite store, MCP server, CLI | render/sync targets (GitHub/Obsidian/…) — deferred |
| Brain | `PLAYBOOK.md` | transcript access + MCP wiring |
| Packaging | — | `SKILL.md` / `.cursorrules` / … |

**v1 builds only the Claude column** — but `PLAYBOOK.md` is written *as if*
agnostic, so adding Cursor later is a ~20-line shim, not a rewrite.

---

## 8. Decisions log (with rationale — for the blog)

| # | Decision | Why |
| --- | --- | --- |
| 1 | Manual trigger only; drop "continuous extraction" | LLM agents don't reliably do background bookkeeping mid-conversation; user *prefers* explicit control |
| 2 | Global store, independent of `cwd` (not per-repo) | A stream is a domain, not a project; it may span repos or have none |
| 3 | Routed multi-stream (not one flat blob) | Matches how work actually spans domains |
| 4 | Lazy fetching (thin index + fetch-on-demand) | Don't burn context up front; give *access*, not a dump |
| 5 | Agent emits a diff; engine validates + applies | Separate judgment from mutation; auditable, no lossy full-file rewrites |
| 6 | Engine is a **library**; MCP + CLI are frontends | Reuse logic across frontends; testable; backends stay protocol-agnostic |
| 7 | MCP as primary agent interface | Resources = lazy reads, Tools = writes — a near-exact fit |
| 8 | Split reusable `PLAYBOOK.md` from agent-specific `SKILL.md` | Makes the brain portable; wrapper stays thin |
| 9 | Streams created only by deliberate user choice | Anti-fragmentation: fewer, stronger streams |
| 10 | `capture` split into Phase A (digest) + Phase B (route/diff) | Don't bet the system on one heroic LLM pass; each phase stays simple and inspectable |
| 11 | "Events" repositioned as the Phase A digest (transport, not storage) | Gives the v0.2 event idea a correct home without it driving the storage model |
| 12 | Storage = mutable projection + append-only commit log ("Git for streams") | Resolves the event-sourced-vs-mutable fork: auditability + provenance without full event-sourcing |
| 13 | `suggested_reads` fetching hints in the thin `state` layer | Counters lazy-loading's failure mode (agent doesn't fetch when it should) cheaply |
| 14 | One `capture` with uncertainty-scaled friction (not quick/full modes) | Smooth-by-default; user shouldn't have to pre-decide quality. Questions rare, approval one-glance |
| 15 | Data model must not block refactoring (stable ids, provenance) | Prevent entropy now; enable repair (split/merge/rename) later without a rewrite |
| 16 | Separate **canonical model** / **storage** / **render** as three layers | Storage and human-inspection are different concerns; conflating them forced a worse storage choice. The agent only ever sees the canonical model |
| 17 | `context` bucket: tracked threads as mini-streams (status + append-only updates) | Captures ongoing "you just know" state (e.g. people mid-thread) without re-feeding long histories |
| 18 | Diff uses **typed semantic operations**, not JSON-paths | Engine validates *intent*, ops read cleanly in approval, projection internals stay free to change |
| 19 | **Dry-run is first-class** (`apply_diff(diff, {dry_run})`) | Powers the one-glance approval: preview the exact changes before committing |
| 20 | **Python for v1** engine; revisit Go once proven | Fastest path to validate the specs against real data; spec is language-agnostic so a later Go rewrite of a proven engine is cheap |
| 21 | **SQLite as the canonical store** for v1 (not plain files) | ACID transactions give atomic multi-part commits + concurrency + crash-safety *for free* (deletes a hand-rolled journaling module); single-file = a literal portable file; stdlib, zero-dep; vector-ready later |
| 22 | "Store anywhere" reframed as a **deferred render/sync layer**, not pluggable live storage | You can't design the right backend seam against one backend; disk's durability primitives are exactly what Notion can't honor. Build SQLite directly behind a thin internal boundary |
| 23 | **Engine-assigned ids** on goals/loops/actions/decisions/insights; diff addresses items **by id**, not by free-text match | Two independent reviewers flagged that exact-string-match-or-abort fails on the most common edit (a paraphrase). Ids make close/update reliable and unlock `update_*` ops |
| 24 | **`purpose`** (enduring identity) vs **`goals`** (transient projection) | Removes the lexical collision; "goal" now means exactly one thing, where intuition puts it. `set_purpose` is rare + user-confirmed (identity change) |
| 25 | Add **`insights`** (append-only) + **`supersedes`** on decisions | `insight` was a digest type with no landing op; `supersedes` keeps the append-only decision log trustworthy when a choice is reversed |
| 26 | Stamp **`schema_version`** on the store from day one | It cannot be retrofitted; its absence would foreclose the projection-evolution decision #18 explicitly allows |
| 27 | Add `spec_engine_contract.md` (the systems layer) | Reviews found the specs strong at the contract layer, silent at the systems layer — exactly where data-loss lives. This doc owns atomicity, concurrency, config, ids, dates, error contract |
| 28 | Engine ids come from a **non-reusing per-node counter**, not `max(live rows)+1` | `todo`s are deleted on complete/close; `max`-over-live-rows would reissue a freed id (e.g. `todo-5`) and collide with old provenance. Counter keeps ids stable handles (the promise of #23) |
| 29 | **Property-graph reframe** — one `nodes` table + `edges` + per-node contents, replacing per-stream fields | Generalizes streams/threads/people/assets/events into nodes (kind × position); promote/condense = re-parenting; containment is just an edge. Canonical model → `glossary.md` + `verbs.md` |
| 30 | Renamed **Memory Stick → Pensieve**; flows **`capture`** (write) + **`fetch`** (read) | The Pensieve metaphor (extract a strand, deposit it); accepts the trademark risk as a good-problem-to-have; `fetch` avoids clashing with the existing `hydrate` skill |
| 31 | Validated the model **cold** (fresh agent, rules-only) across 4 vertical-slice runs *before* building | Removes orchestrator bias; proves the rules are self-sufficient and the production shape works |
| 32 | **Capture is incremental & in-session** ("pensieve this"); end-of-session sweep is the fallback | Tiny per-capture diffs keep approval one-glance and make the edit-ops central; still human-triggered (the Pensieve model) |

### Considered, deferred

- **Stream refactoring UX** (split / merge / rename). Real risk (streams drift),
  but a *slow* one, and merge/split with history provenance is genuinely hard. We
  adopt the enabling **data constraints** now (stable ids, append-only history,
  provenance) and build the repair UX when entropy actually shows up.
- **Contradiction detection** (new session info contradicting a stream's existing
  state). Interesting, but should be *rare*: the stream was loaded at session
  start, so in-session decisions already supersede stale state. Not a v1 concern.
- **Continuous / passive extraction.** Possible future optimization on top of the
  manual backbone — not now.
- **Render / sync layer** (export to JSON/Markdown/Obsidian/Notion; push to
  GitHub) — read-only projections *off* the SQLite store. Designed-for, not built.
- **A pluggable `Backend` interface.** Deliberately *not* shipped in v1 — build
  SQLite directly behind a thin internal boundary; design the real seam only when
  a second store actually exists (decision #22).
- **Semantic / vector retrieval** over context & decisions (e.g. `sqlite-vec`) to
  power smarter fetch/routing. SQLite keeps the door open; not a v1 concern.
- **Collection filters `?since` / `?q`** — ship `?limit` only; add the rest when a
  stream is big enough to need them.
- **Cross-stream same-event provenance.** A signal routed to two streams becomes
  two op blocks with no shared event id linking them across streams. Per-stream
  provenance is intact; only the cross-stream "these are the same event" link is
  absent. A known, accepted v1 gap (flagged by the consumer review).

### Resolved (previously parked)

- **Event-sourced log vs. mutable state file** → **both, at the right
  granularity** (decision #12): mutable projection for current state, append-only
  diff-log for history. See §4, "Git for streams."
- **Plain JSON files vs. a database** → **SQLite** (decisions #21, #16). Separating
  storage from inspection removed the only argument for plain files (git-diffable
  ≈ a render concern), and SQLite's transactions deliver the atomicity the
  files-version would have hand-rolled badly.
- **Exact-string match vs. ids for closing items** → **ids** (decision #23).
- **`goal` naming collision** → **`purpose` vs `goals`** (decision #24).

---

## 9. What's next

**The model was reframed to a property graph** (post-v0.5). Canonical model now:
**`glossary.md`** (nouns) + **`verbs.md`** (verbs). The older specs were reconciled
to it:

- `spec_stream_layout.md` → **stub** (→ glossary) · `spec_diff_format.md` → **stub**
  (→ verbs)
- `spec_resource_uris.md` (read surface) + `spec_engine_contract.md` (SQLite **graph**
  schema) → **rewritten** to the graph.

**Validated** via **four cold-agent vertical-slice runs** (capture + update;
declarative + imperative) — the agent's translation/filter is the make-or-break, and
it held on real, messy data. Details in `handoff.md`.

**Next: build the engine** in **Python** (decision #20). Order: transactional SQLite
**graph** core (nodes + edges + contents) → diff-apply → CLI (exercises everything)
→ MCP server → Claude `SKILL.md` shim last. Fold the validated judgment rules (R1–R9)
+ the incremental capture model into `brain/PLAYBOOK.md`.

---

## Appendix — evolution of the idea

- **v0.2 (inherited):** a multi-stream, "event-driven" memory with continuous
  extraction and mutable per-stream state files.
- **v0.3:** manual-trigger only; lazy fetching as a first-class read path;
  streams as two-half aggregates (references + state); a clean three-layer
  architecture (engine library → MCP/CLI frontends → agentic brain) with a
  universal/agent-specific split at every layer; disk-first pluggable backends.
- **v0.4:** in response to an external design review — `capture` split into Phase A
  (digest) + Phase B (route/diff), with "events" repositioned as the digest;
  storage fork resolved as "Git for streams" (mutable projection + append-only
  commit log); `suggested_reads` fetching hints; uncertainty-scaled friction
  instead of quick/full modes; explicit handling of the unrouted case; refactoring
  kept buildable via data-model constraints. Reframed as *version-controlled,
  domain-partitioned working memory.*
- **v0.5 (this doc):** after a **consumer-agent** review (usability) and an
  **implementer** review (buildability/durability) — **SQLite** chosen as the
  canonical store (separating model / storage / render layers), making commits
  atomic via DB transactions; **id-addressed** projection items (fixing the
  exact-string-match trap both reviews flagged); **`purpose` vs `goals`** naming;
  added **`insights`** + decision **`supersedes`**; **`schema_version`** from day
  one; new **`spec_engine_contract.md`** for the systems layer; scope trims
  (deferred `Backend` interface, `?since`/`?q`, cut redundant `…/meta`).
- **v0.6:** renamed **Memory Stick → Pensieve**; **reframed the data model to a
  property graph** (canonical model split into `glossary.md` *nouns* + `verbs.md`
  *verbs*, superseding the per-stream specs); flows renamed **`capture`** /
  **`fetch`**; the model + verb layer **validated cold** across four vertical-slice
  runs; capture reframed as **incremental / in-session** (the Pensieve model). §4–§6
  kept as the v0.5 telling under a reframe banner.
