# ADCS Lifecycle Demo

## What this is

A demonstration of bidirectional requirements traceability for a satellite
Attitude Determination and Control System (ADCS). The demo traces the full
lifecycle from SysMLv2 structural specification through symbolic analysis
(SymPy), numerical simulation (scipy), and human expert attestation — with
all traceability stored as RDF in a named-graph quadstore and all artifacts
version-controlled in git.

## Core principle

**Evidence does not verify requirements; evidence supports a human judgment
that requirements are satisfied.** Models are imperfect representations of
physical systems. The engineer judges model adequacy and evidence sufficiency.
Only human attestation connects evidence to requirement satisfaction.

This split is the Hawkins–Habli Assurance Claim Point categorization:
adequacy is a `gsn:Assumption`, sufficiency is a `gsn:Justification`. The
project's `rtm:` namespace introduces NO novel epistemic vocabulary.

## Architecture — integration ontology

`rtm:` is a thin application/integration ontology. Convenience classes and
properties are subclasses / subproperties of established standards; the
project's contribution is the assembly, not new terms.

| Namespace                            | Role                                             |
| ------------------------------------ | ------------------------------------------------ |
| `prov:`                              | Provenance spine                                 |
| `sysml:` ↔ `omg-sysml:`              | SysMLv2; local prefix aliased to openCAESAR     |
| `earl:`                              | Assertion + outcome lattice + mode               |
| `gsn:` (OntoGSN)                     | Goal / Strategy / Solution / Assumption / Justification |
| `p-plan:`                            | Process model (one Step per pipeline stage)      |
| `oslc_rm:` / `oslc_qm:`              | Tool-interop aliases for RM tools                |
| `sh:`                                | SHACL closure-rule suite                         |

## Named-graph layout (rdflib.Dataset)

The runtime is `Dataset(default_union=True)` so SPARQL queries match across
named graphs without `GRAPH` clauses. Each layer lives in its own graph,
sized to match Flexo MMS branch conventions:

```text
<rtm:ontology>        TBox + shapes + individuals
<rtm:plan>            P-PLAN process model
<adcs:structural>     SysMLv2 instance data
<adcs:context>        Stable gsn:Context / gsn:Assumption individuals
<adcs:evidence>       rtm:Evidence artifacts
<adcs:attestations>   rtm:Attestation events
<adcs:plan-execution> p-plan:Activity instances (one per stage)
<adcs:audit>          Forward/backward/bidirectional audit summary
```

IRIs and the `NAMED_GRAPHS` dict are in [`ontology/prefixes.py`](ontology/prefixes.py).

## Key directories

- `ontology/` — `rtm-edit.ttl` (source), `rtm.ttl` (built artifact),
  `rtm_shapes.ttl` (closure-rule suite), `rtm_individuals.ttl`,
  `sysml_term_map.csv`, `assembly_manifest.json`, `imports/` (vendored upstreams)
- `structural/` — SysMLv2 RDF model
- `analysis/` — SymPy symbolic analysis + scipy numerical simulation
- `compute/` — `LocalCompute` (in-process) + `DockerCompute` (containerized
  remote-emulation with PROV provenance capture) + `Dockerfile`
- `evidence/` — content hashing + RDF evidence binding (with execution metadata)
- `traceability/` — RTM assembly, SPARQL queries, attestation (GSN-based),
  closure-rule validation, audit module
- `pipeline/` — stage orchestrator, `dataset.py` (named-graph helpers),
  `stage0_assembly.py`, `plan.ttl`, `backends/` (Local / Flexo / Fuseki)
- `flexo/` — Flexo MMS provisioning scripts + integration docs
- `interrogate/` — explain / reproduce / visualize
- `scripts/` — `fetch_imports.py`, `build_ontology.py`
- `tests/` — 166 tests (alignment, named graphs, shape suite, audit,
  backends, compute, live Flexo opt-in)

## Pipeline (stages 0–8)

Stage 0 narrates the ontology assembly; Stage 6.5 runs the closure-rule
suite; Stage 7a runs the audit. Every stage emits a `p-plan:Activity`
into `<adcs:plan-execution>` so the construction process is itself
queryable.

## Toolchain

- Python 3.12+, managed by `uv` — required
- `rdflib` for RDF/SPARQL, `sympy` for symbolic math, `scipy` for ODE integration
- `pyshacl` for closure-rule validation, `httpx` for backend HTTP
- ProofScript/ProofBuilder pattern reimplemented from gds-proof
- Docker — optional, for `--compute=docker`
- OBO ROBOT (Java) — optional, for `make ontology-robot`

## Running

```bash
uv run python -m pipeline.runner --auto            # local backend, local compute
uv run python -m pipeline.runner --auto --backend=flexo   # push to Flexo MMS
uv run python -m pipeline.runner --auto --compute=docker  # remote-compute emulation
```

## Tests

```bash
uv run pytest                       # 166 tests
uv run pytest -m "not live"         # skip Flexo live tests (already auto-skip)
```

## Ontology rebuild

```bash
make ontology                       # Python build (default; no Java needed)
make ontology-robot                 # ROBOT merge + ELK reason + report
```

`rtm.ttl` is a built artifact. Edit `rtm-edit.ttl` and rebuild.
