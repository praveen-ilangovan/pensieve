# Pensieve — Verbs (the operation layer)

> **Status:** drafted from validation · **Date:** 2026-06-27
> **Pairs with `glossary.md`:** glossary = the **nouns** (what exists); this = the
> **verbs** (how it changes). Together they are the model.
> **Grounded, not guessed:** every op here is one a *cold agent successfully used* on
> real transcripts across three vertical-slice runs (see `handoff.md`).
> **Supersedes** the op catalog in `spec_diff_format.md` (now a stub pointing here).

---

## 0. The contract

The **brain** (agent) reads a session + the current graph, and emits a **diff**:
a list of typed **ops** + a `dropped` list + `questions`. The **engine** validates
and applies the ops as one **atomic commit** (per `spec_engine_contract.md`).

Ops are **imperative and id-addressed**, not a declarative graph dump (glossary
decision: validate *intent*, enable edits-by-id, and read cleanly in the one-glance
approval). *(The slice agents output a declarative graph because it was easier to
eyeball; that maps 1:1 to the ops below — each node = a `create_node` + its contents
as `add_*` ops.)*

---

## 1. The diff envelope

```json
{
  "session": "<opaque provenance id>",
  "date": "YYYY-MM-DD",
  "ops": [ /* typed ops, applied atomically, in order */ ],
  "dropped": [ "<what the filter discarded + why>" ],
  "questions": [ "<ambiguous routing/keep calls for the user>" ]
}
```

- **`ops`** — applied as one commit.
- **`dropped`** — shown at approval for transparency (what was *not* captured); never
  applied. This is what makes aggressive filtering trustworthy.
