"""Tests for scripts/speaker_notes.py: notes are concatenated in the notebook's slide order."""

from __future__ import annotations

from typer.testing import CliRunner

from scripts.speaker_notes import app, deck_order

NOTEBOOK = """
# <!-- SLIDE:S0 -->
# <!-- SLIDE:S1 --> first
# <!-- SLIDE:S1 --> second
# <!-- BEAT:B2 -->
# <!-- BEAT:B1 -->
# <!-- SLIDE:S2 -->
"""


def _module(dir_, name, mid, notes):
    (dir_ / name).write_text(f"---\nid: {mid}\n---\n\n# x\n\n## Speaker notes\n{notes}\n\n## Open questions\nnone\n")


def test_deck_order_takes_first_occurrence_in_file_order(tmp_path):
    nb = tmp_path / "talk.py"
    nb.write_text(NOTEBOOK)
    assert deck_order(nb) == ["S0", "S1", "B2", "B1", "S2"]


def test_notes_are_written_in_deck_order(tmp_path):
    nb = tmp_path / "talk.py"
    nb.write_text(NOTEBOOK)
    mods = tmp_path / "private" / "talk" / "modules"
    mods.mkdir(parents=True)
    _module(mods, "S2-b.md", "S2", "pattern notes")
    _module(mods, "S0-a.md", "S0", "title notes")
    _module(mods, "S1-c.md", "S1", "history notes then tools notes")
    _module(mods, "S3-d.md", "S3", "B1: one\nB2: two")
    res = CliRunner().invoke(app, ["--private", str(tmp_path / "private"), "--notebook", str(nb)])
    assert res.exit_code == 0, res.output
    text = (tmp_path / "private" / "talk" / "speaker_notes.md").read_text()
    order = [text.index(k) for k in ("title notes", "history notes", "B2: two", "B1: one", "pattern notes")]
    assert order == sorted(order)
    assert text.count("history notes") == 1


def test_no_private_directory_exits_zero(tmp_path):
    nb = tmp_path / "talk.py"
    nb.write_text(NOTEBOOK)
    res = CliRunner().invoke(app, ["--private", str(tmp_path / "absent"), "--notebook", str(nb)])
    assert res.exit_code == 0 and "nothing to write" in res.output
