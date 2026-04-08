# ADCS Lifecycle Demo

## What this is

A demonstration of bidirectional requirements traceability for a satellite Attitude Determination and Control System (ADCS). The demo traces the full lifecycle from SysMLv2 structural specification through symbolic analysis (SymPy), numerical simulation (scipy), and human expert attestation — with all traceability stored as RDF and all artifacts version-controlled in git.

## Core principle

**Evidence does not verify requirements; evidence supports a human judgment that requirements are satisfied.** Models are imperfect representations of physical systems. The engineer judges model adequacy and evidence sufficiency. Only human attestation connects evidence to requirement satisfaction.

## Architecture

Three-layer ontology:
- **Layer 1 (W3C):** PROV-O for provenance, Dublin Core for metadata
- **Layer 2 (SysMLv2):** Structural model, requirements, satisfy relationships
- **Layer 3 (RTM):** Evidence, attestation, traceability (custom `rtm:` namespace)

## Key directories

- `ontology/` — OWL TBox (rtm.ttl) and namespace constants (prefixes.py)
- `structural/` — SysMLv2 RDF model (satellite.ttl, parameters.ttl)
- `analysis/` — SymPy symbolic analysis + scipy numerical simulation
- `evidence/` — Content hashing and RDF evidence binding
- `traceability/` — RTM assembly, SPARQL queries, human attestation
- `pipeline/` — Stage orchestrator (stages 1-8)
- `interrogate/` — Visualization, explanation chains, reproducibility checks

## Toolchain

- Python 3.12+, managed by uv
- rdflib for RDF/SPARQL, sympy for symbolic math, scipy for ODE integration
- ProofScript/ProofBuilder pattern reimplemented from gds-proof (self-contained)

## Running

```bash
uv run python -m pipeline.runner
```

## Tests

```bash
uv run pytest
```
