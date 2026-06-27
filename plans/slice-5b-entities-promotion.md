# Slice 5b — Entities & Promotion (the self-organising memory)

> **Status:** planned · **Date:** 2026-06-27 · **Model:** `docs/glossary.md` §4 (entities,
> promotion) · **Builds on:** 5a (notes standalone + attachments). **Phase 2 of 2.**

## 1. Goal

Make the memory **group itself**. Recurring things (people, orgs, topics) get recognised
at capture, accumulate, and — past a threshold — earn their **own thread**. After 5b,
"what about Rafia?" is a direct lookup, not a scan of `recs`.

The make-or-break is **entity recognition + resolution** ("Rafia" = "Rafia Naseem" =
"her" → one entity, no duplicates). That's a *language* task → the **agent** does it; the
engine is the **ledger** (entities + tags + counts) and a **candidate-search** helper.

## 2. The resolution strategy (the heart) — engine narrows, agent decides

- **Engine** retrieves candidates cheaply: `find_entities(query)` (fuzzy/substring over
  canonical name + aliases) and `list_entities()` (the whole registry — small now).
  Mechanical, fast; **cannot** do coreference.
- **Agent** does the semantic call: loads/searches existing entities at capture, decides
  *same vs new* (it's what knows "her" = Rafia), and emits tags. Creates a new entity
  **only** when genuinely novel. This prevents the #1 failure mode — **duplication**.
- **Access by size:** load-all (`list_entities`) while tiny (now) → `find_entities` at
  scale. Same agent logic, narrower input.
- The same interface powers **recall**: "what do I know about Rafia?" → `find_entities`
  → the entity → its notes. One mechanism, two jobs (resolution + fetch).

## 3. Model

- **`Entity`** (lighter registry; *not* a node until promoted): `id` (slug, e.g.
  `rafia`), `name` (canonical), `kind` (person/org/topic/…), `aliases` (JSON list),
  `node_id` (null until promoted → points at its thread node), `created`/`updated`.
- **`Tag`**: `(note_id, entity_id)` — note ↔ entity, many-to-many. `COUNT(tags for
  entity)` *is* the promotion counter (derived; nothing stored).
- **Nodes/threads unchanged:** promotion **creates a Node** (parent = target stream → it's
  a thread) and points `entity.node_id` at it. No new node fields (thread = node with a
  parent; `list_streams` already excludes them).
- **Migration `0004`** — create `entities` + `tags`.

## 4. Tagging at capture

`add_note` gains an **`entities`** argument — the agent's resolved output: existing ids
and/or new `{name, kind, aliases}`. In one transaction the engine: creates any new
entities, adds the note, **tags** it, and attaches it to the stream.

- **Tagging a *promoted* entity also attaches the note to its thread node** (so new notes
  show under the thread). Pre-promotion, tagging just records the tag (for counting).

## 5. Counts & promotion (propose → approve → materialise)

- `list_entities()` returns each entity with its **count** and a **promotable** flag
  (count ≥ threshold). Threshold is **configurable** — `PENSIEVE_PROMOTION_THRESHOLD`
  (default **5**).
- **Promotion is proposed, never automatic** (R9): the agent surfaces it at the next
  natural moment — a capture touching the entity, or a **query for it** — and only acts on
  approval. Reads stay safe.
- `promote_entity(entity, parent_stream)` (on approval): create the thread node, **attach
  every tagged note** to it (additive — notes keep their stream attachments), set
  `entity.node_id`. Promotion is **non-destructive**; nothing moves.

## 6. Thin-view-as-summary — 📌 PINNED to 5c (not a blocker)

Deferred to its own follow-up (`5c`). Tagging, entity-retrieval, and promotion don't
depend on it, and it carries the one genuinely thorny call (loose-vs-covered) — better
decided later with real promoted data in front of us.

- **Interim behaviour (5b):** a **stream**'s view stays the current **flat note list**
  (`get_stream_view` returns its attached notes); a **thread**'s view is the same op on
  the thread node (its notes). A promoted entity's notes show *both* under its thread and
  inline in the stream (they're attached to both) — slightly redundant, fully functional.
- **5c will add:** stream view = **thread summaries + loose notes**, and settle the
  **loose-vs-covered** rule (the note-4 "partnership is both Rafia *and* recs-level" case).

## 7. Surface (ops / tools)

- **Repo (port + both adapters):** `add_entity`, `get_entity`, `save_entity`,
  `list_entities` (+counts), `find_entities(query)` (fuzzy), `tag_note`, `untag_note`,
  `tags_for_note`, `notes_for_entity`, `count_for_entity`.
- **Services:** `EntityService` (list/find/promote, registry) + `ContentService.add_note`
  gains tagging. `NoteNotFound`/new `EntityNotFound` as needed.
- **CLI:** `pensieve entities` (list + counts) · `pensieve find <q>` · `pensieve promote
  <entity> --stream <s>` (manual/testing). `add` stays human-simple (no entity args — the
  *human* doesn't tag; the agent does).
- **MCP:** `list_entities`, `find_entities`, `add_note(… entities=[…])`, `promote_entity`,
  and an entity recall view (`get_entity`/its notes).
- **Skill:** capture = filter → load/resolve entities → add_note(with tags); surface
  promotion proposals; fetch via entities.

## 8. Build order (chunked, green each step)
1. **Entity model + migration `0004`** (entities + tags) + repo entity/tag methods +
   `EntityService` (list/find/count). Unit + integration + migration tests.
2. **Tagging at capture** — `add_note(entities=…)` creates/resolves/tags atomically;
   `list_entities`/`find_entities` on CLI + MCP. Tests (incl. dedup/resolution at the
   service level with pre-seeded entities).
3. **Promotion** — `promote_entity` (create thread + attach + set node_id); counts +
   promotable flag; tagging a promoted entity attaches to its node. Tests.
4. **Skill** — capture-with-resolution + promotion-proposal + entity-recall flows.
5. **Evaluator + live** — extend `make eval` (tagging, dedup, count, promote).
   **Recognition test on real data:** run a retro-tagging pass over the existing
   `~/.pensieve` `recs` notes, `pensieve entities` to eyeball (`rafia`, `travis`,
   `curator-outreach` — no dupes/over-tag), then **re-capture clean** and live-verify
   promotion (Rafia should cross the threshold and earn a thread).

*(Thin-view-as-summary = `5c`, pinned — see §6.)*

## 9. Open questions
- **Loose-vs-covered** rule for the stream thin view — deferred to **5c** (§6).
- **Entity scope** — registry is **global** (one Rafia, resolves across streams). First
  promotion targets one stream; cross-stream entity homes (a person under two streams)
  deferred — multi-homed notes already carry most cross-stream weight.
- **What earns a tag** — lazy/track-worthy (people, orgs, recurring topics); not dates,
  values, incidental nouns. A playbook rule; refine against the recognition test (§8.6).
- **Promotion target choice** — thread-under-stream vs new top-level stream: agent
  judgment at proposal time.
- **Recognition reliability** — the cold runs under-fired on entity decisions; the win is
  in the playbook rules + the load-existing-entities step. Measure via the eval.

## 10. Progress log
> Updated as we build (resume anchor).

- **Chunk 1 — entity registry + migration `0004`** — ✅ done.
  - **Model:** `Entity` (id/name/kind/aliases/`node_id`/timestamps) + `Tag` (note↔entity,
    m:n). Migration `0004_entities`. `slugify` extracted to `pensieve/slug.py` (shared).
  - **Repo (port + both adapters):** entity CRUD, `list_entities`, `find_entities`
    (sqlite `LIKE`/`ilike` over name+id+aliases; memory substring), `tag_note`/`untag_note`/
    `tags_for_note`/`notes_for_entity`/`count_for_entity`. (sqlite `tag_note` flushes
    first, same FK-ordering reason as `attach`.)
  - **`EntityService`:** create (slug, `EntityExists`), get (`EntityNotFound`), list/find
    returning counts + `promoted`/`promotable` (threshold = `PENSIEVE_PROMOTION_THRESHOLD`,
    default 5). `entity_service()` in factory.
  - Tests: unit (`test_entities.py`) + integration (`TestEntityServiceIntegration`) +
    migration fresh-store. **Suite 41 green, lint clean.**
  - *Not yet wired:* tagging-at-capture (chunk 2), promotion (chunk 3).
- **Chunk 2 — tagging at capture** — ✅ done.
  - `ContentService.add_note(entities=…)` resolves/creates entities and tags the note in
    one transaction; `tag_note(note, entities)` for existing notes; shared `_resolve_entity`
    (spec is `{id}` reuse, or `{name, kind, aliases?}` resolve-or-create by slug, merging
    new aliases; dedupes within a call). Raises `EntityNotFound` on bad id.
  - **MCP:** `add_note(… entities=[…])`, `list_entities`, `find_entities` (tool docstrings
    steer the agent to resolve against the registry before creating).
  - **CLI:** `entities` (list + counts + ★promotable), `find <q>`, `tag <note> <name>
    [-k kind]` (manual tagging for testing — `add` stays human-simple).
  - Tests: unit (create/reuse/dedup/alias-merge/tag-existing) + integration (sqlite, MCP
    add_note-tags, CLI flow). **Suite 48 green, lint clean.** Smoke: tag 2 notes → Rafia ×2.
  - *Not yet:* promotion (chunk 3) — counts accrue, nothing promotes.
- **Chunk 3 — promotion** — ✅ done.
  - `EntityService.promote_entity(entity, parent_stream)`: create the thread node
    (`id = entity slug`, `parent = stream`), **attach every tagged note** (additive —
    notes keep their stream attachment), set `entity.node_id`. Guards: missing entity/
    stream, already-promoted, node-id collision.
  - `ContentService._tag`: tagging a **promoted** entity also attaches the note to its
    thread node (new notes land under the thread automatically).
  - **CLI:** `promote <entity> -s <stream>`. **MCP:** `promote_entity`.
  - Tests: unit (promote + attach + errors + tag-promoted-attaches) + integration (sqlite
    round-trip, MCP, CLI). **Suite 54 green, lint clean.** Smoke (threshold=3): Rafia → ★
    promotable → promoted → thread shows her notes → `ls` still lists only the stream.
- **Chunk 4 — skill (the brain) + recall primitive** — ✅ done.
  - Added `get_entity` recall (entity + its notes, promoted or not): `EntityService.
    get_entity_view`, MCP `get_entity`, CLI `pensieve entity <id>`. Suite **55 green**.
  - Rewrote `adapters/claude/SKILL.md` for the four concepts: capture now **loads the
    entity registry + resolves before creating** (the dup-avoidance cardinal rule),
    tags via `add_note(entities=…)`, **proposes promotion** when `promotable`, and recalls
    via `find_entities`/`get_entity`. Vocabulary updated (streams/threads/notes + real
    names; never node/edge/attachment/tag). Also **fixed 5a staleness** — dropped the old
    `flavor` references.
- **Chunk 5 — pending** (evaluator + live: re-capture clean, watch Rafia self-organise +
  promote). Goes live after `./install.sh` (new skill).
