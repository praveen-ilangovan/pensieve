# Pensieve — Glossary (canonical vocabulary)

> **Status:** rebuilt on the graph model · **Date:** 2026-06-26
>
> The **conceptual vocabulary** for Pensieve — *what things are*, not how
> they're stored. Once vocabulary + verbs settle, this is the source of truth and
> the older `spec_*.md` (which carry the pre-graph vocabulary) get reconciled to it.
>
> **We are not inventing this** — it's a small **property graph** (nodes + edges +
> properties), with **named-entity** kinds (à la NER / schema.org) and a
> **Zettelkasten / Topic-Maps** linked-memory philosophy. We borrow the *models*,
> not the machinery.
>
> Legend: ✅ locked · 🔄 in progress · ❓ open

---

## 1. Foundation — a small, opinionated graph

Everything reduces to three primitives:

- **Node** — a thing that exists.
- **Edge** — a typed relationship between two nodes.
- **Property** — an attribute on a node or edge.

We keep an **opinionated vocabulary on top** (stream, thread, person, event, …) and
**never expose raw "node/edge" to the user** — otherwise we've built a generic
graph editor, not Pensieve.

---

## 2. The two axes — `kind` × `position`

Every node has both:

- **`kind`** — *what the node is*. A small **closed-core, extensible** set:
  `subject · person · org · place · event · asset`.
- **`position`** — *where the node sits*: **top-level** (we call it a **stream**) vs
  **contained** (we call it a **thread**). Position is literally just the `contains`
  edge.

So **`stream` and `thread` are positions, not kinds.** Rafia is *a person (kind)
sitting as a thread (position)*. recs is *a subject (kind) at top-level (a stream)*.

> **Why this matters:** a node has *one* kind, but a person can be contained in a
> stream — so "thread" can't be a kind (Rafia would be both `person` and `thread`).
> Position resolves it. And the payoff: **promote / condense changes position,
> never kind** — it's just re-attaching one `contains` edge.

---

## 3. Node kinds (✅ + predefined properties)

A `kind` earns first-class status **only if the agent treats it differently**;
otherwise it's just a free-text label. Lazy rule: **a property graduates to its own
node only when it recurs or needs its own edges** (Shenzhen is a property of one
trip until you track it across many → then it becomes a `place` node).

| kind | predefined properties | notes |
| --- | --- | --- |
| **subject** | `purpose` (if top-level), `status` | the work spine — domains / projects / processes. Usually the top-level (stream) kind. |
| **person** | `name`, `role`, `bio`, `status` | someone you track; has relationship/interaction state |
| **org** | `name`, `description` | a collective you deal with |
| **place** | `name`, `location` | a location; usually anchors events |
| **event** | `name`, `when`, `status` (upcoming/past) | **time-anchored** |
| **asset** | `location`, `sub_kind` (file/image/dir/repo/link), `label` | a **pointer to external content**; engine stores the pointer, agent resolves on demand; shareable (many edges → one asset node) |

**Shared by every node:** `id`, `label`, `kind`, `created`, `updated`. Unknown
extras → free-text properties. **New kinds are added on demand**, not up front.

---

## 4. Edge kinds (✅)

Same discipline as node kinds — a small opinionated set + a generic fallback:

- **`contains`** — the hierarchy/position edge (stream → thread).
- **`located-in`** — event → place.
- **`requested-by`** — subject/feature → person.
- **`attended` / `participates-in`** — person → event.
- **`about`** — node → node ("this thread is about recs").
- **`relates-to`** — generic fallback when nothing specific fits.

Extensible on demand, like kinds.

---

## 4b. Inside a node — working state vs log

A node's contents split **the same way the whole system does** (mutable projection
+ append-only log — fractal):

- **Properties (mutable)** — `when` on an event, `status` on a person, `purpose` on
  a subject. Overwritten freely.
- **Working state (mutable)** — open **todos** and list-items: the live "current
  truth." Edited/removed freely, **by id**.
- **Log (append-only)** — **notes** recording *what happened*. The memory; never
  rewritten.

**Entry types — only two** (a type earns its place only if it *behaves*
differently):

- **`todo`** — actionable; `open` / `done`. (Open todos are the resumption surface.)
- **`note`** — any logged statement; optional **`flavor`** (`decision` / `outcome`
  / `observation` …, extensible) and optional **`supersedes`**.

