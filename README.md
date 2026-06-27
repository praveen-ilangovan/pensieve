# Pensieve

A manually-triggered, multi-stream **agent memory**. You *capture* a session's
durable state into a personal **knowledge graph**, and *fetch* it back when you
resume — across sessions and across the domains you actually work in.

> The Pensieve metaphor: deliberately extract a strand of thought and deposit it in
> the vessel. (Formerly codenamed "Memory Stick".)

**Status:** engine build underway — **Python + SQLite**. Shipped: a CLI and an MCP
server for streams (create / list), wired into Claude Code. (Design validated via four
cold-agent vertical-slice runs.)

## Install (use it in Claude Code)

Assumes Python 3.12+ is on your system.

```bash
git clone git@github.com:praveen-ilangovan/pensieve.git
cd pensieve
./install.sh
```

`install.sh` checks prerequisites up front (and changes nothing if any are missing),
ensures `pipx`, installs Pensieve (`pensieve` + `pensieve-mcp` on your PATH), drops the
Claude skill into `~/.claude/skills/pensieve/`, and registers the MCP server
user-scope. It's **idempotent** — re-run it anytime to pick up changes.

Then **restart Claude Code** and, from any directory, ask:

> "what streams do I have? check pensieve"

Your memory lives in `~/.pensieve`. You can also use it as a CLI: `pensieve stream list`,
`pensieve stream create "Travel" -p "…"`, `pensieve show <id>`, `pensieve find <q>`.

### Develop on it
`make install` (poetry env + hooks) · `make test` · `make check` · `make manual ARGS="stream list"`.

This repo is a **dev environment** — nothing global. The project MCP server
(`.mcp.json`, `poetry run`) and the CLI both use the **local dev store**
(`.env` → `.local/manual`), so testing never touches your real memory. The **global**
install (`./install.sh`) is separate and points at `~/.pensieve`; to try the installed
experience, run it and launch Claude Code from **another directory**.

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
