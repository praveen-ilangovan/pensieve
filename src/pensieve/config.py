"""
config.py

Configuration for Pensieve. All values are overridable via `PENSIEVE_*` env vars
(or a local `.env`). The store is global and cwd-independent.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ----------------------------------------------------------------------------#
# Settings
# ----------------------------------------------------------------------------#
class Settings(BaseSettings):
    """Pensieve configuration (env prefix: ``PENSIEVE_``)."""

    model_config = SettingsConfigDict(
        env_prefix="PENSIEVE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where the store lives (PENSIEVE_HOME). Defaults to ~/.pensieve.
    HOME: Path = Path.home() / ".pensieve"
    DB_FILENAME: str = "pensieve.db"

    # SQLite pragmas / engine
    BUSY_TIMEOUT_MS: int = 5000
    ECHO: bool = False  # SQLAlchemy echo (SQL logging)

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def db_path(self) -> Path:
        """Absolute path to the SQLite database file."""
        return self.HOME.expanduser() / self.DB_FILENAME

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def db_url(self) -> str:
        """SQLAlchemy URL for the SQLite database."""
        return f"sqlite:///{self.db_path}"


def get_settings() -> Settings:
    """Build a fresh Settings from the current environment (re-reads ``PENSIEVE_*``)."""
    return Settings()