(`decision` and `outcome` are **flavors of a note**, not separate types — they
behave identically; only `todo` has a distinct lifecycle.)

**Addressable vs linkable:**
- every entry is **addressable** (stable `id`; the diff targets it by id);
- only **nodes** are **linkable** (edges connect nodes) → **promote** an entry to a
  node when it needs edges. Same fractal mechanism, one level down.

**Three mutation patterns — and only these:**
1. **Edit working state** — overwrite a property, remove/complete a todo by id. Free.
2. **Supersede a log entry** — append a correction pointing at the old; the old
   stays for audit.
3. **Redact** — a privileged hard-delete (sensitive/wrong); the *only* thing that
   truly removes from the log. Deferred escape-hatch.

> Edit the present freely; correct the past by superseding; only redaction truly
> deletes.

---

## 5. How the old vocabulary reclassifies

| Old term | Is now… |
| --- | --- |
| **Stream** | a node at **top-level** (no `contains` parent); usually `kind: subject`; carries `purpose` |
| **Thread** | any node **contained** by another (via `contains`); a "mini-stream" |
| **Purpose** | a **property** of a top-level subject node |
| **Asset** | a **node** of `kind: asset` (external pointer) |
| **Link** | an **edge** — a relationship between two internal nodes |
| **Person / place / event / org** | **node kinds** |
| "stream *has* threads" | a **`contains` edge** |

---

## 6. What the graph model resolves (previously open)

- **Promote / condense** = re-attaching one `contains` edge (position change, not
  kind change). Our scariest "refactoring" is now trivial.
- **People across streams** = **one** person node with **multiple edges**;
  **backlinks** (incoming edges) *are* the "see Rafia everywhere" view. No
  duplication, no "which stream owns her."
- **Asset sharing** = one asset node, many incoming edges.
- **Cross-stream** = **edges**, never duplication.

---

## 7. Running example (recs + employment as one graph)

```
recs (subject, STREAM)
  ──contains──▶ mcp-layer (subject, thread)
  ──contains──▶ offline-mode (subject, thread) ──requested-by──▶ Rafia (person)
  ──contains──▶ Rafia (person, thread)         [bio + status live here, once]
  ──contains──▶ growth (subject, thread)        [status: "Reddit tried → failed"]

employment (subject, STREAM)
  ──contains──▶ eng-manager-interview (subject, thread)
  ──contains──▶ shenzhen-trip (event, thread) ──located-in──▶ Shenzhen (place)
  ──contains──▶ apps-im-building (subject, thread) ──relates-to──▶ recs   [cross-stream]

Amit (person) ──participates-in──▶ amit-intro-chat (event)
```

---

## 8. Storage (not vocabulary — noted to prevent confusion)

The graph is stored in **SQLite** (`nodes` + `edges` tables) — **private to the
engine**. The agent only ever sees the canonical model via **URIs / diffs**
(decision #16). Storage is therefore **swappable** without touching the contract.
So: **graph *model* · relational *storage* · Zettelkasten/Topic-Maps *philosophy*.**

---

## 9. ❓ Open questions

- **`org` vs `person`** — keep separate or fold into one `contact` kind?
- **`place`** — weakest distinct behaviour; rely on the lazy-promotion rule.
- **Condense vs nesting** — if a condensed stream had its own threads, do they come
  along (nesting), flatten, or is condense restricted?
- **Static facts** (past-jobs) — a degenerate node (`kind: fact`?) or a property?
- **"Link" as a user-facing word** for association-edges, or just "edge"?

---

## Cut / deferred (so we don't re-litigate)

- ❌ **focus** — cut (redundant; a highlight over existing nodes).
- ⏸️ **suggested_reads** — deferred; a *fetch optimization*, not part of the model.
- ⚙️ **history / commit** — kept but **structural** (engine-written provenance).
- ✅ **goals / actions / loops / decisions / insights** — *resolved* as node
  contents: **`todo`** + **`note`**(+flavor). See "Inside a node" (§4b).

## Pipeline terms (a different layer — define at the "verbs" stage)

`session`, `digest`, `signal`, `diff`, `op` describe the **process** of capturing
memory, not the **contents** of the graph. Parked until we do the verbs.
