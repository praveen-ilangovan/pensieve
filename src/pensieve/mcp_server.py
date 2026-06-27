"""
mcp_server.py

MCP server exposing Pensieve's **ops** as tools for agents (Claude Code, etc.):

    agent  ->  MCP (this file)  ->  services  ->  SQLite

These are mechanical ops (`list_streams`, `create_stream`, `add_note`, `get_stream`) —
the judgment-bearing `capture`/`fetch` *flows* live in the agent's skill, which composes
these tools (see docs/verbs.md §0a). Run with `pensieve-mcp` (or `make mcp`).
"""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP

from .errors import NodeNotFound, NoteNotFound
from .factory import content_service, stream_service

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
def add_note(stream: str, text: str, ctx: Context) -> dict:
    """Add a note (a piece of information) to a stream.

    This is the mechanical commit step. Do the judgment first — decide *which* stream
    this belongs to (use `list_streams`), and get the user's OK — then call this. A
    change in the world is a *new* note; use `update_note` only to fix a mistake.

    Args:
        stream: Id of the target stream (from `list_streams`).
        text: The note text.
    """
    try:
        note = content_service().add_note(
            stream, text, actor=_client_name(ctx), interface="mcp"
        )
    except NodeNotFound as exc:
        raise ValueError(f"No stream '{stream}'") from exc
    return {"id": note.id, "stream": stream}


@mcp.tool()
def update_note(note: str, text: str, ctx: Context) -> dict:
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
def delete_note(note: str) -> dict:
    """Delete a note (truly removes it).

    Args:
        note: Id of the note to remove (e.g. "note-3").
    """
    try:
        content_service().delete_note(note)
    except NoteNotFound as exc:
        raise ValueError(f"No note '{note}'") from exc
    return {"deleted": note}


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


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
