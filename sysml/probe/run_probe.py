"""Probe which SysML v2 standard-library constructs OpenSysML 0.10.0 parses and evaluates
for the pattern: requirement -> evidence -> automated verdict -> human attestation.

Run:  uv run python sysml/probe/run_probe.py [--markdown]

Evidence numbers come from the scipy step response (analysis.numerical), are written into
probe.sysml, and are read back through OpenSysML. Nothing is typed in by hand.
Exit 0 when the probe ran to the end, whatever each construct did. Exit 1 only if the
scipy numbers (settling time, peak torque, limit) drift from the expected values or the service is unreachable.
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
        "__OVER_PT__": 1.5 * base["maxTorque"],
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


def satisfy_result(model, scope: str) -> tuple[bool, str, str]:
    """(holds, error, label) of the single satisfy verdict in `scope` (a name or a package)."""
    v = model.verify_satisfaction(scope)[0]
    return v.holds, v.error, v.error or f"{v.element}: {v.condition or ('holds' if v.holds else 'fails')}"


YN = "ny"  # index with int(bool); every parses/evaluates cell is derived, never typed


def yn(flag: bool) -> str:
    return YN[int(flag)]


def sat_cell(holds: bool, error: str) -> str:
    """evaluates cell for a satisfy: evaluated iff the service returned a verdict, not an error."""
    return f"{yn(not error)} (holds={holds})" + (f"; error: {error}" if error else "")


def build_rows(model, idx: Index, ev: dict[str, float]) -> list[dict]:
    rows: list[dict] = []
    clean = not model.diagnostics

    def present(*names: str, kind: str | None = None) -> bool:
        """Parses = no load diagnostics AND each element is in the export (with the expected @type)."""
        return clean and all(P + n in idx.by_qn and (kind is None or idx.by_qn[P + n]["@type"] == kind)
                             for n in names)

    def row(construct, parses, evaluates, excerpt, notes):
        rows.append(dict(construct=construct, parses=parses, evaluates=evaluates,
                         excerpt=excerpt, notes=notes))

    # 0. evidence, computed
    row("evidence computed by `analysis.numerical.run_step_response` (Kp=1,Kd=10 and Kp=4,Kd=30)",
        "n/a", "n/a",
        f"weak settling {ev['__BAD_ST__']:.2f} s, tuned settling {ev['__GOOD_ST__']:.2f} s; "
        f"peak torque weak {ev['__BAD_PT__']:.4f}, tuned {ev['__GOOD_PT__']:.4f} N*m; limit {ev['__LIMIT__']:.4f} N*m",
        "Values are computed on every run, written into `probe.sysml` and read back below. The run "
        "stops with exit 1 if settling or torque numbers drift from the expected ones.")

    # 1. imports
    row("import VerificationCases, ModelingMetadata, AnalysisTooling",
        yn(clean), "n/a", f"diagnostics: {len(model.diagnostics)}",
        "Package-level `private import X::*;` for all three libraries resolves in a single-file load.")

    # 2. requirement def + usage
    weak_r = model.verify_requirement(P + "req001", subject=P + "weak")
    tuned_r = model.verify_requirement(P + "req001", subject=P + "tuned")
    row("requirement def with `require constraint { adcs.settlingTime <= 120 [s] }`, usage `req001`",
        yn(present("SettlingReq", kind="RequirementDefinition") and present("req001", kind="RequirementUsage")),
        f"{yn(not (weak_r.error or tuned_r.error))} (weak: {'holds' if weak_r.holds else 'fails'}; "
        f"tuned: {'holds' if tuned_r.holds else 'fails'})",
        str(weak_r),
        "Unit form `120 [s]` works. `model.verify_requirement(id, subject=part)` evaluates a usage against a "
        "concrete part. Bare `adcs` needs `subject=`.")

    # 3. candidate values
    wv = model.eval(P + "weak.settlingTime")
    gv = model.eval(P + "tuned.settlingTime")
    wf, gf = float(wv.magnitude), float(gv.magnitude)
    try:
        model.eval("weak.settlingTime")
        bare = "evaluated"
    except Exception as e:  # noqa: BLE001
        bare = f"{type(e).__name__}"
    row("candidate parts with `settlingTime` bound to scipy values (Kp=1,Kd=10) and (Kp=4,Kd=30)",
        yn(present("weak", "tuned", kind="PartUsage")),
        f"{yn(wf == ev['__BAD_ST__'] and gf == ev['__GOOD_ST__'])} ({wf:.2f} s, {gf:.2f} s)",
        f"model.eval -> Quantity, magnitude type {type(wv.magnitude).__name__}, as decimals {wf:.4f} and {gf:.4f}",
        f"Round-trip equals scipy exactly: weak {wf == ev['__BAD_ST__']}, tuned {gf == ev['__GOOD_ST__']}. "
        f"`Quantity.magnitude` is a `{type(wv.magnitude).__name__}`; cast with float(). `eval` of a bare name "
        f"({bare}) fails unless the package is imported; use qualified names.")

    # 4/5. verification forms, differentiated
    for label, case, extra in (
            ("explicit inequality `PassIf(adcs.settlingTime <= 120 [s])`", "Explicit", "explicit"),
            ("single source `PassIf(req001(adcs))`", "Single", "single")):
        kw, _, rw = verdict_kind(model, f"weak{case}")
        kt, _, rt = verdict_kind(model, f"tuned{case}")
        kd, _, _ = verdict_kind(model, f"SettlingCheck{case}", "weak")
        ok = (kw, kt) == ("fail", "pass")
        ev_w = model.eval(f"{P}req001({P}weak)")
        ev_t = model.eval(f"{P}req001({P}tuned)")
        evaluated = kw in ("pass", "fail") and kt in ("pass", "fail")
        if extra == "explicit":
            excerpt = (f"kinds weak={kw!r}, tuned={kt!r}; outputs.verdict = {rw.outputs['verdict'].name} / "
                       f"{rt.outputs['verdict'].name}")
            notes = ("The inequality is typed a second time inside the case, so the verdict does not read "
                     "`req001`; the two can drift apart. "
                     f"Run as a def with `subject=` (weak) gives the same kind: {kd}.")
        else:
            excerpt = (f"kinds weak={kw!r}, tuned={kt!r}; model.eval('req001(weak)') -> {ev_w!r}, "
                       f"req001(tuned) -> {ev_t!r} ({type(ev_w).__name__})")
            notes = ("The verdict is computed from `req001` itself (one source of truth). Same kinds as the "
                     f"explicit form (as a def with `subject=`, weak: {kd}). `model.eval` of the requirement "
                     "gives the same truth value outside the case, which is the verdict fallback.")
        row(f"verification def, {label}, `objective {{ verify req001; }}`, `return verdict : VerdictKind`",
            yn(present(f"weak{case}", f"tuned{case}", kind="VerificationCaseUsage")),
            f"{yn(evaluated)} (weak: {kw}; tuned: {kt})" + ("" if ok else " UNEXPECTED"),
            excerpt, notes)
    obj_text = rw.verdicts[0].explain()
    row("the `objective { verify req001; }` verdict on its own",
        "n/a", f"{yn('no condition' not in obj_text)} (value: {obj_text.split(' — ')[0].split('): ')[-1]})", obj_text,
        "The objective states no condition to check, so the case's `VerdictKind` comes only from the "
        "`return` binding, not from the verified requirement.")

    # 6. REQ-004 style, no verdict binding: tuned (peak == limit) and over (peak > limit)
    for subj, desc in (("tuned", "tuned design (peak torque equals the limit)"),
                       ("over", "synthetic subject whose peak torque exceeds the limit")):
        k, detail, r4 = verdict_kind(model, f"{subj}Torque")
        vr = model.verify_requirement(P + "req004", subject=P + subj)
        ev4 = model.eval(f"{P}req004({P}{subj})")
        pt = model.eval(f"{P}{subj}.peakTorque")
        row(f"REQ-004 style: `peakTorque <= torqueLimit`, verification with no verdict binding, {desc}",
            yn(present("req004", f"{subj}Torque")),
            f"{yn(k in ('pass', 'fail'))} (kind={k}); req004({subj}) = {ev4}",
            f"kind={k!r} detail={detail!r}; outputs={r4.outputs}; verify_requirement "
            f"{'holds' if vr.holds else 'fails'}; peakTorque {float(pt.magnitude):.4f} vs limit {ev['__LIMIT__']:.4f} N*m",
            "`inconclusive` means no `VerdictKind` was bound by the case, not a measured borderline; it is the "
            "same for a holding and a violated constraint. "
            + ("The tuned design's peak torque equals the limit because `analysis/numerical.py` clips torque "
               f"(`np.clip`) at the actuator limit (equal: {ev['__GOOD_PT__'] == ev['__LIMIT__']}), so the "
               "`<=` holds at saturation as a model artefact (ACE-04)." if subj == "tuned" else
               "This subject is hand-built for the probe: the simulation cannot produce it, since it clips torque. "
               "The direct evaluation turns False while the case verdict does not change."))

    # 7. named satisfy forms
    forms = (
        ("def-typed named satisfy `satisfy requirement attTuned : SettlingReq by tuned;`",
         "attTuned", "attTuned", "Typed by the requirement def, so it never mentions the `req001` usage."),
        ("usage-subsetting named satisfy `satisfy requirement subTuned :> req001 by tuned;` (ACE-01 choice)",
         "subTuned", "subTuned", "Names the claim, traces to the `req001` usage and is evaluated; this is why "
         "ACE-01 chose it as the attestation form. The verdict label drops the name."),
        ("reference-subsetting named satisfy `satisfy requirement refTuned ::> req001 by tuned;`",
         "refTuned", "refTuned", "Parses and is exported; compare its evaluation with the `:>` form."),
    )
    for label, name, scope, note in forms:
        h, err, msg = satisfy_result(model, P + scope)
        row(label, yn(present(name, kind="SatisfyRequirementUsage")), sat_cell(h, err), msg,
            f"{note} Evaluator: {'error, no verdict' if err else 'returned a verdict'}.")
    h, err, msg = satisfy_result(model, P + "UnnamedScope")
    row("unnamed satisfy `satisfy req001 by tuned;`",
        yn(clean and any(e["@type"] == "SatisfyRequirementUsage" and e["qualifiedName"].startswith(P + "UnnamedScope::")
                         for e in idx.elements)),
        sat_cell(h, err), msg,
        "Evaluates like the usage-subsetting form but has no name, so StatusInfo and Rationale have nothing "
        "to hang on except by position. Scoped here via an enclosing package, since an anonymous element has "
        "no usable `symbol_id`.")

    # 8. not satisfy
    for label, name in (("`not satisfy requirement attWeakNot : SettlingReq by weak;` (def-typed)", "attWeakNot"),
                        ("`not satisfy requirement subWeakNot :> req001 by weak;` (usage-subsetting)", "subWeakNot")):
        h, err, msg = satisfy_result(model, P + name)
        neg = idx.by_qn.get(P + name, {}).get("isNegated")
        row(label, yn(present(name, kind="SatisfyRequirementUsage") and bool(neg)), sat_cell(h, err), msg,
            f"isNegated={neg} in to_api_json, so the claim is representable. "
            + ("A correct negative claim (weak does fail req001) evaluates to holds=True." if not err else
               "Same evaluation failure as the positive def-typed form."))

    # 9-12. metadata
    sw, st, sd = idx.metadata("statWeak"), idx.metadata("statTuned"), idx.metadata("statDesign")
    row("`metadata statWeak : ModelingMetadata::StatusInfo about attWeak { originator; status = StatusKind::done; }`",
        yn(present("statWeak", "statTuned", "statDesign", kind="MetadataUsage")),
        "n/a (data, read back from to_api_json)", json.dumps(sw),
        f"Attaches to a def-typed named satisfy. Values read back: originator={sw['originator']!r}, "
        f"status={sw['status']!r}. Also attaches to subTuned ({st['about']}) and to the design part "
        f"(statDesign about {sd['about']}, status={sd['status']!r}). Enum values come back as "
        "the literal's qualified name.")
    rt, rd = idx.metadata("ratTuned"), idx.metadata("ratDesign")
    row("`metadata ratTuned : ModelingMetadata::Rationale about attTuned { text; explanation = tunedExplicit; }`",
        yn(present("ratTuned", "ratDesign", kind="MetadataUsage")), "n/a (data)", json.dumps(rt),
        f"`explanation` is a ref to the verification usage and reads back as `{rt['explanation']}`. "
        f"Same on a design part (`ratDesign` about {rd['about']}).")
    ew = idx.metadata("execWeak")
    row("`metadata execWeak : AnalysisTooling::ToolExecution about weak { toolName; uri; }`",
        yn(present("execWeak", kind="MetadataUsage")), "n/a (data)", json.dumps(ew),
        f"Attaches to a part. Fields present on read-back: {sorted(k for k in ew if k not in ('type', 'about'))}; "
        "the library defines no version, digest or time (a gap for evidence provenance).")
    ec = idx.metadata("execChain")
    row("`metadata execChain : AnalysisTooling::ToolExecution about tuned::settlingTime` (feature chain)",
        yn(present("execChain", kind="MetadataUsage")), "n/a (data)", json.dumps(ec),
        f"The chain resolves to `{ec['about'][0]}`, the anonymous redefining attribute that carries the "
        "value, not the inherited ADCS::settlingTime declaration.")

    # 13. verify_satisfaction on contradiction
    okc, errc, msgc = satisfy_result(model, P + "subWeakContra")
    allv = model.verify_satisfaction()
    noise = [v for v in allv if v.error and "no value for feature" in v.error]
    nreq = sum(1 for v in allv if "no requirement to satisfy" in (v.error or ""))
    row("`model.verify_satisfaction()` on a deliberately contradicting `satisfy requirement subWeakContra :> req001 by weak;`",
        yn(present("subWeakContra", kind="SatisfyRequirementUsage")), sat_cell(okc, errc), msgc,
        f"A false claim loads without a diagnostic (as toaster D-021 recorded for 0.9.0) and "
        f"verify_satisfaction evaluates it to holds=False with the failing condition text. Whole-model call "
        f"returns {len(allv)} verdicts: {len(noise)} are errors from objectives with no subject "
        f"('no value for feature adcs') and {nreq} are 'no requirement to satisfy' (def-typed and "
        "reference-subsetting named satisfies); scope with `symbol_id`.")

    # 14. to_api_json types
    types = idx.types()
    want = ["SatisfyRequirementUsage", "RequirementVerificationMembership", "VerificationCaseUsage",
            "VerificationCaseDefinition", "MetadataUsage", "RequirementUsage", "RequirementDefinition"]
    row("`to_api_json()`: satisfy, verify and metadata elements",
        yn(all(types[t] for t in want)), "n/a", "; ".join(f"{t}={types[t]}" for t in want),
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


def drifted(ev: dict[str, float]) -> bool:
    """True if the scipy numbers differ from the ones this probe was written against."""
    want = {"__BAD_ST__": (310.63, 0.01), "__GOOD_ST__": (77.97, 0.01),
            "__BAD_PT__": (0.0436, 0.00005), "__GOOD_PT__": (0.1000, 0.00005), "__LIMIT__": (0.1000, 0.00005)}
    return any(abs(ev[k] - v) >= tol for k, (v, tol) in want.items())


def main() -> int:
    ev = evidence()
    if drifted(ev):
        print(f"FAIL scipy numbers drifted: {ev}")
        return 1
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
