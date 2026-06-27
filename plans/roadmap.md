# Pensieve — roadmap (post-v1)

> **v1 is stable & shipped** (streams · threads · notes · entities · promotion · thin view ·
> edit · soft remove/restore · CLI + MCP at parity). This is the backlog beyond it, in the
> order we agreed. Guiding principle: **Pensieve is an information lake, not a
> project-management layer** — capture information and let structure emerge; resist
> task/PM-flavoured features. (See memory: pensieve-information-lake-principle.)

## Committed order

### 1. Lead-architect review *(do first — review on a clean base before adding features)*
A read-only architect pass over **code + plans + docs**: structure, layering (ports/adapters,
service boundaries), model coherence, test/eval coverage, and risks. Output = a findings
doc + a short refactor list to do *before* piling on retrieval/assets. Not a feature.

### 2. Assets — attach files / directories / URLs
Let a note (and maybe a thread/stream) carry **assets**: a file, a directory, a URL.
Open design questions to settle first:
- What *is* an asset — a row referencing a path/URL + metadata? Stored by reference (path/
  URL) only, never copied into the store? (lake = pointers, not a blob store.)
- Where does it attach — note-level (reuse the m:n `attachments` shape), or also
  thread/stream-level?
- How does it surface in `get_stream` / recall, and in the CLI/MCP?
- Provenance/permanence: a moved/deleted file → dangling pointer; do we validate or just hold.
- ⚠️ **Restore invariant to revisit (from the slice-6 review):** `restore_entity` currently
  blanket-revives *all* of an entity's soft-unlinked tags, which is correct only because
  `entity rm` is the *sole* producer of soft-unlinked tags today. If assets introduce a
  second soft-unlink path, that blanket revive could over-restore — scope restore to the
  owning operation (e.g. a deletion-batch key) when this lands.

### 3. `search_notes(query)` — retrieval over note *text*
The #1 recall gap: "what did we decide about pricing" when no entity is named "pricing".
**Open question: FTS vs vectors — see the note below.** Recommendation: start with SQLite
**FTS5** (keyword/phrase, zero deps, deterministic, local), behind a backend-agnostic
`search_notes` tool, and add a semantic/vector layer later only if real misses prove it out.

### 4. Recency path — hydrate "what changed", not everything
`get_stream` is oldest-first/all. Add **newest-first** + **`since <timestamp>`** so a new
session can pull recent deltas cheaply. Feeds a future auto-hydrate on session start.

## Backlog (later / not yet sequenced)
- **Multi-stream note surface.** Storage already supports it (notes↔nodes is m:n); just no
  op to file one note into a 2nd stream. Cheap whenever wanted. Pulls the model toward
  "streams as views over one note set."
- **Entity-to-entity edges.** The `Edge` table exists but is unused — typed relationships
  (Rafia → runs → The Reader Life) so recall can traverse, not just read note text.
- **Graph hygiene** — surface orphan/untagged notes; a re-lint/re-tag pass to keep the
  graph healthy over months.
- **Consolidation / compaction** — a "sleep" that digests old notes into summaries while
  keeping raw history. Cheap to reserve now.
- **Auto-hydrate** — wire a compact memory index so session bootstrap is automatic, not
  prompted (depends on recency + search).
- **`supersedes` relation** — a note marks an earlier one stale, for cheap current-state
  without deleting history. A refinement of recency; revisit after #4.

## Explicitly parked (against the principle)
- **Typed notes (decision / status / commitment).** Tempting for "show open commitments",
  but that's a PM layer. Pensieve stores information; the *agent* infers state at read time.
