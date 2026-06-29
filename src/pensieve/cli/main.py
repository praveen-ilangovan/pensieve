"""
cli/main.py

Pensieve CLI — the engine's **op** surface, organised by concept:

    pensieve init | show <id> | find <q> [--type …] | search <q> | recent
    pensieve stream  create | list | edit | rm | restore
    pensieve note    add | edit | rm | restore | file | unfile
    pensieve entity  link | unlink | list | promote | edit | rm | restore
    pensieve asset   add | list | rm

``rm`` is a **soft-delete** (reversible via ``restore``); a future ``forget`` will hard
-delete. The judgment-bearing flows (capture / fetch) live in the agent skill, not here
(see adapters/claude/SKILL.md).
"""

from __future__ import annotations

import typer

from ..config import get_settings
from ..database.session import init_db
from ..errors import (
    AssetNotFound,
    EntityNotFound,
    NodeNotFound,
    NoteNotFound,
    PensieveError,
    StreamExists,
)
from ..factory import asset_service, content_service, entity_service, stream_service
from ..services.assets import local_missing

_HELP = """
Pensieve — your manually-triggered, self-organising memory.

**The idea:** keep everything in a few **streams** (top-level domains, e.g. `recs`,
`health`). Drop **notes** into a stream; the people/orgs/topics they mention become
**entities** on their own, and recurring ones grow into their own **threads**.

**Start here**

* `pensieve stream create Recs -p "Build Recs"` — make a stream
* `pensieve stream list` — see your streams
* `pensieve note add "met Rafia at the salon" -s recs` — add a note
* `pensieve show recs` — look inside (its threads + loose notes)
* `pensieve find rafia` — search streams, threads & entities

Run `pensieve <command> --help` for a group's verbs (e.g. `pensieve note --help`).
"""

app = typer.Typer(
    name="pensieve",
    help=_HELP,
    no_args_is_help=True,
    rich_markup_mode="markdown",
)
stream_app = typer.Typer(no_args_is_help=True, help="Streams — top-level domains.")
note_app = typer.Typer(no_args_is_help=True, help="Notes — pieces of information.")
entity_app = typer.Typer(
    no_args_is_help=True, help="Entities — people/orgs/topics, and their threads."
)
asset_app = typer.Typer(
    no_args_is_help=True, help="Assets — by-reference pointers (files/dirs/URLs)."
)
app.add_typer(stream_app, name="stream")
app.add_typer(note_app, name="note")
app.add_typer(entity_app, name="entity")
app.add_typer(asset_app, name="asset")


# --------------------------------------------------------------------------- #
# Top-level: init / show / find
# --------------------------------------------------------------------------- #
@app.command()
def init() -> None:
    """Initialise the Pensieve store (idempotent)."""
    init_db()
    typer.echo(f"✓ Pensieve store ready at {get_settings().db_path}")


@app.command()
def show(
    target: str = typer.Argument(..., help="A stream, thread, or entity id."),
) -> None:
    """Show a stream/thread (its threads + notes) or an entity (its notes)."""
    try:  # a node first (stream or thread)
        view = content_service().get_stream_view(target)
    except NodeNotFound:
        pass
    else:
        purpose = view["purpose"] or "—"
        typer.echo(f"{view['label']} · {purpose}")
        if not view["children"] and not view["notes"] and not view["assets"]:
            typer.echo("  (empty)")
        for asset in view["assets"]:
            _echo_asset(asset)
        for child in view["children"]:
            typer.echo(
                f"  ⤷ thread: {child['id']}  ({child['kind']}) ×{child['count']}"
            )
        for note in view["notes"]:
            typer.echo(f"  {note['id']}  {note['text']}  ({note['date'][:10]})")
            for asset in note["assets"]:
                _echo_asset(asset, indent="    ")
        return

    try:  # else an entity (recall)
        ev = entity_service().get_entity_view(target)
    except EntityNotFound as exc:
        typer.echo(f"✗ No stream, thread, or entity '{target}'", err=True)
        raise typer.Exit(code=1) from exc
    badge = " [thread]" if ev["promoted"] else ""
    typer.echo(f"{ev['name']} ({ev['kind']}) ×{ev['count']}{badge}")
    for asset in ev["assets"]:
        _echo_asset(asset)
    for note in ev["notes"]:
        typer.echo(f"  {note['id']}  {note['text']}  ({note['date'][:10]})")
        for asset in note["assets"]:
            _echo_asset(asset, indent="    ")


def _echo_asset(asset: dict, indent: str = "  ") -> None:
    hint = f"  — {asset['hint']}" if asset["hint"] else ""
    flag = "  ⚠ missing" if asset.get("missing") else ""
    typer.echo(
        f"{indent}▸ {asset['id']}  [{asset['kind']}] {asset['location']}{hint}{flag}"
    )


