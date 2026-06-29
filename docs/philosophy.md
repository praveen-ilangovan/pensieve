# Pensieve — Philosophy & Model

> The thinking behind Pensieve and the model it produces — the deeper companion to the
> [README](../README.md). The README tells you *what it is and how to use it*; this tells you
> *why it's shaped this way and how it's organised*. The command surface is in
> [`cli.md`](cli.md); the agent flows live in [`adapters/claude/SKILL.md`](../adapters/claude/SKILL.md).

---

## What Pensieve is — and is not

Pensieve is an **information lake**: a personal memory substrate whose job is to **remember**,
not to act. You pour pieces of information in; later you (or an agent) read them back to
recall facts *and notice patterns*.

> **The guiding non-goal — Pensieve remembers; it does not act.** Scheduling, tasking,
> reminding, sending — those live in *other* tools (calendar, todo app, email) that an agent
> drives **from** Pensieve's memory. If a proposed feature is about *doing* something rather
> than *recording or recalling* it, it doesn't belong here. That one line answers a whole
> class of "should Pensieve also do X?" — no.

---

## The principles

Five ideas drive every decision:

1. **An information lake, not a project manager.** It stores *what you know* and recalls it —
   no tasks, statuses, due dates, or open/closed lifecycles. State is *inferred at read time*
   by the agent, not stamped on the data.

2. **Deliberate on both ends.** Pensieve never acts on its own. It writes only when you ask
   ("add this to pensieve") and recalls only when you ask ("what do I know about X?"). No
   silent saves, no auto-loading your memory at the start of a session.

3. **Structure emerges; you don't design it upfront.** You keep a few deliberate top-level
   **streams** and drop notes in. The people/orgs/topics your notes mention become **entities**
   automatically, and one that recurs enough earns its own **thread**. Organisation is a
   *consequence of use*, not a taxonomy you maintain.

4. **Notes are the atoms; everything else references them.** A note can stand alone or live in
   several streams. Entities and threads are *views over notes*, not owners — so removing a
   topic never destroys a note that's also about something else.

5. **Point at the world, don't copy it.** External context (a repo, file, URL) is an **asset**:
   a by-reference pointer plus a usage hint. Pensieve stores the pointer and reads it *on
   demand*; it never crawls your disk or follows a link on its own.

---

## The model

Everything you interact with is a handful of concepts:

- **Stream** — a top-level **domain** of your life/work (`career`, `personal`,
  `side-projects`). Has a `purpose` (its enduring reason to exist). Deliberate and few.
- **Note** — an **atomic piece of information**. *Everything starts life as a note.* It's
  attached to one or more streams (multi-homed), references zero-or-more entities, and carries
  a date + provenance.
- **Entity** — a **named thing a note is about** (a person, org, topic). It lives as a
  *reference on notes* until it recurs enough to earn its own thread.
- **Thread** — an entity (or sub-topic) **promoted** into a focused node under a stream
  (`maya`, `interview-prep`). A thread lives under exactly one stream.
- **Asset** — a **by-reference pointer** (repo / file / dir / URL / image / doc) + a one-line
  usage hint, attached to a stream, thread, or note.

### The relationships

| relationship | cardinality | meaning |
| --- | --- | --- |
| Stream → Thread | `1 — N` | a thread sits under one stream; a stream has many |
| Note → Stream/Thread | `N — M` | a note is **multi-homed** — in one *or several* streams |
| Note → Entity | `N — M` | a note references 0+ entities; an entity spans many notes |
| Asset → owner | `N — 1` | an asset points from exactly one owner (a note **or** a node) |
| Entity → Thread | promotion | a recurring entity is promoted into its own node; its notes attach there too |

**Lifecycle in one sentence:** information lands as a **note** → entities accumulate
references across notes → when an entity recurs and is queried, it's **proposed for
promotion** into its own **thread**, and its notes attach there.

---

## Notes — append-only information

A note holds one piece of information. The model is deliberately tiny — fancy concepts were a
*reliability* problem (the agent fumbles them), not just clutter.

