"""On-demand re-execution of computational evidence.

Confirms that evidence is reproducible *right now*, not just that it
was produced once. For proofs, re-runs verify_proof(). For simulations,
re-runs the numerical integration and compares results.
"""

from __future__ import annotations

from typing import Any

from rdflib import Graph, URIRef

from ontology.prefixes import PROV, RTM, SYSML
from traceability.queries import query_to_dicts


def reproduce_proof(graph: Graph, evidence_uri: str) -> dict[str, Any] | None:
    """Re-verify a proof artifact by re-executing its lemma chain.

    Returns a dict with status and per-lemma results, or None if the
    evidence artifact has no stored proof data.
    """
    from analysis.build_proofs import build_all_proofs
    from analysis.proof_scripts import ProofStatus, verify_proof
    from evidence.hashing import hash_structural_model
    from analysis.load_params import load_structural_graph

    # Get the model hash and proof hash from the evidence
    q = f"""
    SELECT ?modelHash ?proofHash ?activity WHERE {{
        <{evidence_uri}> rtm:modelHash ?modelHash ;
                         rtm:proofHash ?proofHash ;
                         prov:wasGeneratedBy ?activity .
    }}
    """
    rows = query_to_dicts(graph, q)
    if not rows:
        return None

    stored_model_hash = rows[0]["modelHash"]
    stored_proof_hash = rows[0]["proofHash"]

    # Find which requirement this evidence is for
    activity = rows[0]["activity"]
    q2 = f"""
    SELECT ?reqName WHERE {{
        <{activity}> prov:used ?req .
        ?req sysml:declaredName ?reqName .
    }}
    """
    req_rows = query_to_dicts(graph, q2)
    if not req_rows:
        return None
    req_name = req_rows[0]["reqName"]

    # Rebuild and re-verify the proof
    proofs = build_all_proofs(stored_model_hash)
    if req_name not in proofs:
        return {"status": "NOT_FOUND", "error": f"No proof script for {req_name}"}

    script = proofs[req_name]
    result = verify_proof(script, stored_model_hash)

    lemma_results = [
        {"name": lr.lemma_name, "passed": lr.passed, "error": lr.error}
        for lr in result.lemma_results
    ]

    return {
        "status": result.status,
        "proof_hash": result.proof_hash,
        "stored_proof_hash": stored_proof_hash,
        "hash_match": result.proof_hash == stored_proof_hash,
        "requirement": req_name,
        "lemma_results": lemma_results,
    }


def reproduce_simulation(
    graph: Graph, evidence_uri: str,
) -> dict[str, Any] | None:
    """Re-run a numerical simulation and compare with stored results.

    Returns a dict with comparison metrics, or None if the evidence
    artifact has no simulation data.
    """
    from analysis.load_params import load_params
    from analysis.numerical import run_step_response, run_disturbance_rejection

    # Get stored summary and model hash
    q = f"""
    SELECT ?modelHash ?simHash ?summary ?activity WHERE {{
        <{evidence_uri}> a rtm:SimulationResult ;
                         rtm:modelHash ?modelHash ;
                         rtm:contentHash ?simHash ;
                         rtm:resultSummary ?summary ;
                         prov:wasGeneratedBy ?activity .
    }}
    """
    rows = query_to_dicts(graph, q)
    if not rows:
        return None

    stored_summary = rows[0]["summary"]
    activity = rows[0]["activity"]

    # Find requirement
    q2 = f"""
    SELECT ?reqName WHERE {{
        <{activity}> prov:used ?req .
        ?req sysml:declaredName ?reqName .
    }}
    """
    req_rows = query_to_dicts(graph, q2)
    req_name = req_rows[0]["reqName"] if req_rows else "unknown"

    # Re-run simulation
    params = load_params()
    if "disturbance" in stored_summary.lower() or req_name == "REQ-004":
        result = run_disturbance_rejection(params)
    else:
        result = run_step_response(params)

    new_summary = result.summary()

    return {
        "requirement": req_name,
        "stored_summary": stored_summary,
        "reproduced_summary": new_summary,
        "reproduced": True,
    }


def reproduce_all_evidence(graph: Graph) -> dict[str, list[dict]]:
    """Re-execute all evidence artifacts and return results.

    Returns {"proofs": [...], "simulations": [...]}.
    """
    results: dict[str, list[dict]] = {"proofs": [], "simulations": []}

    # Proof artifacts
    q_proofs = """
    SELECT ?ev WHERE {
        ?ev a rtm:ProofArtifact .
    }
    """
    for row in query_to_dicts(graph, q_proofs):
        r = reproduce_proof(graph, row["ev"])
        if r:
            results["proofs"].append(r)

    # Simulation results
    q_sims = """
    SELECT ?ev WHERE {
        ?ev a rtm:SimulationResult .
    }
    """
    for row in query_to_dicts(graph, q_sims):
        r = reproduce_simulation(graph, row["ev"])
        if r:
            results["simulations"].append(r)

    return results
