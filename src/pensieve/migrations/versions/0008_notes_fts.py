"""notes full-text search (FTS5)

Revision ID: 0008_notes_fts
Revises: 0007_assets
Create Date: 2026-06-29 10:00:00.000000

A standalone FTS5 virtual table indexing note text for `search` (slice 8). `note_id` is
stored UNINDEXED (so we can map a hit back to the note) and only `text` is searched, with
the `porter` stemmer over `unicode61` (stemmed, case/diacritic-folded recall). The `notes`
table stays the single source of truth — this is just a text index, kept in sync by the
repo on note add/edit and filtered for liveness at query time.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0008_notes_fts"
down_revision: Union[str, Sequence[str], None] = "0007_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE VIRTUAL TABLE notes_fts USING fts5("
        "note_id UNINDEXED, text, tokenize='porter unicode61')"
    )
    # backfill existing notes (no-op on a fresh store)
    op.execute("INSERT INTO notes_fts (note_id, text) SELECT id, text FROM notes")


def downgrade() -> None:
    op.execute("DROP TABLE notes_fts")
