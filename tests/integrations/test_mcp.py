"""Integration test: the MCP server over stdio (the agent-facing protocol).

Spawns the server as a subprocess and drives it with the MCP client — proving the
full agent → MCP → services → SQLite path without needing a live agent.
"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation

CLIENT_NAME = "claude-code-test"


@asynccontextmanager
async def _client(store: Path) -> AsyncIterator[ClientSession]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pensieve.mcp_server"],
        env={**os.environ, "PENSIEVE_HOME": str(store)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read,
            write,
            client_info=Implementation(name=CLIENT_NAME, version="9.9"),
        ) as session:
            await session.initialize()
            yield session


async def _roundtrip(store: Path) -> tuple[set[str], object, object, str]:
    async with _client(store) as session:
        tools = {t.name for t in (await session.list_tools()).tools}
        await session.call_tool("create_stream", {"name": "Recs", "purpose": "Build"})
        added = await session.call_tool(
            "add_note", {"stream": "recs", "text": "talking to 4 curators"}
        )
        fetched = await session.call_tool("get_stream", {"stream": "recs"})
        listed = await session.call_tool("list_streams", {})
        return tools, added, fetched, str(listed)


def test_mcp_stdio_roundtrip(integration_store: Path):
    tools, added, fetched, listed = asyncio.run(_roundtrip(integration_store))

    assert {
        "create_stream",
        "list_streams",
        "add_note",
        "update_note",
        "delete_note",
        "get_stream",
        "list_entities",
        "find_entities",
    } <= tools
    assert added.isError is False
    assert "recs" in listed
    assert "talking to 4 curators" in str(fetched)


def test_mcp_records_client_as_actor(integration_store: Path):
    asyncio.run(_roundtrip(integration_store))

    # provenance now lives on the note (no separate commit log)
    from sqlmodel import select

    from pensieve.database.models import Note
    from pensieve.database.session import get_session

    with get_session() as session:
        rows = list(session.exec(select(Note)))

    assert any(r.actor == CLIENT_NAME and r.interface == "mcp" for r in rows)


async def _edit_delete(store: Path) -> tuple[object, object, str]:
    async with _client(store) as session:
        await session.call_tool("create_stream", {"name": "Recs"})
        await session.call_tool("add_note", {"stream": "recs", "text": "Tuesday"})
        edited = await session.call_tool(
            "update_note", {"note": "note-1", "text": "Wednesday"}
        )
        deleted = await session.call_tool("delete_note", {"note": "note-1"})
        fetched = await session.call_tool("get_stream", {"stream": "recs"})
        return edited, deleted, str(fetched)


def test_mcp_update_and_delete(integration_store: Path):
    edited, deleted, fetched = asyncio.run(_edit_delete(integration_store))
    assert edited.isError is False
    assert deleted.isError is False
    assert "Wednesday" not in fetched and "Tuesday" not in fetched  # note removed


async def _tag_via_capture(store: Path) -> str:
    async with _client(store) as session:
        await session.call_tool("create_stream", {"name": "Recs"})
        await session.call_tool(
            "add_note",
            {
                "stream": "recs",
                "text": "met Rafia",
                "entities": [{"name": "Rafia Naseem", "kind": "person"}],
            },
        )
        listed = await session.call_tool("list_entities", {})
        return str(listed)


def test_mcp_add_note_tags_entities(integration_store: Path):
    listed = asyncio.run(_tag_via_capture(integration_store))
    assert "rafia-naseem" in listed


async def _fetch_missing(store: Path) -> object:
    async with _client(store) as session:
        return await session.call_tool("get_stream", {"stream": "nope"})


def test_mcp_missing_stream_is_friendly(integration_store: Path):
    result = asyncio.run(_fetch_missing(integration_store))
    text = str(result)
    assert result.isError is True
    assert "No stream 'nope'" in text
    assert "node" not in text.lower()  # internal term must not leak
