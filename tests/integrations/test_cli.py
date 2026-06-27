"""Integration test: the full CLI → service → SQLite round-trip (local integration store)."""

from pathlib import Path

from typer.testing import CliRunner

from pensieve.cli.main import app

runner = CliRunner()


def test_init_and_stream_crud(integration_store: Path):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert (integration_store / "pensieve.db").exists()

    result = runner.invoke(app, ["stream", "create", "Recs", "-p", "Build Recs"])
    assert result.exit_code == 0 and "recs" in result.stdout

    result = runner.invoke(app, ["stream", "list"])
    assert result.exit_code == 0
    assert "recs" in result.stdout and "Build Recs" in result.stdout

    # duplicate stream
    assert runner.invoke(app, ["stream", "create", "Recs"]).exit_code == 1


def test_note_lifecycle_and_show(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs", "-p", "Build Recs"])

    assert runner.invoke(app, ["note", "add", "talking to curators", "-s", "recs"]).exit_code == 0
    assert runner.invoke(app, ["note", "add", "Rafia is one", "-s", "recs"]).exit_code == 0

    result = runner.invoke(app, ["show", "recs"])
    assert result.exit_code == 0
    assert "Build Recs" in result.stdout
    assert "talking to curators" in result.stdout
    assert "note-1" in result.stdout and "note-2" in result.stdout

    assert runner.invoke(app, ["note", "edit", "note-1", "talking to 4 curators"]).exit_code == 0
    assert "4 curators" in runner.invoke(app, ["show", "recs"]).stdout

    assert runner.invoke(app, ["note", "rm", "note-2"]).exit_code == 0
    assert "Rafia is one" not in runner.invoke(app, ["show", "recs"]).stdout


def test_show_empty_and_missing(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs"])
    assert "(empty)" in runner.invoke(app, ["show", "recs"]).stdout

    result = runner.invoke(app, ["show", "nope"])
    assert result.exit_code == 1
    assert "No stream, thread, or entity 'nope'" in result.output
    assert "node" not in result.output.lower()


def test_note_add_errors(integration_store: Path):
    result = runner.invoke(app, ["note", "add", "hi", "-s", "nope"])
    assert result.exit_code == 1
    assert "No stream 'nope'" in result.output and "node" not in result.output


def test_entity_link_list_find(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs"])
    runner.invoke(app, ["note", "add", "met rafia", "-s", "recs"])  # note-1

    result = runner.invoke(app, ["entity", "link", "note-1", "Rafia Naseem", "-k", "person"])
    assert result.exit_code == 0 and "rafia-naseem" in result.stdout

    assert "rafia-naseem" in runner.invoke(app, ["entity", "list"]).stdout

    # find: entity + stream both surface; --type narrows
    assert "rafia-naseem" in runner.invoke(app, ["find", "rafia"]).stdout
    assert "recs" in runner.invoke(app, ["find", "rec"]).stdout
    only_entity = runner.invoke(app, ["find", "r", "-t", "entity"]).stdout
    assert "rafia-naseem" in only_entity and "stream " not in only_entity

    assert runner.invoke(app, ["entity", "link", "note-99", "X"]).exit_code == 1

    # unlink (fix a mis-tag) → entity loses its last note → vanishes (derived)
    assert runner.invoke(app, ["entity", "unlink", "note-1", "rafia-naseem"]).exit_code == 0
    assert "rafia-naseem" not in runner.invoke(app, ["entity", "list"]).stdout
    assert runner.invoke(app, ["entity", "unlink", "note-99", "rafia-naseem"]).exit_code == 1


def test_find_dedups_promoted_entity(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs"])
    runner.invoke(app, ["note", "add", "met rafia", "-s", "recs"])
    runner.invoke(app, ["entity", "link", "note-1", "Rafia Naseem", "-k", "person"])
    runner.invoke(app, ["entity", "promote", "rafia-naseem", "-s", "recs"])

    out = runner.invoke(app, ["find", "rafia"]).stdout
    assert out.count("rafia-naseem") == 1  # once (as its thread), not thread + entity
    assert "thread" in out

    # but --type entity still surfaces it (no node search to dedup against)
    assert "rafia-naseem" in runner.invoke(app, ["find", "rafia", "-t", "entity"]).stdout


def test_promote_show_thread_and_recall(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs"])
    runner.invoke(app, ["note", "add", "met rafia", "-s", "recs"])
    runner.invoke(app, ["entity", "link", "note-1", "Rafia Naseem", "-k", "person"])
    assert runner.invoke(app, ["entity", "promote", "rafia-naseem", "-s", "recs"]).exit_code == 0

    # the stream view now lists the thread
    recs = runner.invoke(app, ["show", "recs"]).stdout
    assert "thread: rafia-naseem" in recs

    # show the thread (node) and the entity (recall) both reach the note
    assert "met rafia" in runner.invoke(app, ["show", "rafia-naseem"]).stdout

    # adding to a thread is rejected; promoting again / empty is rejected
    assert runner.invoke(app, ["note", "add", "x", "-s", "rafia-naseem"]).exit_code == 1
    assert runner.invoke(app, ["entity", "promote", "rafia-naseem", "-s", "recs"]).exit_code == 1


def test_edit_commands(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs", "-p", "old"])
    assert (
        runner.invoke(
            app, ["stream", "edit", "recs", "--name", "Recommendations", "-p", "new"]
        ).exit_code
        == 0
    )
    out = runner.invoke(app, ["show", "recs"]).stdout
    assert "Recommendations" in out and "new" in out

    runner.invoke(app, ["note", "add", "x", "-s", "recs"])
    runner.invoke(app, ["entity", "link", "note-1", "Rafia", "-k", "person"])
    assert runner.invoke(app, ["entity", "edit", "rafia", "--name", "Rafia Naseem"]).exit_code == 0
    assert "Rafia Naseem" in runner.invoke(app, ["show", "rafia"]).stdout

    assert runner.invoke(app, ["stream", "edit", "nope", "--name", "x"]).exit_code == 1
    assert runner.invoke(app, ["entity", "edit", "ghost", "--name", "x"]).exit_code == 1


def test_note_rm_restore(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs"])
    runner.invoke(app, ["note", "add", "keep me", "-s", "recs"])  # note-1
    runner.invoke(app, ["note", "add", "drop me", "-s", "recs"])  # note-2

    assert runner.invoke(app, ["note", "rm", "note-2"]).exit_code == 0
    assert "drop me" not in runner.invoke(app, ["show", "recs"]).stdout
    # soft — re-removing a hidden note reads as absent; restore brings it back
    assert runner.invoke(app, ["note", "rm", "note-2"]).exit_code == 1
    assert runner.invoke(app, ["note", "restore", "note-2"]).exit_code == 0
    assert "drop me" in runner.invoke(app, ["show", "recs"]).stdout

    assert runner.invoke(app, ["note", "restore", "note-99"]).exit_code == 1


def test_stream_rm_restore_and_shared_note(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs"])
    runner.invoke(app, ["stream", "create", "Employment"])
    # rafia rides a note in each stream
    runner.invoke(app, ["note", "add", "met rafia", "-s", "recs"])  # note-1
    runner.invoke(app, ["entity", "link", "note-1", "Rafia", "-k", "person"])
    runner.invoke(app, ["note", "add", "rafia asked about a role", "-s", "employment"])
    runner.invoke(app, ["entity", "link", "note-2", "Rafia", "-k", "person"])

    assert runner.invoke(app, ["stream", "rm", "recs"]).exit_code == 0
    assert runner.invoke(app, ["show", "recs"]).exit_code == 1  # stream gone
    assert "recs" not in runner.invoke(app, ["stream", "list"]).stdout
    # rafia survives via the employment note (cross-stream)
    assert "rafia" in runner.invoke(app, ["entity", "list"]).stdout
    assert "rafia asked" in runner.invoke(app, ["show", "rafia"]).stdout

    # restore brings the stream + its notes back
    assert runner.invoke(app, ["stream", "restore", "recs"]).exit_code == 0
    assert "met rafia" in runner.invoke(app, ["show", "recs"]).stdout
    assert runner.invoke(app, ["stream", "restore", "nope"]).exit_code == 1


def test_entity_rm_purges_notes_and_derived_entities(integration_store: Path):
    runner.invoke(app, ["stream", "create", "Recs"])
    runner.invoke(app, ["note", "add", "plain note", "-s", "recs"])  # note-1, no entity
    runner.invoke(app, ["note", "add", "rafia and travis", "-s", "recs"])  # note-2
    runner.invoke(app, ["entity", "link", "note-2", "Rafia", "-k", "person"])
    runner.invoke(app, ["entity", "link", "note-2", "Travis", "-k", "person"])

    # rm rafia purges note-2 → travis (riding only that note) vanishes too; note-1 stays
    assert runner.invoke(app, ["entity", "rm", "rafia"]).exit_code == 0
    out = runner.invoke(app, ["entity", "list"]).stdout
    assert "rafia" not in out and "travis" not in out
    recs = runner.invoke(app, ["show", "recs"]).stdout
    assert "plain note" in recs and "rafia and travis" not in recs

    # restore rafia → its note (and travis) come back
    assert runner.invoke(app, ["entity", "restore", "rafia"]).exit_code == 0
    out = runner.invoke(app, ["entity", "list"]).stdout
    assert "rafia" in out and "travis" in out
    assert runner.invoke(app, ["entity", "rm", "ghost"]).exit_code == 1
