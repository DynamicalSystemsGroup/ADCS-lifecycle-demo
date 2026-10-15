"""Tests for sysml/lanes.py: the three-lane Mermaid view of already-evaluated model elements."""

from __future__ import annotations

import re

import pytest

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from evidence.hashing import hash_simulation
from sysml.lanes import lanes_mermaid, sandwich_mermaid, stack_mermaid, two_store_mermaid
from sysml.model import (DEFAULT_ADEQUACY, DEMO_ENGINEER, assemble, attestation_block, evidence_block, load_structure,
                         status_block, symbolic_settling, to_elements)

pytestmark = pytest.mark.filterwarnings("ignore")


def _evidence(design, kp, kd):
    params = dict(load_params(), Kp=kp, Kd=kd)
    sim = run_step_response(params)
    summary = sim.summary()
    t_est, est_hash = symbolic_settling(params)
    return evidence_block(design, params, summary, hash_simulation(sim.config.to_dict(), summary),
                          DEFAULT_ADEQUACY, DEMO_ENGINEER, t_est, est_hash)


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


def test_lane_titles_say_what_each_lane_is(states):
    titles = dict(_subgraphs(states["c2"]))
    assert titles["E"] == "EVIDENCE · computed (scipy, SymPy)"
    assert titles["A"] == "ATTESTATION · a person's judgement, or its absence"


def test_evidence_title_names_the_tools_the_lane_shows(states):
    lane, title = _lane(states["c2"], "E"), dict(_subgraphs(states["c2"]))["E"]
    for tool in ("scipy", "SymPy"):
        assert tool in lane and tool in title
    assert lane.count("ToolExecution") == 2


def test_structure_lane_holds_part_def_and_requirements(states):
    lane = _lane(states["c0"], "S")
    assert "part def" in lane and "req001" in lane
    assert "tuned" not in lane


def test_c0_has_only_structure_filled(states):
    m = states["c0"]
    assert "ToolExecution" not in m and "satisfy" not in m and "tbc" not in m


def test_evidence_lane_holds_design_and_tool_execution(states):
    lane = _lane(states["c2"], "E")
    assert "tuned</b> : ADCS" in lane and "ToolExecution" in lane


def test_negated_claim_is_styled_distinctly(states):
    c1, c3 = states["c1"], states["c3"]
    assert "<b>NOT satisfied</b>" in c1 and "-. not satisfy .->" in c1
    assert "line-through" not in c1
    assert "stroke:#d97706" in _classdef(c1, "negated") and "fill:#fbd38d" in _classdef(c1, "negated")
    assert re.search(r"class \w+ negated", c1)
    assert "<b>satisfy</b>" in c3 and "== satisfy ==>" in c3
    assert not re.search(r"class \w+ negated", c3)
    assert "NOT satisfied" not in c3 and "not satisfy" not in c3.split("classDef")[0]


def _classdef(m, name):
    return re.search(rf"classDef {name} (.*)", m).group(1)


def _node_class(m, label_part):
    """The class of the node whose label contains `label_part`."""
    nid = re.search(rf'(\w+)\(?\[?"[^"\n]*{re.escape(label_part)}', m).group(1)
    return re.search(rf"class {nid} (\w+)", m).group(1)


def test_pending_unnamed_is_dashed_grey_no_one_has_judged(states):
    m = states["c2"]  # status tbc, no originator
    assert "tbc · no one has judged" in _lane(m, "A")
    assert _node_class(m, "tbc · no one has judged") == "pending"
    assert "stroke-dasharray" in _classdef(m, "pending") and "#d97706" not in _classdef(m, "pending")
    assert "satisfy" not in m.split("classDef")[0]


def test_pending_named_is_dashed_amber_by_name():
    text = assemble(load_structure(), status_block("req001", "tbc", DEMO_ENGINEER, "Not yet judged."))
    m = lanes_mermaid(to_elements(text))
    assert f"tbc · by {DEMO_ENGINEER}" in _lane(m, "A")
    assert "no one has judged" not in m
    assert _node_class(m, "tbc · by") == "pendingNamed"
    cd = _classdef(m, "pendingNamed")
    assert "stroke:#d97706" in cd and "stroke-dasharray" in cd and "fill:#ffffff" in cd


def test_done_named_is_solid_amber(states):
    m = states["c3"]
    assert _node_class(m, "status=done") == "human"
    cd = _classdef(m, "human")
    assert "stroke:#d97706" in cd and "stroke-dasharray" not in cd
    assert "tbc" not in m


def test_pending_is_decided_by_status_not_by_missing_name(states):
    # done with no one named is not pending; tbc with a name is
    assert "tbc · by" not in states["c3"] and "tbc · no one has judged" in states["c2"]


def test_attested_states_have_no_pending_marker(states):
    for k in ("c1", "c3"):
        assert "tbc" not in states[k]


