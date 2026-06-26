"""
Integration tests for the Alembic self-migration in `init_db`.

Covers the two real cases: a brand-new store, and a *legacy* store created before
migrations existed (tables present, no `alembic_version`) — which must be adopted at the
baseline and upgraded **without losing data**.
"""

from pathlib import Path

from sqlalchemy import inspect

from pensieve.database.session import get_engine, init_db


def _history_columns() -> set[str]:
    return {c["name"] for c in inspect(get_engine()).get_columns("history")}


def test_fresh_store_migrates_to_head(integration_store: Path):
    init_db()
    insp = inspect(get_engine())
    assert insp.has_table("alembic_version")
    assert {"actor", "interface"} <= _history_columns()


def test_legacy_store_is_adopted_and_upgraded(integration_store: Path):
    # Simulate a pre-migrations store: v1 tables, a row of real data, no alembic_version.
    with get_engine().begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE nodes (id VARCHAR PRIMARY KEY, label VARCHAR, kind VARCHAR, "
            "parent_id VARCHAR, properties JSON, version INTEGER, schema_version INTEGER,"
            " created DATETIME, updated DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE history (node_id VARCHAR, commit_id VARCHAR, version INTEGER, "
            "session VARCHAR, date DATETIME, summary VARCHAR, changes JSON, "
            "PRIMARY KEY (node_id, commit_id))"
        )
        conn.exec_driver_sql(
            "INSERT INTO nodes (id, label, kind, version, schema_version) "
            "VALUES ('recs', 'Recs', 'subject', 1, 1)"
        )

    init_db()  # should stamp baseline, then upgrade

    insp = inspect(get_engine())
    assert insp.has_table("alembic_version")
    assert {"actor", "interface"} <= _history_columns()  # 0002 applied

    # the pre-existing data survived the migration
    with get_engine().begin() as conn:
        ids = [row[0] for row in conn.exec_driver_sql("SELECT id FROM nodes")]
    assert "recs" in ids
