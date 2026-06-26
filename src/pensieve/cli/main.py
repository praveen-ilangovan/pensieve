"""
cli/main.py

Pensieve CLI entry point — the engine's **op** surface (init / create / ls / add /
show). The judgment-bearing flows (capture / fetch) live in the agent skill, not here
(see docs/verbs.md §0a).
"""

from __future__ import annotations

from enum import Enum

import typer

from ..config import get_settings
from ..database.session import init_db
from ..errors import NodeNotFound, PensieveError, StreamExists
from ..factory import content_service, stream_service

app = typer.Typer(
    name="pensieve",
    help=(
        "Pensieve — manually-triggered, multi-stream agent memory.\n\n"
        "A stream is a top-level domain (recs, employment, …); notes are captured "
        "onto it. These commands are the mechanical op surface — the judgment-bearing "
        "capture/fetch flows live in the agent skill."
    ),
    epilog=(
        "Typical flow: **create** a stream → **add** notes to it → **show** it. "
        "Run `pensieve COMMAND --help` for a per-command example."
    ),
    no_args_is_help=True,
    rich_markup_mode="markdown",
)


class Flavor(str, Enum):
    """Optional classification of a note (mirrors content.VALID_FLAVORS)."""

    decision = "decision"
    outcome = "outcome"
    observation = "observation"


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
    flavor: Flavor | None = typer.Option(
        None, "--flavor", "-f", help="Optional: classify the note."
    ),
) -> None:
    """Add a note to a stream.

    You supply the structure (which stream, the text). This is the mechanical
    `add_note` op; the agent's `capture` flow is what does this with judgment.

    Example: pensieve add "talking to 4 curators" -s recs -f outcome
    """
    try:
        note = content_service().add_note(
            stream,
            text,
            flavor=flavor.value if flavor else None,
            actor="cli",
            interface="cli",
        )
    except NodeNotFound as exc:
        typer.echo(f"✗ No stream '{stream}'", err=True)
        raise typer.Exit(code=1) from exc
    except PensieveError as exc:
        typer.echo(f"✗ {exc}", err=True)
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
        flavor = f"[{note['flavor']}] " if note["flavor"] else ""
        date = note["date"][:10]  # YYYY-MM-DD
        typer.echo(f"  {note['id']}  {flavor}{note['text']}  ({date})")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
