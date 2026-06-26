# Pensieve

A manually-triggered, multi-stream **agent memory**. You *capture* a session's
durable state into a personal **knowledge graph**, and *fetch* it back when you
resume — across sessions and across the domains you actually work in.

> The Pensieve metaphor: deliberately extract a strand of thought and deposit it in
> the vessel. (Formerly codenamed "Memory Stick".)

**Status:** design complete and validated (four cold-agent vertical-slice runs);
engine build starting — **Python + SQLite**.

## What it is, in one breath
A small **property graph** — nodes (`subject` / `person` / `org` / `place` / `event`
/ `asset`) + typed edges + per-node contents (`todo`s and `note`s). The agent reads a
session, distills the *durable* bits, and emits a **diff** of typed ops; the engine
applies it atomically. Two flows: **`capture`** (write) and **`fetch`** (read).

## Read the design
Start with **`docs/handoff.md`** — current state + next steps. Then:

- `docs/glossary.md` — the model (**nouns**: nodes · edges · properties · kinds).
- `docs/verbs.md` — the operations (**verbs**: op catalog · judgment rules · capture model).
- `docs/core_concept.md` — the narrative + decisions log (the *why* / the journey).
- `docs/spec_resource_uris.md` — the read surface (`stream://…` URIs).
- `docs/spec_engine_contract.md` — storage / atomicity / config (SQLite graph schema).
- `brain/PLAYBOOK.md` — the agent-agnostic brain.
