"""
factory.py

The composition root: wires the domain services to the default (SQLite) storage
adapter. The CLI, the MCP server, and runners build services from here, so the choice
of storage lives in exactly one place.
"""

from __future__ import annotations

from .repository.sqlite import SqliteUnitOfWork
from .services.assets import AssetService
from .services.content import ContentService
from .services.entities import EntityService
from .services.streams import StreamService


def stream_service() -> StreamService:
    return StreamService(SqliteUnitOfWork)


def asset_service() -> AssetService:
    return AssetService(SqliteUnitOfWork)


def content_service() -> ContentService:
    return ContentService(SqliteUnitOfWork)


def entity_service() -> EntityService:
    return EntityService(SqliteUnitOfWork)
