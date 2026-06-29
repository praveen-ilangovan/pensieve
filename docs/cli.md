# Pensieve — CLI reference

> The CLI is the engine's **op surface** (mechanical), organised by concept. It mirrors
> the model: **streams · threads · notes · entities · assets**. The judgment-bearing
> `capture` / `fetch` *flows* are the agent's job (the skill), not CLI commands. *(Day to day
> you'll mostly drive Pensieve through the agent; the CLI is for quick checks and scripting.)*

## A quick taste

```bash
pensieve stream create Career -p "Job search & work"
pensieve note add "called Maya about the role" -s career   # repeat -s for several streams
pensieve show career                                       # threads + notes + assets
pensieve search "salary"                                   # full-text recall (stemmed)
pensieve recent --since 2026-06-01                         # what changed
pensieve find maya                                         # by name
pensieve asset add side-projects ~/projects/acme --hint "read README.md first"
```

## Shape: `pensieve <noun> <verb>`

### Top-level
| command | what |
| --- | --- |
| `pensieve init` | create/migrate the store (idempotent) |
| `pensieve show <id>` | show a **stream/thread** (its threads + notes + assets) or an **entity** (its notes) — universal |
| `pensieve find <q> [--type stream\|thread\|entity]` | fuzzy-search **names** across streams, threads, entities |
| `pensieve search <q>` | full-text **content** recall — note prose (stemmed, ranked) + asset pointers |
| `pensieve recent [--since <iso>] [--limit N]` | newest-added/edited notes across all streams (**time** lens) |

### `stream`
| command | what |
| --- | --- |
| `pensieve stream create <name> [-p <purpose>]` | create a top-level stream |
| `pensieve stream list` | list streams |
| `pensieve stream edit <id> [--name] [-p]` | rename / repurpose (id stays stable) |
| `pensieve stream rm <id>` | remove a stream + its threads (**soft**; notes shared with another stream survive there) |
| `pensieve stream restore <id>` | bring back a removed stream (+ its threads) |

### `note`
| command | what |
| --- | --- |
| `pensieve note add <text> -s <stream> [-s <stream> …]` | add a note to one or more streams (notes reach a thread by tagging an entity, not directly) |
| `pensieve note edit <id> <text>` | rewrite a note (fix a mistake; a world-change is a *new* note) |
| `pensieve note file <id> -s <stream>` | file an existing note into another stream (one note, several homes) |
| `pensieve note unfile <id> -s <stream>` | remove a note from a stream (can't remove its last home — use `rm`) |
| `pensieve note rm <id>` | remove a note (**soft** — an entity that loses its last note vanishes) |
| `pensieve note restore <id>` | bring back a removed note |

### `entity`
| command | what |
| --- | --- |
| `pensieve entity link <note> <name> [-k <kind>]` | link a note to an entity (creates it if new) — this *is* entity creation |
| `pensieve entity unlink <note> <entity-id>` | remove an entity tag from a note (fix a mis-tag; detaches from the thread if promoted) |
| `pensieve entity list` | the registry with counts + `★ promotable` / `✓ promoted` |
| `pensieve entity promote <id> -s <stream>` | promote an entity into its own thread |
| `pensieve entity edit <id> [--name] [--alias]` | rename / edit aliases (id stays stable) |
| `pensieve entity rm <id>` | remove an entity + its thread (**soft**; *unlinks* it from every note — notes are never deleted; a shared note survives under its other subject) |
| `pensieve entity restore <id>` | bring back a removed entity (re-links its notes + thread) |

### `asset`
| command | what |
| --- | --- |
| `pensieve asset add <target> <location> [--hint] [--label] [-k <kind>]` | attach a by-reference pointer (repo/file/dir/URL/image/doc) to a stream/thread/note; kind inferred if omitted |
| `pensieve asset list <target>` | list the assets on a stream/thread/note |
| `pensieve asset rm <asset-id>` | remove an asset pointer (a plain delete — cheap to re-add) |

## Notes on the shape
- **No `thread` namespace** — a thread is the same *type* as a stream (a node), just
  positioned under one. You `show <stream>` to see its threads, then `show <thread>`.
  Threads are *born* from `entity promote`, never created directly.
- **`show` is universal** — streams, threads, and entities are all "things you look at."
- **Ids are stable slugs** (globally unique across nodes). A promoted entity's id *is*
  its thread node's id.
- **`rm` is a soft-delete — and removal is bottom-up.** Notes are the atoms; streams
  *contain* them, entities/threads merely *reference* them. So:
  - **`stream rm`** lets go of the stream's notes (a note also homed in another stream
    stays live there); entities then alive iff they still have ≥1 *live* note (not
    deleted, still attached to a visible node) — pure ones derive away, cross-stream ones
    survive.
  - **`note rm`** hides one note; an entity that loses its last live note derives away.
  - **`entity rm`** *unlinks*, it never deletes a note — a shared note survives under its
    other subject; a note left subject-less becomes a plain note.
  - Everything is reversible with `restore`; a future `forget` will hard-delete.
