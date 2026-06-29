# Pensieve

**A personal, agent-driven memory that survives across sessions.**

You talk to an AI assistant (Claude Code) every day, but it forgets everything between
sessions. Pensieve is the long-term memory you control: at the end of a session you say
*"add this to pensieve,"* and next time you say *"what do I know about X?"* and it's there —
organised, current, and yours.

> The metaphor: deliberately draw out a strand of thought and deposit it in the vessel for
> later. (Formerly codenamed "Memory Stick".)

It's a small **Python + SQLite** engine with two front doors: an **MCP server** the agent
uses, and a **CLI** for you. Your memory lives in a single file at `~/.pensieve`.

---

## Philosophy

Five ideas shape every decision in Pensieve:

1. **An information lake, not a project manager.** It stores *what you know* and lets you
   recall it. It deliberately has no tasks, statuses, or due dates — the agent infers state
   by reading, the store just holds the information.

2. **Deliberate on both ends.** Pensieve never acts on its own. It writes only when you say
   *"remember this,"* and recalls only when you *ask*. No silent saves, no auto-loading your
   memory at the start of a session. You stay in control of what goes in and what comes out.

3. **Structure emerges; you don't design it upfront.** You don't build a taxonomy. You keep
   a few top-level **streams** (the domains you actually work in) and drop notes in. The
   people, orgs and topics your notes mention become **entities** automatically, and one that
   keeps recurring earns its own **thread**. Organisation is a *consequence of use*.

4. **Notes are the atoms; everything else references them.** A note can stand alone or live
   in several streams at once. Entities and threads are *views over notes*, not owners of
   them — so removing a topic never destroys a note that's also about something else.

5. **Point at the world, don't copy it.** Attach a repo, file or URL as an **asset** — a
   by-reference pointer with a one-line "how to use me" hint. Pensieve stores the pointer and
   reads it *on demand*; it never crawls your disk or follows a link on its own.

---

## The model

| Thing | What it is |
|---|---|
| **stream** | A top-level domain of your work/life — `recs`, `employment`, `writing`. Deliberate and few. |
| **note** | An atomic piece of information — the unit you capture. Can live in more than one stream. |
| **entity** | A person / org / topic your notes are *about*. Born from a note (by tagging); never created in a vacuum. |
| **thread** | An entity that recurred enough to earn its own focused sub-topic under a stream. |
| **asset** | A by-reference pointer (repo / file / dir / URL / image / doc) + a usage hint, attached to a stream, thread, or note. |

**Recall has three lenses:** by **name** (`find`), by **content** (`search` — full-text,
stemmed, ranked), and by **time** (`recent` — what changed lately).

---

## Install

Assumes Python 3.12+.

```bash
git clone git@github.com:praveen-ilangovan/pensieve.git
cd pensieve
./install.sh
```

`install.sh` checks prerequisites up front (and changes nothing if any are missing), ensures
`pipx`, installs Pensieve (`pensieve` + `pensieve-mcp` on your PATH), drops the agent skill
into `~/.claude/skills/pensieve/`, and registers the MCP server with Claude Code (user
scope). It's **idempotent** — re-run anytime to pick up updates.

Then **restart Claude Code** and, from any directory:

> "what streams do I have? check pensieve"

Your memory lives in `~/.pensieve`.

---

## Using it (with the agent)

Pensieve shines through the agent — you speak naturally, it does the judgment and calls the
tools. Everything below is just *talking to Claude Code*.

**Set up your domains** (do this once, deliberately):
> "Create a pensieve stream called Recs — for building my recommendations app."

**Capture** — the end-of-session move:
> "Add this to pensieve: we're talking to 4 curators, Rafia is the furthest along."

The agent filters for what's *durable*, routes it to the right stream, and recognises that
"Rafia" is a person worth tracking — without you managing any of that. If a note spans two
domains (an article that's about *Writing* and *Recs*), it files **one** note in both.

**Recall** — pick the lens that fits the question:
> "What do I know about Rafia?" · "What did we decide about pricing?" · "Catch me up — what's
> changed lately?"

**Point at live context** — so the agent knows where to read:
> "Add my Recs repo at ~/code/recs as an asset on the Recs stream — hint: read CLAUDE.md
> first." Later: "pull up the Recs repo." (It follows the pointer only when you ask.)

**Promote** — when something recurs, the agent proposes it:
> "Rafia's come up across 5 notes — want her own thread under Recs?"

**Remove / restore** — everything is soft and reversible:
> "Remove that note." / "Actually, bring it back." / "I'm done with the X stream."

---

## Using it (the CLI)

The CLI is the same engine, for when you want it directly (it's also handy for scripting).
Full reference: [`docs/cli.md`](docs/cli.md).

```bash
pensieve stream create Recs -p "Build Recs"   # a domain
pensieve note add "met Rafia" -s recs         # a note (repeat -s for several streams)
pensieve show recs                            # a stream's threads + notes + assets
pensieve search "pricing"                     # full-text recall (stemmed)
pensieve recent --since 2026-06-01            # what changed
pensieve find rafia                           # by name
pensieve asset add recs ~/code/recs --hint "read CLAUDE.md first"
```

Nouns and their verbs: `stream` (create/list/edit/rm/restore), `note`
(add/edit/rm/restore/file/unfile), `entity` (link/unlink/list/promote/edit/rm/restore),
`asset` (add/list/rm), plus top-level `show`, `find`, `search`, `recent`.

---

## How it works (under the hood)

- **SQLite** store (`~/.pensieve`), self-migrating via Alembic on first use.
- **Full-text search** via SQLite FTS5 + a porter stemmer (so "pricing" recalls "priced").
- A clean **ports/adapters** core: services depend on a storage *port* with two
  interchangeable backends (SQLite + an in-memory double), kept honest by a conformance test.
- The **MCP server** and **CLI** are thin "op" layers; the *judgment* (what to keep, how to
  resolve an entity, when to promote) lives in the agent **skill** (`adapters/claude/`).

---

## Develop on it

```bash
make install         # poetry env + pre-commit hooks
make test            # unit + integration
make eval            # deterministic engine evaluators
make check           # ruff (lint+format) + mypy
make manual ARGS="stream list"   # run the CLI against the local dev store
```

This repo is a self-contained **dev environment** — it never touches your real `~/.pensieve`.
The in-repo MCP server and CLI use a local dev store (`.env` → `.local/manual`); the global
install (`./install.sh`) is what points at `~/.pensieve`.

Design notes live in [`plans/`](plans) (one file per slice, plus
[`plans/roadmap.md`](plans/roadmap.md)) and [`docs/`](docs) (`cli.md`, `glossary.md`).

---

## Status

Working and in daily use: streams · threads · notes · entities · promotion · assets ·
search · recency · multi-stream notes · soft remove/restore — all via CLI **and** MCP.
Built and validated slice by slice with a real agent. See `plans/roadmap.md` for what's next.
