"""Tests for scripts/talk_check.py: each check fails only on the module it concerns."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "talk_check", Path(__file__).resolve().parent.parent / "scripts" / "talk_check.py"
)
talk_check = importlib.util.module_from_spec(SPEC)
sys.modules["talk_check"] = talk_check  # dataclasses resolve their module via sys.modules
SPEC.loader.exec_module(talk_check)


def _module(path: Path, mid: str, minutes: int, receives: str, hands_off: str,
            facts: str = "[]", beats: str = "[]", body: str = "") -> None:
    path.write_text(
        f"---\nid: {mid}\nminutes: {minutes}\nneeds_facts: {facts}\nneeds_beats: {beats}\n"
        f'receives: "{receives}"\nhands_off: "{hands_off}"\nstatus: ready\n---\n{body}\n'
    )


@pytest.fixture
def talk(tmp_path: Path) -> Path:
    private = tmp_path / "private"
    mods = private / "talk" / "modules"
    mods.mkdir(parents=True)
    (private / "talk" / "facts.md").write_text(
        "| id | claim | source | verified | public |\n|---|---|---|---|---|\n"
        "| F-01 | A public fact. | https://example.org/a | 2026-10-14 | y |\n"
        "| F-02 | A private framing fact here. | notes | 2026-10-14 | n |\n"
    )
    _module(mods / "S0-a.md", "S0", 10, "", "one", facts="[F-01]")
    _module(mods / "S1-b.md", "S1", 20, "one", "two", beats="[B1]")
    _module(mods / "S2-c.md", "S2", 10, "two", "")
    return private


def _status(results, name):
    return next(r for r in results if r.check == name)


def test_clean_skeleton_passes(talk: Path, tmp_path: Path) -> None:
    nb = tmp_path / "nb.py"
    nb.write_text("# BEAT:B1 SLIDE:S0 SLIDE:S2\n")
    results = talk_check.run_checks(talk, nb, 50, root=tmp_path)
    assert {r.check: r.status for r in results} == {
        "facts": "passed", "beats": "passed", "slides": "passed", "handoff": "passed",
        "minutes": "passed", "public": "passed",
    }


def test_missing_notebook_is_open_not_failed(talk: Path, tmp_path: Path) -> None:
    results = talk_check.run_checks(talk, tmp_path / "absent.py", 50, root=tmp_path)
    assert _status(results, "beats").status == "open"


def test_broken_fact_flags_only_citing_module(talk: Path, tmp_path: Path) -> None:
    facts = talk / "talk" / "facts.md"
    facts.write_text(facts.read_text().replace("https://example.org/a", "TODO"))
    res = _status(talk_check.run_checks(talk, tmp_path / "nb.py", 50, root=tmp_path), "facts")
    assert res.status == "failed"
    assert res.details == ["S0: cites F-01, which has no source"]


def test_broken_handoff_flags_only_that_seam(talk: Path, tmp_path: Path) -> None:
    mod = talk / "talk" / "modules" / "S1-b.md"
    mod.write_text(mod.read_text().replace('hands_off: "two"', 'hands_off: "changed"'))
    res = _status(talk_check.run_checks(talk, tmp_path / "nb.py", 50, root=tmp_path), "handoff")
    assert res.status == "failed"
    assert len(res.details) == 1 and res.details[0].startswith("S1 -> S2")


def test_minutes_over_budget_fails(talk: Path, tmp_path: Path) -> None:
    res = _status(talk_check.run_checks(talk, tmp_path / "nb.py", 30, root=tmp_path), "minutes")
    assert res.status == "failed"


def test_non_public_fact_in_tracked_file_fails(talk: Path, tmp_path: Path) -> None:
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("see F-02 for details\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    res = _status(talk_check.run_checks(talk, tmp_path / "nb.py", 50, root=tmp_path), "public")
    assert res.status == "failed" and "F-02" in res.details[0]


def test_missing_private_dir_is_all_open(tmp_path: Path) -> None:
    results = talk_check.run_checks(tmp_path / "nope", tmp_path / "nb.py", 50, root=tmp_path)
    assert {r.status for r in results} == {"open"}


def test_missing_slide_marker_flags_only_that_module(talk: Path, tmp_path: Path) -> None:
    nb = tmp_path / "nb.py"
    nb.write_text("# BEAT:B1 SLIDE:S0\n")  # S1 is covered by its beat; S2 has no marker
    res = _status(talk_check.run_checks(talk, nb, 50, root=tmp_path), "slides")
    assert res.status == "failed" and res.details == ["S2: no SLIDE:S2 marker in nb.py"]


# ---- guards on talk.py itself (source level: the notebook needs a live stack to run) ----

import re  # noqa: E402

TALK = (Path(__file__).resolve().parent.parent / "talk.py").read_text()
ORDER = "T0 H0 P1 W1 W2 H1 H2 G1 M1 E1 M2 D1 D2 D3 L1 F2 X1 T1 C1".split()  # deck order


def test_slides_are_in_storyboard_order_one_cell_each() -> None:
    assert re.findall(r"^@app\.cell", TALK, re.M).__len__() == len(ORDER)
    seen = []
    for sid in re.findall(r"SLIDE:([A-Z]\d+)", TALK):
        if sid not in seen:
            seen.append(sid)
    assert seen == ORDER


def test_talk_probes_flexo_once_with_a_long_timeout_and_one_project_per_sha() -> None:
    assert TALK.count("httpx.get(") == 1 and "timeout=20" in TALK
    # reused across sessions: the local store never frees a project (sysml/FLEXO_LOCAL.md, Store growth)
    assert 'f"sysml-talk-{GIT_SHA[:7]}"' in TALK and "strftime" not in TALK and "uuid" not in TALK


def test_talk_has_no_notebook_chrome_banners_and_no_script_hacks() -> None:
    for banned in ("mo.callout", "pre-seeded", "Export mode", "Local mode:", "uncommitted", "setInterval", "onerror",
                   "clientWidth", "<script"):
        assert banned not in TALK, banned
    assert "git_sha(" not in TALK and "tag_of" not in TALK  # tags are stored at publish time, never looked up


def test_talk_wording_discipline() -> None:
    """The contract's grep gate, plus the glossary's banned words, over talk.py and the fragments."""
    gate = re.compile(r"proof|proved|verified satisfied|the truth|neighbo|human-validated", re.I)
    for path in [Path(__file__).resolve().parent.parent / "talk.py",
                 *(Path(__file__).resolve().parent.parent / "talk" / "slides").glob("*.html")]:
        assert not gate.search(path.read_text()), path.name


def test_talk_uses_group_diff_names_not_private_model_helpers() -> None:
    for banned in ("_in_model", "_lib_reach", "_top", "in_model", "lib_reach", "top_of", "group_names"):
        assert banned not in TALK, banned


def test_talk_uses_only_the_model_constants_for_the_approved_text() -> None:
    for text in ("I attest not satisfied", "I attest REQ-001's", "adequate for judging"):
        assert text not in TALK, text  # approved wording comes from sysml/model.py constants, never retyped


def test_verdict_pills_say_automated_and_the_draft_card_is_gated() -> None:
    assert "REQ-001: PASS" not in TALK and "REQ-001: FAIL" not in TALK
    assert "automated verdict:" in TALK
    assert "draft=not K.C2_CONFIRMED" in TALK  # DRAFT tag until Michael approves
    assert "lucide-hourglass" in TALK  # the marimo busy indicator is hidden
    assert "ConnectError" not in TALK  # no raw exception names on screen
