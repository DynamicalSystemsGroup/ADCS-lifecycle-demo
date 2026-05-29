"""SPARQL query templates for RTM interrogation.

All queries use the project namespace prefixes. Results are returned as
lists of dicts for easy consumption.
"""

from __future__ import annotations

from rdflib import Graph

from ontology.prefixes import ADCS, EARL, GSN, PROV, RTM, SYSML

_INIT_NS = {
    "sysml": SYSML, "rtm": RTM, "prov": PROV, "adcs": ADCS,
    "earl": EARL, "gsn": GSN,
}

# ---------------------------------------------------------------------------
# Requirement queries
# ---------------------------------------------------------------------------

ADCS_REQUIREMENTS = """
SELECT ?req ?name ?text WHERE {
    ?req a sysml:RequirementDefinition ;
         sysml:declaredName ?name ;
         sysml:text ?text .
    FILTER(STRSTARTS(?name, "REQ-"))
}
ORDER BY ?name
"""

REQUIREMENT_ALLOCATION = """
SELECT ?reqName ?elementName WHERE {
    ?req a sysml:RequirementDefinition ;
         sysml:declaredName ?reqName ;
         sysml:ownedRelationship ?rel .
    ?rel a sysml:SatisfyRequirementUsage ;
         sysml:satisfyingElement ?element .
    ?element sysml:declaredName ?elementName .
    FILTER(STRSTARTS(?reqName, "REQ-"))
}
ORDER BY ?reqName ?elementName
"""

REQUIREMENT_DERIVATION = """
SELECT ?adcsName ?satName WHERE {
    ?req sysml:declaredName ?adcsName ;
         rtm:derivedFrom ?parent .
    ?parent sysml:declaredName ?satName .
}
ORDER BY ?adcsName
"""

# ---------------------------------------------------------------------------
# Evidence queries
# ---------------------------------------------------------------------------

ALL_EVIDENCE = """
SELECT ?ev ?type ?method ?hash ?summary WHERE {
    ?ev a ?type ;
        rtm:contentHash ?hash ;
        rtm:resultSummary ?summary .
    OPTIONAL { ?ev rtm:evidenceMethod ?method }
    FILTER(?type IN (rtm:ProofArtifact, rtm:SimulationResult))
}
ORDER BY ?ev
"""

EVIDENCE_FOR_REQUIREMENT = """
SELECT ?ev ?type ?hash ?summary WHERE {
    ?ev a ?type ;
        rtm:contentHash ?hash ;
        rtm:resultSummary ?summary ;
        rtm:addresses ?req .
    ?req sysml:declaredName ?reqName .
    FILTER(?type IN (rtm:ProofArtifact, rtm:SimulationResult))
    FILTER(?reqName = "%s")
}
ORDER BY ?ev
"""

# ---------------------------------------------------------------------------
# Attestation queries
# ---------------------------------------------------------------------------

ALL_ATTESTATIONS = """
SELECT ?att ?reqName ?engineer ?adequacy ?sufficiency ?outcome ?mode ?timestamp WHERE {
    ?att a rtm:Attestation ;
         rtm:attests ?req ;
         rtm:hasOutcome ?outcome ;
         prov:wasAssociatedWith ?agent ;
         prov:generatedAtTime ?timestamp .
    OPTIONAL { ?att rtm:attestationMode ?mode }
    ?att gsn:inContextOf ?adequacyNode .
    ?adequacyNode a gsn:Assumption ;
                  gsn:statement ?adequacy .
    ?att gsn:inContextOf ?sufficiencyNode .
    ?sufficiencyNode a gsn:Justification ;
                     gsn:statement ?sufficiency .
    ?req sysml:declaredName ?reqName .
    ?agent rdfs:label ?engineer .
}
ORDER BY ?reqName
"""

ATTESTATION_STATUS = """
SELECT ?reqName (COUNT(?att) AS ?attestCount) WHERE {
    ?req a sysml:RequirementDefinition ;
         sysml:declaredName ?reqName .
    FILTER(STRSTARTS(?reqName, "REQ-"))
    OPTIONAL {
        ?att a rtm:Attestation ;
             rtm:attests ?req .
    }
}
GROUP BY ?reqName
ORDER BY ?reqName
"""

