"""Assemble and evaluate the GeoSatADCS SysML v2 model with OpenSysML 0.10.0.

Three blocks, three owners, spliced into one package:
  structure    hand-authored, static, in Git         (sysml/satellite.sysml)
  evidence     generated from scipy results          (evidence_block)
  attestation  written only by a human action        (attestation_block)

Verdicts and `holds` are verification (automated). The attestation is the human's
`satisfy` plus its StatusInfo; `evaluate` only checks the claim for consistency.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import opensysml

from analysis.symbolic import run_symbolic_analysis
from evidence.hashing import hash_simulation

VERSION = "v0.10.0"
PACKAGE = "GeoSatADCS"
STRUCTURE_PATH = Path(__file__).with_name("satellite.sysml")

# Names that must never be recorded as the human who attested. A blunt guard, not a
# security boundary: copied from sysmlv2-testing (same trust model as git authorship).
NOT_A_HUMAN = frozenset({"svt", "svt-cli", "cli", "claude", "llm", "ai", "agent", "bot", "assistant"})

# The person the demo fixtures are attributed to: the pre-seeded name in export mode and the
# pre-filled (editable) name field in live mode.
DEMO_ENGINEER = "Michael Zargham"

# The demo uses only two statuses: "tbc" (pending, the human has not yet decided) and
# "done" (attested). The rest of StatusKind (for example inwork, closed) is not used, so
# anything else is refused rather than silently recorded.
_STATUS = {"tbc", "done"}
_IDENT = re.compile(r"^[A-Za-z_]\w*$")

# Human judgement text, approved by Michael Zargham (DL-25/DL-26), verbatim. `{...}` fields in
# the satisfied template are filled from computed values by `sufficiency_satisfied`.
ADEQUACY_TEXT = (
    "The linear model and the nonlinear simulation are adequate for judging REQ-001's "
    "settling-time clause at this design stage. Both represent the same rigid-body loop and "
    "control law, and the simulation also enforces the actuator torque limit. Neither "
    "represents sensor noise, so this judgement covers the settling-time clause, not the "
    "3-sigma accuracy clause."
)
DEFAULT_ADEQUACY = ADEQUACY_TEXT  # alias: the notebook's pre-filled adequacy text

SUFFICIENCY_NOT_SATISFIED = (
    "Both the linear estimate and the simulation settle well after the limit, so this evidence "
    "is sufficient for me to say this design does not satisfy REQ-001. I attest not satisfied."
)
SUFFICIENCY_SATISFIED_TEMPLATE = (
    "At Kp={Kp}, Kd={Kd} the simulation settles in {t_sim} s and the linear estimate in {t_sym} s, "
    "both within the {limit} s limit. This evidence is sufficient: I attest REQ-001's "
    "settling-time clause satisfied for this design."
)

# Exact excerpts of the texts above, for the amber card.
CARD_ADEQUACY = ("The linear model and the nonlinear simulation are adequate for judging REQ-001's "
                 "settling-time clause at this design stage.")
CARD_NOT_SATISFIED = ("This evidence is sufficient for me to say this design does not satisfy REQ-001. "
                      "I attest not satisfied.")
CARD_SATISFIED = ("This evidence is sufficient: I attest REQ-001's settling-time clause satisfied "
                  "for this design.")


def sufficiency_satisfied(Kp, Kd, t_sim, t_sym, limit) -> str:
    """The approved C3 sufficiency text with live numbers: times as whole seconds, gains as given."""
    return SUFFICIENCY_SATISFIED_TEMPLATE.format(Kp=Kp, Kd=Kd, t_sim=f"{t_sim:.0f}",
                                                 t_sym=f"{t_sym:.0f}", limit=limit)


def _q(text: str) -> str:
    """Escape text for a SysML string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _ident(kind: str, value: str) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ValueError(f"{kind} {value!r} is not a SysML identifier (^[A-Za-z_]\\w*$)")
    return value


def symbolic_settling(params: dict) -> tuple[float, str]:
    """The linear (SymPy) settling estimate and its evidence hash, both computed here."""
    t = float(run_symbolic_analysis(params).pointing_budget["settling_time_s"])
    return t, hash_simulation({"method": "sympy", "Kp": params["Kp"], "Kd": params["Kd"]},
                              {"settling_time_s": t})


