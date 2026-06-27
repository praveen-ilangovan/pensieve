"""remodel notes standalone + attachments

Revision ID: 0003_remodel
Revises: 0002_provenance
Create Date: 2026-06-27

Slice 5a — the information-lake remodel:
  * notes become standalone (global id) + provenance on the note (actor/interface);
  * a notes<->nodes ``attachments`` table makes notes multi-homed;
  * drop the commit-log (``history``), the unused ``todos``, and notes' flavor/supersedes.

Notes are intentionally **reset** here (clear-and-rebuild — agreed, the data is tiny);
this is not a data-preserving migration of note content.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "0003_remodel"
down_revision: Union[str, Sequence[str], None] = "0002_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("history")
    op.drop_table("todos")
    op.drop_table("notes")  # reset — recreated under the new model

    op.create_table(
        "notes",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("updated", sa.DateTime(), nullable=False),
        sa.Column("actor", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("interface", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "attachments",
        sa.Column("note_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("node_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"]),
        sa.PrimaryKeyConstraint("note_id", "node_id"),
    )
    op.create_index("ix_attachments_note_id", "attachments", ["note_id"])
    op.create_index("ix_attachments_node_id", "attachments", ["node_id"])

    # sweep pre-remodel counter cruft (slice-4 per-node note + _commit counters);
    # note ids are global now (scope='_note').
    op.execute("DELETE FROM counters WHERE NOT (scope = '_note' AND kind = 'note')")


def downgrade() -> None:
    op.drop_index("ix_attachments_node_id", table_name="attachments")
    op.drop_index("ix_attachments_note_id", table_name="attachments")
    op.drop_table("attachments")
    op.drop_table("notes")

    op.create_table(
        "notes",
        sa.Column("node_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("flavor", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("supersedes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("commit_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("node_id", "id"),
    )
    op.create_table(
        "todos",
        sa.Column("node_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("node_id", "id"),
    )
    op.create_table(
        "history",
        sa.Column("node_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("commit_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("session", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("actor", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("interface", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("node_id", "commit_id"),
    )