# Per-requirement outcome with the EARL outcome value short name.
# Returns one row per requirement; ?outcome is "passed" / "failed" /
# "cantTell" / "inapplicable" / "untested" / "" (no attestation).
# Distinguishes "ATTESTED+failed" from "no attestation" — neither was
# possible before the GSN/EARL refactor (Phase F).
REQUIREMENT_OUTCOMES = """
SELECT ?reqName ?outcomeShort WHERE {
    ?req a sysml:RequirementDefinition ;
         sysml:declaredName ?reqName .
    FILTER(STRSTARTS(?reqName, "REQ-"))
    OPTIONAL {
        ?att a rtm:Attestation ;
             rtm:attests ?req ;
             rtm:hasOutcome ?outcome .
        BIND(REPLACE(STR(?outcome), "^.*[#/]", "") AS ?outcomeShort)
    }
}
ORDER BY ?reqName
"""

UNATTESTED_REQUIREMENTS = """
SELECT ?reqName WHERE {
    ?req a sysml:RequirementDefinition ;
         sysml:declaredName ?reqName .
    FILTER(STRSTARTS(?reqName, "REQ-"))
    FILTER NOT EXISTS {
        ?att a rtm:Attestation ;
             rtm:attests ?req .
    }
}
ORDER BY ?reqName
"""

# ---------------------------------------------------------------------------
# Forward / backward trace
# ---------------------------------------------------------------------------

FORWARD_TRACE = """
SELECT ?reqName ?elementName ?evType ?evHash ?evSummary ?attEngineer ?attTime WHERE {
    ?req a sysml:RequirementDefinition ;
         sysml:declaredName ?reqName ;
         sysml:ownedRelationship ?rel .
    ?rel a sysml:SatisfyRequirementUsage ;
         sysml:satisfyingElement ?element .
    ?element sysml:declaredName ?elementName .
    FILTER(?reqName = "%s")

    OPTIONAL {
        ?ev a ?evType ;
            rtm:contentHash ?evHash ;
            rtm:resultSummary ?evSummary ;
            rtm:addresses ?req .
        FILTER(?evType IN (rtm:ProofArtifact, rtm:SimulationResult))
    }
    OPTIONAL {
        ?att a rtm:Attestation ;
             rtm:attests ?req ;
             prov:wasAssociatedWith ?agent ;
             prov:generatedAtTime ?attTime .
        ?agent rdfs:label ?attEngineer .
    }
}
ORDER BY ?elementName ?evType
"""

BACKWARD_TRACE = """
SELECT ?reqName ?evHash ?evSummary ?activityType ?attEngineer ?attTime WHERE {
    ?att a rtm:Attestation ;
         rtm:attests ?req ;
         rtm:hasEvidence ?ev ;
         prov:wasAssociatedWith ?agent ;
         prov:generatedAtTime ?attTime .
    ?agent rdfs:label ?attEngineer .
    ?req sysml:declaredName ?reqName .
    ?ev rtm:contentHash ?evHash ;
        rtm:resultSummary ?evSummary ;
        prov:wasGeneratedBy ?activity .
    ?activity a ?activityType .
    FILTER(?activityType IN (rtm:SymbolicAnalysis, rtm:NumericalSimulation))
}
ORDER BY ?reqName ?evHash
"""

# ---------------------------------------------------------------------------
# Hash chain validation
# ---------------------------------------------------------------------------

EVIDENCE_HASH_CHAIN = """
SELECT ?ev ?modelHash ?proofHash ?contentHash WHERE {
    ?ev a rtm:ProofArtifact ;
        rtm:modelHash ?modelHash ;
        rtm:proofHash ?proofHash ;
        rtm:contentHash ?contentHash .
}
ORDER BY ?ev
"""


# ---------------------------------------------------------------------------
# WP3 §4.5 — DockerImage / evidence cross-reference
# ---------------------------------------------------------------------------

EVIDENCE_BY_IMAGE = """
SELECT ?ev ?type ?evContentHash ?modelHash WHERE {
    ?image a rtm:DockerImage ;
           rtm:contentHash ?imageDigest .
    ?ev prov:wasDerivedFrom ?image ;
        a ?type ;
        rtm:contentHash ?evContentHash ;
        rtm:modelHash ?modelHash .
    FILTER(?imageDigest = ?digest)
}
ORDER BY ?ev
"""


# ---------------------------------------------------------------------------
# Query runner helpers
# ---------------------------------------------------------------------------

