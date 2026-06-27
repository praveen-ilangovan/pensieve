"""
models.py

SQLModel table models — the physical realization of the Pensieve model
(see docs/glossary.md). A generic ``nodes`` table (streams + threads) + ``edges``
(deferred), standalone ``notes`` + a ``notes``↔``nodes`` ``attachments`` table
(notes are multi-homed), plus id ``counters``. Kind-specific data lives in
``Node.properties`` (JSON), so a new node-kind needs no schema change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

SCHEMA_VERSION = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Node(SQLModel, table=True):
    """A node: top-level ("stream") or contained ("thread"), of any ``kind``."""

    __tablename__ = "nodes"

    id: str = Field(primary_key=True)  # kebab slug
    label: str
    kind: str  # subject | person | org | place | event | asset
    parent_id: str | None = Field(
        default=None, foreign_key="nodes.id", index=True
    )  # None = top-level ("stream"); the `contains` edge
    properties: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    version: int = 1
    schema_version: int = SCHEMA_VERSION
    created: datetime = Field(default_factory=_utcnow)
    updated: datetime = Field(default_factory=_utcnow)


class Edge(SQLModel, table=True):
    """A typed relationship between two nodes (NON-`contains`)."""

    __tablename__ = "edges"

    from_id: str = Field(foreign_key="nodes.id", primary_key=True, index=True)
    to_id: str = Field(foreign_key="nodes.id", primary_key=True, index=True)
    kind: str = Field(
        primary_key=True
    )  # located-in | requested-by | about | relates-to | ...


class Note(SQLModel, table=True):
    """An atomic piece of information (global id). Append-only by default; edited only to
    fix a genuine mistake. Multi-homed via the ``attachments`` table. Provenance
    (``actor``/``interface``) lives here — there is no separate commit log."""

    __tablename__ = "notes"

    id: str = Field(primary_key=True)  # global: note-<n>
    text: str
    created: datetime = Field(default_factory=_utcnow)
    updated: datetime = Field(default_factory=_utcnow)
    # provenance (agent-agnostic): who last wrote it, and how.
    actor: str | None = None  # "cli" | "claude-code" | …
    interface: str | None = None  # "cli" | "mcp"


class Attachment(SQLModel, table=True):
    """A note attached to a node (stream/thread). Many-to-many — a note can be
    multi-homed (the same note under several threads/streams)."""

    __tablename__ = "attachments"

    note_id: str = Field(foreign_key="notes.id", primary_key=True, index=True)
    node_id: str = Field(foreign_key="nodes.id", primary_key=True, index=True)


class Counter(SQLModel, table=True):
    """Non-reusing id counters (scope ``_note`` for global note ids; kind ``note``)."""

    __tablename__ = "counters"

    scope: str = Field(primary_key=True)
    kind: str = Field(primary_key=True)
    next: int = 0
