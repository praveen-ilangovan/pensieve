"""
cli/main.py

Pensieve CLI entry point. Slice 1: init / create / ls.
"""

from __future__ import annotations

import typer

from ..config import get_settings
from ..database.session import init_db
from ..services import streams

app = typer.Typer(
    name="pensieve",
    help="Pensieve — manually-triggered, multi-stream agent memory.",
    no_args_is_help=True,
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
    """Create a new stream (a top-level subject node)."""
    try:
        node = streams.create_stream(stream, purpose)
    except streams.StreamExists as exc:
        typer.echo(f"✗ {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"✓ Created stream '{node.id}'")


@app.command("ls")
def ls() -> None:
    """List all streams."""
    rows = streams.list_streams()
    if not rows:
        typer.echo("No streams yet. Create one: pensieve create --stream <name>")
        return
    for node in rows:
        purpose = node.properties.get("purpose") or "—"
        typer.echo(f"{node.id:<24} {purpose}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
