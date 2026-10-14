"""Probe which SysML v2 standard-library constructs OpenSysML 0.10.0 parses and evaluates
for the pattern: requirement -> evidence -> automated verdict -> human attestation.

Run:  uv run python sysml/probe/run_probe.py [--markdown]

Evidence numbers come from the scipy step response (analysis.numerical), are written into
probe.sysml, and are read back through OpenSysML. Nothing is typed in by hand.
Exit 0 when the probe ran to the end, whatever each construct did. Exit 1 only if the
scipy numbers drift from the expected ~310.63 s and ~77.97 s or the service is unreachable.
"""

from __future__ import annotations

import collections
import json
import sys
import warnings
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import opensysml  # noqa: E402

from analysis.load_params import load_params  # noqa: E402
from analysis.numerical import run_step_response  # noqa: E402

VERSION = "v0.10.0"
P = "ProbePkg::"
warnings.simplefilter("ignore")  # to_api_json is flagged experimental


def evidence() -> dict[str, float]:
    base = load_params()
    bad = run_step_response(dict(base, Kp=1.0, Kd=10.0)).summary()
    good = run_step_response(dict(base, Kp=4.0, Kd=30.0)).summary()
    return {
        "__BAD_ST__": bad["settling_time_s"],
        "__GOOD_ST__": good["settling_time_s"],
        "__BAD_PT__": bad["peak_control_torque"],
        "__GOOD_PT__": good["peak_control_torque"],
        "__LIMIT__": base["maxTorque"],
    }


def load_model(conn, ev: dict[str, float]):
    src = (Path(__file__).parent / "probe.sysml").read_text()
    for key, val in ev.items():
        src = src.replace(key, repr(float(val)))
    return conn.load_from_content(src)


class Index:
    """The to_api_json export, indexed. The only route to satisfy and metadata elements."""

    def __init__(self, model):
        self.elements = json.loads(model.to_api_json().content)
        self.by_id = {e["@id"]: e for e in self.elements}
        self.by_qn = {e["qualifiedName"]: e for e in self.elements if e.get("qualifiedName")}

    def types(self) -> collections.Counter:
        return collections.Counter(e["@type"] for e in self.elements)

    def qn(self, ref) -> str | None:
        return self.by_id.get(ref["@id"], {}).get("qualifiedName")

    def metadata(self, name: str) -> dict:
        """Metadata usage by short name: type, annotated elements and field values."""
        e = self.by_qn[P + name]
        out = {
            "type": [self.qn(t) or t["@id"] for t in e.get("type", [])],
            "about": [self.qn(a) for a in e.get("annotatedElement", [])],
        }
        for f in e.get("ownedFeature", []):
            feat = self.by_id[f["@id"]]
            expr = self.by_id[feat["value"]["@id"]]
            if "referent" in expr:  # enum literal or element reference
                tgt = self.by_id.get(expr["referent"]["@id"], {})
                out[feat["qualifiedName"].rsplit("::", 1)[1]] = tgt.get("qualifiedName") or expr["referent"]["@id"]
            else:
                out[feat["qualifiedName"].rsplit("::", 1)[1]] = expr.get("value")
        return out


def verdict_kind(model, case: str, subject: str | None = None):
    r = model.run_analysis(P + case, subject=P + subject if subject else None)
    v = r.verifications[0]
    return v.kind, v.detail, r


def satisfy_result(model, name: str) -> tuple[bool, str]:
    v = model.verify_satisfaction(P + name)[0]
    if v.error:
        return v.holds, v.error
    return v.holds, f"{v.element}: {v.condition or ('holds' if v.holds else 'fails')}"


