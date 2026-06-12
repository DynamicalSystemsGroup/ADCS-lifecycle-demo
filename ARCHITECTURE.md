# ADCS Lifecycle Demo — Architecture

This document is the **first read** for a new collaborator. It
describes the three-remote (now four-service) architecture WP4 makes
real, the URI scheme that links them, and the trust queries that
operationalize "how can I trust this evidence?"

If you only have time for the demo's value prop, watch the marimo
notebook (`notebook.py`, rendered to `output/notebook.html` after a
pipeline run). This file is the architectural complement.

## The three remotes — and the fourth service

| Surface | Holds | URI shape |
| --- | --- | --- |
| **git** (`DynamicalSystemsGroup/ADCS-lifecycle-demo`) | code, ontology, Dockerfile, structural model | `git+https://github.com/.../@<sha>#<path>` |
| **Flexo** (Planetary Utilities hosted) | RDF named graphs incl. `rtm:DockerImage` records | `urn:adcs:flexo:<org>/<repo>/<branch>` |
| **local Docker** | image (static recipe) + container (transient materialization) | image: `urn:adcs:docker-image:<digest>` · container: `urn:adcs:docker-container:<container-id>` · host: `urn:adcs:location:docker:<host>` |
| **transaction-log store** (CouchDB, fourth service) | per-invocation wire-log JSON documents | `urn:adcs:service:transaction-log-store` |

The three-remote story (git + Flexo + local Docker) describes where
the evidence's source-of-truth, witness, and runtime live. The fourth
service (txnlog) records the wire-level service-invocation history —
the audit trail beneath the trail.

## Image vs. container vs. host

A common conflation worth flattening up-front:

- **Image** — static, content-addressed by runtime digest, shared
  across runs. RDF: `rtm:DockerImage` (subclass of `prov:Entity`).
- **Container** — transient materialization; identity = container-id;
  one per run. RDF: `rtm:DockerContainer` (subclass of `prov:Entity`).
- **Host** — the physical/virtual machine the container ran on.
  RDF: `prov:Location`.

Standard PROV edges link them:

```
<container> prov:wasDerivedFrom <image>     (materialization)
<activity>  prov:used            <container> (what runtime executed me)
<activity>  prov:atLocation      <host>      (where I physically ran)
<activity>  prov:wasAssociatedWith <executor> (the agent that drove it)
```

## Organizational auspices

