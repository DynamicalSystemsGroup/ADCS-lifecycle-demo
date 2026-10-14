# OpenSysML 0.10.0 probe: findings

What `opensysml==0.10.0` (service `v0.10.0`) parses and evaluates for the pattern
requirement -> evidence -> automated verdict -> human attestation, using standard-library
constructs only. Reproduce with `uv run python sysml/probe/run_probe.py` (add `--markdown` to
regenerate the table below). Model: [`probe.sysml`](probe.sysml). Every value in the table
was produced by that run; the scipy numbers are computed by `analysis.numerical`, written into
the model, and read back through OpenSysML.

Terms follow the project discipline: a verdict from `run_analysis` or `verify_satisfaction` is
**verification** (an automated check). Only a person's `satisfy` is **validation**, and nothing here
changes that.

## Summary for the model author (WP2)

- Verdicts work. `run_analysis('Pkg::caseUsage').verifications[0].kind` returns `fail` / `pass`
  for the two candidates, in both the explicit-inequality and the single-source form. A
  verification with no `return` binding comes back `inconclusive` (detail: "the case body bound no
  VerdictKind value"), not `error`.
- The spec-form named satisfy (`satisfy requirement a : ReqDef by part;`) **parses, is exported and
  takes metadata, but cannot be evaluated** (`no requirement to satisfy`).
- The named satisfy that subsets the usage (`satisfy requirement a :> req001 by part;`) parses,
  keeps a name, takes metadata, **and** evaluates. It was not in the contract; see ESCALATE in the report.
- `StatusInfo`, `Rationale` and `ToolExecution` all load, attach (to a satisfy, a part, a feature chain)
  and read back through `to_api_json()`.
- `model.query()` on 0.10.0 sees satisfy and metadata elements (0.9.0 did not, per toaster D-001/D-015).
  The two exports disagree on the type of the anonymous requirement inside a `verify` (see last row).

## Findings

Computed evidence: weak settling 310.63 s, tuned settling 77.97 s, peak torque 0.0436/0.1000 N*m, limit 0.1000 N*m

| construct | parses y/n | evaluates y/n (value) | raw output excerpt | notes |
|---|---|---|---|---|
| import VerificationCases, ModelingMetadata, AnalysisTooling | y | n/a | diagnostics: 0 | Package-level `private import X::*;` for all three libraries resolves in a single-file load. |
| requirement def with `require constraint { adcs.settlingTime <= 120 [s] }`, usage `req001` | y | y (weak: fails; tuned: holds) | ✗ requirement ProbePkg::req001 fails (on ProbePkg::weak ID: 1): condition evaluated to false: adcs.settlingTime <= 120 [s] — witnessed by run | Unit form `120 [s]` works. `model.verify_requirement(id, subject=part)` evaluates a usage against a concrete part. Bare `adcs` needs `subject=`. |
| candidate parts with `settlingTime` bound to scipy values (Kp=1,Kd=10) and (Kp=4,Kd=30) | y | y (310.63 s, 77.97 s) | model.eval -> Fraction 15531309074792827/50000000000000 | Round-trip equals scipy: weak 310.63, tuned 77.97 (equal: True). `Quantity.magnitude` is a `Fraction`; cast with float(). `eval` of a bare name -> ExecutionError: evaluation failed: unresolved reference: weak — did you mean...; use qualified names. |
| verification def, explicit inequality `PassIf(adcs.settlingTime <= 120 [s])`, `objective { verify req001; }`, `return verdict : VerdictKind` | y | y (weak: fail; tuned: pass) | run_analysis(...).verifications[0].kind = 'fail' / 'pass'; outputs.verdict = VerdictKind::fail | As a usage with `subject = part;` and as a def run with `subject=` (weak: fail) give the same kind. The objective's own verdict reads: `? objective obj (on ProbePkg::weak ID: 1): states no condition to check — witnessed by run`, so the kind comes from the `return` binding only. Verdict-fallback check: model.eval('req001(weak)') -> False, req001(tuned) -> True (type bool). |
| verification def, single source `PassIf(req001(adcs))`, `objective { verify req001; }`, `return verdict : VerdictKind` | y | y (weak: fail; tuned: pass) | run_analysis(...).verifications[0].kind = 'fail' / 'pass'; outputs.verdict = VerdictKind::fail | As a usage with `subject = part;` and as a def run with `subject=` (weak: fail) give the same kind. The objective's own verdict reads: `? objective obj (on ProbePkg::weak ID: 1): states no condition to check — witnessed by run`, so the kind comes from the `return` binding only. Verdict-fallback check: model.eval('req001(weak)') -> False, req001(tuned) -> True (type bool). |
| REQ-004 style: real constraint `peakTorque <= torqueLimit`, verification with no verdict binding | y | y (inconclusive: True) | kind='inconclusive' detail='the case body bound no VerdictKind value'; outputs={} | Not pass/fail/error: `inconclusive`, with a detail string. The requirement itself does hold when evaluated directly (`verify_requirement` -> holds), so inconclusive marks 'no verdict was declared', not 'constraint unmet'. peakTorque tuned 0.1000 N*m vs limit 0.1000 N*m (equal, so the <= holds at the boundary). |
| `satisfy requirement attTuned : SettlingReq by tuned;` (spec form, typed by the requirement def) | y | n (verify_satisfaction: holds=False) | satisfy attTuned by tuned: no requirement to satisfy | Loads clean, appears in to_api_json as SatisfyRequirementUsage and takes metadata, but verify_satisfaction reports an error, not a verdict: the claim is typed by the def and names no requirement usage, which the evaluator takes as 'no requirement to satisfy'. |
| `satisfy requirement subTuned :> req001 by tuned;` (named, subsets the usage) | y | y (holds=True) | verify_satisfaction(ProbePkg::subTuned) -> satisfy req001 by tuned: holds | Not the spec form the contract asked for, but standard SysML. Keeps a name for the claim AND is evaluated. The name is lost in the verdict label (reads `satisfy req001 by tuned`). |
| `not satisfy requirement attWeakNot : SettlingReq by weak;` (spec form) | y | n (holds=False) | not satisfy attWeakNot by weak: no requirement to satisfy | isNegated=True in to_api_json, so the claim is representable; it fails to evaluate for the same reason as the positive spec form. |
| `not satisfy requirement subWeakNot :> req001 by weak;` (subsetting form) | y | y (holds=True) | verify_satisfaction(ProbePkg::subWeakNot) -> not satisfy req001 by weak: holds | A correct negative claim evaluates to holds=True (weak does fail req001). Without a name in the verdict label. |
| `metadata statWeak : ModelingMetadata::StatusInfo about attWeak { originator; status = StatusKind::done; }` | y | n/a (data, read back from to_api_json) | {"type": ["ModelingMetadata::StatusInfo"], "about": ["ProbePkg::attWeak"], "originator": "probe", "status": "ModelingMetadata::StatusKind::done"} | Attaches to a named satisfy (spec form too). Values read back: originator='probe', status='ModelingMetadata::StatusKind::done'. Also attaches to subTuned (['ProbePkg::subTuned']) and to the design part (statDesign about ['ProbePkg::tuned'], status='ModelingMetadata::StatusKind::tbc'). Enum values come back as the literal's qualified name. |
| `metadata ratTuned : ModelingMetadata::Rationale about attTuned { text; explanation = tunedExplicit; }` | y | n/a (data) | {"type": ["ModelingMetadata::Rationale"], "about": ["ProbePkg::attTuned"], "text": "Model adequate for step response; evidence sufficient.", "explanation": "ProbePkg::tunedExplicit"} | `explanation` is a ref to the verification usage and reads back as `ProbePkg::tunedExplicit`. Same on a design part (`ratDesign` about ['ProbePkg::tuned']). |
| `metadata execWeak : AnalysisTooling::ToolExecution about weak { toolName; uri; }` | y | n/a (data) | {"type": ["AnalysisTooling::ToolExecution"], "about": ["ProbePkg::weak"], "toolName": "scipy.integrate.solve_ivp", "uri": "urn:probe:tool:scipy"} | Attaches to a part. ToolExecution has only toolName and uri: no timestamp, digest or version (a library gap for evidence provenance). |
| `metadata execChain : AnalysisTooling::ToolExecution about tuned::settlingTime` (feature chain) | y | n/a (data) | {"type": ["AnalysisTooling::ToolExecution"], "about": ["ProbePkg::tuned::@0"], "toolName": "scipy.integrate.solve_ivp", "uri": "urn:probe:tool:scipy"} | The chain resolves to the anonymous redefining attribute that carries the value (`tuned::@0`), not to the inherited ADCS::settlingTime declaration. |
| `model.verify_satisfaction()` on a deliberately contradicting `satisfy requirement subWeakContra :> req001 by weak;` | y | y (holds=False) | satisfy req001 by weak: adcs.settlingTime <= 120 [s] | A false claim loads without a diagnostic (as toaster D-021 recorded for 0.9.0) and verify_satisfaction evaluates it to holds=False with the failing condition text. Whole-model call returns 9 verdicts, of which 3 are errors from `verify` objectives with no subject ('no value for feature adcs'), and 3 are the spec-form named satisfies; scope with `symbol_id`. |
| `to_api_json()`: satisfy, verify and metadata elements | y | n/a | SatisfyRequirementUsage=6; RequirementVerificationMembership=3; VerificationCaseUsage=5; VerificationCaseDefinition=3; MetadataUsage=7; RequirementUsage=8; RequirementDefinition=2 | satisfy = SatisfyRequirementUsage (isNegated true for `not satisfy`). `verify` is RequirementVerificationMembership owning an unnamed RequirementUsage. metadata = MetadataUsage with annotatedElement. Metadata field values are ReferenceUsage -> FeatureValue -> LiteralString or FeatureReferenceExpression.referent. |
| (extra) `model.query()` visibility of satisfy / metadata / verification usages | n/a | n/a | named: {'RequirementUsage': 2, 'VerificationCaseUsage': 5, 'SatisfyRequirementUsage': 6, 'MetadataUsage': 7}; anonymous: {'RequirementUsage': 3, 'SatisfyRequirementUsage': 3} | On 0.10.0 model.query() returns every named satisfy and metadata usage, and also the anonymous ones inside verification defs (toaster D-001/D-015 recorded the opposite on 0.9.0). Mismatch: the anonymous `...::@1::@0` elements are SatisfyRequirementUsage in query() but ['RequirementUsage'] in to_api_json(). |

Notes on the table:

- Unit form: `120 [s]` works; so does `[N * m]` for torque.
- Subjects: `verify_requirement`, `verify_constraint` and `run_analysis` on a verification *def* need
  `subject=<part>`; a verification *usage* with `subject = part;` needs none.
- `eval` needs qualified names (`ProbePkg::weak.settlingTime`) unless the package is imported; the
  error message says so.
- Numbers: `Quantity.magnitude` is a `Fraction`; cast with `float()`.
- `verify_satisfaction()` with no argument also returns one error verdict per `verify` objective
  inside a verification def (`no value for feature adcs`): those objectives have no subject bound.
  Pass `symbol_id` to scope to one claim.

## Fallbacks

- **Verdict fallback: does not apply.** A `VerdictKind` comes back from the verification case
  (`fail` for the Kp=1, Kd=10 candidate, `pass` for Kp=4, Kd=30). No need to evaluate `req001(design)` via
  `model.eval` outside the case. If it were ever needed, `model.eval('ProbePkg::req001(ProbePkg::weak)')`
  returns a plain `bool` (checked in the explicit-inequality row's notes).
- **Named-satisfy fallback: applies, in part.** The spec-form named satisfy cannot be evaluated by
  `verify_satisfaction`. If the demo must use exactly that form, attach `StatusInfo` and `Rationale` to
  the design part instead: the probe shows this works (`statDesign`, `ratDesign` in the metadata rows),
  and the automated check then runs through `run_analysis` on the verification case. Note the named
  satisfy still loads and takes metadata, so the metadata anchor itself does not fail; only the
  evaluation does. The `:> req001` form is a candidate that avoids the fallback entirely.

## Draft upstream issues

Drafts only; not filed. Section numbers are those used in the toaster repo's DEFERRED.md
(SysML v2 formal/2026-03-02) and were not re-checked against the specification text here.

1. **`satisfy requirement x : ReqDef by part;` is not evaluable.** Spec section 7.19
   (Requirements, SatisfyRequirementUsage). The statement loads with no diagnostic and is exported as
   `SatisfyRequirementUsage`, but `Model.verify_satisfaction()` returns `no requirement to satisfy`
   (holds=False, an error rather than a verdict). The `:> req001` form evaluates. Ask: either evaluate
   the typed form against its own constraint with the subject bound, or emit a diagnostic at load.
2. **A `verify` objective contributes no verdict.** Spec section 7.24 (Verification cases). Inside
   `verification def ... { objective { verify req001; } return verdict : VerdictKind = ...; }` the
   objective's verdict reads `states no condition to check`, and the case's `VerdictKind` comes only from
   the `return` binding. A case without a binding is `inconclusive` even when the verified requirement
   holds when evaluated directly. The library states no roll-up from `requirementVerifications` to the
   verdict. Ask: document this, or offer a way to derive the verdict from the verified requirements.
3. **`verify_satisfaction()` returns an error per `verify` objective.** Spec section 7.24. Whole-model
   calls return `no value for feature adcs` for each verification def's objective, which has no subject
   bound; callers must filter by `symbol_id`. Ask: skip definitions' objectives, or mark them
   `not applicable`.
4. **`model.query()` and `to_api_json()` disagree on the anonymous requirement inside `verify`.** Spec
   section 7.19. The same element is `SatisfyRequirementUsage` in one and `RequirementUsage` in the other
   (see the last table row).
5. **`AnalysisTooling::ToolExecution` carries only `toolName` and `uri`.** The standard library defines no
   slot for a tool version, a timestamp or an input/output digest, so evidence provenance beyond a tool
   name needs prose or commit metadata. This is a library gap for the standards body, not a client bug.
