# Pensieve — Glossary (canonical vocabulary)

> **Status:** rebuilt on the **information-lake** model · **Date:** 2026-06-26
>
> The **conceptual vocabulary** for Pensieve — *what things are*, not how they're
> stored. This is the source of truth for nouns; `verbs.md` is the source of truth for
> operations.
>
> Legend: ✅ locked · 🔄 in progress · ❓ open

---

## 0. What Pensieve is — and is not

Pensieve is an **information lake**: a personal **memory substrate** whose job is to
**remember**, not to act. You pour pieces of information in; later you (or an agent)
read them back to recall facts *and notice patterns*.

> **Guiding non-goal — Pensieve remembers; it does not act.** Scheduling, tasking,
> reminding, sending — those live in *other* tools (calendar, Todoist, email) that an
> agent drives **from** Pensieve's memory. If a proposed feature is about *doing*
> something rather than *recording/recalling* it, it does not belong here. This single
> line answers a whole class of "should Pensieve also do X?" — no.

Everything the user sees is **four concepts**: **streams · threads · notes ·
entities**. (A property graph realises them under the hood — §6 — but that is never
shown to the user.)

---

## 1. The four concepts

- **Stream** — a top-level **domain** of the user's life/work (`recs`, `employment`,
  `writing`). Has a `purpose` (its enduring reason to exist).
- **Thread** — a **focused sub-topic within a stream** (`rafia`, `curator-outreach`).
  A thread lives under exactly one stream.
- **Note** — an **atomic piece of information**. *Everything starts life as a note.* A
  note is attached to one or more threads/streams, references zero-or-more entities,
  and carries a date + provenance.
- **Entity** — a **named thing a note refers to** (a person, org, topic, place,
  event). An entity lives as a **reference on notes** until it recurs enough to earn
  **its own thread** (or stream).

---

## 2. The relationships (the crux)

| relationship | cardinality | meaning |
| --- | --- | --- |
| Stream → Thread | `1 — N` | a thread sits under **one** stream; a stream has many threads |
| Note → Stream/Thread | `N — M` | a note is **multi-homed**: attached to one *or several* threads/streams |
| Note → Entity | `N — M` | a note references 0+ entities; an entity is referenced across many notes |
| Entity → Thread/Stream | promotion | a recurring entity is **promoted** into its own node; its notes attach there too |

**Lifecycle, in one sentence:** information lands as a **note** (attached to a
stream/thread, referencing entities) → entities accumulate references across notes →
when an entity crosses the threshold and is queried, it's **proposed for promotion**
into its own **thread**, and its notes attach there.

---

## 3. Notes — append-only information ✅

A note holds a **piece of information**. The model is deliberately tiny — fancy
concepts were a *reliability* problem (the agent fumbles them), not just clutter.

- **Append is the default.** New information — *including a change in the world* — is a
  **new note**. "Meeting was Tuesday" then "moved to Wednesday (weak internet)" are
  **two notes**, on purpose: the *change itself is memory* (it's how you later notice
  "this client always reschedules"). Overwriting would destroy that.
- **The agent derives the present by reading.** "What's true now?" and "what's the
  pattern?" come from reading the notes in time order — **not** from a stored
  `supersede` link or a `flavor` tag. Currency is inferred, not stamped.
- **Edit only to fix a genuine mistake** (a typo, a wrong value *you* recorded) — where
  the old text has zero memory value. **Delete** only to truly remove something.
- **Safety asymmetry** (why append is the safe default): a wrong *append* costs a little
  redundancy; a wrong *overwrite* loses memory. So when unsure, add.

A note carries: **text**, **attachments** (which threads/streams), **entities**
(references), a **date**, and **provenance** (`created` + `actor` — e.g. `claude-code`
or `cli`). **No flavor, no type, no open/closed state.** It's just information.

> **Three operations, plain words:** **add** (new info) · **update** (fix a mistake) ·
> **delete** (truly remove). That's all.

---

## 4. Entities & promotion ✅

An **entity** is a named thing notes refer to. Before it earns a node it exists only as
a **reference (tag) on notes** — carrying a provisional **kind** (person/org/topic/…).

- **Count = `COUNT(notes referencing the entity)`** — *derived*, not a stored counter.
  (So it's always recomputable; nothing to drift or backfill.)
- **Threshold** — when an entity's count crosses a **configurable** threshold (default
  **5**), it becomes a **promotion candidate**.
- **Promotion is proposed, never automatic.** It's surfaced (with approval) at the next
  natural moment — a capture that touches the entity, or a **query for it** ("you ask
  about Rafia a lot — give her a dedicated thread?"). Reads stay safe; the *proposal*
  may ride on a read, the *mutation* never does.
- **Promotion is additive.** Approving it: create the entity's **node** (a thread under
  a stream, or a new stream) and **attach** every note that references it. Prior
  attachments **stay** — relevant ones keep showing; irrelevant ones simply never get
  queried again. Nothing moves, nothing is lost (no triage, because a note can be
  multi-homed).

The hard part is **recognition/resolution** — tagging a note with `rafia` and knowing
"Rafia", "Rafia Naseem", and "her" are the *same* entity. That judgment (at capture, on
the small slice in front of the agent) is the real new capability; counting and
promotion are easy on top of it.

