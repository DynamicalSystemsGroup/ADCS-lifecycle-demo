"""Human attestation — CLI-based expert review and sign-off.

The attestation is the ONLY mechanism that connects evidence to requirement
satisfaction. The engineer judges:
  (a) Model adequacy — is the model an adequate representation?
  (b) Evidence sufficiency — is the computational evidence sufficient?

These judgments are recorded as rtm:Attestation (prov:Activity) in the RDF
graph, with full provenance (who, when, what evidence, what judgments).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from ontology.prefixes import ADCS, G_ATTESTATIONS, PROV, RTM, SYSML
from traceability.queries import EVIDENCE_FOR_REQUIREMENT, query_to_dicts


def _writable_graph(target: Graph | Dataset) -> Graph:
    """Return the graph where attestation triples should be written.

    If `target` is a Dataset, return its <adcs:attestations> named graph
    view. Otherwise return `target` itself (legacy / flat-Graph path).
    Queries against `target` always see the union (Dataset default_union).
    """
    if isinstance(target, Dataset):
        return target.graph(URIRef(G_ATTESTATIONS))
    return target


def _get_git_commit() -> str:
    """Get current HEAD commit SHA, or empty string if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def present_evidence(graph: Graph, req_name: str) -> str:
    """Format evidence summary for a requirement as a human-readable string."""
    lines = []

    # Requirement text
    q_req = f"""
    SELECT ?text WHERE {{
        ?req sysml:declaredName "{req_name}" ;
             sysml:text ?text .
    }}
    """
    rows = query_to_dicts(graph, q_req)
    req_text = rows[0]["text"].strip() if rows else "(not found)"
    lines.append(f"\n{'='*60}")
    lines.append(f"  Requirement: {req_name}")
    lines.append(f"  {req_text}")

    # Derived from
    q_derived = f"""
    SELECT ?parentName WHERE {{
        ?req sysml:declaredName "{req_name}" ;
             rtm:derivedFrom ?parent .
        ?parent sysml:declaredName ?parentName .
    }}
    """
    derived = query_to_dicts(graph, q_derived)
    if derived:
        lines.append(f"  Derived from: {derived[0]['parentName']}")

    # Allocated design elements
    q_alloc = f"""
    SELECT ?elementName WHERE {{
        ?req sysml:declaredName "{req_name}" ;
             sysml:ownedRelationship ?rel .
        ?rel a sysml:SatisfyRequirementUsage ;
             sysml:satisfyingElement ?el .
        ?el sysml:declaredName ?elementName .
    }}
    ORDER BY ?elementName
    """
    alloc = query_to_dicts(graph, q_alloc)
    if alloc:
        elements = ", ".join(r["elementName"] for r in alloc)
        lines.append(f"  Allocated to: {elements}")

    # Evidence artifacts
    evidence = query_to_dicts(graph, EVIDENCE_FOR_REQUIREMENT % req_name)
    if evidence:
        lines.append(f"\n  Evidence ({len(evidence)} artifacts):")
        for ev in evidence:
            ev_type = ev["type"].split("#")[-1] if ev["type"] else "?"
            lines.append(f"    [{ev_type}] hash={ev['hash'][:16]}...")
            lines.append(f"      {ev['summary']}")
    else:
        lines.append("\n  Evidence: NONE")

    lines.append(f"{'='*60}")
    return "\n".join(lines)


def request_attestation(
    graph: Graph | Dataset,
    req_name: str,
    engineer_name: str,
    *,
    auto_attest: bool = False,
    model_adequacy: str = "",
    evidence_sufficiency: str = "",
) -> URIRef | None:
    """Present evidence and request human attestation for a requirement.

    If auto_attest is True, skips the CLI prompt (for testing/scripted runs).
    Otherwise, prompts the engineer interactively.

    Returns the attestation URI if attested, None if declined.
    """
    # Show evidence summary
    summary = present_evidence(graph, req_name)
    print(summary)

    if not auto_attest:
        # Interactive prompts
        print(f"\n  Attestation for {req_name}:")
        print(f"  Engineer: {engineer_name}")
        print()

        adequacy = input(
            "  (a) Model adequacy — Is this model adequate for evaluating\n"
            "      this requirement? (Enter statement or 'no' to decline): "
        ).strip()
        if adequacy.lower() in ("no", "n", ""):
            print(f"  {req_name}: attestation DECLINED (model inadequacy)")
            return None

        sufficiency = input(
            "  (b) Evidence sufficiency — Is the evidence sufficient to\n"
            "      conclude the requirement is satisfied? (Enter statement or 'no'): "
        ).strip()
        if sufficiency.lower() in ("no", "n", ""):
            print(f"  {req_name}: attestation DECLINED (insufficient evidence)")
            return None

        model_adequacy = adequacy
        evidence_sufficiency = sufficiency
    else:
        if not model_adequacy or not evidence_sufficiency:
            raise ValueError(
                "auto_attest=True requires model_adequacy and evidence_sufficiency"
            )

    # Create attestation node. Writes route to <adcs:attestations> when
    # `graph` is a Dataset; queries (above and below) continue to see
    # the union via default_union.
    write = _writable_graph(graph)

    att_id = f"ATT-{req_name}"
    att_uri = ADCS[att_id]
    req_uri = ADCS[req_name]
    engineer_uri = ADCS[f"engineer-{engineer_name.replace(' ', '_')}"]

    write.add((att_uri, RDF.type, RTM.Attestation))
    write.add((att_uri, RTM.attests, req_uri))
    write.add((att_uri, RTM.modelAdequacy, Literal(model_adequacy)))
    write.add((att_uri, RTM.evidenceSufficiency, Literal(evidence_sufficiency)))
    write.add((att_uri, PROV.wasAssociatedWith, engineer_uri))
    write.add((att_uri, PROV.generatedAtTime, Literal(
        datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime,
    )))

    git_sha = _get_git_commit()
    if git_sha:
        write.add((att_uri, RTM.gitCommit, Literal(git_sha)))

    # Link attestation to all evidence for this requirement
    evidence = query_to_dicts(graph, EVIDENCE_FOR_REQUIREMENT % req_name)
    for ev in evidence:
        ev_uri = URIRef(ev["ev"])
        write.add((att_uri, RTM.hasEvidence, ev_uri))

    # Engineer agent node
    write.add((engineer_uri, RDF.type, RTM.Engineer))
    write.add((engineer_uri, RDFS.label, Literal(engineer_name)))

    print(f"\n  {req_name}: ATTESTED by {engineer_name}")
    return att_uri
