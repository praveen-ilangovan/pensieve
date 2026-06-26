"""
factory.py

The composition root: wires the domain services to the default (SQLite) storage
adapter. The CLI, the MCP server, and runners build services from here, so the choice
of storage lives in exactly one place.
"""

from __future__ import annotations

from .repository.sqlite import SqliteUnitOfWork
from .services.content import ContentService
from .services.streams import StreamService


def stream_service() -> StreamService:
    return StreamService(SqliteUnitOfWork)


def content_service() -> ContentService:
    return ContentService(SqliteUnitOfWork)
