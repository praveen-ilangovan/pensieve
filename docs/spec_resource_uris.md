# Pensieve — Spec 2: Resource URIs (the read surface)

> **Status:** reconciled to the graph model · **Date:** 2026-06-27
> **Depends on:** `glossary.md` (the model/nouns) · `verbs.md` (the writes)

The **read** surface. Every **node** and its parts are addressable by URI. Reads are
**lazy / on-demand**; writes go through the diff (`verbs.md`), never here. Each URI
returns **canonical JSON**.

**Storage-agnostic:** the agent only speaks URIs. The engine translates each into
queries against its store (SQLite; `spec_engine_contract.md`) and assembles the JSON.
The on-disk format is invisible.

---

## 1. Grammar

```
uri  = "stream://" ( "_index" / node-id [ "/" sub ] )
sub  = "notes"    [ "/" note-id ]
     / "todos"    [ "/" todo-id ]
     / "children" 
     / "edges"
     / "history"  [ "/" commit-id ]
```

- `stream://` is the Pensieve resource scheme; it addresses **any node by its id** —
  a top-level node (a "stream") *or* a contained node (a "thread"). (The scheme name
  is legacy; everything is a node now.)
- **Reserved:** ids beginning with `_` (e.g. `_index`).
- A bare collection (`…/notes`) returns the **list**; appending an id returns the
  **single item**.
- There is **no `…/state`, `…/references`, `…/context`, `…/decisions`, `…/insights`**
  — those pre-graph sub-resources are gone. State is node *properties* + *contents*;
  references are `asset` child-nodes; context is `person` child-nodes; decisions/
  insights are `note`s. Reach them via `…/children`, `…/notes`, or by the child's own
  `stream://<child-id>`.

---

## 2. The map

| URI | Returns |
| --- | --- |
| `stream://_index` | the registry — all **top-level** nodes (id, label, kind, purpose, status) |
| `stream://<id>` | the **composed thin view** (the `fetch` payload) — see below |
| `stream://<id>/notes` (`/<note-id>`) | the node's notes (append-only log) |
| `stream://<id>/todos` (`/<todo-id>`) | the node's open todos |
| `stream://<id>/children` | contained nodes (id, label, kind) |
| `stream://<id>/edges` | the node's typed relationships (non-`contains` edges) |
| `stream://<id>/history` (`/<commit-id>`) | the node's commit log |

### The composed thin view (`stream://<id>`) — what `fetch` loads

Identity + key properties + open todos + `suggested_reads` + the **child list**
(id/label/kind) + outgoing edges. **Not** included: the full note log, history,
child *contents*, or resolved asset contents — those are on-demand.

```json
{
  "id": "recs", "label": "Recs", "kind": "subject", "position": "top-level",
  "properties": { "purpose": "Build and grow Recs", "status": "growth + retention" },
  "todos": [ { "id": "act-9", "text": "instrument step-3 of signup", "state": "open" } ],
  "suggested_reads": [ "stream://recs/notes?limit=5", "stream://recs/children" ],
  "children": [
    { "id": "rafia",       "label": "Rafia",        "kind": "person" },
    { "id": "mcp-layer",   "label": "MCP layer",    "kind": "subject" },
    { "id": "recs-claude", "label": "Recs CLAUDE.md","kind": "asset" }
  ],
  "edges": [ { "to": "writing", "kind": "relates-to" } ]
}
```

- A child is itself a node → fetch `stream://rafia` for its thin view, or
  `stream://rafia/notes` for its log. This is the fractal payoff: **one uniform
  shape at every level**, no special-case sub-resources.
- **Asset nodes are pointer-only:** `stream://recs-claude` returns the pointer
  (`location`/`kind`); the engine never reads the file — the agent fetches it on
  demand.

---

## 3. Filtering & pagination

| Param | Applies to | Meaning |
| --- | --- | --- |
| `?limit=N` | `notes`, `history`, `children` | cap returned items (most-recent first) |

`?limit` covers the "recent notes" need that `suggested_reads` leans on.
**`?since=` / `?q=` deferred** until a collection is actually too big.

---

## 4. MCP & CLI mapping

- **MCP:** each URI is an MCP **Resource** (`uri`, `name`, `mimeType:
  application/json`, `text`: the JSON), enumerable via `resources/list`. **Read-only**
  by contract.
- **CLI / non-MCP agents:** `pensieve get <uri>` (and `pensieve ls` ≈
  `stream://_index`).
- **Pointer-only resolution:** reading an `asset` node returns its pointer, never the
  content — fetching content is the agent's job, by design.
