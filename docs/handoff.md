# Pensieve — Handoff / Resume Point

> **Updated:** 2026-06-27 · **Pick up by reading:** this file, then `docs/glossary.md`
> (nouns) + `docs/verbs.md` (verbs), then `docs/core_concept.md` (v0.6, narrative).

## Where we are

**Design + reconciliation complete.** The whole doc set now speaks one coherent
**graph model**:
- **`glossary.md`** = canonical nouns · **`verbs.md`** = canonical verbs (ops · rules
  R1–R9 · capture model).
- `spec_resource_uris.md` + `spec_engine_contract.md` rewritten to the graph;
  `spec_stream_layout.md` + `spec_diff_format.md` are stubs; `core_concept.md` bumped
  to **v0.6** (reframe banner + decisions #29–32 + appendix).
- Renamed **Memory Stick → Pensieve**; flows are **`capture`** (write) / **`fetch`**
  (read).

The model + verb layer are **validated cold** (4 vertical-slice runs).

**We are at the design→build boundary. Building is the active next step.**

## Locked this session — the graph model (full detail in `glossary.md`)

- **Foundation:** it's a small, opinionated **property graph** — **nodes + edges +
  properties**. We expose friendly vocabulary, never raw "node/edge." Anchored in
  established models (property graph / ER, named-entities for kinds, Zettelkasten +
  Topic Maps for the linked-memory philosophy).
- **Two axes:** every node has a **`kind`** (what it is) and a **`position`** (where
  it sits). `stream` = top-level node; `thread` = contained node — **position, not
  kind.** Promote/condense = re-attaching one `contains` edge (never changes kind).
- **Node kinds** (closed-core, extensible): `subject · person · org · place · event
  · asset`, each with predefined properties.
- **Edge kinds:** `contains · located-in · requested-by · attended ·
  participates-in · about` + `relates-to` fallback.
- **`asset`** = a node (external pointer; pointer-only, agent resolves on demand).
  **`link`** = an edge (internal relationship). Different things.
- **Inside a node:** working state (mutable: properties + open `todo`s + list items)
  vs **log** (append-only: `note`s). Two entry types only — **`todo`** (open/done)
  and **`note`** (+ optional `flavor`: decision/outcome/observation, + optional
  `supersedes`). `decision`/`outcome` are *flavors*, not types.
- **Three mutation patterns:** edit working state freely · supersede a log entry ·
  **redact** (privileged hard-delete). *Edit the present; correct the past by
  superseding; only redaction truly deletes.*
- **Addressable vs linkable:** every entry has an id (addressable); only nodes are
  linkable (edges connect nodes) → **promote** an entry to a node to link it.
- **Storage:** graph **model**, relational **storage** (SQLite, swappable behind the
  engine), Zettelkasten/Topic-Maps **philosophy** — three independent layers. Graph
  model ≠ graph DB (our graph is tiny + shallow; SQLite wins on portability/zero-dep;
  Kùzu/Neo4j only if it ever outgrows that).

## Validated — vertical slice: 3 cold-agent runs (the make-or-break test)

**Method (the honest test):** a *fresh* agent with **zero** prior context, given only
the written rules + a transcript (+ the existing graph), outputs a graph as JSON with
a `dropped` list. This mirrors production (fresh agent + playbook + transcript) and
removes the orchestrator's bias. The extraction-spec used in the runs is the de-facto
**first draft of the graph-extraction playbook** (lives in the run prompts).

**Runs:**
1. **Shenzhen, empty graph** — extraction + filter correct; trip became a *top-level*
   node (nothing to route into); lazy-promotion correct (Shenzhen kept as a *property*,
   not a node — more disciplined than the hand-done version).
2. **Shenzhen, with graph** — correctly routed the trip as a **`contained` event under
   `employment`**. Confirms the routing fix.
3. **Recs (hard, dense, with graph)** — multi-stream routing worked (career/recs/
   writing); **emergent good structure** (it created a `curator-outreach` subject and
   nested people under it); **`org` vs `person`** correct; filter held on ~85%-advice
   input; temporal placement, **supersede-awareness** (dropped a superseded reply),
   and ambiguity-as-questions all worked. Matched/beat the hand-done version.

**Validated:** the rules are **self-sufficient** for extraction, filtering, kind/
position classification, multi-stream routing (when the graph is fed in), temporal
placement, supersede, and ambiguity-surfacing. Production shape works.

**The consistent finding — variance lives in exactly TWO borderline decisions, never
the high-signal core:**
1. **Node-vs-note promotion** — e.g. Rafia made a person *node* but Travis/Violet/BR
   left as *notes* despite equal activity. When does someone/something earn a node?
2. **Borderline keep/drop** — e.g. kept the reading *list* but dropped the exec *goal*
   it serves; the prep checklist and an un-acted recommendation flipped between runs.

Absorbed by the **approval gate** + **explicit capture**. Tightenable with rules (below).

**Two tightening rules to bake into the verb layer / playbook:**
- **Node-promotion heuristic:** a person/topic that recurs with its own status/activity
  across the session → **node**; a single mention → **note** (or nothing).
- **Keep/drop sharpening:** the user's own commitments / decisions / **goals** → keep;
  pure how-to / reference the assistant *delivered* → drop. An un-acted-on
  recommendation is borderline → **surface at approval**, don't silently decide.

**Other confirmed findings (carry into verb layer + playbook):**
- **Routing needs the graph fed in** (registry/streams) — extraction works from rules
  alone, routing does not. Confirms Phase B's "load `stream://_index` first."
- **The filter is the make-or-break and it works** — ~85–90% of a session is *advice
  delivered* (drop); the residue is *state changed*. That separation is the core job.
- **"One glance" is per-node, not per-session** — a rare mega-session yields several
  glances; fine.
- **Sessions narrate the past** → place things in time (close past, schedule future).
- **Sensitive/emotional content → conservative DROP** by default; persist only on
  explicit capture. Redaction is a posture, not just an escape-hatch.
- **Edge-kind precision is the least-exercised** part of the rules (one fuzzy edge in
  the Recs run) — needs examples/tightening.

**Verb inventory, grounded in what the slice actually emitted** (seed for the verb
layer): `create_node` (subject/person/org), `set_parent`/`contains`, `set_property`,
`add_note` (+flavor), `add_todo`, `promote` (the node-vs-note call), `supersede`,
`drop`.

### Run 4 — update session (edit lifecycle + imperative op format)

Ran a cold agent on a *follow-up* session against the Run-3 graph (closing/changing
prior state) with the **imperative op catalog** as the output format. Result:
- ✅ Validated: `complete_todo`, `set_property` (status updates), **`supersede` on a
  true reversal** (shared-decks), promotion of a note→node, **idempotent routing**
  (didn't recreate existing nodes), and the **imperative `apply_diff` format** itself.
- ⚠️ Three precise gaps → now fixed in `verbs.md`:
  1. **append vs supersede** — agent over-applied `supersede` to *new-but-non-
     reversing* notes (would destroy still-true history). Rule added: supersede =
     reversal/correction only.
  2. **node-promotion (R4)** still under-fires (left Travis a note after he launched).
     R4 strengthened + "surface borderline promotions as questions."
  3. **promotion orphaned its source** (used `create_node`, left the original note).
     `promote_entry` now specified as **migrate-and-remove**.

**=> The verb layer (`docs/verbs.md`) is drafted AND validated end-to-end** (capture +
update; declarative + imperative).

### Capture model refinement — incremental, in-session (now the PRIMARY mode)

Realistic usage is **repeated human-triggered capture *throughout* a session**
("save this" … later "save this too"), each digesting only the recent slice — not one
big end-of-session pour. Consequences (now in `verbs.md` §5b):
- **Resolves the one-glance problem** — incremental slices are naturally tiny, so
  every diff is genuinely one glance. The mega-digest is the rare *fallback*.
- **Makes the edit ops central** (capture #2 updates capture #1 within a session) —
  which is why validating them mattered.
- New mechanic: **capture scoping** (slice = since-last-capture; agent tracks its own
  last-capture point in-session). A playbook judgment, not an op.
- Still human-triggered (principle 1 intact) — the "Pensieve" model.

## Open questions

- Minor glossary opens: `org` vs `person`; `place` (weak kind); condense-vs-nesting;
  static facts (degenerate node vs property); keep "link" as a user word.
- Routing: `career` vs `personal` as one stream or two? Cross-stream artifacts (a
  reading list that's both `career` content *and* a literal Recs deck) — link or
  duplicate? (First real cross-stream case.)

## Next steps

1. ✅ **Verb/op layer defined + validated** → `docs/verbs.md`.
2. ✅ **Reconciled** `core_concept.md` + the older `spec_*.md` down to glossary +
   verbs (graph vocabulary, op catalog, capture model). Done.
3. ✅ **Renamed → Pensieve**; git-initialised + pushed to remote (`pensieve`).
4. **BUILD (active).** Order: transactional **SQLite graph core** (nodes + edges +
   contents — the substrate) → diff-apply (the op catalog from `verbs.md`) → CLI
   (exercises everything) → MCP server → Claude `SKILL.md`. **Fold R1–R9 + the
   capture model into `brain/PLAYBOOK.md`** during this phase (the playbook still has
   a graph-reframe-pending banner). Python; tooling TBD.
5. Resolve minor open questions as they block the build (org/person, place,
   condense-vs-nesting, static facts, career-vs-personal, cross-stream links).

## Reference: doc map

- `glossary.md` — vocabulary (graph model). **Current source of truth for nouns.**
- `core_concept.md` (v0.5) — master design/narrative; data-model specifics being
  superseded by glossary.
- `spec_resource_uris.md` (read surface) + `spec_engine_contract.md` (storage/engine)
  — reconciled to the graph model.
- `spec_stream_layout.md` / `spec_diff_format.md` — **stubs** (superseded by
  glossary / verbs respectively).
- `brain/PLAYBOOK.md` — the agnostic brain.
