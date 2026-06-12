# The AI-Aided Engineering Loop

An LLM agent accelerates the engineering work in this demo, but it cannot be
accountable for any of it. The demo does not constrain the agent with policy
text; it constrains it by **interface**. Everything the agent can do passes
through a narrow waist of typed CLI surfaces; everything the pipeline produces
is checked by SHACL closure rules; every stage emits a `p-plan:Activity` so the
construction process is itself queryable; and the only edge in the whole graph
that asserts requirement satisfaction is human attestation. Evidence — however
it was computed, and however reproducibly — only ever *supports* that
judgement.

The term discipline of the repo applies to the loop itself: **verification**
is automated and fully specified (SHACL conformance, digest matching,
behavior-oracle metric-vs-criterion comparison) and is therefore safe to
delegate to machines and to re-run; **validation** is human judgement (model
adequacy, evidence sufficiency) and is therefore reserved for the accountable
engineer, recorded with `earl:mode = earl:manual` and a
`prov:qualifiedAssociation` naming who judged. The agent sits on the
verification side of that line and never crosses it. Above the attesting
engineer, supervisor and auditor roles review the same record through
deterministically compiled roll-ups, drilling down to detail when needed.

**Architecture vs. demo instantiation.** This document describes the
architecture; the repo demonstrates its feasibility by instantiation, and the
two differ in one deliberate place. So the loop can run end-to-end without an
operator present, `pipeline.runner --auto` substitutes a scripted stand-in for
the engineer's role, and the record marks that substitution honestly:
auto-attestations carry `earl:mode = earl:semiAuto`, never `earl:manual`, so
no quad ever claims a human judgement that did not happen. That the
substitution is visible *in the record itself* is the constraint structure
working as designed; a production deployment gates or disables the flag and
reserves Stage 6 for the accountable engineer.

## Standing constraint structure

```mermaid
flowchart LR
    subgraph HUMAN["Human engineer — accountable"]
        INTENT["Intent /<br/>requirement change"]
        JUDGE["Validation judgement<br/>adequacy → gsn:Assumption<br/>sufficiency → gsn:Justification"]
        OVERSIGHT["Supervisor / Auditor<br/>reviews deterministic roll-ups;<br/>drills down on demand"]
    end

    subgraph AGENT["LLM agent"]
        LLM["Proposes & operates<br/>(no direct graph writes,<br/>no attestation authority)"]
    end

    subgraph IFACE["Constrained interface — the narrow waist"]
        CLI1["pipeline.runner<br/>typed flags, Enum choices<br/>--backend --compute --auto"]
        CLI2["interrogate.rerun<br/>--requirement --input"]
    end

    subgraph PIPE["Sequenced pipeline — p-plan enforced"]
        PRE["Preflight gate<br/>probe every remote, fail fast"]
        S05["Stages 0–5<br/>assemble → load → analyze →<br/>simulate → bind evidence → RTM"]
        S6["Stage 6 · Attestation<br/>earl:mode = manual<br/>(semiAuto under --auto)<br/>prov:qualifiedAssociation → engineer"]
        S65["Stage 6.5 · Closure rules<br/>SHACL closure-rule suite<br/>earl:mode = automatic"]
        S7A["Stage 7a · Bidirectional audit"]
        S7["Stage 7 · Reports<br/>audit.md · audit.csv<br/>deterministic render of &lt;adcs:audit&gt;"]
    end

    subgraph TRACE["Traceability + computational provenance"]
        QS["Quadstore / Flexo MMS<br/>8 named graphs"]
        IMG["Docker image (digest)<br/>rtm:gitRef · rtm:flexoRecord"]
        CTR["Container (per-run)"]
        TXN["Transaction-log store"]
    end

    INTENT --> LLM
    LLM --> CLI1 --> PRE --> S05
    S05 -->|"evidence — never verdicts"| JUDGE
    JUDGE -->|"the only edge that asserts<br/>requirement satisfaction"| S6
    S6 --> S65 --> S7A --> S7
    S7 -->|"rolled-up view"| OVERSIGHT
    S05 --> QS
    S6 --> QS
    S7A --> QS
    OVERSIGHT -.->|"drill down: six trust queries,<br/>interrogate.explain / visualize"| QS
    OVERSIGHT -.->|"findings → new intent"| INTENT
    S05 -.->|"--compute=docker"| CTR
    CTR -.->|prov:wasDerivedFrom| IMG
    S05 -.-> TXN
    S65 -.->|violations| LLM
    S7A -.->|broken traces| CLI2
    CLI2 -.->|"minimal rerun plan"| LLM
```

Solid edges are the forward flow of one run; dotted edges are feedback and
provenance references. Four properties of the topology do the governing:

- **The narrow waist.** The agent reaches the pipeline only through Typer
  CLIs whose flags are typed and whose choices are `Enum`-validated. There is
  no API for "write a triple into the attestations graph" — the only producer
  of attestations is Stage 6, and Stage 6's input is the engineer (or, in the
  demo instantiation, the `--auto` stand-in, whose attestations are
  distinguishable in the graph by `earl:mode = earl:semiAuto`).
