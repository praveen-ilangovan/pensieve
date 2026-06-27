"""
errors.py

Shared domain errors, kept storage-agnostic (no SQL/SQLModel here) so the service
layer and any repository adapter can raise/catch the same types.
"""

from __future__ import annotations


class PensieveError(Exception):
    """Base error for Pensieve operations."""


class StreamExists(PensieveError):
    """A stream with this id already exists."""


class NodeNotFound(PensieveError):
    """No node exists with the given id."""


class NoteNotFound(PensieveError):
    """No note exists with the given id."""


class EntityNotFound(PensieveError):
    """No entity exists with the given id."""


class EntityExists(PensieveError):
    """An entity with this id already exists."""
