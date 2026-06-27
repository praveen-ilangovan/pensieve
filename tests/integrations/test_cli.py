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

    result = runner.invoke(app, ["add", "Rafia is one of them", "-s", "recs"])
    assert result.exit_code == 0
    assert "note-2" in result.stdout

    result = runner.invoke(app, ["show", "recs"])
    assert result.exit_code == 0
    assert "Build Recs" in result.stdout
    assert "talking to 4 curators" in result.stdout
    assert "note-1" in result.stdout and "note-2" in result.stdout


def test_edit_and_rm_round_trip(integration_store: Path):
    assert runner.invoke(app, ["create", "--stream", "Recs"]).exit_code == 0
    assert runner.invoke(app, ["add", "meeting Tuesday", "-s", "recs"]).exit_code == 0

    assert runner.invoke(app, ["edit", "note-1", "meeting Wednesday"]).exit_code == 0
    result = runner.invoke(app, ["show", "recs"])
    assert "meeting Wednesday" in result.stdout
    assert "Tuesday" not in result.stdout

    assert runner.invoke(app, ["rm", "note-1"]).exit_code == 0
    assert "(empty)" in runner.invoke(app, ["show", "recs"]).stdout


def test_edit_missing_note_exits_nonzero(integration_store: Path):
    result = runner.invoke(app, ["edit", "note-99", "x"])
    assert result.exit_code == 1
    assert "No note 'note-99'" in result.output


def test_entities_find_tag_flow(integration_store: Path):
    assert runner.invoke(app, ["create", "--stream", "Recs"]).exit_code == 0
    assert runner.invoke(app, ["add", "met rafia", "-s", "recs"]).exit_code == 0  # note-1

    result = runner.invoke(app, ["tag", "note-1", "Rafia Naseem", "-k", "person"])
    assert result.exit_code == 0
    assert "rafia-naseem" in result.stdout

    result = runner.invoke(app, ["entities"])
    assert "rafia-naseem" in result.stdout and "person" in result.stdout

    result = runner.invoke(app, ["find", "rafia"])
    assert "rafia-naseem" in result.stdout

    assert runner.invoke(app, ["tag", "note-99", "X"]).exit_code == 1


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
