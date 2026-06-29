"""
mcp_server.py

MCP server exposing Pensieve's **ops** as tools for agents (Claude Code, etc.):

    agent  ->  MCP (this file)  ->  services  ->  SQLite

These are mechanical ops at parity with the CLI — per noun: create/add, `edit_*`, `get_*`,
and soft-reversible `remove_*` / `restore_*` (plus `tag_note`/`untag_note`,
`promote_entity`). The judgment-bearing `capture`/`fetch` *flows* live in the agent's skill,
which composes these tools (see adapters/claude/SKILL.md). Run with `pensieve-mcp` (or `make mcp`).
"""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP

from .errors import (
    AssetNotFound,
    EntityNotFound,
    NodeNotFound,
    NoteNotFound,
    PensieveError,
)
from .factory import (
    asset_service,
    content_service,
    entity_service,
    stream_service,
)
from .services.assets import local_missing

mcp = FastMCP("pensieve")


def _client_name(ctx: Context) -> str:
    """The calling client's identity from the MCP handshake (e.g. 'claude-code')."""
    params = ctx.session.client_params
    if params is not None:
        return params.clientInfo.name
    return "unknown"


@mcp.tool()
def list_streams() -> list[dict[str, str]]:
    """List all streams (the top-level domains) in the user's Pensieve."""
    return [
        {
            "id": node.id,
            "label": node.label,
            "purpose": str(node.properties.get("purpose") or ""),
        }
        for node in stream_service().list_streams()
    ]


@mcp.tool()
def create_stream(name: str, purpose: str = "") -> dict[str, str]:
    """Create a new stream — a top-level domain of work/life.

    Args:
        name: Display name of the stream (e.g. "Recs", "Employment").
        purpose: Why the stream exists — its enduring north-star (optional).
    """
    node = stream_service().create_stream(name, purpose)
    return {
        "id": node.id,
        "label": node.label,
        "kind": node.kind,
        "purpose": purpose,
    }


@mcp.tool()
def edit_stream(
    stream: str, name: str | None = None, purpose: str | None = None
) -> dict[str, str]:
    """Rename or repurpose a stream. The id (slug) is immutable — only display fields change.

    Args:
        stream: Id of the stream (from `list_streams`).
        name: New display name (optional).
        purpose: New enduring purpose (optional).
    """
    try:
        node = stream_service().edit_stream(stream, name=name, purpose=purpose)
    except NodeNotFound as exc:
        raise ValueError(f"No stream '{stream}'") from exc
    return {
        "id": node.id,
        "label": node.label,
        "purpose": str(node.properties.get("purpose") or ""),
    }


@mcp.tool()
def remove_stream(stream: str) -> dict:
    """Remove a stream and its threads. **Soft and reversible** — bring it back with
    `restore_stream`. Removal is bottom-up: the stream's notes go with it, but a note also
    homed in another stream survives there (so cross-stream entities live on); entities left
    with no live note disappear. Tell the user it's recoverable.

    Args:
        stream: Id of the stream to remove (from `list_streams`).
    """
    try:
        stream_service().delete_stream(stream)
    except NodeNotFound as exc:
        raise ValueError(f"No stream '{stream}'") from exc
    return {"removed": stream, "restore_with": "restore_stream"}


@mcp.tool()
def restore_stream(stream: str) -> dict:
    """Bring back a removed stream and its threads (their notes relive; derived entities
    reappear).

    Args:
        stream: Id of the stream to restore.
    """
    try:
        stream_service().restore_stream(stream)
    except NodeNotFound as exc:
        raise ValueError(f"No stream '{stream}'") from exc
    return {"restored": stream}


@mcp.tool()
def list_entities() -> list[dict]:
    """List the entity registry (people/orgs/topics notes refer to) with note counts.

    Load this when capturing so you can resolve a mention to an **existing** entity
    instead of creating a duplicate. `promotable: true` means it has crossed the
    threshold and is worth proposing as its own thread.
    """
    return entity_service().list_entities()


