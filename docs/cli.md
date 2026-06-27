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
| `pensieve entity rm <id>` | remove an entity + its thread (**soft**; purges its notes — notes/entities riding only those go too) |
| `pensieve entity restore <id>` | bring back a removed entity (its notes + thread) |

## Notes on the shape
- **No `thread` namespace** — a thread is the same *type* as a stream (a node), just
  positioned under one. You `show <stream>` to see its threads, then `show <thread>`.
  Threads are *born* from `entity promote`, never created directly.
- **`show` is universal** — streams, threads, and entities are all "things you look at."
- **Ids are stable slugs** (globally unique across nodes). A promoted entity's id *is*
  its thread node's id.
- **`rm` is a soft-delete** — reversible with `restore`. Removal is **note-centric and
  derived**: entities are alive iff they still have ≥1 *live* note (a live note is one
  that isn't deleted and is still attached to a visible node). So removing a stream or an
  entity ripples through to the entities that no longer have any reason to exist, while a
  note shared with another stream — or a plain entity-less note — survives. A future
  `forget` will hard-delete.
