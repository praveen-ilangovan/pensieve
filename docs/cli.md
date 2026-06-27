# Pensieve — CLI reference

> The CLI is the engine's **op surface** (mechanical), organised by concept. It mirrors
> the model: **streams · threads · notes · entities**. The judgment-bearing `capture` /
> `fetch` *flows* are the agent's job (the skill), not CLI commands. *(The CLI is mostly
> for dev/testing; agents use the MCP tools.)*

## Shape: `pensieve <noun> <verb>`

### Top-level
| command | what |
| --- | --- |
| `pensieve init` | create/migrate the store (idempotent) |
| `pensieve show <id>` | show a **stream/thread** (its threads + notes) or an **entity** (its notes) — universal |
| `pensieve find <q> [--type stream\|thread\|entity]` | fuzzy-search across streams, threads, entities |

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
| `pensieve note add <text> -s <stream>` | add a note to a stream (notes reach a thread by tagging an entity, not directly) |
| `pensieve note edit <id> <text>` | rewrite a note (fix a mistake; a world-change is a *new* note) |
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
