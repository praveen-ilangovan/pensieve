# Pensieve — Spec 3: Diff Format (SUPERSEDED → see `verbs.md`)

> **Status:** superseded 2026-06-27 by the graph verb layer. Kept as a stub so links
> don't break — **do not build from this file.**

The write contract — the op catalog, the diff envelope, the judgment rules, and the
capture model — now lives in **`verbs.md`**.

This file originally described the **pre-graph, per-field ops** (`add_goal`,
`close_open_loop`, `append_decision`, `append_insight`, `set_status`, …). Those were
**generalized into graph ops** (`create_node`, `add_note`(+flavor), `add_todo` /
`complete_todo`, `add_edge`, `reparent`, `promote_entry`, `supersede`, `redact`),
validated across four cold-agent runs.

**Use `verbs.md`.**
