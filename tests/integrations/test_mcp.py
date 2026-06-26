"""Integration test: the MCP server over stdio (the agent-facing protocol).

Spawns the server as a subprocess and drives it with the MCP client — proving the
full agent → MCP → services → SQLite path without needing a live agent.
"""

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _roundtrip(store: Path) -> tuple[set[str], object, str]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pensieve.mcp_server"],
        env={**os.environ, "PENSIEVE_HOME": str(store)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            created = await session.call_tool(
                "create_stream", {"name": "Recs", "purpose": "Build Recs"}
            )
            listed = await session.call_tool("list_streams", {})
            return tools, created, str(listed)


def test_mcp_stdio_roundtrip(integration_store: Path):
    tools, created, listed_str = asyncio.run(_roundtrip(integration_store))

    assert {"create_stream", "list_streams"} <= tools
    assert created.isError is False
    assert "recs" in listed_str