@app.command()
def find(
    query: str = typer.Argument(..., help="Name/label/alias substring to search."),
    node_type: str | None = typer.Option(
        None, "--type", "-t", help="Narrow to: stream | thread | entity."
    ),
) -> None:
    """Fuzzy-search streams, threads, and entities."""
    rows: list[tuple[str, str, str]] = []
    node_ids: set[str] = set()
    if node_type in (None, "stream", "thread"):
        for node in stream_service().find_nodes(query):
            pos = "stream" if node.parent_id is None else "thread"
            if node_type in (None, pos):
                rows.append((pos, node.id, node.label))
                node_ids.add(node.id)
    if node_type in (None, "entity"):
        for e in entity_service().find_entities(query):
            if e["id"] in node_ids:
                continue  # a promoted entity already shows as its thread node
            rows.append(("entity", e["id"], f"{e['name']} ×{e['count']}"))
    if not rows:
        typer.echo(f"No matches for '{query}'.")
        return
    for kind, rid, label in rows:
        typer.echo(f"{kind:<7} {rid:<22} {label}")


@app.command()
def search(
    query: str = typer.Argument(
        ..., help="Words to search note content + asset pointers."
    ),
) -> None:
    """Search the memory's **content** — note prose (stemmed, ranked) + asset pointers
    (hint/label/location). For "what did we decide about X"; `find` matches names instead.
    """
    res = content_service().search(query)
    if not res["notes"] and not res["assets"]:
        typer.echo(f"No matches for '{query}'.")
        return
    if res["notes"]:
        typer.echo("Notes:")
        for n in res["notes"]:
            homes = ", ".join(h["id"] for h in n["streams"]) or "—"
            typer.echo(f"  {n['id']}  {n['snippet']}  [{homes}]")
        if res["notes_truncated"]:
            typer.echo("  … more note matches (showing top results)")
    if res["assets"]:
        typer.echo("Assets:")
        for a in res["assets"]:
            hint = f" — {a['hint']}" if a["hint"] else ""
            miss = "  ⚠ missing" if a.get("missing") else ""
            typer.echo(
                f"  {a['id']}  [{a['kind']}] {a['location']}{hint}  (on {a['owner']}){miss}"
            )
        if res["assets_truncated"]:
            typer.echo("  … more asset matches (showing top results)")


@app.command()
def recent(
    since: str | None = typer.Option(
        None, "--since", help="Only notes updated at/after this ISO date/datetime."
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max notes to show."),
) -> None:
    """Most recently added/edited notes across all streams (newest first) — "what changed"."""
    from ..services.content import parse_since

    try:
        cutoff = parse_since(since)
    except ValueError as exc:
        typer.echo(f"✗ Bad --since '{since}' (use ISO, e.g. 2026-06-01)", err=True)
        raise typer.Exit(code=1) from exc
    res = content_service().recent(since=cutoff, limit=limit)
    if not res["notes"]:
        typer.echo("No recent notes.")
        return
    for n in res["notes"]:
        homes = ", ".join(h["id"] for h in n["streams"]) or "—"
        typer.echo(f"{n['id']}  {n['updated'][:10]}  {n['text']}  [{homes}]")
    if res["truncated"]:
        typer.echo("… more (showing the most recent)")


# --------------------------------------------------------------------------- #
# stream
# --------------------------------------------------------------------------- #
@stream_app.command("create")
def stream_create(
    name: str = typer.Argument(..., help="Display name of the stream."),
    purpose: str = typer.Option(
        "", "--purpose", "-p", help="Why this stream exists (its enduring north-star)."
    ),
) -> None:
    """Create a new stream (a top-level domain). Example: pensieve stream create Recs -p "…"."""
    try:
        node = stream_service().create_stream(name, purpose)
    except StreamExists as exc:
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ created stream '{node.id}'")


@stream_app.command("list")
def stream_list() -> None:
    """List all streams."""
    rows = stream_service().list_streams()
    if not rows:
        typer.echo("No streams yet. Create one: pensieve stream create <name>")
        return
    for node in rows:
        typer.echo(f"{node.id:<24} {node.properties.get('purpose') or '—'}")


@stream_app.command("edit")
def stream_edit(
    stream: str = typer.Argument(..., help="Stream id."),
    name: str | None = typer.Option(None, "--name", help="New display name."),
    purpose: str | None = typer.Option(None, "--purpose", "-p", help="New purpose."),
) -> None:
    """Rename / repurpose a stream (id stays stable).

    Example: pensieve stream edit recs --name "Recommendations" -p "…"
    """
    try:
        stream_service().edit_stream(stream, name=name, purpose=purpose)
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ updated stream '{stream}'")


@stream_app.command("rm")
def stream_rm(stream: str = typer.Argument(..., help="Stream id to remove.")) -> None:
    """Remove a stream and its threads (soft — bring it back with 'stream restore').

    Notes living only here go too; ones shared with another stream survive there.
    """
    try:
        stream_service().delete_stream(stream)
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"✓ removed stream '{stream}' (restore with: pensieve stream restore {stream})"
    )