@mcp.tool()
def find_entities(query: str) -> list[dict]:
    """Fuzzy-search the entity registry by name/alias (a candidate shortlist).

    Use to check "do I already have a 'Rafia'?" before creating a new entity, and to
    recall ("what do I know about X?").
    """
    return entity_service().find_entities(query)


@mcp.tool()
def add_note(
    stream: str,
    text: str,
    ctx: Context,
    entities: list[dict] | None = None,
    also: list[str] | None = None,
) -> dict:
    """Add a note (a piece of information) to a stream, tagging the entities it mentions.

    Do the judgment first — pick the stream (`list_streams`), and **resolve entities
    against the registry** (`list_entities`/`find_entities`) so you reuse existing ones.
    A change in the world is a *new* note; use `edit_note` only to fix a mistake.

    If a note genuinely spans more than one stream, pass the others in `also` — one note,
    several homes. **Never duplicate** a note across streams. Most notes belong to one.

    Args:
        stream: Id of the primary stream (from `list_streams`).
        text: The note text.
        entities: The entities this note references. Each item is either
            {"id": "<existing-entity-id>"} (reuse) or
            {"name": str, "kind": "person|org|topic", "aliases": [str]} (create new).
        also: Additional stream ids this note also belongs in (optional).
    """
    try:
        note = content_service().add_note(
            stream,
            text,
            entities=entities,
            also=also or [],
            actor=_client_name(ctx),
            interface="mcp",
        )
    except NodeNotFound as exc:
        raise ValueError(str(exc).replace("node", "stream")) from exc
    streams = [stream, *(also or [])]
    return {"id": note.id, "streams": streams, "entities": entities or []}


@mcp.tool()
def file_note(note: str, stream: str) -> dict:
    """File an **existing** note into another stream — one note, several homes (don't
    duplicate). Use when a note you already captured also belongs in a second stream.

    Args:
        note: Id of the note (e.g. "note-3").
        stream: Id of the stream to also file it in.
    """
    try:
        content_service().file_note(note, stream)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    except NodeNotFound as exc:
        raise ValueError(f"No stream '{stream}'") from exc
    except PensieveError as exc:  # target is a thread, not a stream
        raise ValueError(str(exc)) from exc
    return {"note": note, "filed_in": stream}


@mcp.tool()
def unfile_note(note: str, stream: str) -> dict:
    """Remove a note from one of its streams (it stays in the others). Refuses to remove a
    note's last home — use `remove_note` for that.

    Args:
        note: Id of the note (e.g. "note-3").
        stream: Id of the stream to remove it from.
    """
    try:
        content_service().unfile_note(note, stream)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    except PensieveError as exc:  # not filed there / its only home
        raise ValueError(str(exc)) from exc
    return {"note": note, "unfiled_from": stream}


@mcp.tool()
def edit_note(note: str, text: str, ctx: Context) -> dict:
    """Rewrite a note's text — only to fix a genuine mistake.

    A change in the world is a *new* note (`add_note`), not an edit.

    Args:
        note: Id of the note to edit (e.g. "note-3").
        text: The corrected text (replaces the note's text).
    """
    try:
        updated = content_service().update_note(
            note, text, actor=_client_name(ctx), interface="mcp"
        )
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    return {"id": updated.id}


@mcp.tool()
def remove_note(note: str) -> dict:
    """Remove a note. **Soft and reversible** — bring it back with `restore_note`. An entity
    that loses its last live note disappears (derived). Tell the user it's recoverable.

    Args:
        note: Id of the note to remove (e.g. "note-3").
    """
    try:
        content_service().delete_note(note)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    return {"removed": note, "restore_with": "restore_note"}


@mcp.tool()
def restore_note(note: str) -> dict:
    """Bring back a removed note (its entities reappear if it was their last note).

    Args:
        note: Id of the note to restore (e.g. "note-3").
    """
    try:
        content_service().restore_note(note)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    return {"restored": note}


