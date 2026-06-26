"""
models.py

SQLModel table models — the physical realization of the Pensieve property graph
(see docs/glossary.md). One generic ``nodes`` table + ``edges`` + per-node contents
(``todos``, ``notes``) + ``history``, plus id ``counters``. Kind-specific data lives
in ``Node.properties`` (JSON), so a new node-kind needs no schema change.
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


class Todo(SQLModel, table=True):
    """A todo — the mutable working set (open items only; completed are deleted)."""

    __tablename__ = "todos"

    node_id: str = Field(foreign_key="nodes.id", primary_key=True)
    id: str = Field(primary_key=True)  # todo-<n>
    text: str


class Note(SQLModel, table=True):
    """A note — the append-only log. ``flavor`` optional; ``supersedes`` links a reversal."""

    __tablename__ = "notes"

    node_id: str = Field(foreign_key="nodes.id", primary_key=True)
    id: str = Field(primary_key=True)  # note-<n>
    text: str
    flavor: str | None = None  # decision | outcome | observation
    supersedes: str | None = None
    date: datetime = Field(default_factory=_utcnow)
    commit_id: str


class History(SQLModel, table=True):
    """Per-node commit log (provenance)."""

    __tablename__ = "history"

    node_id: str = Field(foreign_key="nodes.id", primary_key=True)
    commit_id: str = Field(primary_key=True)  # c<n>
    version: int
    session: str | None = None
    date: datetime = Field(default_factory=_utcnow)
    summary: str | None = None
    changes: list[Any] = Field(default_factory=list, sa_column=Column(JSON))


class Counter(SQLModel, table=True):
    """Non-reusing id counters (scope = node_id or '_commit'; kind = note|todo|commit)."""

    __tablename__ = "counters"

    scope: str = Field(primary_key=True)
    kind: str = Field(primary_key=True)
    next: int = 0