- **`questions`** — surfaced to the user; resolved before/at commit (don't guess).

---

## 2. Op catalog

Every op is `{ "op": "<name>", … }`. Ids: **node ids** are agent-proposed kebab
slugs (engine validates uniqueness); **todo/note/commit ids** are engine-assigned
from a non-reusing counter (per `spec_engine_contract.md`).

### Nodes
| op | args | effect |
| --- | --- | --- |
| `create_node` | `id, label, kind, position`(top-level\|contained)`, parent?, properties{}` | create a node. `parent` set ⇒ contained (a `contains` edge); absent ⇒ top-level (a stream) |
| `set_property` | `node, key, value` | set/overwrite a property (mutable working state). Rename = `set_property(label)` |

### Edges
| op | args | effect |
| --- | --- | --- |
| `add_edge` | `from, to, kind` | add a typed relationship (kinds in §4). `contains` is normally set via `parent`/`reparent`, not here |
| `remove_edge` | `from, to, kind` | drop a relationship |

### Contents (inside a node)
| op | args | effect |
| --- | --- | --- |
| `add_todo` | `node, text` | append a todo (engine assigns id, `state: open`) |
| `complete_todo` | `node, todo` | mark done → leaves the working set (engine notes it in history) |
| `update_todo` | `node, todo, text` | edit a todo's text in place |
| `add_note` | `node, text, flavor?`(decision\|outcome\|observation)`, supersedes?` | append a note (append-only log). **`supersedes` is for REVERSALS/CORRECTIONS only** — when the prior note is now *wrong*. A *new* development about the same thing (prior still true) is a **plain `add_note`, not a supersede**. *(Validated gap: the update-run over-applied supersede to new-but-non-reversing notes, which would destroy still-true history.)* |

### Lifecycle (the fractal "promote / condense")
| op | args | effect |
| --- | --- | --- |
| `reparent` | `node, parent`(id or null) | **one move, both directions:** `null` ⇒ **promote** to top-level (becomes a stream); an id ⇒ **condense**/attach under that node |
| `promote_entry` | `node, entry, new_id, new_kind` | turn a `todo`/`note` into its own node (so it can be **linked**). **Migrate-and-remove:** the source entry's content moves into the new node and the source entry is removed — **don't leave the original orphaned.** *(Validated gap: the update-run used `create_node` to promote a note's topic but left the source note behind → duplication.)* |

### Removal (privileged)
| op | args | effect |
| --- | --- | --- |
| `redact` | `node?` / `entry?` | the **only true delete** — for sensitive/wrong content. Distinct from `complete_todo` (lifecycle) and from `drop` (filter) |

### Non-ops (named so they aren't mistaken for ops)
- **`drop`** — the filter *not emitting*. Reported in `dropped`, never sent to the engine.
- **`supersede`** — expressed as `add_note { supersedes }`, not a separate op.

---

## 3. The judgment rules — what the agent applies *before* emitting ops

This is the brain's filter/routing logic — the make-or-break, and the part the three
runs validated (and stress-tested). It belongs in `PLAYBOOK.md`; summarized here
because it shapes which ops get emitted.

- **R1 — Load the graph first.** Routing *requires* the current graph (registry +
  node index). Route into existing nodes; `create_node` at top-level **only when
  nothing fits**. *(Run 1 proved: from empty, everything over-promotes to top-level.)*
- **R2 — The filter.** Keep **durable state** (decisions, goals, todos, status of
  people/projects, findings). **Drop** advice/reference *delivered in the session*,
  small talk, reasoning, and message/email drafting. Expect to drop ~85–90%.
- **R3 — Keep/drop sharpening** (cuts borderline variance): the user's own
  **commitments / decisions / goals → keep**; pure **how-to the assistant delivered
  → drop**; an **un-acted-on recommendation → borderline → put in `questions`**,
  don't silently decide.
- **R4 — Node-promotion heuristic** (the *stubbornest* borderline — apply
  explicitly): a person/topic that **recurs with its own status/activity** → a node;
  a **single mention → a note** (or nothing). When a noted thing **gains its own
  todos/notes/edges or a status that changes**, that is the promotion trigger — use
  `promote_entry`. *(Two runs left Travis a note even after he became the first
  launched curator, while the equally-active Rafia was a node — the agent under-fires
  R4.)* **When promotion is plausible-but-unsure, surface it as a `question`** (R9)
  rather than silently leaving it a note.
- **R5 — Lazy nodes.** Prefer a property or note over a node until it earns one. *(A
  one-off place = a `location` property, not a `place` node — Run 1 did this right.)*
- **R6 — Temporal placement.** Past events → `status: past`/closed; future → upcoming
  + date (often an `add_todo`). Sessions narrate across time — place things.
- **R7 — Conservative on sensitive content.** Emotional/personal/private material →
  **drop by default**; persist only on explicit capture.
- **R8 — Explicit-capture override.** "Remember this" forces a keep, bypassing R2/R7.
- **R9 — Surface, don't guess.** Genuinely ambiguous routing or keep/drop → a
  `question`, not a silent decision. The approval gate + `dropped`/`questions` are
  the safety net that lets the filter be aggressive.

---

## 4. Edge-kinds (tightened, with examples)

The least-exercised part of the rules — give the agent concrete anchors:

| kind | shape | example |
| --- | --- | --- |
| `contains` | parent → child (hierarchy/position) | `recs → curator-outreach → Rafia` (set via `parent`) |
| `located-in` | event → place | `shenzhen-trip → Shenzhen` |
| `requested-by` | subject/feature → person | `offline-mode → Rafia` |
| `attended` / `participates-in` | person → event | `you → amit-intro-chat` |
| `about` | node → node | a `writing` piece → `recs` |
| `relates-to` | generic fallback | `apps-im-building → recs` |

**Rule:** use the **most specific** kind that fits; fall back to `relates-to`. **Don't
over-edge** — if `contains` already expresses the relationship, a second edge is
noise. *(Run 3 emitted `Rafia participates-in recs`, redundant with her containment
under it — avoid.)*

---

## 5. Phase A / Phase B mapping (where the ops come from)

- **Phase A — digest** (no graph needed): read the session → a list of durable
  *signals* + what to drop. Generic, portable.
- **Phase B — route → ops** (graph loaded): apply R1–R9 → emit the **diff** (ops +
  `dropped` + `questions`).

The agent calls `apply_diff(diff, { dry_run })` → shows the user the preview +
`dropped` + `questions` (the one-glance approval) → on approval, commits.

---

## 5b. Capture model — incremental & in-session (the PRIMARY mode)

Capture is **human-triggered repeatedly, throughout a session** ("pensieve this" …
later … "pensieve this too") — not only one big pour at the end. Each trigger:

1. **Scope** the slice — the conversation *since the last capture*, or the specific
   thing the user points at.
2. Run Phase A → B on that slice → emit a **small** diff.
3. One-glance approve → commit → **continue the same conversation.**

- **Incremental is primary; the end-of-session sweep is the fallback** — a capture
  trigger scoped to "everything still unsaved," for when you forgot to capture along
  the way. Both are supported.
- **This is why diffs are one-glance.** Small slices → a few items each. The
  mega-digest (the whole Recs session at once) is the *rare* case, not the norm — in
  practice it would have been ~8 small captures.
- **This is why the edit ops are central, not edge cases.** Capture #2 within a
  session frequently *updates* what capture #1 just wrote (complete / supersede /
  add-to). Within-session **idempotent routing** — reference existing ids, never
  recreate — is essential (validated in the update-run).
- **Scoping is a playbook judgment, not an op.** The agent tracks its own
  last-capture point — trivial in-session (same conversation; it remembers what it
  committed).
- Still **human-triggered** (principle 1 intact) — just finer-grained. *(The
  Pensieve: extract a strand of thought, deposit it in the vessel.)*

---

## 6. Open / to-tighten

- `org` vs `person` (keep both — Run 3 used both cleanly); `place` weak-kind (lazy
  rule covers it); condense-vs-nesting; static facts (one-off `note`/`fact` vs node).
- Whether `promote_entry` and `reparent` should share one `promote` op (they're the
  same fractal move) — leaning keep-separate for clarity; revisit at build.
- Does the engine compute `dropped`/`questions` handling, or is that purely
  brain-side? (Brain-side; engine only consumes `ops`.)