- **Append is the default.** New information — *including a change in the world* — is a **new
  note**. "Meeting was Tuesday" then "moved to Wednesday" are **two notes**, on purpose: the
  *change itself is memory* (it's how you later notice "this always slips"). Overwriting would
  destroy that.
- **The present is derived by reading.** "What's true now?" comes from reading notes in time
  order — not from a stored `supersede` link or a `flavor` tag. Currency is inferred.
- **Edit only to fix a genuine mistake** (a typo, a wrong value you recorded); **remove** only
  to take something out (softly — see below).
- **Safety asymmetry** — *why append is the safe default:* a wrong append costs a little
  redundancy; a wrong overwrite loses memory. When unsure, add.

A note carries text, its stream/thread homes, entity references, a date, and provenance
(`created` + `actor`, e.g. `claude-code` or `cli`). No flavour, no type, no open/closed state.

---

## Entities & promotion

An **entity** is a named thing notes refer to. Before it earns a node it's just a *reference
(tag) on notes*, carrying a provisional **kind** (person/org/topic/…).

- **Count is derived** — `COUNT(live notes referencing the entity)`, never a stored counter,
  so it can't drift.
- **Threshold** — when the count crosses a configurable threshold (default **5**) the entity
  becomes a promotion candidate.
- **Promotion is proposed, never automatic** — surfaced for approval at a natural moment (a
  capture that touches it, or a query for it: "you ask about Maya a lot — give her a thread?").
  The *proposal* may ride on a read; the *mutation* never does.
- **Promotion is additive** — create the entity's node (a thread under a stream) and attach
  every note that references it. Prior attachments stay; nothing moves, nothing is lost
  (a note can be multi-homed).

The hard part is **resolution** — knowing "Maya", "Maya Chen", and "she" are the same entity.
That judgment (by the agent, at capture) is the real new capability; counting and promotion
are easy on top of it.

---

## Removal — bottom-up and reversible

Removal follows the ownership arrow (principle 4): **notes are owned by streams; entities and
threads only reference notes.** So:

- **`rm` is a soft-delete** — reversible with `restore`. (A future `forget` will hard-delete.)
- **Remove a note** → it's hidden; an entity that loses its last live note simply *derives
  away*.
- **Remove a stream** → its notes go with it, **but** a note also homed in another stream
  survives there — so cross-stream entities live on, and only the truly-orphaned vanish.
- **Remove an entity/thread** → it **unlinks** from its notes; it never deletes a note. A note
  shared with another subject survives under that subject; one left with no subject becomes a
  plain note.

Nothing cascades destructively, and everything comes back on `restore`.

---

## Recall — three lenses + the thin view

You reach memory three ways, each in its own natural order:

- **By name** (`find`) — match a stream/thread/entity by label or alias.
- **By content** (`search`) — full-text over note prose (stemmed, ranked) *and* asset pointers.
  For "what did we decide about X" when nothing is named X.
- **By time** (`recent`) — the newest-added/edited notes across the whole memory. "What
  changed lately."

And the **thin view**: fetching a stream shows *its own loose notes + a summary of its child
threads*, not every note in every descendant. A promoted entity turns entity-recall into a
direct lookup ("what about Maya" → her thread) instead of scan-and-filter — which is *why*
promotion exists.

---

## Assets — pointers to live context

An asset is the bridge between durable memory and the current working world. A note rots as
prose; a pointer to `~/projects/acme` stays fresh because it's read *on demand* when relevant.

- **By reference only** — Pensieve stores the path/URL + a usage hint ("read README.md
  first"), never the contents.
- **Read on demand, never automatically** — following an asset is a deliberate, user-visible
  step. Local paths are low-risk; **remote URLs/images are an injection surface** and get
  caution.
- **Visibility is derived** from the owner — remove the owning note/stream/thread and its
  assets hide; restore and they return.

---

## Under the hood (never user-facing)

- The concepts are realised as a small **property graph** — streams/threads are `nodes`
  (a `kind` × a position: top-level vs contained), a note↔node link is an `attachment`
  (multi-homing), a note↔entity link is a `tag`, and node↔node typed `edges` are reserved for
  later (most "relating" already happens via shared multi-homed notes).
- **SQLite** storage (`~/.pensieve`), schema owned by Alembic migrations; **FTS5 + porter**
  powers content search. The agent only ever sees the model via tools, so storage is
  **swappable** behind a clean port (there's a second, in-memory backend used in tests).
- Graph **model** · relational **storage** · Zettelkasten/topic-map **philosophy** — three
  independent layers.

---

## Deliberately cut / deferred

So we don't re-litigate:

- **Cut:** note `flavor`/`type` tags · a `supersede` op · todo/task/open-closed lifecycle ·
  an append-only commit log — replaced by "everything is a note; state is read, not stamped"
  (provenance lives on the note).
- **Cut:** auto-hydrate (loading memory at session start) — violates principle 2.
- **Deferred:** node↔node typed edges · consolidation ("digest old notes while keeping the raw
  history") · an `export`/backup path. See [`../plans/roadmap.md`](../plans/roadmap.md).