def query_to_dicts(graph: Graph, sparql: str) -> list[dict[str, str]]:
    """Execute a SPARQL query and return results as list of dicts.

    Note: pass a Dataset to walk the union view (uses
    ``default_union=True``); pass a single named-graph view (obtained
    via ``pipeline.dataset.graph_for`` or ``query_named_graph``) to
    restrict to one layer. The queries shipped in this module are
    written assuming the union view.
    """
    results = graph.query(sparql, initNs=_INIT_NS)
    rows = []
    for row in results:
        d = {}
        for var in results.vars:
            val = getattr(row, str(var), None)
            d[str(var)] = str(val) if val is not None else None
        rows.append(d)
    return rows


def evidence_by_image(graph, digest: str) -> list[dict[str, str]]:
    """Return evidence artifacts derived from the image with the given digest.

    `digest` is the runtime digest (e.g. ``sha256:71a59f23...``) as
    stored in the image node's ``rtm:contentHash``. Returns a list of
    row dicts with keys ``ev``, ``type``, ``evContentHash``,
    ``modelHash``; empty list on miss.

    Implements WP3 §4.5 / issue #4 AC5. Use case: given an image
    digest, find every evidence node that was produced by a container
    started from that image — the cross-reference that today's
    "agent label" model cannot answer.

    Pass a Dataset (union view) to query across the assembled RTM;
    pass a single named-graph view if you intend layer scoping.
    """
    from rdflib import Literal
    results = graph.query(
        EVIDENCE_BY_IMAGE, initNs=_INIT_NS,
        initBindings={"digest": Literal(digest)},
    )
    rows = []
    for row in results:
        d = {}
        for var in results.vars:
            val = getattr(row, str(var), None)
            d[str(var)] = str(val) if val is not None else None
        rows.append(d)
    return rows


# ===========================================================================
# WP4 c13 — Trust queries: "how can I trust this evidence?"
# ===========================================================================
#
# Six typed dataclasses + queries answering the technical-trust questions.
# Used by interrogate.explain's Trust panel and by external consumers.
# All read-only; safe to run against the union view of the Dataset.

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TechnicalProvenance:
    evidence: str
    activity: str | None
    container: str | None
    container_id: str | None
    image: str | None
    image_digest: str | None
    git_ref: str | None
    host: str | None
    hosting_org: str | None
    operating_org: str | None
    executor: str | None


@dataclass(frozen=True)
class DigestWitness:
    assertion: str
    outcome: str
    mode: str | None
    agent: str | None
    at_time: str | None


@dataclass(frozen=True)
class ClosureWitness:
    assertion: str
    outcome: str
    violation_count: int | None
    at_time: str | None


@dataclass(frozen=True)
class AuspicesChain:
    operating_org: str | None
    operating_org_label: str | None
    hosting_org: str | None
    hosting_org_label: str | None


@dataclass(frozen=True)
class ServiceInvocationRow:
    invocation: str
    txn_id: str | None
    service: str | None
    caller: str | None
    log_evidence: str | None
    document_ref: str | None
    content_hash: str | None


@dataclass(frozen=True)
class TrustSummary:
    evidence: str
    technical: TechnicalProvenance | None
    auspices: AuspicesChain | None
    digest_witnesses: list[DigestWitness] = field(default_factory=list)
    closure_witnesses: list[ClosureWitness] = field(default_factory=list)
    service_invocations: list[ServiceInvocationRow] = field(default_factory=list)


_TECHNICAL_PROVENANCE_Q = """
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rtm:  <http://example.org/ontology/rtm#>
SELECT ?activity ?container ?containerId ?image ?digest ?gitRef ?host ?hostingOrg ?operatingOrg ?executor WHERE {
  ?evidence prov:wasGeneratedBy ?activity .
  OPTIONAL { ?activity prov:used ?container .
             ?container a rtm:DockerContainer ;
                        rtm:containerId ?containerId ;
                        prov:wasDerivedFrom ?image .
             OPTIONAL { ?container prov:wasAttributedTo ?operatingOrg . } }
  OPTIONAL { ?image rtm:contentHash ?digest . }
  OPTIONAL { ?image rtm:gitRef ?gitRef . }
  OPTIONAL { ?activity prov:atLocation ?host . OPTIONAL { ?host rtm:operatedBy ?hostingOrg . } }
  OPTIONAL { ?activity prov:wasAssociatedWith ?executor . }
}
"""