@stream_app.command("restore")
def stream_restore(
    stream: str = typer.Argument(..., help="Stream id to bring back."),
) -> None:
    """Bring back a removed stream (and its threads)."""
    try:
        stream_service().restore_stream(stream)
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ restored stream '{stream}'")


# --------------------------------------------------------------------------- #
# note
# --------------------------------------------------------------------------- #
@note_app.command("add")
def note_add(
    text: str = typer.Argument(..., help="The note text (quote it)."),
    stream: list[str] = typer.Option(
        ...,
        "--stream",
        "-s",
        help="Stream(s) to file the note in (repeat -s for several).",
    ),
) -> None:
    """Add a note to one or more streams. (Notes reach a thread by tagging its entity.)

    Example: pensieve note add "the AI-agents article" -s writing -s recs
    """
    try:
        note = content_service().add_note(
            stream[0], text, also=stream[1:], actor="cli", interface="cli"
        )
    except NodeNotFound as exc:
        typer.echo(f"✗ {exc}".replace("node", "stream"), err=True)
        raise typer.Exit(code=1) from exc
    except PensieveError as exc:  # e.g. target is a thread, not a stream
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ added {note.id} to {', '.join(stream)}")


@note_app.command("file")
def note_file(
    note: str = typer.Argument(..., help="Note id (e.g. note-3)."),
    stream: str = typer.Option(
        ..., "--stream", "-s", help="Stream to also file it in."
    ),
) -> None:
    """File an existing note into another stream (one note, several homes)."""
    try:
        content_service().file_note(note, stream)
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc
    except PensieveError as exc:  # target is a thread
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ filed {note} in '{stream}'")


@note_app.command("unfile")
def note_unfile(
    note: str = typer.Argument(..., help="Note id (e.g. note-3)."),
    stream: str = typer.Option(..., "--stream", "-s", help="Stream to remove it from."),
) -> None:
    """Remove a note from a stream (it stays in its other streams; can't remove its last)."""
    try:
        content_service().unfile_note(note, stream)
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    except PensieveError as exc:  # not filed there / only home
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ unfiled {note} from '{stream}'")


@note_app.command("edit")
def note_edit(
    note: str = typer.Argument(..., help="Note id (e.g. note-3)."),
    text: str = typer.Argument(..., help="The corrected text (replaces the note)."),
) -> None:
    """Rewrite a note's text — for fixing a genuine mistake (a world-change is a new note)."""
    try:
        content_service().update_note(note, text, actor="cli", interface="cli")
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ updated {note}")


@note_app.command("rm")
def note_rm(note: str = typer.Argument(..., help="Note id to remove.")) -> None:
    """Remove a note (soft — bring it back with 'note restore')."""
    try:
        content_service().delete_note(note)
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ removed {note} (restore with: pensieve note restore {note})")


@note_app.command("restore")
def note_restore(
    note: str = typer.Argument(..., help="Note id to bring back."),
) -> None:
    """Bring back a removed note."""
    try:
        content_service().restore_note(note)
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ restored {note}")


# --------------------------------------------------------------------------- #
# entity
# --------------------------------------------------------------------------- #
@entity_app.command("link")
def entity_link(
    note: str = typer.Argument(..., help="Note id (e.g. note-3)."),
    name: str = typer.Argument(..., help="Entity name (resolved/created by slug)."),
    kind: str = typer.Option(
        "topic", "--kind", "-k", help="person | org | topic (for a new entity)."
    ),
) -> None:
    """Link a note to an entity (creates the entity if new)."""
    try:
        ids = content_service().tag_note(note, [{"name": name, "kind": kind}])
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ linked {note} → {ids[0]}")


@entity_app.command("unlink")
def entity_unlink(
    note: str = typer.Argument(..., help="Note id (e.g. note-3)."),
    entity: str = typer.Argument(..., help="Entity id to remove (see 'entity list')."),
) -> None:
    """Remove an entity tag from a note (fix a mis-tag).

    Example: pensieve entity unlink note-5 rafia-naseem
    """
    try:
        content_service().untag_note(note, entity)
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ unlinked {entity} from {note}")


@entity_app.command("list")
def entity_list() -> None:
    """List the entity registry with note counts."""
    rows = entity_service().list_entities()
    if not rows:
        typer.echo("No entities yet.")
        return
    for e in rows:
        mark = " ★ promotable" if e["promotable"] else (" ✓" if e["promoted"] else "")
        typer.echo(f"{e['id']:<20} {e['kind']:<8} ×{e['count']}{mark}")


