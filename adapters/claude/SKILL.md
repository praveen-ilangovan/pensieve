---
name: pensieve
description: The user's personal Pensieve memory — a persistent, multi-stream knowledge graph that survives across sessions. Use whenever the user mentions "pensieve", asks about "my streams" / "my memory" / "what have I saved", says "add this to pensieve" / "remember this" / "save this", or wants to recall/resume durable context. Reads and writes via the pensieve MCP tools.
---

# Pensieve

Pensieve is the user's **manually-triggered, multi-stream memory** — a personal
knowledge graph of **streams** (top-level domains of their work/life, e.g. `recs`,
`employment`, `writing`), each holding **notes**. It persists across sessions.

Operate it through the **`pensieve` MCP tools**. **You judge; the engine writes** — never
edit the store directly.

## When to reach for this skill
- The user says "pensieve", "my streams", "my memory", "what have I saved".
- **"add this to pensieve" / "remember this" / "save this"** → run **capture**.
- **"what's in pensieve" / "what's in <stream>" / resuming** → run **fetch**.
- The user wants to see or create a stream.

## Vocabulary (important)
- Speak in **streams** and **notes** only. **Never** expose internal terms — *node*,
  *edge*, *thread*. (If a tool error leaks "node", say "stream".)
- **`capture`** and **`fetch`** are *your* flows (they take judgment). `add_note` /
  `get_stream` are the engine *ops* you call. **Calling `add_note` is not capturing** —
  you do the routing and get the user's OK *around* it.

## Tools (the `pensieve` MCP server)
- **`list_streams()`** — the index (`id`, `label`, `purpose`). Load this before routing.
- **`create_stream(name, purpose)`** — a new top-level domain (deliberate; confirm first).
- **`add_note(stream, text, flavor?)`** — append a note (the commit step).
- **`get_stream(stream)`** — a stream's thin view (identity, purpose, notes).

## CAPTURE — "add this to pensieve"
The user points at something worth remembering; you structure and route it.

1. **Filter.** Keep **durable state** — decisions, status, who/what is in play,
   commitments. Drop advice you just delivered, small talk, transient reasoning. (Most of
   a conversation is droppable; the residue is what changed.)
2. **Load the index** — call `list_streams`.
3. **Decide placement, propose once, get an OK:**
   - fits an existing stream → propose that stream;
   - fits none and looks **enduring** → propose a **new stream** (name + one-line
     purpose); don't create thin, one-off streams;
   - the user named a stream → use it (no need to ask which).
4. **Tidy the text** so it stands alone, and **pin relative dates to absolute**
   ("Tuesday" → the actual date).
5. On approval → `add_note(stream, text[, flavor])`. `flavor` is optional:
   `decision` | `outcome` | `observation`.
6. **Confirm briefly** — what landed where.

Everything is captured as a **note** for now. Don't try to split out people/sub-topics
as separate entries — if something seems to deserve its own place, surface it as a
question rather than guessing.

## FETCH — "what's in pensieve / in <stream>"
1. Named a stream → `get_stream(it)`. Vague → `list_streams` and ask which (or show the
   index).
2. Render the thin view **tightly**: the purpose, then the notes (oldest → newest).
   Don't dump everything — summarise if it's long.

## Discipline
- **Propose once; don't interrogate.** The approval is the safety net — keep friction low.
- Streams are **deliberate and few-but-strong**; a stream's `purpose` is enduring and
  rarely changes.
- **Surface ambiguity, don't guess** — if placement or keep/drop is genuinely unclear,
  ask.
- Keep replies tight: the user wants their memory, not a lecture.

> **First capture/fetch pass.** The fuller routing/keep rules (R1–R9) and the
> counter-driven note→node promotion are coming (see the project's `verbs.md`). For now:
> capture as notes, route to streams, and surface anything ambiguous.