def test_human_nodes_are_amber_and_in_the_attestation_lane(states):
    m = states["c3"]
    lane = _lane(m, "A")
    assert "StatusInfo" in lane and "status=done" in lane and "Michael Zargham" in lane
    assert "Rationale (sufficiency)" in lane and "Rationale (adequacy)" in lane
    assert len(re.findall(r"class \w+ human", m)) == 5  # satisfy; its StatusInfo and Rationale; the adequacy StatusInfo and Rationale
    assert re.search(r"classDef human .*stroke:#d97706", m)


def test_requirements_are_prescribed_neutral_not_blue(states):
    m = states["c2"]
    assert _node_class(m, "req001") == "req"
    cd = _classdef(m, "req")
    assert "stroke:#111111" in cd and "stroke-width:3px" in cd and "#2166ac" not in cd and "#e8f0fe" not in cd
    assert re.search(r'\(\["<b>req001</b>', m)  # stadium shape sets it apart


def test_blue_only_for_machine_output(states):
    m = states["c3"]
    blue_classes = {n for n in re.findall(r"classDef (\w+) ", m) if "#2166ac" in _classdef(m, n)}
    assert blue_classes == {"machine"}
    assert {_node_class(m, "ToolExecution"), _node_class(m, "tuned</b> : ADCS")} == {"machine"}


def test_both_tool_executions_are_in_the_evidence_lane(states):
    lane = _lane(states["c2"], "E")
    assert "scipy solve_ivp" in lane and "SymPy linear analysis" in lane
    assert lane.count("ToolExecution") == 2


def test_rationale_unattributed_is_neutral_attributed_is_amber(states):
    # C2: the adequacy Rationale is about a design with a named StatusInfo -> amber
    assert _node_class(states["c2"], "Rationale (adequacy)") == "human"


def test_unattributed_rationale_is_neutral():
    s = load_structure()
    text = assemble(s, "    metadata : ModelingMetadata::Rationale about req001 {\n        text = \"anon\";\n    }\n")
    m = lanes_mermaid(to_elements(text))
    assert _node_class(m, "Rationale<br/>") == "neutral"
    assert "#d97706" not in _classdef(m, "neutral")


def test_no_edge_points_at_an_undrawn_node(states):
    for m in states.values():
        defined = set(re.findall(r'^\s+(\w+)(?:\(\[|\[|\{\{)', m, re.M))
        for a, b in re.findall(r"^\s+(\w+) (?:-\.|==|--)[^\n]*?(?:->|=>) (\w+)$", m, re.M):
            assert a in defined and b in defined, (a, b)


def test_two_store_mermaid_names_both_stores_and_the_tag():
    m = two_store_mermaid()
    assert "flowchart LR" in m
    for part in ("GIT · source", ".sysml", "analysis code", "notebook", "OpenSysML", "evaluates",
                 "FLEXO · model", "model elements", "git-&lt;sha&gt;", "reads", "diffs"):
        assert part in m
    assert "G --> X --> F" in m
    assert "same commit" not in m and not re.search(r"\bF -[.-]*> G\b", m)  # flow is Git -> OpenSysML -> Flexo only
    assert "tagged <b>git-" in m and "reviewer" not in m
    assert m.startswith("%%{init") and "'fontSize': '24px'" in m


def test_sandwich_mermaid_stacks_three_labels():
    m = sandwich_mermaid(["top <b>layer</b>", "middle", 'bottom "x"'])
    assert m.startswith("%%{init") and "'fontSize': '26px'" in m and "\nflowchart TB\n" in m
    assert "L0 --- L1 --- L2" in m
    assert 'L0["top <b>layer</b>"]' in m and 'L1["middle"]' in m and "bottom 'x'" in m
    with pytest.raises(ValueError):
        sandwich_mermaid(["a", "b"])
    with pytest.raises(ValueError):
        sandwich_mermaid(["a", "", "c"])


def test_stack_mermaid_four_layers_three_arrows_and_feedback():
    m = stack_mermaid()
    assert "\nflowchart TB\n" in m
    for part in ("Standards", "OMG SysML v2", "KerML", "Systems Modeling API", "Open-source software", "OpenSysML REDK",
                 "sysml-toolkit", "Flexo MMS", "OMG Pilot", "Commercial software", "Kotar", "hosted Flexo MMS",
                 "Engineering organizations"):
        assert part in m
    for edge in ("L0 -- implemented as --> L1", "L1 -- imported by --> L2", "L2 -- used by --> L3",
                 "L3 -. feedback .-> L0"):
        assert edge in m
    assert "#e8f0fe" not in m and "#fff4d6" not in m  # neutral: no machine blue, no human amber


# ---------- compact (presentation) mode ----------

