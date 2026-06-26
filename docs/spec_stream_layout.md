# Pensieve — Spec 1: Data Model (SUPERSEDED → see `glossary.md`)

> **Status:** superseded 2026-06-26 by the graph reframe. Kept as a stub so links
> don't break — **do not build from this file.**

The canonical data model is now the **property graph**, defined in:

- **`glossary.md`** — the nouns: nodes · edges · properties · kinds · positions.
- **`verbs.md`** — the ops + judgment rules + capture model.

This file originally described the **pre-graph, per-stream model** — a stream with
fixed `state` fields (`current_focus` / `goals` / `open_loops` / `next_actions`) plus
`references` / `context` / `decisions` / `insights` / `history`. That model was
**generalized into the graph**: a stream is a top-level `subject` node; goals/loops/
actions became `todo` contents; decisions/insights became `note`s (with a `flavor`);
references became `asset` child-nodes; context became `person` child-nodes; history is
the per-node commit log.

**Use `glossary.md`.**