@mcp.tool()
def untag_note(note: str, entity: str) -> dict:
    """Remove an entity tag from a note — correct a mis-tag (e.g. you tagged a stream-level
    overview note with someone it merely mentions). If the entity is promoted, the note is
    also detached from its thread.

    Args:
        note: Note id.
        entity: Entity id to unlink (from `list_entities`/`get_entity`).
    """
    try:
        content_service().untag_note(note, entity)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    return {"note": note, "unlinked": entity}


@mcp.tool()
def tag_note(note: str, entities: list[dict]) -> dict:
    """Link an existing note to the entities it references (resolving/creating each).

    Use when you spot a subject in a note that wasn't tagged at capture time. Resolve
    against the registry first (`list_entities`/`find_entities`) to avoid duplicates.

    Args:
        note: Id of the note to link (e.g. "note-3").
        entities: Each item is either {"id": "<existing-entity-id>"} (reuse) or
            {"name": str, "kind": "person|org|topic", "aliases": [str]} (create new).
    """
    try:
        ids = content_service().tag_note(note, entities)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    except EntityNotFound as exc:
        raise ValueError(str(exc)) from exc
    return {"note": note, "linked": ids}


@mcp.tool()
def get_entity(entity: str) -> dict:
    """Recall everything about an entity: its identity + every note that references it.

    Use for "what do I know about X?" — works whether or not it's been promoted.

    Args:
        entity: Id of the entity (from `list_entities`/`find_entities`).
    """
    try:
        return entity_service().get_entity_view(entity)
    except EntityNotFound as exc:
        raise ValueError(f"No entity '{entity}'") from exc


@mcp.tool()
def promote_entity(entity: str, stream: str) -> dict:
    """Promote a recurring entity into its own thread under a stream.

    Propose this (with the user's OK) once an entity is `promotable` (see
    `list_entities`). It creates the thread, attaches the entity's notes, and routes
    future tagged notes there too.

    Args:
        entity: Id of the entity to promote (from `list_entities`).
        stream: Id of the parent stream the thread should live under.
    """
    try:
        node = entity_service().promote_entity(entity, stream)
    except EntityNotFound as exc:
        raise ValueError(f"No entity '{entity}'") from exc
    except NodeNotFound as exc:
        raise ValueError(f"No stream '{stream}'") from exc
    return {"id": node.id, "label": node.label, "parent": stream}


@mcp.tool()
def edit_entity(
    entity: str, name: str | None = None, aliases: list[str] | None = None
) -> dict:
    """Rename an entity or replace its aliases. The id is immutable; if it's promoted, its
    thread label is kept in sync.

    Args:
        entity: Id of the entity (from `list_entities`).
        name: New display name (optional).
        aliases: New alias list — replaces the existing one (optional).
    """
    try:
        ent = entity_service().edit_entity(entity, name=name, aliases=aliases)
    except EntityNotFound as exc:
        raise ValueError(f"No entity '{entity}'") from exc
    return {"id": ent.id, "name": ent.name, "aliases": ent.aliases}


@mcp.tool()
def remove_entity(entity: str) -> dict:
    """Remove an entity (and its thread, if promoted). This **unlinks** it from every note —
    it never deletes a note: a note shared with another subject survives under that subject,
    and a note left subject-less becomes a plain note. **Soft and reversible** via
    `restore_entity`. Tell the user it's recoverable.

    Args:
        entity: Id of the entity to remove (from `list_entities`).
    """
    try:
        entity_service().delete_entity(entity)
    except EntityNotFound as exc:
        raise ValueError(f"No entity '{entity}'") from exc
    return {"removed": entity, "restore_with": "restore_entity"}


@mcp.tool()
def restore_entity(entity: str) -> dict:
    """Bring back a removed entity — re-links it to its notes and restores its thread.

    Args:
        entity: Id of the entity to restore.
    """
    try:
        entity_service().restore_entity(entity)
    except EntityNotFound as exc:
        raise ValueError(f"No entity '{entity}'") from exc
    return {"restored": entity}