@pytest.fixture(scope="module")
def compact(states):
    s = load_structure()
    ev1, ev2 = _evidence("initial", 1.0, 10.0), _evidence("tuned", 4.0, 30.0)
    return {
        "c0": lanes_mermaid(to_elements(s), compact=True),
        "c1": lanes_mermaid(to_elements(assemble(s, ev1, attestation_block(
            "initial", False, DEMO_ENGINEER, "done", "Too slow.", "vc001_initial"))), compact=True),
        "c2": lanes_mermaid(to_elements(assemble(s, ev2, status_block("req001"))), compact=True),
        "c3": lanes_mermaid(to_elements(assemble(s, ev2, attestation_block(
            "tuned", True, DEMO_ENGINEER, "done", "Inside the limit.", "vc001_tuned"))), compact=True),
    }


def _nodes(m):
    """Node ids defined in the diagram, headers excluded."""
    return [n for n in re.findall(r'^\s+(\w+)(?:\(\[|\[|\{\{)"', m, re.M) if n not in ("hS", "hE", "hA")]


def _lane_c(m, key):
    return re.search(rf'subgraph {key}\[.*?\n  end', m, re.S).group(0)


def test_compact_font_is_20px_or_larger(compact):
    for m in compact.values():
        assert int(re.search(r"'fontSize': '(\d+)px'", m).group(1)) >= 20


def test_compact_titles_are_header_nodes_not_cluster_titles(compact):
    for m in compact.values():
        assert re.findall(r'subgraph \w\[" "\]', m) == ['subgraph S[" "]', 'subgraph E[" "]', 'subgraph A[" "]']
        assert "direction" not in m and m.splitlines()[1] == "flowchart TB"
        heads = dict(re.findall(r'^\s+h([SEA])\["([^"]+)"\]', m, re.M))
        assert [heads[k].split("<br/>")[0] for k in "SEA"] == ["STRUCTURE", "EVIDENCE", "ATTESTATION"]
        assert "hS ~~~ hE" in m and "hE ~~~ hA" in m  # the bands stack in order


def test_compact_one_node_per_evidence_source_and_per_judgement(compact):
    m = compact["c3"]
    assert len(_nodes(m)) == 7  # part def, requirement; design, scipy, SymPy; two judgements
    lane = _lane_c(m, "E")
    assert "scipy<br/>simulation" in lane and "SymPy<br/>estimate" in lane and "ToolExecution" not in m
    assert "StatusInfo" not in m and "Rationale" not in m
    assert len(re.findall(r"class \w+ human", m)) == 2  # adequacy judgement, satisfy judgement
    assert f"<b>{DEMO_ENGINEER}</b><br/>done · adequacy" in m
    assert f"<b>{DEMO_ENGINEER}</b><br/>satisfied" in m and "linkStyle" in m  # satisfy edge: thick, amber


def test_compact_not_satisfied_is_one_amber_card_with_a_distinct_edge(compact):
    m = compact["c1"]
    assert f"<b>{DEMO_ENGINEER}</b><br/>NOT satisfied" in m
    assert re.search(r"class \w+ negated", m)
    assert re.search(r"^\s+\w+ -\.- \w+$", m, re.M) and "linkStyle" in m  # dotted, amber
    assert len(_nodes(m)) == 7
    assert "line-through" not in m


def test_compact_pending_is_one_dashed_node_and_no_person(compact):
    m = compact["c2"]
    assert "tbc · no one has judged" in _lane_c(m, "A")
    assert _node_class(m, "tbc · no one has judged") == "pending"
    assert "satisfied" not in m


def test_compact_c0_has_the_structure_band_filled_only(compact):
    m = compact["c0"]
    assert "part def" in _lane_c(m, "S") and "requirement" in _lane_c(m, "S")
    assert "scipy" not in m and "tbc" not in m and "satisfied" not in m
    assert "hS ~~~ hE" in m and "hE ~~~ hA" in m  # empty bands still stack in order


def test_compact_no_link_points_at_an_undrawn_node(compact):
    for m in compact.values():
        defined = set(re.findall(r'^\s+(\w+)(?:\(\[|\[|\{\{)', m, re.M))
        for a, b in re.findall(r"^\s+(\w+) (?:~~~|-\.|==|-\.-)[^\n]*?(\w+)$", m, re.M):
            assert a in defined and b in defined, (a, b)


def test_full_mode_is_unchanged_by_the_flag(states):
    assert states["c3"].startswith("flowchart LR") and "ToolExecution" in states["c3"]


def test_compact_terms_go_in_the_band_headers(compact):
    s = load_structure()
    m = lanes_mermaid(to_elements(s), compact=True, terms={"S": "≈ sysml:", "E": "≈ prov:", "A": "≈ earl:, gsn:"})
    for k, t in (("S", "≈ sysml:"), ("E", "≈ prov:"), ("A", "≈ earl:, gsn:")):
        assert f"<br/><i>{t}</i>" in _lane_c(m, k)
    assert "<i>≈" not in compact["c0"]  # no terms asked for: headers are unchanged