def technical_provenance(ds, evidence_iri: str) -> TechnicalProvenance:
    """Walk the full technical chain from one evidence node."""
    from rdflib import URIRef
    rows = list(ds.query(
        _TECHNICAL_PROVENANCE_Q,
        initBindings={"evidence": URIRef(evidence_iri)},
    ))

    def _s(val):
        return str(val) if val is not None else None

    if not rows:
        return TechnicalProvenance(
            evidence=evidence_iri, activity=None, container=None,
            container_id=None, image=None, image_digest=None, git_ref=None,
            host=None, hosting_org=None, operating_org=None, executor=None,
        )
    row = rows[0]
    return TechnicalProvenance(
        evidence=evidence_iri,
        activity=_s(row.get("activity")),
        container=_s(row.get("container")),
        container_id=_s(row.get("containerId")),
        image=_s(row.get("image")),
        image_digest=_s(row.get("digest")),
        git_ref=_s(row.get("gitRef")),
        host=_s(row.get("host")),
        hosting_org=_s(row.get("hostingOrg")),
        operating_org=_s(row.get("operatingOrg")),
        executor=_s(row.get("executor")),
    )


_DIGEST_WITNESSES_Q = """
PREFIX earl: <http://www.w3.org/ns/earl#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rtm:  <http://example.org/ontology/rtm#>
SELECT ?assertion ?outcome ?mode ?agent ?time WHERE {
  ?assertion a rtm:DigestMatchAssertion ;
             earl:subject ?image ;
             earl:outcome ?outcome .
  OPTIONAL { ?assertion earl:mode ?mode . }
  OPTIONAL { ?assertion prov:wasAssociatedWith ?agent . }
  OPTIONAL { ?assertion prov:atTime ?time . }
}
"""


def reproducibility_witnesses(ds, image_iri: str) -> list[DigestWitness]:
    from rdflib import URIRef
    rows = list(ds.query(
        _DIGEST_WITNESSES_Q,
        initBindings={"image": URIRef(image_iri)},
    ))
    return [
        DigestWitness(
            assertion=str(r["assertion"]),
            outcome=str(r["outcome"]),
            mode=str(r["mode"]) if r.get("mode") else None,
            agent=str(r["agent"]) if r.get("agent") else None,
            at_time=str(r["time"]) if r.get("time") else None,
        )
        for r in rows
    ]


_CLOSURE_WITNESSES_Q = """
PREFIX earl: <http://www.w3.org/ns/earl#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rtm:  <http://example.org/ontology/rtm#>
SELECT ?assertion ?outcome ?count ?time WHERE {
  ?assertion a rtm:ClosureRuleAssertion ;
             earl:subject ?graph ;
             earl:outcome ?outcome .
  OPTIONAL { ?assertion rtm:violationCount ?count . }
  OPTIONAL { ?assertion prov:atTime ?time . }
}
"""


def closure_witnesses(ds, graph_iri: str) -> list[ClosureWitness]:
    from rdflib import URIRef
    rows = list(ds.query(
        _CLOSURE_WITNESSES_Q,
        initBindings={"graph": URIRef(graph_iri)},
    ))
    return [
        ClosureWitness(
            assertion=str(r["assertion"]),
            outcome=str(r["outcome"]),
            violation_count=int(r["count"]) if r.get("count") is not None else None,
            at_time=str(r["time"]) if r.get("time") else None,
        )
        for r in rows
    ]


_AUSPICES_Q = """
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rtm:  <http://example.org/ontology/rtm#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?operatingOrg ?operatingOrgLabel ?hostingOrg ?hostingOrgLabel WHERE {
  ?evidence prov:wasGeneratedBy ?activity .
  OPTIONAL { ?activity prov:used ?container .
             ?container prov:wasAttributedTo ?operatingOrg .
             OPTIONAL { ?operatingOrg rdfs:label ?operatingOrgLabel . } }
  OPTIONAL { ?activity prov:atLocation ?host .
             ?host rtm:operatedBy ?hostingOrg .
             OPTIONAL { ?hostingOrg rdfs:label ?hostingOrgLabel . } }
}
"""


def auspices_chain(ds, evidence_iri: str) -> AuspicesChain:
    from rdflib import URIRef
    rows = list(ds.query(
        _AUSPICES_Q,
        initBindings={"evidence": URIRef(evidence_iri)},
    ))
    if not rows:
        return AuspicesChain(None, None, None, None)
    r = rows[0]

    def _s(val):
        return str(val) if val is not None else None

    return AuspicesChain(
        operating_org=_s(r.get("operatingOrg")),
        operating_org_label=_s(r.get("operatingOrgLabel")),
        hosting_org=_s(r.get("hostingOrg")),
        hosting_org_label=_s(r.get("hostingOrgLabel")),
    )


