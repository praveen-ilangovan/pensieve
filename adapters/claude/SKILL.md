---
name: pensieve
description: The user's personal Pensieve memory — a persistent, multi-stream knowledge graph that survives across sessions. Use whenever the user mentions "pensieve", asks about "my streams" / "my memory", asks what they've saved, or wants to record or recall durable context. Reads and writes via the pensieve MCP tools.
---

# Pensieve

Pensieve is the user's **manually-triggered, multi-stream memory** — a personal
knowledge graph of **streams** (top-level domains of their work/life, e.g. `recs`,
`employment`, `writing`). It persists across sessions in `~/.pensieve`.

Operate it through the **`pensieve` MCP tools**. Never edit the store directly.

## When to reach for this skill
- The user says "pensieve", "my streams", "my memory", or "what have I saved".
- The user asks to **see** their streams or **create** one.
- (Growing) capturing durable context at the end of a session, or recalling it at the
  start.

## Tools (via the `pensieve` MCP server)
- **`list_streams()`** — list the user's streams (`id`, `label`, `purpose`).
- **`create_stream(name, purpose)`** — create a new stream (a top-level domain).

## How to behave
- **"What streams do I have?"** → call `list_streams`, report them plainly.
- **Creating a stream** → streams are **deliberate**. Confirm the name and a one-line
  `purpose` first; don't auto-create or invent streams the user didn't ask for. Prefer
  *fewer, stronger* streams over many thin ones.
- A stream's **purpose** is its enduring reason for existing (rarely changes) — not a
  passing task.
- Keep replies tight: the user wants their memory, not a lecture.
