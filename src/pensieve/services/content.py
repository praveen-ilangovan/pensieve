"""
content.py

Content domain logic — the stuff that lives *inside* a node (slice 4). For now: notes
(the append-only log). Pure domain/use-case layer atop the `UnitOfWork` port.

Each ``add_note`` is one **atomic commit**: mint a commit id + a per-node note id,
write the note and a ``history`` row, bump the node version — all before a single
``uow.commit()``. ID allocation is 1-based and non-reusing:
  - commit ids — scope ``_commit`` / kind ``commit`` -> ``c1``, ``c2`` … (global)
  - note ids   — scope ``<node_id>`` / kind ``note``  -> ``note-1`` … (per node)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..database.models import History, Note
from ..errors import NodeNotFound, PensieveError  # re-exported for callers/tests
from ..repository.base import UnitOfWork

__all__ = ["VALID_FLAVORS", "ContentService", "NodeNotFound", "PensieveError"]

VALID_FLAVORS = {"decision", "outcome", "observation"}


class ContentService:
    """Append content to nodes, atop an injected unit-of-work factory."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def add_note(
        self,
        node_id: str,
        text: str,
        *,
        flavor: str | None = None,
        supersedes: str | None = None,
        session_id: str | None = None,
        summary: str | None = None,
        actor: str | None = None,
        interface: str | None = None,
    ) -> Note:
        """Append a note to a node (a stream, for now) as one atomic commit.

        ``actor``/``interface`` record commit provenance (who/how) on the history row.
        Raises ``NodeNotFound`` if the node is missing, ``PensieveError`` on a bad
        flavor.
        """
        if flavor is not None and flavor not in VALID_FLAVORS:
            raise PensieveError(
                f"Invalid flavor {flavor!r} (expected one of {sorted(VALID_FLAVORS)})"
            )
        with self._uow() as uow:
            node = uow.repo.get_node(node_id)
            if node is None:
                raise NodeNotFound(f"No node '{node_id}'")

            commit_id = uow.repo.next_id("_commit", "commit", "c")
            note_id = uow.repo.next_id(node_id, "note", "note-")
            now = datetime.now(timezone.utc)

            note = Note(
                node_id=node_id,
                id=note_id,
                text=text,
                flavor=flavor,
                supersedes=supersedes,
                date=now,
                commit_id=commit_id,
            )
            uow.repo.add_note(note)

            new_version = node.version + 1
            uow.repo.add_history(
                History(
                    node_id=node_id,
                    commit_id=commit_id,
                    version=new_version,
                    session=session_id,
                    actor=actor,
                    interface=interface,
                    date=now,
                    summary=summary or text[:80],
                    changes=[{"op": "add_note", "note": note_id}],
                )
            )
            node.version = new_version
            node.updated = now
            uow.repo.save_node(node)

            uow.commit()
            return note

    def get_stream_view(self, node_id: str) -> dict[str, Any]:
        """The node's **thin view**: identity + purpose + its notes (chronological).

        ``todos`` / ``children`` are present but empty — filled by later slices. Raises
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
                "version": node.version,
                "notes": [
                    {
                        "id": n.id,
                        "text": n.text,
                        "flavor": n.flavor,
                        "date": n.date.isoformat(),
                    }
                    for n in notes
                ],
                "todos": [],
                "children": [],
            }