_SERVICE_INVOCATIONS_Q = """
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rtm:  <http://example.org/ontology/rtm#>
SELECT ?invocation ?txnId ?service ?caller ?logEvidence ?docRef ?logHash WHERE {
  ?invocation a prov:Activity ;
              rtm:transactionId ?txnId .
  OPTIONAL { ?invocation prov:used ?service . }
  OPTIONAL { ?invocation prov:wasAssociatedWith ?caller . }
  OPTIONAL {
    ?logEvidence prov:wasGeneratedBy ?invocation ;
                 rtm:documentRef ?docRef ;
                 rtm:contentHash ?logHash .
  }
}
"""


def service_invocations_for(ds, _activity_iri: str | None = None) -> list[ServiceInvocationRow]:
    """Return service invocations (currently global; activity-scoping is a
    future refinement once activity→invocation joins are explicit)."""
    rows = list(ds.query(_SERVICE_INVOCATIONS_Q))
    return [
        ServiceInvocationRow(
            invocation=str(r["invocation"]),
            txn_id=str(r["txnId"]) if r.get("txnId") else None,
            service=str(r["service"]) if r.get("service") else None,
            caller=str(r["caller"]) if r.get("caller") else None,
            log_evidence=str(r["logEvidence"]) if r.get("logEvidence") else None,
            document_ref=str(r["docRef"]) if r.get("docRef") else None,
            content_hash=str(r["logHash"]) if r.get("logHash") else None,
        )
        for r in rows
    ]


def trust_summary(ds, evidence_iri: str) -> TrustSummary:
    """Compose all five trust queries into one record."""
    tech = technical_provenance(ds, evidence_iri)
    ausp = auspices_chain(ds, evidence_iri)
    digest_w: list[DigestWitness] = []
    if tech and tech.image:
        digest_w = reproducibility_witnesses(ds, tech.image)
    closure_w = closure_witnesses(ds, "http://example.org/adcs-demo/graph/audit")
    inv = service_invocations_for(ds)
    return TrustSummary(
        evidence=evidence_iri,
        technical=tech,
        auspices=ausp,
        digest_witnesses=digest_w,
        closure_witnesses=closure_w,
        service_invocations=inv,
    )


def render_trust_summary(summary: TrustSummary) -> str:
    """Compact text rendering for interrogate.explain Trust panel."""
    lines = [
        f"Trust panel for {summary.evidence}",
        "=" * 70,
    ]
    t = summary.technical
    if t:
        lines.append("Technical provenance:")
        lines.append(f"  activity:    {t.activity or '-'}")
        lines.append(f"  container:   {t.container or '-'} (id={t.container_id or '-'})")
        lines.append(f"  image:       {t.image or '-'}")
        lines.append(f"  digest:      {t.image_digest or '-'}")
        lines.append(f"  git ref:     {t.git_ref or '-'}")
        lines.append(f"  host:        {t.host or '-'}")
        lines.append(f"  executor:    {t.executor or '-'}")
    a = summary.auspices
    if a:
        lines.append("Auspices:")
        lines.append(f"  operating:   {a.operating_org_label or a.operating_org or '-'}")
        lines.append(f"  hosting:     {a.hosting_org_label or a.hosting_org or '-'}")
    if summary.digest_witnesses:
        lines.append(f"Digest-match assertions: {len(summary.digest_witnesses)}")
        for w in summary.digest_witnesses[:3]:
            lines.append(f"  - outcome={w.outcome} agent={w.agent or '-'}")
    if summary.closure_witnesses:
        lines.append(f"Closure-rule assertions: {len(summary.closure_witnesses)}")
        for w in summary.closure_witnesses[:3]:
            lines.append(
                f"  - outcome={w.outcome} violations={w.violation_count if w.violation_count is not None else '-'}"
            )
    if summary.service_invocations:
        lines.append(f"Wire-level invocations: {len(summary.service_invocations)}")
        for inv in summary.service_invocations[:3]:
            lines.append(f"  - txn={inv.txn_id} service={inv.service or '-'}")
    return "\n".join(lines)
