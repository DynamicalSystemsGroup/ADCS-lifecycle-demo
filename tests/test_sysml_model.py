"""Tests for sysml/model.py: structure, evidence and attestation blocks evaluated by OpenSysML 0.10.0."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rdflib import Graph

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from evidence.hashing import hash_simulation
from sysml.model import (ADEQUACY_TEXT, CARD_ADEQUACY, CARD_NOT_SATISFIED, CARD_SATISFIED, DEFAULT_ADEQUACY,
                         CARD_DISAGREE_DRAFT, DEMO_ENGINEER, card_disagree, NOT_A_HUMAN, PACKAGE, PER_AXIS_DRAFT_SENTENCE, SCOPE,
                         SUFFICIENCY_DISAGREE_DRAFT, SUFFICIENCY_NOT_SATISFIED, SUFFICIENCY_SATISFIED_TEMPLATE,
                         adequacy_block, assemble, attestation_block, evaluate, evidence_block, group_diff,
                         load_structure, per_axis_sentence, status_block, sufficiency_disagree,
                         sufficiency_satisfied, symbolic_settling, to_elements)

pytestmark = pytest.mark.filterwarnings("ignore")
ROOT_TTL = "structural/satellite.ttl"


def _norm(s: str) -> str:
    return " ".join(s.split())


def _evidence(design: str, kp: float, kd: float) -> str:
    params = dict(load_params(), Kp=kp, Kd=kd)
    sim = run_step_response(params)
    summary = sim.summary()
    t, est_hash = symbolic_settling(params)
    return evidence_block(design, params, summary, hash_simulation(sim.config.to_dict(), summary),
                          t, est_hash)


@pytest.fixture(scope="module")
def structure() -> str:
    return load_structure()


@pytest.fixture(scope="module")
def both(structure) -> dict:
    return evaluate(assemble(structure, _evidence("v1", 1.0, 10.0) + _evidence("v2", 4.0, 30.0)))


def test_structure_alone_loads_clean(structure):
    out = evaluate(structure)  # strict load: raises if the structure does not load
    assert out["diagnostics"] == []


def test_requirement_text_matches_rdf(structure):
    g = Graph().parse(ROOT_TTL, format="turtle")
    texts = {str(s).rsplit(":", 1)[-1].rsplit("/", 1)[-1].rsplit("#", 1)[-1]: str(o)
             for s, p, o in g if str(p).endswith("text")}
    docs = {m.group(1): m.group(2) for m in re.finditer(
        r"requirement def (\w+) \{\s*doc /\*(.*?)\*/", structure, re.S)}
    assert _norm(docs["SettlingRequirement"]) == _norm(texts["REQ-001"])
    assert "DisturbanceRequirement" not in docs  # REQ-004 is out of the demo model (DL-25)


def test_verdicts(both):
    assert both["diagnostics"] == []
    assert both["verdicts"]["vc001_v1"] == "fail"
    assert both["verdicts"]["vc001_v2"] == "pass"
    assert set(both["verdicts"]) == {"vc001_v1", "vc001_v2"}  # no vc004: REQ-004 is out of the demo model


def test_req_truth_values_are_plain_bools(both):
    assert both["req"]["req001(v1)"] is False
    assert both["req"]["req001(v2)"] is True
    assert set(both["req"]) == {"req001(v1)", "req001(v2)"}


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


@pytest.mark.parametrize("bad", ["", "1v", "v 1", "v1;", "v1\n", "a-b", "v1 } part x"])
def test_bad_identifiers_refused(bad):
    params = dict(load_params(), Kp=1.0, Kd=10.0)
    sim = run_step_response(params)
    with pytest.raises(ValueError):
        evidence_block(bad, params, sim.summary(), "0" * 64, 1.0, "0" * 64)
    with pytest.raises(ValueError):
        attestation_block(bad, False, "A. Engineer", "tbc", "x", "vc001_v1")
    with pytest.raises(ValueError):
        attestation_block("v1", False, "A. Engineer", "tbc", "x", bad)


def test_unused_status_refused():
    with pytest.raises(ValueError):
        attestation_block("v1", False, "A. Engineer", "inwork", "x", "vc001_v1")


def test_v2_peak_torque_is_clipped_at_limit():
    params = dict(load_params(), Kp=4.0, Kd=30.0)
    summary = run_step_response(params).summary()
    assert summary["peak_control_torque"] == params["maxTorque"]


def _rationales_about(els: dict, qname: str) -> list:
    """Rationale metadata usages whose annotated element has this qualified name."""
    out = []
    for e in els.values():
        if e["@type"] == "MetadataUsage" and any(
                els.get(t["@id"], {}).get("qualifiedName") == "ModelingMetadata::Rationale" for t in e.get("type", [])):
            if any(els.get(a["@id"], {}).get("qualifiedName") == qname for a in e["annotatedElement"]):
                out.append(e)
    return out


def test_adequacy_is_about_the_scope_element_and_carries_originator(structure):
    block = adequacy_block(DEMO_ENGINEER)
    assert DEMO_ENGINEER == "Michael Zargham"
    assert f"ModelingMetadata::Rationale about {SCOPE} {{" in block
    assert (f"metadata : ModelingMetadata::StatusInfo about {SCOPE} {{\n"
            f'        originator = "{DEMO_ENGINEER}";\n'
            "        status = StatusKind::done;") in block
    assert ADEQUACY_TEXT in block and "metadata def" not in block
    text = assemble(structure, _evidence("v1", 1.0, 10.0), adequacy=block)
    assert evaluate(text)["diagnostics"] == []
    els = {e["@id"]: e for e in to_elements(text)}
    assert els[f"{PACKAGE}__{SCOPE}"]["@type"] == "AnalysisCaseDefinition"
    assert len(_rationales_about(els, f"{PACKAGE}::{SCOPE}")) == 1


def test_no_design_part_carries_an_adequacy_rationale(structure):
    text = assemble(structure, _evidence("v1", 1.0, 10.0) + _evidence("v2", 4.0, 30.0),
                    adequacy=adequacy_block(DEMO_ENGINEER))
    els = {e["@id"]: e for e in to_elements(text)}
    for d in ("v1", "v2"):
        assert not _rationales_about(els, f"{PACKAGE}::{d}")
    assert "adequate" not in _evidence("v1", 1.0, 10.0)


def test_scope_doc_lists_the_assumptions(structure):
    for phrase in ("rigid body with constant inertia", "small-angle linearisation", "no actuator limit",
                   "quaternion kinematics", "0.1 N m torque limit", "10 degree slew", "1% settling band",
                   "no sensor noise", "no flexible modes"):
        assert phrase.lower() in _norm(structure).lower()


def test_adequacy_text_is_caller_supplied():
    assert "My own judgement." in adequacy_block("A. Engineer", "My own judgement.")


@pytest.mark.parametrize("who", sorted(NOT_A_HUMAN) + ["", "  ", "Claude"])
def test_adequacy_by_non_human_refused(who):
    with pytest.raises(ValueError):
        adequacy_block(who)


def test_per_axis_comments_in_evidence_block():
    params = dict(load_params(), Kp=4.0, Kd=25.0)
    summary = {"settling_time_s": 120.5}
    pa = {"x": 120.5, "y": 96.5, "z": 116.5, "worst": 120.5, "worst_axis": "x", "saturated_s": 8.3,
          "peak_torque": 0.1}
    block = evidence_block("v1", params, summary, "0" * 64, 104.7, "0" * 64, per_axis=pa)
    assert "x=120.5, y=96.5, z=116.5; worst axis x governs settlingTime" in block
    assert "torque limit active until 8.3 s" in block
    assert "attribute :>> settlingTime = 120.5 [s];" in block


def test_draft_texts_are_marked_and_format():
    src = (Path(__file__).resolve().parent.parent / "sysml" / "model.py").read_text()
    assert src.count("DRAFT") >= 3
    assert SUFFICIENCY_DISAGREE_DRAFT.startswith("At Kp={Kp}, Kd={Kd} the linear estimate is {t_sym} s and z3")
    assert SUFFICIENCY_DISAGREE_DRAFT.endswith("I attest not satisfied.")
    assert "across this box of nearby designs" in SUFFICIENCY_DISAGREE_DRAFT
    assert "solver step" in SUFFICIENCY_DISAGREE_DRAFT and "{margin}" in SUFFICIENCY_DISAGREE_DRAFT
    assert "neighbo" not in SUFFICIENCY_DISAGREE_DRAFT.lower() and "Z3 confirms" not in SUFFICIENCY_DISAGREE_DRAFT
    text = sufficiency_disagree(4, 25, 104.7, 120.498, "x")
    assert "{" not in text and "is 104.7 s" in text and "settles in 120.5 s on the x axis" in text
    # the card is an exact excerpt of the full text, and the margin (0.5 s) is computed
    card = card_disagree(120.498)
    assert card in text and "misses by 0.5 s" in card and len(card.split()) <= 20
    assert "{" not in per_axis_sentence(1, 2, 3) and "{x}" in PER_AXIS_DRAFT_SENTENCE


# ----- second evidence source: the linear (SymPy) settling estimate -----

def test_evidence_block_has_estimate_and_two_tool_executions():
    block = _evidence("v1", 1.0, 10.0)
    assert "attribute :>> settlingTimeEstimate =" in block
    assert block.count("metadata : AnalysisTooling::ToolExecution") == 2
    assert "about v1::settlingTime {" in block and "about v1::settlingTimeEstimate {" in block
    assert "SymPy linear analysis (analysis/symbolic.py)" in block
    assert "metadata def" not in block


def test_estimate_loads_clean_and_verdicts_unchanged(structure):
    out = evaluate(assemble(structure, _evidence("v1", 1.0, 10.0) + _evidence("v2", 4.0, 30.0)))
    assert out["diagnostics"] == []
    assert out["verdicts"] == {"vc001_v1": "fail", "vc001_v2": "pass"}


def test_tool_executions_annotate_the_value_bearing_redefinitions(structure):
    els = {e["@id"]: e for e in to_elements(assemble(structure, _evidence("v2", 4.0, 30.0)))}
    tools = [e for e in els.values() if e["@type"] == "MetadataUsage" and any(
        els.get(t["@id"], {}).get("qualifiedName") == "AnalysisTooling::ToolExecution"
        for t in e.get("type", []))]
    assert len(tools) == 2
    for t in tools:
        (target,) = [els[a["@id"]] for a in t["annotatedElement"]]
        assert target["@type"] == "AttributeUsage" and target["owner"]["@id"] == "GeoSatADCS__v2"
        assert any(r["@id"].endswith("_pvalue_om") for r in target["ownedRelationship"])  # it carries the value


def test_symbolic_settling_is_computed_and_hashed():
    params = dict(load_params(), Kp=4.0, Kd=30.0)
    t, h = symbolic_settling(params)
    assert t > 0 and re.fullmatch(r"[0-9a-f]{64}", h)
    assert symbolic_settling(params) == (t, h)
    assert symbolic_settling(dict(params, Kd=10.0))[1] != h
    assert repr(t) in _evidence("v2", 4.0, 30.0)


# ----- approved human text (DL-25/DL-26) -----
# talk/human_text_approved.md lives under the private/ tree, which a worktree may not have, so the
# expected strings are hard-coded here and the file (when found beside the repo) is checked too.

_APPROVED = {
    "adequacy_full": "The linear model and the nonlinear simulation are adequate for judging REQ-001's "
                     "settling-time clause at this design stage. Both represent the same rigid-body loop and "
                     "control law, and the simulation also enforces the actuator torque limit. Neither "
                     "represents sensor noise, so this judgement covers the settling-time clause, not the "
                     "3-sigma accuracy clause.",
    "adequacy_card": "The linear model and the nonlinear simulation are adequate for judging REQ-001's "
                     "settling-time clause at this design stage.",
    "not_satisfied_full": "Both the linear estimate and the simulation settle well after the limit, so this "
                          "evidence is sufficient for me to say this design does not satisfy REQ-001. I attest "
                          "not satisfied.",
    "not_satisfied_card": "This evidence is sufficient for me to say this design does not satisfy REQ-001. "
                          "I attest not satisfied.",
    "satisfied_full": "At Kp={Kp}, Kd={Kd} the simulation settles in {t_sim} s and the linear estimate in "
                      "{t_sym} s, both within the {limit} s limit. This evidence is sufficient: I attest "
                      "REQ-001's settling-time clause satisfied for this design.",
    "satisfied_card": "This evidence is sufficient: I attest REQ-001's settling-time clause satisfied for "
                      "this design.",
}


def test_text_constants_equal_approved_text():
    assert ADEQUACY_TEXT == _APPROVED["adequacy_full"] and DEFAULT_ADEQUACY is ADEQUACY_TEXT
    assert CARD_ADEQUACY == _APPROVED["adequacy_card"]
    assert SUFFICIENCY_NOT_SATISFIED == _APPROVED["not_satisfied_full"]
    assert CARD_NOT_SATISFIED == _APPROVED["not_satisfied_card"]
    assert SUFFICIENCY_SATISFIED_TEMPLATE == _APPROVED["satisfied_full"]
    assert CARD_SATISFIED == _APPROVED["satisfied_card"]
    assert "DRAFT" not in ADEQUACY_TEXT


def _approved_file():
    here = Path(__file__).resolve().parent.parent
    for root in (here, here.parent.parent / "ADCS-lifecycle-demo"):
        f = root / "private" / "talk" / "human_text_approved.md"
        if f.is_file():
            return f
    return None


@pytest.mark.skipif(_approved_file() is None, reason="private/talk/human_text_approved.md not reachable")
def test_text_constants_equal_approved_file():
    src = _approved_file().read_text()
    found = {}
    for sec in re.split(r"^## ", src, flags=re.M)[1:]:
        name = sec.split(" ", 1)[0]
        for kind in ("full", "card"):
            m = re.search(rf"^\*\*{kind}:\*\* (.+)$", sec, re.M)
            found[f"{name}_{kind}"] = m.group(1).strip()
    assert found["adequacy_full"] == ADEQUACY_TEXT and found["adequacy_card"] == CARD_ADEQUACY
    assert found["sufficiency_not_satisfied_full"] == SUFFICIENCY_NOT_SATISFIED
    assert found["sufficiency_not_satisfied_card"] == CARD_NOT_SATISFIED
    assert found["sufficiency_satisfied_full"] == SUFFICIENCY_SATISFIED_TEMPLATE
    assert found["sufficiency_satisfied_card"] == CARD_SATISFIED


def test_cards_are_excerpts_of_full_text():
    assert CARD_ADEQUACY in ADEQUACY_TEXT
    # the approved card capitalises "This"; in the full text it begins mid-sentence ("this")
    assert CARD_NOT_SATISFIED[1:] in SUFFICIENCY_NOT_SATISFIED
    assert CARD_SATISFIED in SUFFICIENCY_SATISFIED_TEMPLATE


def test_sufficiency_satisfied_formats_live_numbers():
    text = sufficiency_satisfied(4.0, 30.0, 67.4, 71.6, 120)
    assert "{" not in text and "}" not in text
    assert text.startswith("At Kp=4.0, Kd=30.0 the simulation settles in 67 s and the linear estimate in 72 s, "
                           "both within the 120 s limit.")
    assert text.endswith(CARD_SATISFIED)


def test_group_diff_c2_to_c3_has_nothing_in_other(structure):
    """In-process, on real exported elements: pending marker (C2) replaced by the attestation (C3)."""
    ev = _evidence("v1", 1.0, 10.0)
    att = attestation_block("v1", False, DEMO_ENGINEER, "done", "Evidence is sufficient.", "vc001_v1")
    c2 = to_elements(assemble(structure, ev, status_block("req001")))
    c3 = to_elements(assemble(structure, ev, att))
    g = group_diff(c2, c3)
    assert not g["other"], dict(g["other"])
    assert g["att"] > 0 and g["pending"] == 1 and g["pkg"] > 0


# ----- status_block and to_elements -----

def test_status_block_pending_has_no_originator_and_no_rationale(structure):
    block = status_block("v1")
    assert "StatusKind::tbc" in block
    assert "originator" not in block and "Rationale" not in block and "satisfy" not in block
    # it loads and the evaluated verdicts are unchanged
    out = evaluate(assemble(structure, _evidence("v1", 1.0, 10.0) + block))
    assert out["diagnostics"] == [] and out["verdicts"]["vc001_v1"] == "fail"


def test_status_block_rationale_only_with_originator():
    assert "Rationale" not in status_block("req001", rationale="a reason")
    with_who = status_block("req001", originator="A. Engineer", rationale="a reason")
    assert 'originator = "A. Engineer"' in with_who
    assert "ModelingMetadata::Rationale about req001" in with_who and 'text = "a reason"' in with_who
    assert "Rationale" not in status_block("req001", originator="A. Engineer")


def test_status_block_with_originator_loads(structure):
    block = status_block("req001", originator="A. Engineer", rationale='margin "unknown"')
    out = evaluate(assemble(structure, _evidence("v1", 1.0, 10.0), block))
    assert out["diagnostics"] == []


@pytest.mark.parametrize("who", ["claude", "Bot", "", "  "])
def test_status_block_non_human_originator_refused(who):
    with pytest.raises(ValueError):
        status_block("req001", originator=who)


@pytest.mark.parametrize("bad", ["inwork", "", "DONE"])
def test_status_block_bad_status_refused(bad):
    with pytest.raises(ValueError):
        status_block("req001", status=bad)


@pytest.mark.parametrize("bad", ["", "1x", "req 1", "req001;", "a-b"])
def test_status_block_bad_target_refused(bad):
    with pytest.raises(ValueError):
        status_block(bad)


def test_to_elements_lists_user_and_library_elements(structure):
    els = to_elements(structure)
    ids = {e["@id"] for e in els}
    assert len(ids) == len(els) and "GeoSatADCS" in ids
    assert any(not i.startswith("GeoSatADCS") for i in ids)  # referenced library definitions
    assert all("@type" in e for e in els)


# ---- group_diff on small synthetic snapshots ----------------------------------------------

def _lib(i, qn):
    return {"@type": "AttributeUsage", "@id": i, "qualifiedName": qn, "isLibraryElement": True}


def _top(i, typ, owner_of=(), refs=(), **kw):
    """A top-level element, its owning membership, and one owned child that points at `refs`."""
    e = {"@type": typ, "@id": i, "owner": {"@id": PACKAGE}, "qualifiedName": f"{PACKAGE}::{i}", **kw}
    om = {"@type": "OwningMembership", "@id": i + "_om", "owner": {"@id": PACKAGE},
          "memberElement": {"@id": i}}
    child = {"@type": "FeatureValue", "@id": i + "_c", "owner": {"@id": i},
             "ref": [{"@id": r} for r in refs]}
    return [e, om, child]


def _snap(*groups, members):
    pkg = {"@type": "Package", "@id": PACKAGE,
           "ownedRelationship": [{"@id": m + "_om"} for m in members]}
    return [pkg] + [e for g in groups for e in g]


LIB = [_lib("L_info", "ModelingMetadata::StatusInfo"), _lib("L_tbc", "ModelingMetadata::StatusKind::tbc"),
       _lib("L_done", "ModelingMetadata::StatusKind::done"),
       _lib("L_orig", "ModelingMetadata::StatusInfo::originator"), _lib("L_orphan", "Other::Thing")]
REQ = _top("req001", "RequirementUsage")  # qualifiedName GeoSatADCS::req001
PEND = _top("pend", "MetadataUsage", refs=["L_tbc"], type=[{"@id": "L_info"}],
            annotatedElement=[{"@id": "req001"}])
SAT = _top("sat", "SatisfyRequirementUsage")
ATTM = _top("attm", "MetadataUsage", refs=["L_done", "L_orig"], type=[{"@id": "L_info"}],
            annotatedElement=[{"@id": "sat"}])


def _c2_snap():
    return _snap([LIB[0], LIB[1]], REQ, PEND, members=["req001", "pend"])


def _c3_snap(extra=(), members=("req001", "sat", "attm"), lib=("L_info", "L_done", "L_orig")):
    libs = [e for e in LIB if e["@id"] in lib]
    return _snap(libs, REQ, SAT, ATTM, list(extra), members=list(members))


def test_group_diff_all_four_groups_and_nothing_else():
    g = group_diff(_c2_snap(), _c3_snap())
    assert g["att"] == 6 and g["att_roots"] == {"SatisfyRequirementUsage": 1, "MetadataUsage": 1}
    assert (g["pending"], g["pending_elements"], g["pending_library"]) == (1, 3, 1)
    assert g["pkg"] == 2 and g["lib"] == 2  # done, originator
    assert not g["other"]


def test_group_diff_returns_the_names_it_groups():
    g = group_diff(_c2_snap(), _c3_snap())
    assert g["names"] == {"meta": ["StatusInfo"],
                          "lib": ["ModelingMetadata::StatusInfo::originator", "ModelingMetadata::StatusKind::done"]}
    assert len(g["names"]["lib"]) == g["lib"] and len(g["names"]["meta"]) == g["att_roots"]["MetadataUsage"]


def test_group_diff_accepts_dicts_keyed_by_id():
    by = lambda snap: {e["@id"]: e for e in snap}  # noqa: E731
    assert group_diff(by(_c2_snap()), by(_c3_snap())) == group_diff(_c2_snap(), _c3_snap())


def test_group_diff_design_element_goes_to_other():
    part = _top("tuned", "PartUsage")
    g = group_diff(_c2_snap(), _c3_snap(extra=part, members=("req001", "sat", "attm", "tuned")))
    assert g["other"] == {"added PartUsage GeoSatADCS::tuned": 3, "changed Package GeoSatADCS": 1}
    assert g["pkg"] == 0


def test_group_diff_unreachable_library_addition_goes_to_other():
    g = group_diff(_c2_snap(), _c3_snap(lib=("L_info", "L_done", "L_orig", "L_orphan")))
    assert g["lib"] == 2 and g["other"] == {"added AttributeUsage Other::Thing": 1}


def test_group_diff_marker_with_originator_does_not_qualify():
    named = _top("pend", "MetadataUsage", refs=["L_tbc", "L_orig"], type=[{"@id": "L_info"}],
                 annotatedElement=[{"@id": "req001"}])
    old = _snap([LIB[0], LIB[1], LIB[3]], REQ, named, members=["req001", "pend"])
    g = group_diff(old, _c3_snap())
    assert g["pending"] == 0
    assert g["other"]["removed MetadataUsage GeoSatADCS::pend"] == 3
    assert g["pkg"] == 0 and g["other"]["changed Package GeoSatADCS"] == 1  # lost member is not a pending marker


def test_group_diff_marker_with_done_status_does_not_qualify():
    done = _top("pend", "MetadataUsage", refs=["L_done"], type=[{"@id": "L_info"}],
                annotatedElement=[{"@id": "req001"}])
    old = _snap([LIB[0], LIB[2]], REQ, done, members=["req001", "pend"])
    assert group_diff(old, _c3_snap())["pending"] == 0


def test_group_diff_identical_snapshots_are_empty():
    g = group_diff(_c3_snap(), _c3_snap())
    assert not g["att"] and not g["pending"] and not g["pkg"] and not g["lib"] and not g["other"]


def test_legacy_evidence_block_call_ignores_adequacy():
    params = dict(load_params(), Kp=1.0, Kd=10.0)
    legacy = evidence_block("v1", params, {"settling_time_s": 5.0}, "0" * 64, "adequate!", "A. Engineer", 1.0, "1" * 64)
    assert legacy == evidence_block("v1", params, {"settling_time_s": 5.0}, "0" * 64, 1.0, "1" * 64)
    assert "adequate!" not in legacy
