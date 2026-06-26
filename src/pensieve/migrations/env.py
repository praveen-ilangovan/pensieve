"""
Alembic environment for Pensieve (SQLModel + SQLite).

- target metadata comes from SQLModel (importing models registers the tables);
- the URL comes from Pensieve's own settings (PENSIEVE_HOME), so migrations always
  target the same store the app uses;
- ``render_as_batch=True`` so SQLite ALTERs (drop/alter column) work via batch mode.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import models so they register on SQLModel.metadata (needed for autogenerate).
from pensieve.config import get_settings
from pensieve.database import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Point Alembic at the configured store (overrides any sqlalchemy.url in the ini).
config.set_main_option("sqlalchemy.url", get_settings().db_url)


def run_migrations_offline() -> None:
    """Run migrations without a live connection (emit SQL)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