def evidence_block(design: str, params: dict, summary: dict, sim_hash: str, adequacy: str,
                   adequacy_by: str, t_estimate_s: float, est_hash: str) -> str:
    """The generated block for one design. `params` has Kp, Kd;
    `summary` is SimResult.summary(); `sim_hash` comes from evidence.hashing.hash_simulation.
    `t_estimate_s` and `est_hash` come from `symbolic_settling`: a second, independent estimate.

    `adequacy` is the Rationale text: a person's judgement (validation) that the model is
    adequate for this use, carried with the evidence. The caller supplies it; this function
    makes no judgement of its own. `adequacy_by` is the person whose judgement it is: it is
    recorded as the originator of a StatusInfo about the design (a Rationale has no author
    field) and must pass the NOT_A_HUMAN guard."""
    _ident("design", design)
    who = adequacy_by.strip()
    if not who or who.lower() in NOT_A_HUMAN:
        raise ValueError(f"adequacy_by {adequacy_by!r} is not a named human")
    return f"""\
    // ----- Rationale and StatusInfo below are {_q(who)}'s adequacy judgement, carried with the evidence -----
    part {design} : ADCS {{
        attribute :>> Kp = {float(params['Kp'])!r};
        attribute :>> Kd = {float(params['Kd'])!r};
        attribute :>> settlingTime = {float(summary['settling_time_s'])!r} [s];
        attribute :>> settlingTimeEstimate = {float(t_estimate_s)!r} [s];
    }}
    metadata : AnalysisTooling::ToolExecution about {design}::settlingTime {{
        toolName = "scipy solve_ivp (analysis/numerical.py)";
        uri = "sha256:{sim_hash}";
    }}
    metadata : AnalysisTooling::ToolExecution about {design}::settlingTimeEstimate {{
        toolName = "SymPy linear analysis (analysis/symbolic.py)";
        uri = "sha256:{est_hash}";
    }}
    metadata : ModelingMetadata::Rationale about {design} {{
        text = "{_q(adequacy)}";
    }}
    metadata : ModelingMetadata::StatusInfo about {design} {{
        originator = "{_q(who)}";
        status = StatusKind::done;
    }}
    verification vc001_{design} : SettlingVerification {{ subject = {design}; }}
"""


def attestation_block(design: str, satisfied: bool, originator: str, status: str,
                      sufficiency: str, verification: str) -> str:
    """The human's claim (usage-subsetting form, which OpenSysML 0.10.0 evaluates and which traces to req001) with StatusInfo and the sufficiency Rationale.
    Refuses an empty originator or one in NOT_A_HUMAN."""
    _ident("design", design)
    _ident("verification", verification)
    who = originator.strip()
    if not who or who.lower() in NOT_A_HUMAN:
        raise ValueError(f"originator {originator!r} is not a named human")
    if status not in _STATUS:
        raise ValueError(f"status must be one of {sorted(_STATUS)}, got {status!r}")
    neg = "" if satisfied else "not "
    return f"""\
    {neg}satisfy requirement att_{design} :> req001 by {design};
    metadata : ModelingMetadata::StatusInfo about att_{design} {{
        originator = "{_q(who)}";
        status = StatusKind::{status};
    }}
    metadata : ModelingMetadata::Rationale about att_{design} {{
        text = "{_q(sufficiency)}";
        explanation = {verification};
    }}
"""


def status_block(target: str, status: str = "tbc", originator: str | None = None,
                 rationale: str | None = None) -> str:
    """A StatusInfo (and, for a person, a Rationale) about `target`, with no `satisfy`.

    With no originator this records "no person has acted yet": status is validated, nothing
    is invented, and no Rationale is written (a Rationale is a person's judgement). With an
    originator, the name must pass the NOT_A_HUMAN guard and the Rationale, if given, is
    emitted. A rationale given without an originator is dropped, never attributed."""
    _ident("target", target)
    if status not in _STATUS:
        raise ValueError(f"status must be one of {sorted(_STATUS)}, got {status!r}")
    out = f"    metadata : ModelingMetadata::StatusInfo about {target} {{\n"
    if originator is not None:
        who = originator.strip()
        if not who or who.lower() in NOT_A_HUMAN:
            raise ValueError(f"originator {originator!r} is not a named human")
        out += f'        originator = "{_q(who)}";\n'
    out += f"        status = StatusKind::{status};\n    }}\n"
    if originator is not None and rationale is not None:
        out += (f"    metadata : ModelingMetadata::Rationale about {target} {{\n"
                f'        text = "{_q(rationale)}";\n    }}\n')
    return out


def _banner(label: str, owner: str) -> str:
    return f"    // ===== {label} block ({owner}) =====\n"


