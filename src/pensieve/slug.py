"""
slug.py

Stable kebab-case ids from display names — shared by streams and entities.
"""

from __future__ import annotations

import re

from .errors import PensieveError


def slugify(name: str) -> str:
    """Derive a stable kebab-case id from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise PensieveError(f"Cannot derive an id from name: {name!r}")
    return slug
