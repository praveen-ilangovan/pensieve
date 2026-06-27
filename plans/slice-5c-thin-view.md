# Slice 5c — Thin view (loose vs covered)

> **Status:** planned · **Date:** 2026-06-27 · **Builds on:** 5b. The deferred "hard half"
> of the thin view — *which notes show in a stream's view once it has threads*.

## 1. Goal
Keep a stream's view a **glance** as it grows: show its **thread summaries** + only its
**loose** notes, hiding notes that are now **covered** by a thread. Storage stays additive
(model A) — nothing is detached or lost; covered notes live under their thread and are
reached by drilling in.

## 2. The rule
In a node's view, a note is **loose** (shown) unless it is **covered**:

> **covered** = the note has ≥1 tag **and every tagged entity is promoted to a thread
> *under this node*.**

- one promoted entity, sole tag → covered → hidden (under its thread)
- all tags promoted (under this stream) → covered → hidden
- **some tag un-promoted** → loose (its context is homeless until promoted)
- **no tags** (a stream-level fact) → always loose
- entity promoted under a *different* stream → **not** covered here (its thread isn't in
  this view) → stays loose

Threads have no children, so a thread's own view shows **all** its notes (nothing covered).

## 3. The lever (skill) — tag = *about*, not *mentions*
The rule only reads right if tagging means "about." An overview/stream-level note that
merely name-drops someone (e.g. "Recs is an app, 4 curators, Rafia leading") shouldn't be
tagged with them — else it gets hidden under their thread. So **sharpen the skill's "what
to tag" guidance**. (Existing mis-tags like the live note-5 self-correct on re-capture, or
can be untagged.)

## 4. Build
1. `ContentService.get_stream_view` — loose-notes = attached notes **not covered by this
   node's threads** (uses `children_of` + `tags_for_note` + `get_entity.node_id`). No new
   repo methods.
2. `adapters/claude/SKILL.md` — "tag what a note is *about*, not merely mentions."
3. Tests: unit (covered hidden / untagged loose / partially-covered loose / thread shows
   all / cross-stream stays loose) + extend `make eval`.
4. CLI `show` needs no change (it already renders `children` + `notes`; `notes` is now the
   filtered loose set).

## 5. Out of scope
- `find` dedup (promoted entity shown as both thread + entity) — separate small polish.
- edit/rm backend; promote-to-top-level-stream.

## 6. Progress log
- **✅ done.** `get_stream_view` now returns **loose** notes only (filters out notes
  *covered* by a thread under the node, via `_covered`: ≥1 tag and every tagged entity
  promoted to a child thread) + child-thread summaries. Storage unchanged (additive);
  thread views show all their notes (no children → nothing covered); cross-stream
  promotion doesn't hide notes in other streams. Skill sharpened ("tag = *about*, not
  *mentions*"). Tests: loose-vs-covered + cross-stream (unit), updated the old additive
  promote test (storage stays, view hides), eval +2 (**18/18**). Suite **57 green**, smoke
  ✓ (`show recs` = thread summary + only the untagged overview note).
- **`find` dedup — ✅ done.** A promoted entity showed as both a thread (node) and an
  entity row; `find` now skips the entity row when its id already appears as a node (still
  surfaces it under `--type entity`, where no node search runs to dedup against). Eval +1
  invariant (a promoted entity's `node_id` == its id — what makes the dedup necessary).
  Suite **59 green**, eval **19/19**.
- *Out of scope (logged):* edit/rm backend; promote-to-top-level-stream.