def build_rows(model, idx: Index, ev: dict[str, float]) -> list[dict]:
    rows: list[dict] = []
    clean = not model.diagnostics

    def row(construct, parses, evaluates, excerpt, notes):
        rows.append(dict(construct=construct, parses=parses, evaluates=evaluates,
                         excerpt=excerpt, notes=notes))

    # 1. imports
    row("import VerificationCases, ModelingMetadata, AnalysisTooling",
        "y" if clean else "n", "n/a",
        f"diagnostics: {len(model.diagnostics)}",
        "Package-level `private import X::*;` for all three libraries resolves in a single-file load.")

    # 2. requirement def + usage
    weak_r = model.verify_requirement(P + "req001", subject=P + "weak")
    tuned_r = model.verify_requirement(P + "req001", subject=P + "tuned")
    row("requirement def with `require constraint { adcs.settlingTime <= 120 [s] }`, usage `req001`",
        "y" if P + "SettlingReq" in idx.by_qn and P + "req001" in idx.by_qn else "n",
        f"y (weak: {'holds' if weak_r.holds else 'fails'}; tuned: {'holds' if tuned_r.holds else 'fails'})",
        str(weak_r),
        "Unit form `120 [s]` works. `model.verify_requirement(id, subject=part)` evaluates a usage against a "
        "concrete part. Bare `adcs` needs `subject=`.")

    # 3. candidate values
    wv = model.eval(P + "weak.settlingTime")
    gv = model.eval(P + "tuned.settlingTime")
    wf, gf = float(wv.magnitude), float(gv.magnitude)
    try:
        model.eval("weak.settlingTime")
        bare = "bare name evaluated"
    except Exception as e:  # noqa: BLE001
        bare = f"bare name -> {type(e).__name__}: {str(e)[:60]}"
    row("candidate parts with `settlingTime` bound to scipy values (Kp=1,Kd=10) and (Kp=4,Kd=30)",
        "y", f"y ({wf:.2f} s, {gf:.2f} s)",
        f"model.eval -> {type(wv.magnitude).__name__} {wv.magnitude}",
        f"Round-trip equals scipy: weak {ev['__BAD_ST__']:.2f}, tuned {ev['__GOOD_ST__']:.2f} "
        f"(equal: {wf == ev['__BAD_ST__'] and gf == ev['__GOOD_ST__']}). `Quantity.magnitude` is a "
        f"`{'Fraction' if isinstance(wv.magnitude, Fraction) else type(wv.magnitude).__name__}`; cast with float(). "
        f"`eval` of a {bare}...; use qualified names.")

    # 4/5. verification forms
    for label, case in (("explicit inequality `PassIf(adcs.settlingTime <= 120 [s])`", "Explicit"),
                        ("single source `PassIf(req001(adcs))`", "Single")):
        kw, _, rw = verdict_kind(model, f"weak{case}")
        kt, _, _ = verdict_kind(model, f"tuned{case}")
        kd, _, _ = verdict_kind(model, f"SettlingCheck{case}", "weak")
        ok = (kw, kt) == ("fail", "pass")
        ev_w = model.eval(f"{P}req001({P}weak)")
        ev_t = model.eval(f"{P}req001({P}tuned)")
        row(f"verification def, {label}, `objective {{ verify req001; }}`, `return verdict : VerdictKind`",
            "y", f"y (weak: {kw}; tuned: {kt})" + ("" if ok else " UNEXPECTED"),
            f"run_analysis(...).verifications[0].kind = {kw!r} / {kt!r}; outputs.verdict = {rw.outputs['verdict'].name}",
            f"As a usage with `subject = part;` and as a def run with `subject=` (weak: {kd}) give the same kind. "
            f"The objective's own verdict reads: `{rw.verdicts[0].explain()}`, so the kind comes from the "
            f"`return` binding only. Verdict-fallback check: model.eval('req001(weak)') -> {ev_w!r}, "
            f"req001(tuned) -> {ev_t!r} (type {type(ev_w).__name__}).")

    # 6. REQ-004 style, no verdict binding
    k, detail, r4 = verdict_kind(model, "tunedTorque")
    vr = model.verify_requirement(P + "req004", subject=P + "tuned")
    row("REQ-004 style: real constraint `peakTorque <= torqueLimit`, verification with no verdict binding",
        "y", f"y (inconclusive: {k == 'inconclusive'})",
        f"kind={k!r} detail={detail!r}; outputs={r4.outputs}",
        f"Not pass/fail/error: `inconclusive`, with a detail string. The requirement itself does hold when "
        f"evaluated directly (`verify_requirement` -> {'holds' if vr.holds else 'fails'}), so inconclusive "
        "marks 'no verdict was declared', not 'constraint unmet'. peakTorque tuned "
        f"{ev['__GOOD_PT__']:.4f} N*m vs limit {ev['__LIMIT__']:.4f} N*m (equal, so the <= holds at the boundary).")

    # 7. named satisfy, spec form and subsetting form
    ok_att, msg_att = satisfy_result(model, "attTuned")
    ok_sub, msg_sub = satisfy_result(model, "subTuned")
    row("`satisfy requirement attTuned : SettlingReq by tuned;` (spec form, typed by the requirement def)",
        "y" if P + "attTuned" in idx.by_qn else "n",
        f"n (verify_satisfaction: holds={ok_att})",
        msg_att,
        "Loads clean, appears in to_api_json as SatisfyRequirementUsage and takes metadata, but "
        "verify_satisfaction reports an error, not a verdict: the claim is typed by the def and names no "
        "requirement usage, which the evaluator takes as 'no requirement to satisfy'.")
    row("`satisfy requirement subTuned :> req001 by tuned;` (named, subsets the usage)",
        "y" if P + "subTuned" in idx.by_qn else "n",
        f"y (holds={ok_sub})",
        f"verify_satisfaction({P}subTuned) -> {msg_sub}",
        "Not the spec form the contract asked for, but standard SysML. Keeps a name for the claim AND is "
        "evaluated. The name is lost in the verdict label (reads `satisfy req001 by tuned`).")

    # 8. not satisfy
    okn, msgn = satisfy_result(model, "attWeakNot")
    oks, msgs = satisfy_result(model, "subWeakNot")
    neg = idx.by_qn[P + "attWeakNot"].get("isNegated")
    row("`not satisfy requirement attWeakNot : SettlingReq by weak;` (spec form)",
        "y" if neg else "n", f"n (holds={okn})", msgn,
        f"isNegated={neg} in to_api_json, so the claim is representable; it fails to evaluate for the "
        "same reason as the positive spec form.")
    row("`not satisfy requirement subWeakNot :> req001 by weak;` (subsetting form)",
        "y", f"y (holds={oks})", f"verify_satisfaction({P}subWeakNot) -> {msgs}",
        "A correct negative claim evaluates to holds=True (weak does fail req001). Without a name "
        "in the verdict label.")

    # 9-12. metadata
    sw, st, sd = idx.metadata("statWeak"), idx.metadata("statTuned"), idx.metadata("statDesign")
    row("`metadata statWeak : ModelingMetadata::StatusInfo about attWeak { originator; status = StatusKind::done; }`",
        "y", "n/a (data, read back from to_api_json)", json.dumps(sw),
        f"Attaches to a named satisfy (spec form too). Values read back: originator={sw['originator']!r}, "
        f"status={sw['status']!r}. Also attaches to subTuned ({st['about']}) and to the design part "
        f"(statDesign about {sd['about']}, status={sd['status']!r}). Enum values come back as "
        "the literal's qualified name.")
    rt, rd = idx.metadata("ratTuned"), idx.metadata("ratDesign")
    row("`metadata ratTuned : ModelingMetadata::Rationale about attTuned { text; explanation = tunedExplicit; }`",
        "y", "n/a (data)", json.dumps(rt),
        f"`explanation` is a ref to the verification usage and reads back as `{rt['explanation']}`. "
        f"Same on a design part (`ratDesign` about {rd['about']}).")
    ew = idx.metadata("execWeak")
    row("`metadata execWeak : AnalysisTooling::ToolExecution about weak { toolName; uri; }`",
        "y", "n/a (data)", json.dumps(ew),
        "Attaches to a part. ToolExecution has only toolName and uri: no timestamp, digest or version "
        "(a library gap for evidence provenance).")
    ec = idx.metadata("execChain")
    row("`metadata execChain : AnalysisTooling::ToolExecution about tuned::settlingTime` (feature chain)",
        "y", "n/a (data)", json.dumps(ec),
        "The chain resolves to the anonymous redefining attribute that carries the value (`tuned::@0`), "
        "not to the inherited ADCS::settlingTime declaration.")

    # 13. verify_satisfaction on contradiction
    okc, msgc = satisfy_result(model, "subWeakContra")
    allv = model.verify_satisfaction()
    noise = [v for v in allv if v.error and "no value for feature" in v.error]
    row("`model.verify_satisfaction()` on a deliberately contradicting `satisfy requirement subWeakContra :> req001 by weak;`",
        "y", f"y (holds={okc})", f"{msgc}",
        f"A false claim loads without a diagnostic (as toaster D-021 recorded for 0.9.0) and "
        f"verify_satisfaction evaluates it to holds=False with the failing condition text. Whole-model call returns "
        f"{len(allv)} verdicts, of which {len(noise)} are errors from `verify` objectives with no subject "
        f"('no value for feature adcs'), and {sum(1 for v in allv if 'no requirement to satisfy' in (v.error or ''))} "
        "are the spec-form named satisfies; scope with `symbol_id`.")

    # 14. to_api_json types
    types = idx.types()
    want = ["SatisfyRequirementUsage", "RequirementVerificationMembership", "VerificationCaseUsage",
            "VerificationCaseDefinition", "MetadataUsage", "RequirementUsage", "RequirementDefinition"]
    row("`to_api_json()`: satisfy, verify and metadata elements",
        "y", "n/a", "; ".join(f"{t}={types[t]}" for t in want),
        "satisfy = SatisfyRequirementUsage (isNegated true for `not satisfy`). `verify` is "
        "RequirementVerificationMembership owning an unnamed RequirementUsage. metadata = MetadataUsage "
        "with annotatedElement. Metadata field values are ReferenceUsage -> FeatureValue -> LiteralString "
        "or FeatureReferenceExpression.referent.")

    # extra: model.query visibility
    where = {"@type": "PrimitiveConstraint", "property": "@type", "operator": "=",
             "value": ["SatisfyRequirementUsage", "MetadataUsage", "VerificationCaseUsage", "RequirementUsage"]}
    hits = [(q.id, q.type) for q in model.query(where=where)]
    named = collections.Counter(t for i, t in hits if "::@" not in i)
    anon = collections.Counter(t for i, t in hits if "::@" in i)
    json_anon = [e["qualifiedName"] for e in idx.elements
                 if e.get("qualifiedName", "").endswith("::@1::@0")]
    json_types = {idx.by_qn[q]["@type"] for q in json_anon}
    row("(extra) `model.query()` visibility of satisfy / metadata / verification usages",
        "n/a", "n/a", f"named: {dict(named)}; anonymous: {dict(anon)}",
        "On 0.10.0 model.query() returns every named satisfy and metadata usage, and also the anonymous "
        "ones inside verification defs (toaster D-001/D-015 recorded the opposite on 0.9.0). Mismatch: the "
        f"anonymous `...::@1::@0` elements are SatisfyRequirementUsage in query() but {sorted(json_types)} in "
        "to_api_json().")
    return rows


