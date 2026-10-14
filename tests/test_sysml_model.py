"""Tests for sysml/model.py: structure, evidence and attestation blocks evaluated by OpenSysML 0.10.0."""

from __future__ import annotations

import re

import pytest
from rdflib import Graph

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from evidence.hashing import hash_simulation
from sysml.model import (DEFAULT_ADEQUACY, DEMO_ENGINEER, PACKAGE, NOT_A_HUMAN, assemble, attestation_block, evaluate,
                         evidence_block, group_diff, load_structure, status_block, to_elements)

pytestmark = pytest.mark.filterwarnings("ignore")
ROOT_TTL = "structural/satellite.ttl"


def _norm(s: str) -> str:
    return " ".join(s.split())


def _evidence(design: str, kp: float, kd: float) -> str:
    params = dict(load_params(), Kp=kp, Kd=kd)
    sim = run_step_response(params)
    summary = sim.summary()
    return evidence_block(design, params, summary, hash_simulation(sim.config.to_dict(), summary),
                          DEFAULT_ADEQUACY, DEMO_ENGINEER)


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


@pytest.mark.parametrize("bad", ["", "1v", "v 1", "v1;", "v1\n", "a-b", "v1 } part x"])
def test_bad_identifiers_refused(bad):
    params = dict(load_params(), Kp=1.0, Kd=10.0)
    sim = run_step_response(params)
    with pytest.raises(ValueError):
        evidence_block(bad, params, sim.summary(), "0" * 64, "x", "A. Engineer")
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


def test_adequacy_text_is_caller_supplied():
    params = dict(load_params(), Kp=1.0, Kd=10.0)
    summary = run_step_response(params).summary()
    block = evidence_block("v1", params, summary, "0" * 64, "My own judgement.", "A. Engineer")
    assert "My own judgement." in block
    assert "adequate" not in block.replace("adequacy judgement", "")


def test_adequacy_statusinfo_carries_originator(structure):
    params = dict(load_params(), Kp=1.0, Kd=10.0)
    summary = run_step_response(params).summary()
    block = evidence_block("v1", params, summary, "0" * 64, "x", DEMO_ENGINEER)
    assert DEMO_ENGINEER == "Michael Zargham"
    assert ("metadata : ModelingMetadata::StatusInfo about v1 {\n"
            f'        originator = "{DEMO_ENGINEER}";\n'
            "        status = StatusKind::done;") in block
    assert "metadata def" not in block
    assert f"{DEMO_ENGINEER}'s adequacy judgement" in block  # banner names the owner
    # structure plus evidence loads with no diagnostics (StatusInfo about a part, standard library only)
    out = evaluate(assemble(structure, block))
    assert out["diagnostics"] == []


@pytest.mark.parametrize("who", sorted(NOT_A_HUMAN) + ["", "  ", "Claude"])
def test_adequacy_by_non_human_refused(who):
    params = dict(load_params(), Kp=1.0, Kd=10.0)
    summary = run_step_response(params).summary()
    with pytest.raises(ValueError):
        evidence_block("v1", params, summary, "0" * 64, "x", who)


# ----- status_block and to_elements -----

def test_status_block_pending_has_no_originator_and_no_rationale(structure):
    block = status_block("v1")
    assert "StatusKind::tbc" in block
    assert "originator" not in block and "Rationale" not in block and "satisfy" not in block
    # it loads and the evaluated verdicts are unchanged
    out = evaluate(assemble(structure, _evidence("v1", 1.0, 10.0) + block))
    assert out["diagnostics"] == [] and out["verdicts"]["vc001_v1"] == "fail"


def test_status_block_rationale_only_with_originator():
    assert "Rationale" not in status_block("req004", rationale="a reason")
    with_who = status_block("req004", originator="A. Engineer", rationale="a reason")
    assert 'originator = "A. Engineer"' in with_who
    assert "ModelingMetadata::Rationale about req004" in with_who and 'text = "a reason"' in with_who
    assert "Rationale" not in status_block("req004", originator="A. Engineer")


def test_status_block_with_originator_loads(structure):
    block = status_block("req004", originator="A. Engineer", rationale='margin "unknown"')
    out = evaluate(assemble(structure, _evidence("v1", 1.0, 10.0), block))
    assert out["diagnostics"] == []


@pytest.mark.parametrize("who", ["claude", "Bot", "", "  "])
def test_status_block_non_human_originator_refused(who):
    with pytest.raises(ValueError):
        status_block("req004", originator=who)


@pytest.mark.parametrize("bad", ["inwork", "", "DONE"])
def test_status_block_bad_status_refused(bad):
    with pytest.raises(ValueError):
        status_block("req004", status=bad)


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