def assemble(structure: str, evidence: str = "", attestation: str = "") -> str:
    """Splice the evidence and attestation blocks before the package's closing brace."""
    head, brace, tail = structure.rstrip().rpartition("}")
    if not brace:
        raise ValueError("structure has no closing brace")
    parts = [head.rstrip() + "\n\n"]
    if evidence:
        parts.append(_banner("evidence", "generated by Python from scipy") + evidence + "\n")
    if attestation:
        parts.append(_banner("attestation", "written only by a human") + attestation)
    parts.append("}\n")
    return "".join(parts)


def load_structure() -> str:
    return STRUCTURE_PATH.read_text()


def to_elements(text: str) -> list[dict]:
    """The model's API elements (OpenSysML `to_api_json`), the snapshot published to Flexo.
    The export also lists the standard-library definitions the model references."""
    conn = opensysml.connect(version=VERSION)
    try:
        return json.loads(conn.load_from_content(text, strict=True).to_api_json().content)
    finally:
        conn.close()


# ---- element-level diff of two snapshots, grouped ---------------------------------------
# Keys that only point upward; following them would reach the whole model from any element.
_UP = {"owner", "owningNamespace", "owningRelationship", "owningMembership", "owningFeatureMembership"}
# Package keys that change when members change (membership lists and source positions).
_PKG_MEMBER_KEYS = {"ownedRelationship", "ownedMember", "ownedMembership"}
_PENDING_LIB = ("ModelingMetadata::StatusKind::tbc", "ModelingMetadata::StatusInfo::originator")


def _refs(e: dict):
    """Ids this element points at, ignoring links to its owner."""
    def walk(v):
        if isinstance(v, dict):
            if "@id" in v:
                yield v["@id"]
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)
    for k, v in e.items():
        if k not in _UP:
            yield from walk(v)


def _owner(e: dict):
    return (e.get("owner") or {}).get("@id")


def _in_model(i: str, snap: dict) -> bool:
    for _ in range(200):
        if i == PACKAGE:
            return True
        if i not in snap or _owner(snap[i]) is None:
            return False
        i = _owner(snap[i])
    return False


def _top(i: str, snap: dict) -> str:
    """The element directly under the package that holds `i` (a membership resolves to its
    member); for a standard-library element, the root of its owner chain."""
    for _ in range(200):
        o = _owner(snap[i])
        if o is None or o == PACKAGE or o not in snap:
            break
        i = o
    if snap[i]["@type"] == "OwningMembership" and snap[i].get("memberElement", {}).get("@id") in snap:
        i = snap[i]["memberElement"]["@id"]
    return i


def _label(i: str, snap: dict) -> str:
    e = snap[i]
    return f"{e['@type']} {e.get('declaredName') or e.get('name') or e.get('qualifiedName') or i}"


def _lib_reach(roots, snap: dict) -> set:
    """Library (non-model) elements reachable by following references from `roots`,
    transitively through library elements only."""
    seen, todo = set(), [r for r in roots]
    while todo:
        for t in _refs(snap[todo.pop()]):
            if t in snap and t not in seen and not _in_model(t, snap):
                seen.add(t)
                todo.append(t)
    return seen


