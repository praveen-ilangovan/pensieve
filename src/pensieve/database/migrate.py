"""
migrate.py

Self-migration: bring the configured store to the latest schema by running Alembic
``upgrade head`` programmatically. Called from ``init_db`` so an installed CLI (and the
MCP server) migrate their own store on first use — no manual step.

- **Guarded** to run once per store per process (cheap on the hot path).
- **Legacy stores** (created by ``create_all`` before migrations existed) are stamped at
  the baseline, then upgraded — so existing data is preserved, never wiped.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from ..config import get_settings
from .session import get_engine

# The first migration's revision id — legacy (unmanaged) stores match this schema.
_BASELINE = "0001_initial"

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Which store urls have already been migrated this process.
_migrated: set[str] = set()


def _config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade_to_head() -> None:
    """Bring the configured store to the latest schema (idempotent, once per process)."""
    url = get_settings().db_url
    if url in _migrated:
        return

    logging.getLogger("alembic").setLevel(logging.WARNING)  # quiet the INFO chatter
    cfg = _config(url)
    insp = inspect(get_engine())
    if insp.has_table("nodes") and not insp.has_table("alembic_version"):
        # Pre-migrations store: its schema == the baseline. Adopt it, then upgrade.
        command.stamp(cfg, _BASELINE)
    command.upgrade(cfg, "head")
    _migrated.add(url)


def reset_migration_cache() -> None:
    """Forget which stores were migrated (used by tests that wipe the store)."""
    _migrated.clear()
