"""Tests for sysml/formal.py: live Z3 run and the captured fallback."""

from __future__ import annotations

import pytest

from sysml import formal

pytestmark = pytest.mark.filterwarnings("ignore")


def test_region_check_live_z3():
    r = formal.region_check()
    assert r["engine"] == "z3" and r["verdict"] == "no_counterexample"
    assert r["label"] == "Z3 finds no counterexample in this box for the linear model"
    assert "RegionSettles" in r["raw"] and "ValidAndSettles" in r["raw"]


def test_region_check_finds_a_counterexample_outside_the_linear_region():
    r = formal.region_check(kp=(1, 6), kd=(10, 25))
    assert r["engine"] == "z3" and r["verdict"] == "counterexample"


def test_valid_and_settles_is_unsatisfiable_in_raw():
    assert "ValidAndSettles (satisfiable): holds=False" in formal.region_check()["raw"]


def test_fallback_when_solver_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENSYSML_SMT", str(tmp_path / "no-such-z3"))
    r = formal.region_check()
    assert r["engine"] == "captured" and r["verdict"] == "no_counterexample"
    assert r["raw"] == formal.FALLBACK.read_text().partition("\n")[2].rstrip("\n")


def test_labels_never_claim_proof():
    r = formal.region_check()
    assert "proof" not in r["label"].lower() and "proves the design passes" not in r["label"].lower()
