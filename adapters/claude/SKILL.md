---
name: pensieve
description: The user's personal Pensieve memory — a persistent, self-organising knowledge base that survives across sessions. Use whenever the user mentions "pensieve", asks about "my streams" / "my memory" / "what have I saved", says "add this to pensieve" / "remember this" / "save this", asks "what do I know about <someone/something>", or wants to recall/resume durable context. Reads and writes via the pensieve MCP tools.
---

# Pensieve

Pensieve is the user's **manually-triggered memory** — an information lake that *groups
itself*. Four things:

- **stream** — a top-level domain (`recs`, `employment`).
- **thread** — a focused sub-topic inside a stream (e.g. a person who recurs).
- **note** — an atomic piece of information (the unit you capture).
- **entity** — a named thing notes refer to (a person/org/topic). Notes get **tagged**
  with the entities they mention; once an entity recurs enough, it can earn its own
  **thread**.

Operate it through the **`pensieve` MCP tools**. **You judge; the engine writes** — never
edit the store directly.

## Vocabulary
- Speak in **streams**, **threads**, **notes**, and the **real names** of things ("Rafia",
  "the meeting"). Never expose storage mechanics — *node, edge, attachment, tag* (if a tool
  error leaks "node", say "stream"/"thread").
- **`capture`** / **`fetch`** are *your* flows (judgment). The MCP tools are mechanical
  ops you compose; calling `add_note` isn't capturing — you route, resolve, and get the
  user's OK *around* it.

## Tools
- `list_streams()` — the stream index (load before routing).
- `create_stream(name, purpose)` — a new domain (deliberate; confirm first).
- `list_entities()` — the entity registry with note counts + `promotable` flag.
- `find_entities(query)` — fuzzy search the registry (resolve a mention; recall).
- `add_note(stream, text, entities=[…])` — record a note + tag the entities it mentions.
- `get_stream(stream)` — a stream's (or thread's) view.
- `get_entity(entity)` — everything about an entity (its notes), promoted or not.
- `promote_entity(entity, stream)` — give a recurring entity its own thread.
- `update_note(note, text)` / `delete_note(note)` — fix a mistake / truly remove.

## CAPTURE — "add this to pensieve"
1. **Filter.** Keep **durable state** — decisions, status, who/what is in play,
   commitments. Drop advice you just delivered, small talk, transient reasoning. (Most of
   a conversation is droppable; the residue is what changed.)
2. **Load context.** `list_streams` (routing) **and** `list_entities` (resolution).
3. **Route** to a stream: an existing one if it fits; a **new stream** (name + one-line
   purpose) only if it's a genuinely enduring new domain; or the stream the user named.
4. **Resolve entities** in the note — the part that makes memory cohere:
   - For each person/org/recurring topic mentioned, **match it to an existing entity** and
     reuse its id; only create a new one if it's genuinely novel. **"Rafia", "Rafia
     Naseem", "her" are the same entity** — use `find_entities` to check before creating,
     so you never make duplicates.
   - Pass them as `entities`: `{"id": "<existing>"}` to reuse, or
     `{"name": "Travis King", "kind": "person", "aliases": [...]}` for a new one.
   - **What to tag — what the note is *about*, not merely what it *mentions*.** People,
     orgs, recurring topics/projects the note is genuinely about. **Not** dates, values,
     incidental nouns, and **not** an overview/stream-level note's name-drops (e.g. "Recs
     is an app, 4 curators, Rafia leading" is *about Recs*, not about Rafia — leave it
     untagged so it stays in the stream). When unsure, don't tag — or ask.
5. **Tidy** the text so it stands alone; **pin relative dates to absolute** ("Tuesday" →
   the actual date).
6. On approval → `add_note(stream, text, entities=[…])`.
7. **Promotion check** (below). Then **confirm briefly** — what landed where.

> A change in the world is a **new note**, not an edit. Use `update_note` only to fix a
> genuine mistake; `delete_note` only to truly remove. (Memory keeps history — "the
> meeting moved" is worth remembering.)

## PROMOTION — when something recurs
After capture (or when the user focuses on someone), check `list_entities`. If an entity
is **`promotable`** (it's crossed the threshold), **propose** it — don't do it silently:

> "Rafia's come up across 5 notes now — want her own thread under `recs`?"

On approval → `promote_entity(entity, stream)`. It gathers her notes under a dedicated
thread, so next time "what about Rafia?" is instant. Never auto-promote; it's a proposal.

## FETCH / RECALL
- **"what's in <stream>"** → `get_stream`. Render tightly (purpose, then notes); summarise
  if long. Vague? `list_streams` and ask which.
- **"what do I know about <someone/something>"** → `find_entities` to locate it, then
  `get_entity` for its notes (works whether or not it's a thread yet).

## Discipline
- **Resolve before creating** — the cardinal rule; a duplicated entity fragments the
  memory.
- **Propose once; don't interrogate.** Approval is the safety net — keep friction low.
- Streams are **deliberate and few-but-strong**; promotion is **proposed, never automatic**.
- **Surface ambiguity, don't guess.** Keep replies tight — the user wants their memory,
  not a lecture.