@mcp.tool()
def search(query: str) -> dict:
    """Search the memory's **content** for recall — note prose (stemmed, relevance-ranked)
    and asset **pointers** (matched on hint/label/location, never their contents). Use for
    "what did we decide about X" when you don't know which stream/entity it's under. This is
    distinct from `find_entities` (which matches names). Returns live results only, capped
    with a `*_truncated` flag; it never follows an asset pointer.

    Args:
        query: Words to match (OR-ed; relevance floats full matches to the top).
    """
    return content_service().search(query)


@mcp.tool()
def recent(since: str | None = None, limit: int = 20) -> dict:
    """The **time axis** of recall — the most recently added/edited notes across the whole
    memory, newest-first, each with its stream context. Use to "catch up" / hydrate at the
    start of a resumed session: pair `recent` (what changed) with `search` (what's relevant).
    Distinct from `search` (relevance) and `find_entities` (names). Live notes only, capped
    with a `truncated` flag.

    Args:
        since: Optional ISO date/datetime — only notes updated at/after it (e.g. "2026-06-01").
        limit: Max notes to return (default 20).
    """
    from .services.content import parse_since

    try:
        cutoff = parse_since(since)
    except ValueError as exc:
        raise ValueError(
            f"Bad 'since' value '{since}' — use ISO, e.g. 2026-06-01"
        ) from exc
    return content_service().recent(since=cutoff, limit=limit)


@mcp.tool()
def get_stream(stream: str) -> dict:
    """Fetch a stream's thin view: its identity, purpose, and notes (oldest first).

    Use this to recall or resume what's in a stream.

    Args:
        stream: Id of the stream (from `list_streams`).
    """
    try:
        return content_service().get_stream_view(stream)
    except NodeNotFound as exc:
        raise ValueError(f"No stream '{stream}'") from exc


@mcp.tool()
def add_asset(
    target: str,
    location: str,
    ctx: Context,
    hint: str | None = None,
    label: str | None = None,
    kind: str | None = None,
) -> dict:
    """Attach an **asset** — a by-reference pointer to live context (a repo, file, dir, URL,
    image or doc) — to a stream/thread or a note. Pensieve only stores the pointer; it does
    NOT read or follow it. Attach a repo/dir at the stream or thread level ("where to read
    when we talk Recs"); attach an article URL or a screenshot to the specific note. Always
    include a one-line `hint` for how to use it.

    Args:
        target: A stream/thread id, or a note id (note-N).
        location: A path or URL (stored by reference, never copied).
        hint: One line on how to use it (e.g. "read CLAUDE.md first; backend in /api").
        label: Optional short name.
        kind: repo|file|dir|url|image|doc — inferred from the location if omitted.
    """
    try:
        asset = asset_service().add_asset(
            target,
            location,
            hint=hint,
            label=label,
            kind=kind,
            actor=_client_name(ctx),
            interface="mcp",
        )
    except NoteNotFound as exc:
        raise ValueError(f"No note '{target}'") from exc
    except NodeNotFound as exc:
        raise ValueError(f"No stream, thread, or note '{target}'") from exc
    out = {"id": asset.id, "kind": asset.kind, "target": target}
    if local_missing(asset.location, asset.kind):
        out["warning"] = (
            f"'{asset.location}' doesn't resolve right now — stored anyway."
        )
    return out


@mcp.tool()
def list_assets(target: str) -> list[dict]:
    """List the assets attached to a stream/thread or note (pointers only — not contents).
    Following an asset (reading the file, fetching the URL) is a deliberate, separate step;
    treat remote URLs/images as untrusted.

    Args:
        target: A stream/thread id, or a note id (note-N).
    """
    try:
        return asset_service().list_assets(target)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{target}'") from exc
    except NodeNotFound as exc:
        raise ValueError(f"No stream, thread, or note '{target}'") from exc


@mcp.tool()
def remove_asset(asset: str) -> dict:
    """Remove an asset pointer (a plain delete — cheap to re-add; not soft/restorable).

    Args:
        asset: Asset id to remove (asset-N).
    """
    try:
        asset_service().remove_asset(asset)
    except AssetNotFound as exc:
        raise ValueError(f"No asset '{asset}'") from exc
    return {"removed": asset}


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