@entity_app.command("promote")
def entity_promote(
    entity: str = typer.Argument(..., help="Entity id (see 'pensieve entity list')."),
    stream: str = typer.Option(
        ..., "--stream", "-s", help="Parent stream the new thread lives under."
    ),
) -> None:
    """Promote an entity into its own thread under a stream."""
    try:
        node = entity_service().promote_entity(entity, stream)
    except EntityNotFound as exc:
        typer.echo(f"✗ No entity '{entity}'", err=True)
        raise typer.Exit(code=1) from exc
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc
    except PensieveError as exc:
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ promoted '{entity}' → thread '{node.id}' under '{stream}'")


@entity_app.command("edit")
def entity_edit(
    entity: str = typer.Argument(..., help="Entity id."),
    name: str | None = typer.Option(None, "--name", help="New display name."),
    alias: list[str] | None = typer.Option(
        None, "--alias", help="Alias (repeatable) — replaces the alias list."
    ),
) -> None:
    """Rename an entity / set its aliases (id stays stable).

    Example: pensieve entity edit rafia-naseem --name "Rafia N." --alias Rafia
    """
    try:
        entity_service().edit_entity(entity, name=name, aliases=alias)
    except EntityNotFound as exc:
        typer.echo(f"✗ No entity '{entity}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ updated entity '{entity}'")


@entity_app.command("rm")
def entity_rm(entity: str = typer.Argument(..., help="Entity id to remove.")) -> None:
    """Remove an entity and its thread (soft — bring it back with 'entity restore').

    This *unlinks* the entity from its notes — it never deletes a note: a note shared with
    another subject survives under that subject; a note left with no subject becomes a plain
    note.
    """
    try:
        entity_service().delete_entity(entity)
    except EntityNotFound as exc:
        typer.echo(f"✗ No entity '{entity}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"✓ removed entity '{entity}' (restore with: pensieve entity restore {entity})"
    )


@entity_app.command("restore")
def entity_restore(
    entity: str = typer.Argument(..., help="Entity id to bring back."),
) -> None:
    """Bring back a removed entity (its notes and thread)."""
    try:
        entity_service().restore_entity(entity)
    except EntityNotFound as exc:
        typer.echo(f"✗ No entity '{entity}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ restored entity '{entity}'")


# --------------------------------------------------------------------------- #
# asset
# --------------------------------------------------------------------------- #
@asset_app.command("add")
def asset_add(
    target: str = typer.Argument(..., help="Stream/thread id, or a note id (note-N)."),
    location: str = typer.Argument(..., help="A path or URL (stored by reference)."),
    hint: str | None = typer.Option(
        None, "--hint", help="One line on how to use it (e.g. 'read CLAUDE.md first')."
    ),
    label: str | None = typer.Option(None, "--label", help="Optional short name."),
    kind: str | None = typer.Option(
        None, "--kind", "-k", help="repo|file|dir|url|image|doc (inferred if omitted)."
    ),
) -> None:
    """Attach an asset (a by-reference pointer) to a stream, thread, or note.

    Example: pensieve asset add recs ~/code/recs --hint "read CLAUDE.md first"
    """
    try:
        asset = asset_service().add_asset(
            target,
            location,
            hint=hint,
            label=label,
            kind=kind,
            actor="cli",
            interface="cli",
        )
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{target}'", err=True)
        raise typer.Exit(code=1) from exc
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream, thread, or note '{target}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ added {asset.id} ({asset.kind}) to '{target}'")
    if local_missing(asset.location, asset.kind):
        typer.echo(
            f"  ⚠ '{asset.location}' doesn't resolve right now — stored anyway (pointer).",
            err=True,
        )


@asset_app.command("list")
def asset_list(
    target: str = typer.Argument(..., help="Stream/thread id, or a note id (note-N)."),
) -> None:
    """List the assets attached to a stream, thread, or note."""
    try:
        rows = asset_service().list_assets(target)
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{target}'", err=True)
        raise typer.Exit(code=1) from exc
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream, thread, or note '{target}'", err=True)
        raise typer.Exit(code=1) from exc
    if not rows:
        typer.echo(f"No assets on '{target}'.")
        return
    for a in rows:
        hint = f"  — {a['hint']}" if a["hint"] else ""
        flag = "  ⚠ missing" if a.get("missing") else ""
        typer.echo(f"{a['id']:<10} {a['kind']:<6} {a['location']}{hint}{flag}")


@asset_app.command("rm")
def asset_rm(
    asset: str = typer.Argument(..., help="Asset id to remove (asset-N)."),
) -> None:
    """Remove an asset (a plain delete — pointers are cheap to re-add)."""
    try:
        asset_service().remove_asset(asset)
    except AssetNotFound as exc:
        typer.echo(f"✗ No asset '{asset}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ removed {asset}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
