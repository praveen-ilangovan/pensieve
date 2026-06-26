"""Integration test: the full CLI → service → SQLite round-trip (local integration store)."""

from pathlib import Path

from typer.testing import CliRunner

from pensieve.cli.main import app

runner = CliRunner()


def test_init_create_ls_end_to_end(integration_store: Path):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (integration_store / "pensieve.db").exists()

    result = runner.invoke(app, ["create", "--stream", "Recs", "--purpose", "Build Recs"])
    assert result.exit_code == 0
    assert "recs" in result.stdout

    result = runner.invoke(app, ["ls"])
    assert result.exit_code == 0
    assert "recs" in result.stdout
    assert "Build Recs" in result.stdout


def test_duplicate_stream_exits_nonzero(integration_store: Path):
    assert runner.invoke(app, ["create", "--stream", "Recs"]).exit_code == 0
    assert runner.invoke(app, ["create", "--stream", "Recs"]).exit_code == 1