def main() -> int:
    ev = evidence()
    if not (abs(ev["__BAD_ST__"] - 310.63) < 0.01 and abs(ev["__GOOD_ST__"] - 77.97) < 0.01):
        print(f"FAIL scipy numbers drifted: {ev}")
        return 1
    print(f"Computed evidence: weak settling {ev['__BAD_ST__']:.2f} s, tuned settling {ev['__GOOD_ST__']:.2f} s, "
          f"peak torque {ev['__BAD_PT__']:.4f}/{ev['__GOOD_PT__']:.4f} N*m, limit {ev['__LIMIT__']:.4f} N*m"
          + ("\n" if "--markdown" in sys.argv else ""))
    conn = opensysml.connect(version=VERSION)
    try:
        model = load_model(conn, ev)
        idx = Index(model)
        rows = build_rows(model, idx, ev)
    finally:
        conn.close()
    if "--markdown" in sys.argv:
        print("| construct | parses y/n | evaluates y/n (value) | raw output excerpt | notes |")
        print("|---|---|---|---|---|")
        esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
        for r in rows:
            print("| " + " | ".join(esc(r[k]) for k in ("construct", "parses", "evaluates", "excerpt", "notes")) + " |")
    else:
        for r in rows:
            print(f"[parses {r['parses']} | evaluates {r['evaluates']}] {r['construct']}\n    {r['excerpt']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
