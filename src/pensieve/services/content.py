"""
content.py

Content domain logic — notes (the information in the lake). Pure domain/use-case layer
atop the `UnitOfWork` port.

Notes are **append-only information**: `add_note` records a new piece of information and
attaches it to a node. `update_note` edits a note in place (only to fix a genuine
mistake — a world-change is a *new* note). `delete_note` truly removes one. Note ids are
**global** (`note-1`, `note-2`, …); a note is multi-homed via attachments.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..database.models import Note
from ..errors import (
    NodeNotFound,
    NoteNotFound,
    PensieveError,
)  # re-exported for callers
from ..repository.base import UnitOfWork

__all__ = ["ContentService", "NodeNotFound", "NoteNotFound", "PensieveError"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentService:
    """Add, edit, remove, and read notes — atop an injected unit-of-work factory."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def add_note(
        self,
        node_id: str,
        text: str,
        *,
        actor: str | None = None,
        interface: str | None = None,
    ) -> Note:
        """Record a new piece of information and attach it to a node (stream/thread).

        Raises ``NodeNotFound`` if the node is missing.
        """
        with self._uow() as uow:
            if uow.repo.get_node(node_id) is None:
                raise NodeNotFound(f"No node '{node_id}'")
            note_id = uow.repo.next_id("_note", "note", "note-")
            now = _utcnow()
            note = Note(
                id=note_id,
                text=text,
                created=now,
                updated=now,
                actor=actor,
                interface=interface,
            )
            uow.repo.add_note(note)
            uow.repo.attach(note_id, node_id)
            uow.commit()
            return note

    def update_note(
        self,
        note_id: str,
        text: str,
        *,
        actor: str | None = None,
        interface: str | None = None,
    ) -> Note:
        """Rewrite a note's text in place (for fixing a genuine mistake).

        Raises ``NoteNotFound`` if the note is missing.
        """
        with self._uow() as uow:
            note = uow.repo.get_note(note_id)
            if note is None:
                raise NoteNotFound(f"No note '{note_id}'")
            note.text = text
            note.updated = _utcnow()
            if actor is not None:
                note.actor = actor
            if interface is not None:
                note.interface = interface
            uow.repo.save_note(note)
            uow.commit()
            return note

    def delete_note(self, note_id: str) -> None:
        """Truly remove a note (and its attachments). Raises ``NoteNotFound``."""
        with self._uow() as uow:
            if uow.repo.get_note(note_id) is None:
                raise NoteNotFound(f"No note '{note_id}'")
            uow.repo.delete_note(note_id)
            uow.commit()

    def get_stream_view(self, node_id: str) -> dict[str, Any]:
        """The node's **thin view**: identity + purpose + its notes (chronological).

        ``children`` is present but empty (filled by a later slice). Raises
        ``NodeNotFound`` if the node is missing.
        """
        with self._uow() as uow:
            node = uow.repo.get_node(node_id)
            if node is None:
                raise NodeNotFound(f"No node '{node_id}'")
            notes = uow.repo.notes_for(node_id)
            return {
                "id": node.id,
                "label": node.label,
                "kind": node.kind,
                "purpose": str(node.properties.get("purpose") or ""),
                "notes": [
                    {"id": n.id, "text": n.text, "date": n.created.isoformat()}
                    for n in notes
                ],
                "children": [],
            }