---

## 5. Recall discipline (the thin view) 🔄

- Fetching a stream shows **its own notes + a summary of its child threads** — not every
  note in every descendant. A note attached only to a thread shows **under that thread**,
  not flooded into the parent. Keeps "what's in recs?" a glance, not a dump.
- A promoted entity makes entity-recall a **direct lookup** ("what about Rafia" → her
  thread) instead of scan-the-stream-and-filter — which is *why* promotion exists.

---

## 6. Under the hood — the property graph (never user-facing)

The four concepts are realised as a small property graph — **private to the engine**,
never shown to the user (otherwise we've built a generic graph editor, not Pensieve):

- **Streams & threads are `nodes`.** A node has a **`kind`** (§7) and a **`position`**:
  *top-level* (a stream) vs *contained* (a thread). Position is just the `contains`
  parent. **Promote / condense = re-attaching that one parent** (position change, never
  a kind change).
- **A note↔node link is an `attachment`** (many-to-many) — what makes notes multi-homed.
- **A note↔entity link is a `tag`** — the pre-node form of an entity; `COUNT(tag)` is the
  promotion counter.
- **A node↔node typed link is an `edge`** (§8) — a *later, lighter* concern; much
  "relating" already happens via shared (multi-homed) notes.

So: graph **model** · relational **storage** (SQLite) · Zettelkasten/Topic-Maps
**philosophy** — three independent layers.

---

## 7. Node kinds ✅

A node (stream or thread) — and an entity once promoted — has a **kind**. A kind earns
first-class status **only if the agent treats it differently**; otherwise it's a label.
Lazy rule: **stay a tag/property until you recur or need your own node.**

| kind | predefined properties | notes |
| --- | --- | --- |
| **subject** | `purpose` (if a stream), `status` | the work spine — domains/projects. Usual stream kind. |
| **person** | `name`, `role`, `status` | someone you track |
| **org** | `name`, `description` | a collective you deal with |
| **place** | `name`, `location` | a location; anchors events |
| **event** | `name`, `when`, `status` (upcoming/past) | time-anchored |
| **asset** | `location`, `sub_kind` (file/image/dir/repo/link), `label` | a pointer to external content; engine stores the pointer, agent resolves on demand |

Shared by every node: `id`, `label`, `kind`, `created`, `updated`. New kinds added on
demand, not up front.

---

## 8. Edges (deferred — node↔node typed links) ⏸️

Typed relationships between nodes: `located-in` (event→place), `requested-by`
(subject→person), `attended`/`participates-in` (person→event), `about` (node→node),
`relates-to` (fallback). **Deferred past slice 5** — in the current model a lot of
relating is carried implicitly by **multi-homed notes** (a note on both `rafia` and
`curator-outreach` links them). Revisit when that proves insufficient.

---

## 9. Running example (recs)

```
recs (stream · subject · purpose: "build and grow Recs")
  notes: "talking to 4 curators", …
  └─ rafia (thread · person)            ← promoted once she recurred (≥ threshold)
       attached notes (multi-homed; also still on recs where relevant):
         "Rafia runs The Reader Life — hello@thereaderlife.com"
         "Partnership: early-curator, not paid sponsorship"   (also a recs-level note)
         "Meeting Fri Jun 26 → rescheduled to Tue Jun 30 (weak internet)"
```

`COUNT(notes tagged rafia) ≥ 5` → proposed → `rafia` thread created → her notes
attached. The partnership note stays on `recs` too (it's a recs-level fact *and* a Rafia
fact) — no triage needed.

---

## 10. Storage (not vocabulary — noted to prevent confusion)

SQLite, **private to the engine** (`nodes` + `notes` + `attachments` + `tags`, plus
later `edges`). The agent sees the model only via tools/diffs, so storage is
**swappable** behind the engine. Schema is owned by **Alembic** migrations.

---

## 11. Cut / deferred (so we don't re-litigate)

- ❌ **flavor** (`decision`/`outcome`/`observation`) — cut. It changed no behaviour;
  type is inferred at read time, not stamped.
- ❌ **supersede** (as an op/link) — cut. World-changes are new notes; currency is read,
  not linked. (Fixing a *mistake* is a plain `update`.)
- ❌ **todo / task / question / open-closed lifecycle** — cut. That's a *project-
  management* layer; it lives in other tools (see §0). Everything here is a note.
- ❌ **commit-log / `History` table** — cut. Mutable-by-correction notes don't need an
  append-only commit log; provenance (`created` + `actor`) lives **on the note**.
- ⏸️ **edges** (node↔node typed links) — deferred (§8).
- ⏸️ **condense / tidy** — deferred; when it lands it *summarises while preserving the
  insight* (it keeps "rescheduled twice", never flattens it away).

---

## 12. ❓ Open questions

- **`org` vs `person`** — keep separate or fold into one `contact` kind?
- **`place`** — weakest distinct behaviour; lean on the lazy rule.
- **Entity resolution** — how the agent canonicalises mentions ("Rafia" = "her") and how
  a tag is keyed (normalised string? per-stream registry?). The make-or-break of §4;
  pinned down in `slice-5b`.
- **Promotion target** — thread-under-a-stream vs a new stream: the routing judgment at
  proposal time.
