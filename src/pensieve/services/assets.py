"""
assets.py

Asset domain logic — **by-reference** pointers to live external context (a repo, file,
dir, URL, image or doc) attached to a note or a node (stream/thread). Pure domain/use-case
layer atop the ``UnitOfWork`` port.

An asset stores a *pointer* (path/URL) + a one-line ``hint`` for how to use it — never the
contents. The engine never follows an asset; reading it is a deliberate action by the agent
(see the skill). Visibility is **derived** from the owner's liveness, so an asset has no
soft-delete of its own and ``remove_asset`` is a plain hard delete.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..database.models import Asset
from ..errors import (
    AssetNotFound,
    NodeNotFound,
    NoteNotFound,
)  # re-exported for callers
from ..repository.base import UnitOfWork

__all__ = [
    "AssetNotFound",
    "AssetService",
    "NodeNotFound",
    "NoteNotFound",
    "asset_view",
    "infer_kind",
    "local_missing",
]

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_url(location: str) -> bool:
    return location.strip().lower().startswith(("http://", "https://"))


def infer_kind(location: str) -> str:
    """Best-effort kind from the location (``--kind`` always wins upstream)."""
    loc = location.strip()
    if _is_url(loc):
        bare = loc.lower().split("?", 1)[0].split("#", 1)[0]
        return "image" if bare.endswith(_IMAGE_EXTS) else "url"
    p = Path(loc).expanduser()
    if (p / ".git").exists():
        return "repo"
    if p.is_dir():
        return "dir"
    if loc.lower().endswith(_IMAGE_EXTS):
        return "image"
    return "file"


def local_missing(location: str, kind: str) -> bool:
    """True if it's a *local* pointer that doesn't currently resolve (warn, but still store —
    paths move, and we hold the pointer regardless). URLs are never checked here."""
    if kind == "url" or _is_url(location):
        return False
    return not Path(location).expanduser().exists()


class AssetService:
    """Attach/list/remove by-reference assets, atop an injected unit-of-work factory."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow = uow_factory

    def add_asset(
        self,
        target: str,
        location: str,
        *,
        hint: str | None = None,
        label: str | None = None,
        kind: str | None = None,
        actor: str | None = None,
        interface: str | None = None,
    ) -> Asset:
        """Attach an asset to ``target`` — a note (``note-*``) or a node (stream/thread).
        ``kind`` is inferred from ``location`` if omitted. Raises ``NoteNotFound`` /
        ``NodeNotFound``. (Does not block on a missing local path — callers warn; we store.)
        """
        with self._uow() as uow:
            note_id: str | None = None
            node_id: str | None = None
            if target.startswith("note-"):
                if uow.repo.get_note(target) is None:
                    raise NoteNotFound(f"No note '{target}'")
                note_id = target
            else:
                if uow.repo.get_node(target) is None:
                    raise NodeNotFound(f"No stream or thread '{target}'")
                node_id = target

            now = _utcnow()
            asset = Asset(
                id=uow.repo.next_id("_asset", "asset", "asset-"),
                kind=kind or infer_kind(location),
                location=location,
                hint=hint,
                label=label,
                note_id=note_id,
                node_id=node_id,
                actor=actor,
                interface=interface,
                created=now,
                updated=now,
            )
            uow.repo.add_asset(asset)
            uow.commit()
            return asset

    def list_assets(self, target: str) -> list[dict[str, Any]]:
        """The assets attached to a stream/thread/note. Raises if the target is missing."""
        with self._uow() as uow:
            if target.startswith("note-"):
                if uow.repo.get_note(target) is None:
                    raise NoteNotFound(f"No note '{target}'")
                assets = uow.repo.assets_for_note(target)
            else:
                if uow.repo.get_node(target) is None:
                    raise NodeNotFound(f"No stream or thread '{target}'")
                assets = uow.repo.assets_for_node(target)
            return [asset_view(a) for a in assets]

    def remove_asset(self, asset_id: str) -> None:
        """Hard-remove an asset (pointers are cheap to re-add). Raises ``AssetNotFound``."""
        with self._uow() as uow:
            if uow.repo.get_asset(asset_id) is None:
                raise AssetNotFound(f"No asset '{asset_id}'")
            uow.repo.remove_asset(asset_id)
            uow.commit()


def asset_view(asset: Asset) -> dict[str, Any]:
    """The render shape — the pointer + how to use it, **never** its contents."""
    return {
        "id": asset.id,
        "kind": asset.kind,
        "location": asset.location,
        "hint": asset.hint,
        "label": asset.label,
    }
