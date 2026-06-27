"""
cli/main.py

Pensieve CLI entry point — the engine's **op** surface (init / create / ls / add /
show / edit / rm). The judgment-bearing flows (capture / fetch) live in the agent skill,
not here (see docs/verbs.md §0a).
"""

from __future__ import annotations

import typer

from ..config import get_settings
from ..database.session import init_db
from ..errors import (
    EntityNotFound,
    NodeNotFound,
    NoteNotFound,
    PensieveError,
    StreamExists,
)
from ..factory import content_service, entity_service, stream_service

app = typer.Typer(
    name="pensieve",
    help=(
        "Pensieve — manually-triggered, multi-stream agent memory.\n\n"
        "A stream is a top-level domain (recs, employment, …); notes hold information "
        "and attach to it. These commands are the mechanical op surface — the "
        "judgment-bearing capture/fetch flows live in the agent skill."
    ),
    epilog=(
        "Typical flow: **create** a stream → **add** notes to it → **show** it. "
        "Run `pensieve COMMAND --help` for a per-command example."
    ),
    no_args_is_help=True,
    rich_markup_mode="markdown",
)


@app.command()
def init() -> None:
    """Initialise the Pensieve store (idempotent)."""
    init_db()
    typer.echo(f"✓ Pensieve store ready at {get_settings().db_path}")


@app.command()
def create(
    stream: str = typer.Option(
        ..., "--stream", "-s", help="Name of the stream to create."
    ),
    purpose: str = typer.Option(
        "", "--purpose", "-p", help="Why this stream exists (its enduring north-star)."
    ),
) -> None:
    """Create a new stream.

    A stream is a top-level domain of work/life (a subject node with no parent).

    Example: pensieve create -s recs -p "Build Recs"
    """
    try:
        node = stream_service().create_stream(stream, purpose)
    except StreamExists as exc:
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ Created stream '{node.id}'")


@app.command("ls")
def ls() -> None:
    """List all streams."""
    rows = stream_service().list_streams()
    if not rows:
        typer.echo("No streams yet. Create one: pensieve create --stream <name>")
        return
    for node in rows:
        purpose = node.properties.get("purpose") or "—"
        typer.echo(f"{node.id:<24} {purpose}")


@app.command()
def add(
    text: str = typer.Argument(..., help="The note text to add (quote it)."),
    stream: str = typer.Option(
        ..., "--stream", "-s", help="Id of the stream to add to (see 'pensieve ls')."
    ),
) -> None:
    """Add a note to a stream.

    Records a piece of information and attaches it to the stream. This is the mechanical
    `add_note` op; the agent's `capture` flow is what does this with judgment.

    Example: pensieve add "talking to 4 curators" -s recs
    """
    try:
        note = content_service().add_note(stream, text, actor="cli", interface="cli")
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ added {note.id} to '{stream}'")


@app.command()
def show(
    stream: str = typer.Argument(..., help="Id of the stream to show."),
) -> None:
    """Show a stream's thin view.

    Prints the stream's identity, purpose, and its notes (oldest first).

    Example: pensieve show recs
    """
    try:
        view = content_service().get_stream_view(stream)
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc

    purpose = view["purpose"] or "—"
    typer.echo(f"{view['label']} · {purpose}")
    notes = view["notes"]
    if not notes:
        typer.echo("  (empty)")
        return
    for note in notes:
        date = note["date"][:10]  # YYYY-MM-DD
        typer.echo(f"  {note['id']}  {note['text']}  ({date})")


@app.command()
def edit(
    note: str = typer.Argument(..., help="Note id (e.g. note-3)."),
    text: str = typer.Argument(..., help="The corrected text (replaces the note)."),
) -> None:
    """Rewrite a note's text — for fixing a genuine mistake.

    A change in the world is a *new* note (`add`), not an edit.

    Example: pensieve edit note-3 "corrected text"
    """
    try:
        content_service().update_note(note, text, actor="cli", interface="cli")
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ updated {note}")


@app.command("rm")
def rm(
    note: str = typer.Argument(..., help="Note id to remove (e.g. note-3)."),
) -> None:
    """Delete a note (truly removes it).

    Example: pensieve rm note-3
    """
    try:
        content_service().delete_note(note)
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ deleted {note}")


@app.command()
def entities() -> None:
    """List the entity registry (people/orgs/topics) with note counts."""
    rows = entity_service().list_entities()
    if not rows:
        typer.echo("No entities yet.")
        return
    for e in rows:
        mark = " ★ promotable" if e["promotable"] else (" ✓" if e["promoted"] else "")
        typer.echo(f"{e['id']:<20} {e['kind']:<8} ×{e['count']}{mark}")


@app.command()
def find(
    query: str = typer.Argument(..., help="Name/alias substring to search."),
) -> None:
    """Fuzzy-search the entity registry by name or alias."""
    rows = entity_service().find_entities(query)
    if not rows:
        typer.echo(f"No entities matching '{query}'.")
        return
    for e in rows:
        typer.echo(f"{e['id']:<20} {e['name']} ({e['kind']}) ×{e['count']}")


@app.command()
def tag(
    note: str = typer.Argument(..., help="Note id (e.g. note-3)."),
    name: str = typer.Argument(..., help="Entity name (resolved/created by slug)."),
    kind: str = typer.Option(
        "topic", "--kind", "-k", help="person | org | topic (for a new entity)."
    ),
) -> None:
    """Tag a note with an entity (creates the entity if new).

    Example: pensieve tag note-3 "Rafia Naseem" -k person
    """
    try:
        ids = content_service().tag_note(note, [{"name": name, "kind": kind}])
    except NoteNotFound as exc:
        typer.echo(f"✗ No note '{note}'", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ tagged {note} with {ids[0]}")


@app.command()
def entity(
    entity_id: str = typer.Argument(..., help="Entity id (see 'pensieve entities')."),
) -> None:
    """Show an entity and every note that references it (recall)."""
    try:
        view = entity_service().get_entity_view(entity_id)
    except EntityNotFound as exc:
        typer.echo(f"✗ No entity '{entity_id}'", err=True)
        raise typer.Exit(code=1) from exc
    badge = " [thread]" if view["promoted"] else ""
    typer.echo(f"{view['name']} ({view['kind']}) ×{view['count']}{badge}")
    for n in view["notes"]:
        typer.echo(f"  {n['id']}  {n['text']}  ({n['date'][:10]})")


@app.command()
def promote(
    entity: str = typer.Argument(..., help="Entity id (see 'pensieve entities')."),
    stream: str = typer.Option(
        ..., "--stream", "-s", help="Parent stream the new thread lives under."
    ),
) -> None:
    """Promote an entity into its own thread under a stream.

    Example: pensieve promote rafia-naseem -s recs
    """
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