Auspices are **per substrate** — each service/host node carries
`rtm:operatedBy` the org that actually operates it, modelled with
`prov:Organization` (no FOAF, no Org Ontology — those stay deferred
per CLAUDE.md future-work #2):

| Substrate | Env vars | Predicate | Subject → Object |
| --- | --- | --- | --- |
| Compute (operating) | `ADCS_OPERATING_ORG_*` | `prov:actedOnBehalfOf` | executor → org |
| Compute (operating) | `ADCS_OPERATING_ORG_*` | `prov:wasAttributedTo` | container → org |
| Compute (hosting) | `ADCS_HOSTING_ORG_*` | `rtm:operatedBy` (subPropertyOf prov:wasAttributedTo) | compute host → org |
| Flexo MMS | `ADCS_FLEXO_HOSTING_ORG_*` | `rtm:operatedBy` | `urn:adcs:service:flexo-mms` → org |
| Txnlog store | `ADCS_TXNLOG_HOSTING_ORG_*` | `rtm:operatedBy` | `urn:adcs:service:transaction-log-store` → org |

Compute operating + hosting default to `urn:adcs:org:local-operator`
(hosting falls back to operating). Set
`ADCS_FLEXO_HOSTING_ORG_IRI=urn:adcs:org:planetary-utilities` to record
that PU operates the Starforge Flexo substrate; the local machine's
location node keeps the compute-substrate org. Unset Flexo auspices =
unknown: the service node is emitted without an `rtm:operatedBy` edge.
The txnlog substrate defaults to the compute-substrate hosting org
(the demo's CouchDB runs locally). NOTE: `FLEXO_ORG` is the Flexo MMS
org *slug* (a REST path segment), unrelated to these auspices IRIs.

## End-to-end provenance chain

A query "how can I trust this evidence?" walks the full chain:

```
<evidence-node>
  prov:wasGeneratedBy  <activity>

<activity>
  prov:used                <container>           — runtime env
  prov:atLocation          <host>                — hardware
  prov:wasAssociatedWith   <executor>            — agent
  prov:startedAtTime/endedAtTime

<container>  (urn:adcs:docker-container:<id>)
  prov:wasDerivedFrom      <image>               — recipe → instance
  prov:wasAttributedTo     <operating-org>       — who runs it
  rtm:containerId          "<id>"

<host>  (urn:adcs:location:docker:<host>)
  rtm:operatedBy           <hosting-org>         — who hosts it

<executor>  (urn:adcs:executor:<id>)
  prov:actedOnBehalfOf     <operating-org>

<image>  (urn:adcs:docker-image:<digest>)
  rtm:contentHash          "sha256:..."          — runtime digest
  rtm:dockerfileHash       "<hash>"
  rtm:buildContextHash     "<hash>"
  rtm:gitRef               <git+https://.../@<sha>#compute/Dockerfile>
  rtm:flexoRecord          <urn:adcs:flexo:.../evidence>

<urn:adcs:flexo:.../evidence>
  prov:atLocation          <urn:adcs:service:flexo-mms>

<urn:adcs:service:flexo-mms>  (prov:Location)
  rtm:operatedBy           <flexo-hosting-org>   — who hosts the Flexo
```

`traceability/queries.py` exposes seven typed trust queries that walk
this graph:

1. `technical_provenance(ds, evidence_iri)` — full chain in one row
2. `reproducibility_witnesses(ds, image_iri)` — every `rtm:DigestMatchAssertion` for this image
3. `closure_witnesses(ds, graph_iri)` — SHACL closure outcomes
4. `auspices_chain(ds, evidence_iri)` — operating + hosting orgs
5. `service_invocations_for(ds)` — wire-level activity rows
6. `service_auspices(ds)` — per-service `rtm:operatedBy` rows
7. `trust_summary(ds, evidence_iri)` — composes 1–6 into `TrustSummary`

`render_trust_summary()` produces the text panel for
`interrogate.explain`.

## EARL-wrapped verification outcomes

Automated checks are first-class RDF, beside the human-attestation
witness:

- `rtm:ClosureRuleAssertion` — Stage 6.5 SHACL outcome (one per run)
- `rtm:DigestMatchAssertion` — `compute.reproduce` rebuild outcome

Both subclass `earl:Assertion` + `prov:Activity`. `earl:mode` is
always `earl:automatic` — verification (not validation). Human
attestation continues to use `earl:manual` / `earl:semiAuto`.

## Service-invocation events (wire-level trail)

Every cross-process / cross-network service call (Flexo HTTP, Docker
subprocess, reproduce subprocess) is recorded as evidence about
evidence. The activity is a `prov:Activity` with `rtm:transactionId`;
the wire-log document is an `rtm:Evidence` with `rtm:contentHash` +
`rtm:documentRef` pointing into the txnlog store.

Sensitive headers (`Authorization`, `Cookie`, etc.) and body keys
(`password`, `token`, etc.) are replaced with `<REDACTED>` before
the JSON document is PUT to the store.

## Reproducibility loop

`compute.reproduce` closes the trust loop:

1. Read an `rtm:DockerImage` record (from local TriG or Flexo)
2. Extract `rtm:gitRef` + `rtm:contentHash`
3. `git clone` the recorded ref in a temp worktree
4. `docker build` from `compute/Dockerfile`
5. Compare resulting digest to recorded `rtm:contentHash`
6. Emit `rtm:DigestMatchAssertion` (`earl:passed` / `earl:failed`)

```bash
uv run python -m compute.reproduce \
    --image-digest sha256:71a59f23... \
    --from-trig output/rtm.trig
```

Exit codes: 0 match, 1 mismatch, 2 prerequisite failure.

## Preflight gate

Before Stage 0 the runner probes all configured backends and
fail-fasts (exit code 2) on any failure. This matches WP2's
ROBOT-default fail-fast discipline: the integration story does not
silently degrade when a remote is down.

- `StoreBackend.probe()` — Flexo HEAD `/orgs/<org>` / Fuseki HEAD
  `/data` / LocalBackend tests output dir writability
- `ComputeBackend.probe()` — LocalCompute no-op; DockerCompute calls
  `docker info`
- `TxnLogBackend.probe()` — HEAD the db; create on 404; surface auth

The probe runs in single-digit seconds; the actual work happens after.

## Companion issues (future work)

- [#7](https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo/issues/7) — registry coordination with Planetary Utilities
- [#8](https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo/issues/8) — externally-hosted RIME services (rime-backend-demo cross-link)
- [#9](https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo/issues/9) — reusable oracles in Starforge
