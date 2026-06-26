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


def test_add_and_show_round_trip(integration_store: Path):
    assert (
        runner.invoke(
            app, ["create", "--stream", "Recs", "--purpose", "Build Recs"]
        ).exit_code
        == 0
    )

    result = runner.invoke(app, ["add", "talking to 4 curators", "--stream", "recs"])
    assert result.exit_code == 0
    assert "note-1" in result.stdout

    result = runner.invoke(
        app, ["add", "Rafia postponed call", "-s", "recs", "-f", "outcome"]
    )
    assert result.exit_code == 0
    assert "note-2" in result.stdout

    result = runner.invoke(app, ["show", "recs"])
    assert result.exit_code == 0
    assert "Build Recs" in result.stdout
    assert "talking to 4 curators" in result.stdout
    assert "outcome" in result.stdout
    assert "note-1" in result.stdout and "note-2" in result.stdout


def test_show_empty_stream(integration_store: Path):
    assert runner.invoke(app, ["create", "--stream", "Recs"]).exit_code == 0
    result = runner.invoke(app, ["show", "recs"])
    assert result.exit_code == 0
    assert "(empty)" in result.stdout


def test_add_to_missing_stream_exits_nonzero(integration_store: Path):
    result = runner.invoke(app, ["add", "hi", "--stream", "nope"])
    assert result.exit_code == 1
    # user-facing language: "stream", never the internal "node"
    assert "No stream 'nope'" in result.output
    assert "node" not in result.output


def test_show_missing_stream_exits_nonzero(integration_store: Path):
    result = runner.invoke(app, ["show", "nope"])
    assert result.exit_code == 1
    assert "No stream 'nope'" in result.output
    assert "node" not in result.output
