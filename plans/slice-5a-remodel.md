# Slice 5a — The Remodel (behavior-preserving)

> **Status:** planned · **Date:** 2026-06-26 · **Model:** `docs/glossary.md` (information
> lake; streams · threads · notes · entities). **Phase 1 of 2** — this is the *rewrite*;
> entities + promotion are **5b**.

## 1. Goal

Migrate the data layer to the settled model **without adding user-facing features**, so
the structural change is de-risked on its own. When 5a lands, capture/fetch behave
exactly as today — **the only visible change is `--flavor` going away** — but underneath:
notes are **standalone + multi-homed** (attachments), the dead concepts are gone, and the
note ops are **add / update / delete**.

**Acceptance gate:** the existing capture/fetch behavior, the evaluator (`make eval`), and
the full test suite stay **green** (adapted to the new model). No new capability.

## 2. Scope

**In:**
- **Notes remodel** — a note becomes a standalone row with a **global id** (`note-1…`),
  carrying `text`, `created`, `updated`, and provenance (`actor`, `interface`). A new
  **`attachments`** table (note ↔ node, many-to-many) replaces single-node ownership —
  each note has **exactly one** attachment for now (the many-ness is used in 5b).
- **Deletions** (the model got simpler): drop `flavor`, `supersedes`, the
  `commit_id` + **`History`** commit-log machinery, and the unused **`Todo`** table.
- **Ops:** `add_note` (note + attach), `update_note` (fix a mistake), `delete_note`
  (remove) — plus `attach` / `detach` at the repo layer (5b uses them).
- One **Alembic migration** for the whole remodel. **Clear & rebuild** `~/.pensieve`
  (re-capture the few recs notes) rather than data-migrating — agreed, it's tiny.

**Out (→ 5b or later):**
- **Entities / tags / counts / promotion** — all of 5b.
- **Edges** (node↔node) — deferred (glossary §8); keep the table unused.
- **Condense / tidy**, multi-attachment *usage* (notes attached to >1 node).
- Agent judgment for *when* to `update` vs `add` — the op ships in 5a; the skill smarts
  are 5b.

## 3. Changes by layer

### Model (`database/models.py`)
- `Note`: PK → **global `id`**; fields `text`, `created`, `updated`, `actor`,
  `interface`. **Remove** `node_id` (moves to attachments), `flavor`, `supersedes`,
  `commit_id`, `version`-style commit linkage.
- **New `Attachment`**: `(note_id, node_id)` PK, FKs to both. Many-to-many.
- **Remove** `History` and `Todo` tables. Keep `Edge` (deferred, unused), `Counter`
  (now allocates global note ids; commit scope retired).

### Migration (`migrations/versions/0003_*`)
- Drop `history`, `todos`; create `attachments`; restructure `notes` (drop
  flavor/supersedes/commit_id, add actor/interface/updated, global id). Fresh stores get
  the new shape; we **clear** the existing real store rather than backfill notes.

### Repository (`repository/base.py` + `sqlite.py` + `memory.py`)
- `add_note(note)` + `attach(note_id, node_id)` (or one `add_note(note, node_id)`).
- `notes_for(node_id)` → **join through attachments**.
- `update_note(note_id, text)`, `delete_note(note_id)`, `detach(note_id, node_id)`.
- `next_id` keeps a global `note` scope; drop the `_commit` scope. Remove
  `add_history`.

### Services (`services/content.py`)
- `add_note(node_id, text, *, actor, interface)` → create note (global id) + attach to
  `node_id`. **No flavor.** Provenance on the note.
- `get_stream_view(node_id)` → notes via attachments (drop `flavor` from the view).
- New: `update_note(note_id, text, *, actor)`, `delete_note(note_id)`.
- `StreamService` unchanged.

### CLI (`cli/main.py`)
- `add` — drop `--flavor` (+ the `Flavor` enum). `show` — drop flavor from rendering.
- New: `edit <note-id> <text>` and `rm <note-id>` (the update/delete ops).

### MCP (`mcp_server.py`)
- `add_note` — drop `flavor` arg; keep client-name provenance.
- New tools: `update_note(note, text)`, `delete_note(note)`. `get_stream` unchanged shape
  minus flavor.

### Evaluator + tests
- `evals/capture_fetch.py`: drop flavor assertions; add an `update`/`delete` check.
- Unit (fake) + integration (sqlite) + migration tests updated to the new schema.

## 4. Build order (chunked, each green before the next)
1. **Model + migration** — remodel tables; `0003` migration; fresh-store + (adapted)
   migration tests green.
2. **Repository** — both adapters to attachments + add/update/delete/attach/detach; unit
   tests on the fake.
3. **Services** — `add_note`/`get_stream_view`/`update_note`/`delete_note`; unit +
   integration.
4. **CLI** — drop flavor; `edit`/`rm`; CLI integration tests.
5. **MCP** — drop flavor; `update_note`/`delete_note` tools; MCP integration tests.
6. **Evaluator** — update; `make eval` green.
7. **Clear & rebuild** `~/.pensieve`; live re-verify capture/fetch unchanged (minus
   flavor). Commit/push.

## 5. Open / to-decide
- **Note id scheme** — global `note-N` (drop per-stream `recs/note-1`). Confirmed by the
  remodel; addressing is now `note-N`.
- **Keep `Edge` table** (deferred) vs drop now — leaning keep (it returns; avoids
  migration churn).
- **`update` semantics** — full text replace (simplest) vs patch. Leaning full replace.

## 6. Progress log
> Updated as we build (resume anchor).

- _not started_