def group_diff(old, new) -> dict:
    """Group the element diff between two snapshots (lists of API elements, or dicts keyed by
    @id) for the step "human attests after the evidence changed". Everything is computed from
    @type, ownership, references and qualified names. Groups:

      att       elements added under a top-level `satisfy`, or under top-level metadata that
                is only about an added `satisfy` (att_roots counts those top-level elements)
      pending   removed top-level StatusInfo about req001 with status tbc and no originator
                (pending elements = what it owns; pending_library = library definitions only
                it referenced, such as the `tbc` literal)
      pkg       members the package gained, when they are exactly the att top-level elements
                and the only member lost is a pending marker
      lib       added library elements reachable by reference from the att elements
      other     everything else, rolled up by top-level owner: {"added Type name": count}
      names     the names behind the counts: "meta" = the metadata types of the att top-level
                metadata, "lib" = qualified names of the lib elements (both sorted)

    Empty `other` means nothing outside the four named groups changed."""
    old = {e["@id"]: e for e in (old.values() if isinstance(old, dict) else old)}
    new = {e["@id"]: e for e in (new.values() if isinstance(new, dict) else new)}
    added, removed = new.keys() - old.keys(), old.keys() - new.keys()
    changed = [i for i in old.keys() & new.keys() if old[i] != new[i]]

    # attestation: added top-level satisfy, or metadata whose every target is an added satisfy
    tops = {_top(i, new) for i in added if _in_model(i, new)}
    satisfy = {t for t in tops if t in added and new[t]["@type"] == "SatisfyRequirementUsage"}
    att_tops = set(satisfy)
    for t in tops:
        targets = [x["@id"] for x in new[t].get("annotatedElement", [])]
        if t in added and new[t]["@type"] == "MetadataUsage" and targets and set(targets) <= satisfy:
            att_tops.add(t)
    att = {i for i in added if _in_model(i, new) and _top(i, new) in att_tops}
    reach = _lib_reach(att, new)

    # pending marker: computed from the old snapshot, never named by hand
    pend_tops, pend_lib = set(), set()
    for t in {_top(i, old) for i in removed if _in_model(i, old)}:
        e = old[t]
        sub = {i for i in old if _in_model(i, old) and _top(i, old) == t}
        lib = _lib_reach(sub, old)
        names = {old[i].get("qualifiedName") for i in lib}
        types = {old[x["@id"]].get("qualifiedName") for x in e.get("type", []) if x["@id"] in old}
        about = {old[x["@id"]].get("qualifiedName") for x in e.get("annotatedElement", []) if x["@id"] in old}
        if (e["@type"] == "MetadataUsage" and sub <= removed and types == {"ModelingMetadata::StatusInfo"}
                and about == {f"{PACKAGE}::req001"} and _PENDING_LIB[0] in names
                and _PENDING_LIB[1] not in names):
            pend_tops.add(t)
            pend_lib |= lib & removed

    out = {"att": len(att), "att_roots": Counter(new[t]["@type"] for t in att_tops),
           "pending": len(pend_tops),
           "pending_elements": len({i for i in removed if _in_model(i, old) and _top(i, old) in pend_tops}),
           "pending_library": len(pend_lib), "pkg": 0, "lib": len(reach & added), "other": Counter(),
           "names": {
               "meta": sorted(new[x["@id"]]["qualifiedName"].split("::")[-1] for t in att_tops
                              if new[t]["@type"] == "MetadataUsage" for x in new[t].get("type", [])
                              if x["@id"] in new),
               "lib": sorted(new[i]["qualifiedName"] for i in reach & added)}}
    named = att | (reach & added) | pend_lib | {i for i in removed if _in_model(i, old) and _top(i, old) in pend_tops}

    for i in sorted(added - named):
        out["other"][f"added {_label(_top(i, new), new)}"] += 1
    for i in sorted(removed - named):
        out["other"][f"removed {_label(_top(i, old), old)}"] += 1
    for i in sorted(changed):
        if i == PACKAGE:
            gained = {m["@id"] for m in new[i].get("ownedRelationship", [])} - {
                m["@id"] for m in old[i].get("ownedRelationship", [])}
            lost = {m["@id"] for m in old[i].get("ownedRelationship", [])} - {
                m["@id"] for m in new[i].get("ownedRelationship", [])}
            member = lambda ids, snap: {_top(m, snap) for m in ids if m in snap}  # noqa: E731
            other_keys = {k for k in new[i].keys() | old[i].keys() if new[i].get(k) != old[i].get(k)}
            if (member(gained, new) == att_tops and member(lost, old) == pend_tops
                    and all(k in _PKG_MEMBER_KEYS or k.startswith("sysx:") for k in other_keys)):
                out["pkg"] = len(gained)
                continue
        out["other"][f"changed {_label(_top(i, new) if i != PACKAGE else i, new)}"] += 1
    return out


def evaluate(text: str) -> dict:
    """Load `text` with OpenSysML (strict) and return plain Python:
    diagnostics, verdicts (verification usage -> kind), claims (att_* -> holds/error),
    req ("req001(design)" -> bool)."""
    conn = opensysml.connect(version=VERSION)
    try:
        model = conn.load_from_content(text, strict=True)
        diagnostics = [f"{d.severity}: {d.message}" for d in model.diagnostics]
        verdicts = {
            name: model.run_analysis(f"{PACKAGE}::{name}").verifications[0].kind
            for name in re.findall(r"^\s*verification\s+(vc\d+_\w+)\s*:", text, re.M)
        }
        claims = {}
        for name in re.findall(r"satisfy\s+requirement\s+(att_\w+)\s*:>", text):
            v = model.verify_satisfaction(f"{PACKAGE}::{name}")[0]
            claims[name] = {"holds": bool(v.holds) if not v.error else None, "error": v.error or None}
        req = {}
        for design in re.findall(r"^\s*part\s+(\w+)\s*:\s*ADCS\b", text, re.M):
            req[f"req001({design})"] = bool(model.eval(f"{PACKAGE}::req001({PACKAGE}::{design})"))
        return {"diagnostics": diagnostics, "verdicts": verdicts, "claims": claims, "req": req}
    finally:
        conn.close()
