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


# the agent-facing op surface — keep at parity with the CLI (create/add · edit · get ·
# soft remove/restore · tag/untag · promote).
EXPECTED_TOOLS = {
    "list_streams",
    "create_stream",
    "edit_stream",
    "remove_stream",
    "restore_stream",
    "get_stream",
    "add_note",
    "edit_note",
    "remove_note",
    "restore_note",
    "tag_note",
    "untag_note",
    "list_entities",
    "find_entities",
    "get_entity",
    "edit_entity",
    "remove_entity",
    "restore_entity",
    "promote_entity",
}


def test_mcp_stdio_roundtrip(integration_store: Path):
    tools, added, fetched, listed = asyncio.run(_roundtrip(integration_store))

    assert tools == EXPECTED_TOOLS  # full parity — nothing missing, nothing stray
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


async def _edit_remove_restore(store: Path) -> tuple[object, object, str, str]:
    async with _client(store) as session:
        await session.call_tool("create_stream", {"name": "Recs"})
        await session.call_tool("add_note", {"stream": "recs", "text": "Tuesday"})
        edited = await session.call_tool(
            "edit_note", {"note": "note-1", "text": "Wednesday"}
        )
        removed = await session.call_tool("remove_note", {"note": "note-1"})
        gone = await session.call_tool("get_stream", {"stream": "recs"})
        await session.call_tool("restore_note", {"note": "note-1"})
        back = await session.call_tool("get_stream", {"stream": "recs"})
        return edited, removed, str(gone), str(back)


def test_mcp_edit_remove_restore_note(integration_store: Path):
    edited, removed, gone, back = asyncio.run(_edit_remove_restore(integration_store))
    assert edited.isError is False
    assert removed.isError is False
    assert "Wednesday" not in gone  # soft-removed → hidden from the view
    assert "Wednesday" in back  # restore brings the (edited) note back


async def _stream_remove_restore(store: Path) -> tuple[str, str]:
    async with _client(store) as session:
        await session.call_tool("create_stream", {"name": "Recs"})
        await session.call_tool("add_note", {"stream": "recs", "text": "a note"})
        await session.call_tool("remove_stream", {"stream": "recs"})
        after_rm = await session.call_tool("list_streams", {})
        await session.call_tool("restore_stream", {"stream": "recs"})
        after_restore = await session.call_tool("list_streams", {})
        return str(after_rm), str(after_restore)


def test_mcp_remove_restore_stream(integration_store: Path):
    after_rm, after_restore = asyncio.run(_stream_remove_restore(integration_store))
    assert "recs" not in after_rm
    assert "recs" in after_restore


async def _entity_remove(store: Path) -> tuple[object, str, str]:
    async with _client(store) as session:
        await session.call_tool("create_stream", {"name": "Recs"})
        await session.call_tool(
            "add_note",
            {
                "stream": "recs",
                "text": "Rafia and Travis",
                "entities": [
                    {"name": "Rafia", "kind": "person"},
                    {"name": "Travis", "kind": "person"},
                ],
            },
        )
        removed = await session.call_tool("remove_entity", {"entity": "rafia"})
        listed = await session.call_tool("list_entities", {})
        recs = await session.call_tool("get_stream", {"stream": "recs"})
        return removed, str(listed), str(recs)


def test_mcp_remove_entity_unlinks_keeps_note(integration_store: Path):
    removed, listed, recs = asyncio.run(_entity_remove(integration_store))
    assert removed.isError is False
    assert "rafia" not in listed and "travis" in listed  # rafia unlinked, travis survives
    assert "Rafia and Travis" in recs  # the shared note is NOT deleted


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


async def _promote(store: Path) -> tuple[object, str]:
    async with _client(store) as session:
        await session.call_tool("create_stream", {"name": "Recs"})
        await session.call_tool(
            "add_note",
            {
                "stream": "recs",
                "text": "met Rafia",
                "entities": [{"name": "Rafia", "kind": "person"}],
            },
        )
        promoted = await session.call_tool(
            "promote_entity", {"entity": "rafia", "stream": "recs"}
        )
        thread = await session.call_tool("get_stream", {"stream": "rafia"})
        return promoted, str(thread)


def test_mcp_promote_entity(integration_store: Path):
    promoted, thread = asyncio.run(_promote(integration_store))
    assert promoted.isError is False
    assert "met Rafia" in thread  # the entity's note lives under the new thread


async def _fetch_missing(store: Path) -> object:
    async with _client(store) as session:
        return await session.call_tool("get_stream", {"stream": "nope"})


def test_mcp_missing_stream_is_friendly(integration_store: Path):
    result = asyncio.run(_fetch_missing(integration_store))
    text = str(result)
    assert result.isError is True
    assert "No stream 'nope'" in text
    assert "node" not in text.lower()  # internal term must not leak
