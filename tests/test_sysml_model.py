"""Tests for sysml/model.py: structure, evidence and attestation blocks evaluated by OpenSysML 0.10.0."""

from __future__ import annotations

import re

import pytest
from rdflib import Graph

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from evidence.hashing import hash_simulation
from sysml.model import (NOT_A_HUMAN, assemble, attestation_block, evaluate,
                         evidence_block, load_structure)

pytestmark = pytest.mark.filterwarnings("ignore")
ROOT_TTL = "structural/satellite.ttl"


def _norm(s: str) -> str:
    return " ".join(s.split())


def _evidence(design: str, kp: float, kd: float) -> str:
    params = dict(load_params(), Kp=kp, Kd=kd)
    sim = run_step_response(params)
    summary = sim.summary()
    return evidence_block(design, params, summary, hash_simulation(sim.config.to_dict(), summary))


@pytest.fixture(scope="module")
def structure() -> str:
    return load_structure()


@pytest.fixture(scope="module")
def both(structure) -> dict:
    return evaluate(assemble(structure, _evidence("v1", 1.0, 10.0) + _evidence("v2", 4.0, 30.0)))


def test_structure_alone_loads_clean(structure):
    out = evaluate(structure)
    assert [d for d in out["diagnostics"] if d.startswith("error")] == []


def test_requirement_text_matches_rdf(structure):
    g = Graph().parse(ROOT_TTL, format="turtle")
    texts = {str(s).rsplit(":", 1)[-1].rsplit("/", 1)[-1].rsplit("#", 1)[-1]: str(o)
             for s, p, o in g if str(p).endswith("text")}
    docs = {m.group(1): m.group(2) for m in re.finditer(
        r"requirement def (\w+) \{\s*doc /\*(.*?)\*/", structure, re.S)}
    assert _norm(docs["SettlingRequirement"]) == _norm(texts["REQ-001"])
    assert _norm(docs["DisturbanceRequirement"]) == _norm(texts["REQ-004"])


def test_verdicts(both):
    assert both["diagnostics"] == []
    assert both["verdicts"]["vc001_v1"] == "fail"
    assert both["verdicts"]["vc001_v2"] == "pass"


def test_req004_inconclusive_for_both(both):
    assert both["verdicts"]["vc004_v1"] == "inconclusive"
    assert both["verdicts"]["vc004_v2"] == "inconclusive"


def test_req_truth_values_are_plain_bools(both):
    assert both["req"]["req001(v1)"] is False
    assert both["req"]["req001(v2)"] is True
    assert both["req"]["req004(v2)"] is True


def _claim(structure, satisfied, status="done"):
    att = attestation_block("v1", satisfied, "A. Engineer", status, "Evidence is sufficient.", "vc001_v1")
    return evaluate(assemble(structure, _evidence("v1", 1.0, 10.0), att))["claims"]["att_v1"]


def test_consistent_not_satisfy_holds(structure):
    assert _claim(structure, False) == {"holds": True, "error": None}


def test_contradicting_satisfy_does_not_hold(structure):
    assert _claim(structure, True) == {"holds": False, "error": None}


@pytest.mark.parametrize("who", ["claude", "Claude ", "", "  ", "BOT"])
def test_non_human_originator_refused(who):
    with pytest.raises(ValueError):
        attestation_block("v1", False, who, "tbc", "x", "vc001_v1")
    assert "claude" in NOT_A_HUMAN


def test_evaluate_returns_only_builtins(both):
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                yield from walk(k)
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)
        else:
            yield x
    for leaf in walk(both):
        assert type(leaf) in (str, bool, int, float, type(None))


def test_structure_has_no_designs_or_attestations(structure):
    code = "\n".join(l for l in structure.splitlines() if not l.strip().startswith("//"))
    assert not re.search(r"^\s*part\s+\w+\s*:", code, re.M)
    assert "satisfy" not in code
    assert "metadata def" not in code


def test_pending_status_tbc_loads(structure):
    assert _claim(structure, False, status="tbc")["holds"] is True
