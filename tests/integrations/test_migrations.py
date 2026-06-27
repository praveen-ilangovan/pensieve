"""
Integration tests for the Alembic self-migration in `init_db`.

Covers a brand-new store and a *legacy* store (created before migrations existed:
tables present, no `alembic_version`) — which must be adopted at the baseline and
upgraded through the chain (0001 → 0002 → 0003) **without losing node data**.
"""

from pathlib import Path

from sqlalchemy import inspect

from pensieve.database.session import get_engine, init_db


def _tables() -> set[str]:
    return set(inspect(get_engine()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in inspect(get_engine()).get_columns(table)}


def test_fresh_store_migrates_to_head(integration_store: Path):
    init_db()
    assert {
        "nodes",
        "notes",
        "attachments",
        "entities",
        "tags",
        "alembic_version",
    } <= _tables()
    assert {"history", "todos"}.isdisjoint(_tables())  # dropped by 0003
    assert {"id", "text", "created", "updated", "actor", "interface"} == _columns("notes")
    assert _columns("attachments") == {"note_id", "node_id"}
    assert {"id", "name", "kind", "aliases", "node_id"} <= _columns("entities")


def test_legacy_store_is_adopted_and_upgraded(integration_store: Path):
    # Simulate a pre-migrations (create_all) store: v1 tables, a row of real data, no
    # alembic_version. 0003 drops history/todos/notes, so they must exist to be dropped.
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
            "CREATE TABLE todos (node_id VARCHAR, id VARCHAR, text VARCHAR, "
            "PRIMARY KEY (node_id, id))"
        )
        conn.exec_driver_sql(
            "CREATE TABLE notes (node_id VARCHAR, id VARCHAR, text VARCHAR, "
            "flavor VARCHAR, supersedes VARCHAR, date DATETIME, commit_id VARCHAR, "
            "PRIMARY KEY (node_id, id))"
        )
        conn.exec_driver_sql(
            "CREATE TABLE edges (from_id VARCHAR, to_id VARCHAR, kind VARCHAR, "
            "PRIMARY KEY (from_id, to_id, kind))"
        )
        conn.exec_driver_sql(
            "CREATE TABLE counters (scope VARCHAR, kind VARCHAR, next INTEGER, "
            "PRIMARY KEY (scope, kind))"
        )
        conn.exec_driver_sql(
            "INSERT INTO nodes (id, label, kind, version, schema_version) "
            "VALUES ('recs', 'Recs', 'subject', 1, 1)"
        )
        # a slice-4 counter that 0003 should sweep
        conn.exec_driver_sql(
            "INSERT INTO counters (scope, kind, next) VALUES ('recs', 'note', 2)"
        )

    init_db()  # stamp baseline, then upgrade through 0002 + 0003

    assert {"attachments", "alembic_version"} <= _tables()
    assert {"history", "todos"}.isdisjoint(_tables())
    assert {"actor", "interface"} <= _columns("notes")

    # the pre-existing node survived the chain; the stale counter was swept
    with get_engine().begin() as conn:
        ids = [row[0] for row in conn.exec_driver_sql("SELECT id FROM nodes")]
        counters = list(conn.exec_driver_sql("SELECT scope, kind FROM counters"))
    assert "recs" in ids
    assert ("recs", "note") not in [tuple(r) for r in counters]