- **Evidence flows to the human, verdicts flow from the human.** Stages 0–5
  hash and bind artifacts but attach no judgement. The engineer's validation
  judgement (adequacy as `gsn:Assumption`, sufficiency as
  `gsn:Justification`) is the sole bridge from evidence to requirement
  satisfaction.
- **Verification closes the loop, it doesn't settle it.** SHACL violations
  and audit gaps route back to the agent as work — via `interrogate.rerun`,
  which translates a verification report into the minimal set of stages to
  re-run. Re-running regenerates evidence; it never regenerates attestation.
- **Oversight scales because the roll-up is deterministic.** Stage 7 reports
  (`output/audit.md`, `audit.csv`) are pure renders of the `<adcs:audit>`
  graph — same graph, same report — so they sit on the verification side of
  the line. Supervisors and auditors review at roll-up altitude by default
  and, when something warrants it, drill into the same named graphs that back
  the engineer's attestation (the six trust queries, `interrogate.explain` /
  `visualize`); there is no separately curated view to drift from the record.
  Their review redirects work — it does not attest; aggregated sign-off gates
  are future work (multi-attestation aggregation policy).

## One trip around the loop

```mermaid
sequenceDiagram
    actor E as Engineer
    actor S as Supervisor / Auditor
    participant A as LLM agent
    participant C as CLI (Typer)
    participant P as Pipeline (p-plan)
    participant Q as Quadstore / remotes

    E->>A: intent ("re-run analysis under docker compute")
    A->>C: pipeline.runner --compute=docker --backend=flexo
    C->>P: preflight gate — every remote probed, fail fast
    P->>P: Stages 0–5 in fixed order<br/>(each emits a p-plan:Activity)
    P->>Q: evidence + PROV<br/>(image digest, container, txn-log)
    P-->>E: evidence for review — no verdict attached
    E->>P: Stage 6 attestation<br/>(adequacy + sufficiency, earl:manual)
    P->>P: Stage 6.5 — SHACL closure rules (earl:automatic)
    P->>P: Stage 7a — forward/backward audit
    P->>Q: attestations + audit graphs persisted
    P->>S: Stage 7 — deterministic roll-up<br/>(audit.md / audit.csv)
    S->>Q: drill down when needed<br/>(trust_summary, interrogate.explain)
    Q-->>S: full provenance chain behind any row

    Note over E,Q: later — a requirement or model changes
    A->>C: interrogate.rerun --requirement REQ-003
    C-->>A: minimal set of stages to re-run
    A->>E: proposed rerun — evidence regenerates,<br/>but only the engineer re-attests
```

## Constraint inventory

| Constraint | Mechanism | Where |
|---|---|---|
| Agent acts only through typed surfaces | Typer CLIs, Enum-validated choices | [`pipeline/runner.py`](pipeline/runner.py), [`interrogate/rerun.py`](interrogate/rerun.py) |
| Activity sequencing | p-plan steps + the runner's ordered stage calls; every stage emits a `p-plan:Activity` | [`pipeline/plan.ttl`](pipeline/plan.ttl), [`pipeline/runner.py`](pipeline/runner.py) |
| No silent degrade | Preflight gate probes all configured remotes before Stage 0 | [`pipeline/runner.py`](pipeline/runner.py) |
| Structural invariants | 18 SHACL closure-rule shapes (Stage 6.5) | [`ontology/rtm_shapes.ttl`](ontology/rtm_shapes.ttl), [`traceability/verification.py`](traceability/verification.py) |
| Human accountability for validation | Attestation carries `prov:qualifiedAssociation` to the engineer; `earl:mode` records how the judgement was made (`earl:manual`; `earl:semiAuto` for the demo's `--auto` stand-in); only `rtm:attests` links to requirement satisfaction | [`traceability/attestation.py`](traceability/attestation.py) |
| Reproducible verification | `rtm:ClosureRuleAssertion`, `rtm:DigestMatchAssertion`, `rtm:BehaviorOracleAssertion` — all `earl:automatic`, over content-addressed inputs | [`traceability/oracle_assertion.py`](traceability/oracle_assertion.py), [`interrogate/reproduce.py`](interrogate/reproduce.py) |
| Computational provenance | image / container / host PROV chain + transaction-log records | [`compute/`](compute/), [ARCHITECTURE.md](ARCHITECTURE.md) |
| Scalable oversight | Stage 7 reports are deterministic renders of the audit graph; six trust queries + `interrogate.explain` / `visualize` give drill-down to the same quads | [`pipeline/runner.py`](pipeline/runner.py), [`traceability/audit.py`](traceability/audit.py), [`traceability/queries.py`](traceability/queries.py), [`interrogate/explain.py`](interrogate/explain.py) |
| Loop closure | `interrogate.rerun` translates verification reports into minimal stage re-runs | [`interrogate/rerun.py`](interrogate/rerun.py) |

The result: the agent can be arbitrarily capable inside the loop without
weakening the assurance argument, because capability and accountability are
separated by construction — the agent operates the verification machinery,
and the machinery is built so that validation can only come from a person.
