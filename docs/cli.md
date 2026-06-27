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
| `pensieve stream edit <id> [--name] [-p]` | rename / repurpose — **stub (planned)** |
| `pensieve stream rm <id>` | delete — **stub (planned)** |

### `note`
| command | what |
| --- | --- |
| `pensieve note add <text> -s <stream>` | add a note to a stream (notes reach a thread by tagging an entity, not directly) |
| `pensieve note edit <id> <text>` | rewrite a note (fix a mistake; a world-change is a *new* note) |
| `pensieve note rm <id>` | delete a note |

### `entity`
| command | what |
| --- | --- |
| `pensieve entity link <note> <name> [-k <kind>]` | link a note to an entity (creates it if new) — this *is* entity creation |
| `pensieve entity list` | the registry with counts + `★ promotable` / `✓ promoted` |
| `pensieve entity promote <id> -s <stream>` | promote an entity into its own thread |
| `pensieve entity edit <id> [--name] [--alias]` | rename / edit aliases — **stub (planned)** |
| `pensieve entity rm <id>` | delete — **stub (planned)** |

## Notes on the shape
- **No `thread` namespace** — a thread is the same *type* as a stream (a node), just
  positioned under one. You `show <stream>` to see its threads, then `show <thread>`.
  Threads are *born* from `entity promote`, never created directly.
- **`show` is universal** — streams, threads, and entities are all "things you look at."
- **Ids are stable slugs** (globally unique across nodes). A promoted entity's id *is*
  its thread node's id.
- **Stubs** (`edit`/`rm`) are surfaced for completeness but not wired — the delete-cascade
  and rename semantics are their own backend layer (open decisions: cascade vs refuse;
  id-immutability on rename).
