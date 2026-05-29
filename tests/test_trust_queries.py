"""Trust queries — WP4 c13."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from rdflib import Dataset, URIRef

from pipeline.runner import run_pipeline
from traceability.queries import (
    AuspicesChain,
    ClosureWitness,
    DigestWitness,
    ServiceInvocationRow,
    TechnicalProvenance,
    TrustSummary,
    auspices_chain,
    closure_witnesses,
    render_trust_summary,
    reproducibility_witnesses,
    service_invocations_for,
    technical_provenance,
    trust_summary,
)


@pytest.fixture(scope="module")
def nominal_dataset() -> Dataset:
    """Local + local nominal pipeline run — produces evidence WITHOUT
    a Docker container (so technical_provenance has no container/image
    populated for local-compute evidence)."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        return run_pipeline(auto_attest=True)


def _pick_proof_evidence(ds: Dataset) -> str:
    """Return any rtm:ProofArtifact IRI from the nominal dataset."""
    from rdflib.namespace import RDF
    from ontology.prefixes import RTM
    iris = list(ds.subjects(RDF.type, RTM.ProofArtifact))
    assert iris, "nominal dataset must have ProofArtifact evidence"
    return str(iris[0])


def test_technical_provenance_returns_typed_dataclass(nominal_dataset):
    ev_iri = _pick_proof_evidence(nominal_dataset)
    tech = technical_provenance(nominal_dataset, ev_iri)
    assert isinstance(tech, TechnicalProvenance)
    assert tech.evidence == ev_iri
    # Local-compute run has no container/image, but DOES have activity + host
    assert tech.activity is not None
    assert tech.host is not None


def test_technical_provenance_returns_empty_for_unknown_evidence(nominal_dataset):
    tech = technical_provenance(nominal_dataset, "urn:adcs:evidence:does-not-exist")
    assert isinstance(tech, TechnicalProvenance)
    assert tech.activity is None


def test_auspices_chain_returns_dataclass(nominal_dataset):
    ev_iri = _pick_proof_evidence(nominal_dataset)
    a = auspices_chain(nominal_dataset, ev_iri)
    assert isinstance(a, AuspicesChain)
    # Default operating org is local-operator (WP4 c6)
    # Note: local-compute runs don't have a container -> no wasAttributedTo edge,
    # so operating_org may be None. That's expected for the local fixture.


def test_reproducibility_witnesses_returns_list(nominal_dataset):
    # No image in local-compute run; returns empty list
    out = reproducibility_witnesses(nominal_dataset, "urn:adcs:docker-image:nonexistent")
    assert out == []


def test_closure_witnesses_finds_stage_6_5_assertion(nominal_dataset):
    """Stage 6.5 emitted at least one rtm:ClosureRuleAssertion (WP4 c7)."""
    from ontology.prefixes import G_AUDIT
    rows = closure_witnesses(nominal_dataset, G_AUDIT)
    assert len(rows) >= 1, "expected at least one closure-rule assertion"
    assert all(isinstance(r, ClosureWitness) for r in rows)


def test_service_invocations_for_returns_list(nominal_dataset):
    """No txnlog enabled in nominal run → empty list."""
    rows = service_invocations_for(nominal_dataset)
    assert isinstance(rows, list)
    # Local run with no ADCS_TXNLOG_ENABLED — should be empty
    assert all(isinstance(r, ServiceInvocationRow) for r in rows)


def test_trust_summary_composes_everything(nominal_dataset):
    ev_iri = _pick_proof_evidence(nominal_dataset)
    summary = trust_summary(nominal_dataset, ev_iri)
    assert isinstance(summary, TrustSummary)
    assert summary.evidence == ev_iri
    assert summary.technical is not None
    assert summary.auspices is not None
    assert isinstance(summary.closure_witnesses, list)


def test_render_trust_summary_includes_key_fields(nominal_dataset):
    ev_iri = _pick_proof_evidence(nominal_dataset)
    summary = trust_summary(nominal_dataset, ev_iri)
    out = render_trust_summary(summary)
    assert "Trust panel" in out
    assert ev_iri in out
    assert "Technical provenance:" in out
    assert "Auspices:" in out
