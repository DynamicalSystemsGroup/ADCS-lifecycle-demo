# Demo model: gaps and workarounds

Gaps the GeoSatADCS model (`satellite.sysml`, `model.py`) works around, with OpenSysML 0.10.0.
Started from the probe's gap list (`sysml/probe/FINDINGS.md`); items marked "new" were found while building the model.

| # | gap | workaround in the demo |
|---|---|---|
| 1 | The standard library has no home for an evidence hash beyond `AnalysisTooling::ToolExecution::uri`, and no timestamp, version or digest field. | The hash goes in `uri = "sha256:<hash>"`. No time is recorded in the model; the commit carries the time. No attribute is invented. |
| 2 | The Flexo SysML v2 service does not persist commit descriptions (ACE-02). | Each Flexo commit is tagged `git-<sha>`; nothing in the model carries the SHA. |
| 3 | `::>` (reference-subsetting) and def-typed named `satisfy` load but are not evaluated: `verify_satisfaction` returns `no requirement to satisfy`. | The attestation uses the usage-subsetting form `satisfy requirement att :> req001 by <design>;` (ACE-01), which evaluates. |
| 4 | A `verify` objective contributes no verdict: a case with no `return` binding is `inconclusive` whether the constraint holds or not. | REQ-001: the case binds `PassIf(req001(adcs))`. REQ-004: no binding, on purpose (ACE-04); `inconclusive` means "no automated verdict was declared", never "borderline". |
| 5 | `verify_satisfaction()` with no argument returns one error per `verify` objective in a verification def (`no value for feature adcs`). | `evaluate` scopes each call to one `att_*` claim by name. |
| 6 | (new) `evaluate` reads verification names, claim names and part names from the model text with regular expressions, not from `to_api_json()`. | Kept small on purpose. A block that does not follow the `vc<N>_<design>`, `att_<design>`, `part <name> : ADCS` shapes is not reported. |
| 7 | (new) `VerificationMethod` takes `VerificationMethodKind::analyze` (the library literals are `inspect`, `analyze`, `demo`, `test`). It parses on both verification defs and does not change the verdicts. Nothing evaluates it. | Used as documentation only. |
| 8 | (new) REQ-001's text mentions pointing accuracy (0.1 degrees, 3-sigma) as well as 120 s, but the simulation yields a settling time only. | The `doc` is verbatim from `structural/satellite.ttl`. The `require constraint` encodes only the 120 s clause. A pass means "settling time within 120 s in this model", not the full text; the human judges the rest. |
| 9 | (new) The tuned design's peak torque equals the limit because `analysis/numerical.py` clips torque with `np.clip`. | REQ-004's constraint holds only as a model artefact. The adequacy `Rationale` on each design says so, and the verification stays `inconclusive` (ACE-04). |
| 10 | (new) `Quantity.magnitude` is a `Fraction`. | `evaluate` returns floats and plain bools only. |
| 11 | (new) The two exports disagree on the anonymous requirement inside `verify` (`SatisfyRequirementUsage` in `query()`, `RequirementUsage` in `to_api_json()`). | Not used by the model. |
