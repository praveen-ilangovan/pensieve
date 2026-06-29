"""
models.py

SQLModel table models — the physical realization of the Pensieve model
(see docs/philosophy.md). A generic ``nodes`` table (streams + threads) + ``edges``
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
    deleted_at: datetime | None = None  # soft-delete (null = active)


class Edge(SQLModel, table=True):
    """A typed relationship between two nodes (NON-`contains`).

    RESERVED — declared & migrated but not yet read/written by any code. Kept for the
    planned entity-to-entity edges (see plans/roadmap.md); do not assume it holds data.
    """

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
    deleted_at: datetime | None = None  # soft-delete (null = active)
    # provenance (agent-agnostic): who last wrote it, and how.
    actor: str | None = None  # "cli" | "claude-code" | …
    interface: str | None = None  # "cli" | "mcp"


class Attachment(SQLModel, table=True):
    """A note attached to a node (stream/thread). Many-to-many — a note can be
    multi-homed (the same note under several threads/streams)."""

    __tablename__ = "attachments"

    note_id: str = Field(foreign_key="notes.id", primary_key=True, index=True)
    node_id: str = Field(foreign_key="nodes.id", primary_key=True, index=True)


class Entity(SQLModel, table=True):
    """A named thing notes refer to (person/org/topic/…). Lives as a lightweight
    registry entry — a *tag target* — until it recurs enough to be **promoted** into its
    own thread node (``node_id`` then points at it)."""

    __tablename__ = "entities"

    id: str = Field(primary_key=True)  # kebab slug, e.g. "rafia"
    name: str  # canonical display name
    kind: str  # person | org | topic | …
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    node_id: str | None = Field(
        default=None, foreign_key="nodes.id"
    )  # set on promotion
    created: datetime = Field(default_factory=_utcnow)
    updated: datetime = Field(default_factory=_utcnow)


class Tag(SQLModel, table=True):
    """A note references an entity (a *link*). Many-to-many. The count of **live** links
    per entity is the promotion counter (derived, not stored). ``entity rm`` soft-deletes
    these links (it unlinks — it never deletes a note); ``entity restore`` revives them."""

    __tablename__ = "tags"

    note_id: str = Field(foreign_key="notes.id", primary_key=True, index=True)
    entity_id: str = Field(foreign_key="entities.id", primary_key=True, index=True)
    deleted_at: datetime | None = None  # soft-unlink (null = active link)


class Asset(SQLModel, table=True):
    """A **by-reference** pointer to live external context — a repo, file, dir, URL, image
    or doc — attached to a note OR a node (stream/thread). Holds the pointer + a one-line
    usage ``hint``; never the contents, and the engine never follows it (read-on-demand).
    Visibility is **derived** from its owner's liveness — it has no ``deleted_at`` of its
    own, so removal is a plain hard delete."""

    __tablename__ = "assets"

    id: str = Field(primary_key=True)  # global: asset-<n>
    kind: str  # repo | file | dir | url | image | doc (recommended; not enforced)
    location: str  # the path or URL (the pointer)
    hint: str | None = None  # one-line "how to use me"
    label: str | None = None  # optional short display name
    # owner: exactly one of the two is set
    note_id: str | None = Field(default=None, foreign_key="notes.id", index=True)
    node_id: str | None = Field(default=None, foreign_key="nodes.id", index=True)
    # provenance (agent-agnostic)
    actor: str | None = None
    interface: str | None = None
    created: datetime = Field(default_factory=_utcnow)
    updated: datetime = Field(default_factory=_utcnow)


class Counter(SQLModel, table=True):
    """Non-reusing id counters (scope ``_note`` for global note ids; kind ``note``)."""

    __tablename__ = "counters"

    scope: str = Field(primary_key=True)
    kind: str = Field(primary_key=True)
    next: int = 0
