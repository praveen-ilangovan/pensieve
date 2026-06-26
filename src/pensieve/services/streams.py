"""
streams.py

Stream operations (slice 1). A "stream" is a top-level `subject` node (no parent).
"""

from __future__ import annotations

import re

from sqlmodel import col, select

from ..database.models import SCHEMA_VERSION, Node
from ..database.session import get_session, init_db


class PensieveError(Exception):
    """Base error for Pensieve service operations."""


class StreamExists(PensieveError):
    """A stream with this id already exists."""


def slugify(name: str) -> str:
    """Derive a stable kebab-case id from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise PensieveError(f"Cannot derive an id from name: {name!r}")
    return slug


def create_stream(name: str, purpose: str = "") -> Node:
    """Create a top-level `subject` node (a stream). Raises if the id is taken."""
    init_db()
    node_id = slugify(name)
    with get_session() as session:
        if session.get(Node, node_id) is not None:
            raise StreamExists(f"Stream '{node_id}' already exists")
        node = Node(
            id=node_id,
            label=name,
            kind="subject",
            parent_id=None,
            properties={"purpose": purpose},
            version=1,
            schema_version=SCHEMA_VERSION,
        )
        session.add(node)
        session.commit()
        session.refresh(node)
        return node


def list_streams() -> list[Node]:
    """All top-level nodes (streams), ordered by label."""
    init_db()
    with get_session() as session:
        statement = (
            select(Node).where(col(Node.parent_id).is_(None)).order_by(col(Node.label))
        )
        return list(session.exec(statement))
