"""
mcp_server.py

MCP server exposing Pensieve operations as tools for agents (Claude Code, etc.).
It reuses the exact same service layer as the CLI, so the whole path is:

    agent  ->  MCP (this file)  ->  services.streams  ->  SQLModel/SQLite

Run it with `pensieve-mcp` (or `make mcp`). Store location comes from the same
config as the CLI (PENSIEVE_HOME / .env).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .services import streams

mcp = FastMCP("pensieve")


@mcp.tool()
def list_streams() -> list[dict[str, str]]:
    """List all streams (the top-level domains) in the user's Pensieve."""
    return [
        {
            "id": node.id,
            "label": node.label,
            "purpose": str(node.properties.get("purpose") or ""),
        }
        for node in streams.list_streams()
    ]


@mcp.tool()
def create_stream(name: str, purpose: str = "") -> dict[str, str]:
    """Create a new stream — a top-level domain of work/life.

    Args:
        name: Display name of the stream (e.g. "Recs", "Employment").
        purpose: Why the stream exists — its enduring north-star (optional).
    """
    node = streams.create_stream(name, purpose)
    return {
        "id": node.id,
        "label": node.label,
        "kind": node.kind,
        "purpose": purpose,
    }


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
