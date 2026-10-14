"""Tests for sysml/lanes.py: the three-lane Mermaid view of already-evaluated model elements."""

from __future__ import annotations

import re

import pytest

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from evidence.hashing import hash_simulation
from sysml.lanes import lanes_mermaid
from sysml.model import (DEFAULT_ADEQUACY, DEMO_ENGINEER, assemble, attestation_block, evidence_block, load_structure,
                         status_block, to_elements)

pytestmark = pytest.mark.filterwarnings("ignore")


def _evidence(design, kp, kd):
    params = dict(load_params(), Kp=kp, Kd=kd)
    sim = run_step_response(params)
    summary = sim.summary()
    return evidence_block(design, params, summary, hash_simulation(sim.config.to_dict(), summary),
                          DEFAULT_ADEQUACY, DEMO_ENGINEER)


@pytest.fixture(scope="module")
def states():
    s = load_structure()
    ev1, ev2 = _evidence("initial", 1.0, 10.0), _evidence("tuned", 4.0, 30.0)
    return {
        "c0": lanes_mermaid(to_elements(s)),
        "c1": lanes_mermaid(to_elements(assemble(s, ev1, attestation_block(
            "initial", False, DEMO_ENGINEER, "done", "Too slow.", "vc001_initial")))),
        "c2": lanes_mermaid(to_elements(assemble(s, ev2, status_block("req001")))),
        "c3": lanes_mermaid(to_elements(assemble(s, ev2, attestation_block(
            "tuned", True, DEMO_ENGINEER, "done", "Inside the limit.", "vc001_tuned")))),
    }


def _subgraphs(m):
    return re.findall(r'subgraph (\w)\["([^"]+)"\]', m)


def _lane(m, key):
    return re.search(rf'subgraph {key}\[.*?\n  end', m, re.S).group(0)


def test_three_subgraphs_in_every_state(states):
    for m in states.values():
        assert [k for k, _ in _subgraphs(m)] == ["S", "E", "A"]
        assert [t.split(" ·")[0] for _, t in _subgraphs(m)] == ["STRUCTURE", "EVIDENCE", "ATTESTATION"]


def test_structure_lane_holds_part_def_and_requirements(states):
    lane = _lane(states["c0"], "S")
    assert "part def" in lane and "req001" in lane and "req004" in lane
    assert "tuned" not in lane


def test_c0_has_only_structure_filled(states):
    m = states["c0"]
    assert "ToolExecution" not in m and "satisfy" not in m and "tbc" not in m


def test_evidence_lane_holds_design_and_tool_execution(states):
    lane = _lane(states["c2"], "E")
    assert "tuned</b> : ADCS" in lane and "ToolExecution" in lane


def test_negated_claim_is_styled_distinctly(states):
    c1, c3 = states["c1"], states["c3"]
    assert "<b>not satisfy</b>" in c1 and "-. not satisfy .->" in c1
    assert re.search(r"class \w+ negated", c1)
    assert "<b>satisfy</b>" in c3 and "== satisfy ==>" in c3
    assert not re.search(r"class \w+ negated", c3)
    assert "not satisfy" not in c3.split("classDef")[0]


def test_pending_marker_is_dashed_amber_tbc(states):
    m = states["c2"]
    assert "tbc<br/>" in _lane(m, "A")
    assert re.search(r"class \w+ pending", m)
    assert re.search(r"classDef pending .*stroke:#d97706.*stroke-dasharray", m)
    assert "satisfy" not in m.split("classDef")[0].replace("tbc", "")


def test_attested_states_have_no_pending_marker(states):
    for k in ("c1", "c3"):
        assert "tbc<br/>" not in states[k]


def test_human_nodes_are_amber_and_in_the_attestation_lane(states):
    m = states["c3"]
    lane = _lane(m, "A")
    assert "StatusInfo" in lane and "status=done" in lane and "Michael Zargham" in lane
    assert "Rationale (sufficiency)" in lane and "Rationale (adequacy)" in lane
    assert len(re.findall(r"class \w+ human", m)) == 5  # satisfy; its StatusInfo and Rationale; the adequacy StatusInfo and Rationale
    assert re.search(r"classDef human .*stroke:#d97706", m)
