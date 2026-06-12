"""Trust queries — WP4 c13."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest
from rdflib import Dataset, URIRef

from pipeline.runner import run_pipeline
from traceability.queries import (
    AuspicesChain,
    ClosureWitness,
    DigestWitness,
    ServiceAuspicesRow,
    ServiceInvocationRow,
    TechnicalProvenance,
    TrustSummary,
    auspices_chain,
    closure_witnesses,
    render_trust_summary,
    reproducibility_witnesses,
    service_auspices,
    service_invocations_for,
    technical_provenance,
    trust_summary,
)


# A shell with .env exported would flip the auspices defaults these tests
# assert; the org env vars are stripped for the whole module's run.
_ORG_ENV_VARS = tuple(
    f"ADCS_{scope}_ORG_{field}"
    for scope in ("OPERATING", "HOSTING", "FLEXO_HOSTING", "TXNLOG_HOSTING")
    for field in ("IRI", "LABEL", "DESCRIPTION")
)


@pytest.fixture(scope="module")
def _clean_org_env():
    saved = {k: os.environ.pop(k) for k in _ORG_ENV_VARS if k in os.environ}
    yield
    os.environ.update(saved)


@pytest.fixture(scope="module")
def nominal_dataset(_clean_org_env) -> Dataset:
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
    # Default auspices (WP4 c6): operating + hosting both local-operator.
    # The operating org resolves via <executor> prov:actedOnBehalfOf even
    # for local runs (no Docker container in the nominal fixture).
    assert a.operating_org == "urn:adcs:org:local-operator"
    assert a.hosting_org == "urn:adcs:org:local-operator"


def test_technical_provenance_local_run_has_no_image(nominal_dataset):
    """Local-compute evidence must not pick up a free-floating ?image.

    Regression: an unbound ?image in a top-level OPTIONAL used to match
    ANY node carrying rtm:contentHash, so the trust panel showed an
    evidence node as the "image" with its content hash as the "digest".
    """
    ev_iri = _pick_proof_evidence(nominal_dataset)
    tech = technical_provenance(nominal_dataset, ev_iri)
    assert tech.container is None
    assert tech.image is None
    assert tech.image_digest is None
    assert tech.git_ref is None


def test_technical_provenance_executor_is_software_agent(nominal_dataset):
    """The executor column must resolve to the prov:SoftwareAgent executor,
    not the rtm:ComputationEngine node that shares prov:wasAssociatedWith."""
    ev_iri = _pick_proof_evidence(nominal_dataset)
    tech = technical_provenance(nominal_dataset, ev_iri)
    assert tech.executor is not None
    assert tech.executor.startswith("urn:adcs:executor:")


def test_technical_provenance_resolves_operating_org_for_local_runs(nominal_dataset):
    ev_iri = _pick_proof_evidence(nominal_dataset)
    tech = technical_provenance(nominal_dataset, ev_iri)
    assert tech.operating_org == "urn:adcs:org:local-operator"


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


def test_service_auspices_empty_for_local_backend(nominal_dataset):
    """Local backend emits no urn:adcs:service:* nodes."""
    assert service_auspices(nominal_dataset) == []


def test_service_auspices_finds_operated_service():
    from rdflib import Literal
    from rdflib.namespace import RDFS
    from ontology.prefixes import RTM

    ds = Dataset(default_union=True)
    g = ds.graph(URIRef("urn:test:ctx"))
    svc = URIRef("urn:adcs:service:flexo-mms")
    pu = URIRef("urn:adcs:org:planetary-utilities")
    g.add((svc, RTM.operatedBy, pu))
    g.add((svc, RDFS.label, Literal("Flexo MMS")))
    g.add((pu, RDFS.label, Literal("Planetary Utilities")))
    # A non-service location with operatedBy must NOT appear.
    host = URIRef("urn:adcs:location:local:somehost")
    g.add((host, RTM.operatedBy, pu))

    rows = service_auspices(ds)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, ServiceAuspicesRow)
    assert r.service == str(svc)
    assert r.service_label == "Flexo MMS"
    assert r.hosting_org == str(pu)
    assert r.hosting_org_label == "Planetary Utilities"


def test_render_trust_summary_includes_service_auspices():
    summary = TrustSummary(
        evidence="urn:test:ev",
        technical=None,
        auspices=None,
        service_auspices=[ServiceAuspicesRow(
            service="urn:adcs:service:flexo-mms",
            service_label="Flexo MMS",
            hosting_org="urn:adcs:org:planetary-utilities",
            hosting_org_label="Planetary Utilities",
        )],
    )
    out = render_trust_summary(summary)
    assert "Service auspices:" in out
    assert "Flexo MMS: hosted under Planetary Utilities" in out


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
