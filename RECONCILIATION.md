# Slide-language reconciliation

WP5 end-of-roadmap deliverable. Maps every claim in the live deck to
the code receipt that backs it. The reconciliation is **disposable**
after the next deck — it exists so a reviewer can verify that the
talking points line up with the codebase, then it gets replaced when
the deck changes.

Currently-tracked deck: `openbee_dsg_opener.pptx` (May 22 2026
OpenMBEE Flexo/SysMLv2 Dev Meeting).

## Slide 1 — Opening

Claims are organizational (DSG team, R&D firm, etc.); not code-backed.

## Slide 2 — Thesis

Claims about the problem space (engineering loopy / institutions
linear / RTM impedance mismatch / canonical RIME project). Not
code-backed — these are framing. The demo as a whole is the
counter-argument that traceability + auditable evidence can bridge
the gap.

## Slide 3 — Layers (research → practice)

Software-supply-chain-as-stack picture. Not directly code-backed.

## Slide 4 — Ecosystem

Vendor-neutral spines + MOSA. The demo is the existence proof; no
specific claim to reconcile.

## Slide 5 — Agenda / Demo #1

> **Demo #1**: Flexo Deployment, oracles & evidence reproducibility
> with git hashes and docker.

This is the load-bearing slide for reconciliation. Each phrase below
maps to its code receipt:

### "Flexo Deployment"

- `pipeline/backends/flexo.py` — full FlexoBackend implementation;
  HEAD-then-PUT idempotency; pre-issued token + login flow auth.
- `FlexoBackend.probe()` (WP4 c1) — preflight verifies reachability
  + auth before Stage 0.
- `tools/start-services.sh` (WP4 c15) — the *other* hosted service
  (CouchDB txnlog) brought up with one command.
- `.env.example` (WP4 c16) — every `FLEXO_*` env var documented.
- Live test: `tests/test_flexo_live.py` — opt-in
  `@pytest.mark.live` round-trip.

### "oracles"

- Two oracles are exercised in the demo (the symbolic + numerical
  analysis engines): `analysis/symbolic.py` (SymPy), `analysis/numerical.py`
  (scipy). These produce evidence (`rtm:ProofArtifact`,
  `rtm:SimulationResult`).
- A reusable-oracle ecosystem is future work — tracked in
  [#9](https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo/issues/9)
  (Starforge oracle catalog).
- Notebook Acts 9–10 narrate the oracle invocations.

### "evidence reproducibility with git hashes and docker"

The most-concrete slide claim. Four code receipts:

1. **Git hashes** — every `rtm:DockerImage` carries `rtm:gitRef`
   pointing at `compute/Dockerfile` at the build commit. Captured
   by `compute/git_ref.py` (WP4 c3); emitted by
   `DockerCompute._emit_image_node` (WP3 + WP4 c3).
2. **Docker** — `compute/docker_compute.py` runs each analysis
   stage in an `adcs-compute:latest` container; container ID +
   image digest captured into RDF.
3. **Reproducibility** — `compute/reproduce.py` (WP4 c9) closes the
   loop: rebuild the image at the recorded git ref + digest-compare.
   Outcome lands as `rtm:DigestMatchAssertion` (earl:passed/failed).
4. **Hash chain** — `evidence/hashing.py::hash_docker_image` computes
   Dockerfile + build-context hashes (WP3) so the *recipe*'s content
   is verifiable independently of the *runtime* digest.

### "with git hashes and docker" — extended (WP4 deliverable)

The slide claim has been *exceeded* by WP4. Beyond what the slide
promised:

- **Container as a first-class entity** (`rtm:DockerContainer`) —
  distinct from the image (static) and the host (location). The
  audit can answer "how many containers were spawned from this
  image?" via standard PROV traversal.
- **Organizational auspices** (`prov:wasAttributedTo` /
  `rtm:operatedBy` / `prov:actedOnBehalfOf`) — the demo models
  "under whose authority did this run happen?" alongside
  "on what machine."
- **Wire-level audit trail** — every service invocation can be
  recorded in the CouchDB txnlog store via `TransactionLogger`
  (opt-in via `ADCS_TXNLOG_ENABLED=1`).
- **Six trust queries** in `traceability/queries.py` operationalize
  "how can I trust this evidence?" as queryable SPARQL.

## Outcome

Every slide claim has a receipt. The deck's framing of "Demo #1"
is honest with respect to the merged staging branch (post-WP4 + WP5).

## Companion future-work tracking

The path from this demo to a Starforge-resident production
substrate is tracked in three companion issues, intentionally
co-authored for the Planetary Utilities team to read as a set:

- [#7](https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo/issues/7) — Docker registry coordination (locked WP4 decision: build local; PU hosts registry as future enabler)
- [#8](https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo/issues/8) — externally-hosted RIME services (with @rororowyourboat)
- [#9](https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo/issues/9) — Starforge oracle catalog (the synthesizing ask)
