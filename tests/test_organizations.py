"""Organizational auspices loaders + emitters — per-service auspices.

The compute substrate (operating + hosting) and each remote service
(Flexo MMS, txnlog store) carry their own auspices, configured via
separate env vars. See compute/organizations.py.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

from compute.organizations import (
    OrgRef,
    emit_org_node,
    load_auspices,
    load_flexo_hosting_org,
    load_txnlog_hosting_org,
)
from ontology.prefixes import PROV

_FLEXO_VARS = (
    "ADCS_FLEXO_HOSTING_ORG_IRI",
    "ADCS_FLEXO_HOSTING_ORG_LABEL",
    "ADCS_FLEXO_HOSTING_ORG_DESCRIPTION",
)
_TXNLOG_VARS = (
    "ADCS_TXNLOG_HOSTING_ORG_IRI",
    "ADCS_TXNLOG_HOSTING_ORG_LABEL",
    "ADCS_TXNLOG_HOSTING_ORG_DESCRIPTION",
)


def test_load_flexo_hosting_org_returns_none_when_unset(monkeypatch):
    """Unset Flexo auspices = honest 'unknown', not a wrong default."""
    for var in _FLEXO_VARS:
        monkeypatch.delenv(var, raising=False)
    assert load_flexo_hosting_org() is None


def test_load_flexo_hosting_org_reads_env(monkeypatch):
    monkeypatch.setenv("ADCS_FLEXO_HOSTING_ORG_IRI", "urn:adcs:org:planetary-utilities")
    monkeypatch.setenv("ADCS_FLEXO_HOSTING_ORG_LABEL", "Planetary Utilities")
    monkeypatch.setenv("ADCS_FLEXO_HOSTING_ORG_DESCRIPTION", "Hosts the Flexo substrate.")
    org = load_flexo_hosting_org()
    assert isinstance(org, OrgRef)
    assert str(org.iri) == "urn:adcs:org:planetary-utilities"
    assert org.label == "Planetary Utilities"
    assert org.description == "Hosts the Flexo substrate."


def test_load_flexo_hosting_org_label_defaults_to_iri(monkeypatch):
    for var in _FLEXO_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ADCS_FLEXO_HOSTING_ORG_IRI", "urn:adcs:org:pu")
    org = load_flexo_hosting_org()
    assert org.label == "urn:adcs:org:pu"


def test_load_txnlog_hosting_org_falls_back_to_compute_substrate(monkeypatch):
    """The txnlog store runs on the local machine by default, so its
    auspices default to the compute-substrate hosting org."""
    for var in _TXNLOG_VARS:
        monkeypatch.delenv(var, raising=False)
    fallback = OrgRef(
        iri=URIRef("urn:adcs:org:local-operator"),
        label="Local Operator",
        description="fallback",
    )
    org = load_txnlog_hosting_org(fallback)
    assert org == fallback


def test_load_txnlog_hosting_org_reads_env(monkeypatch):
    monkeypatch.setenv("ADCS_TXNLOG_HOSTING_ORG_IRI", "urn:adcs:org:other-host")
    fallback = OrgRef(
        iri=URIRef("urn:adcs:org:local-operator"),
        label="Local Operator",
        description="fallback",
    )
    org = load_txnlog_hosting_org(fallback)
    assert str(org.iri) == "urn:adcs:org:other-host"


def test_emit_org_node_is_idempotent():
    g = Graph()
    iri = URIRef("urn:adcs:org:planetary-utilities")
    emit_org_node(g, iri, "Planetary Utilities", "Hosts the Flexo substrate.")
    n = len(g)
    emit_org_node(g, iri, "Planetary Utilities", "Hosts the Flexo substrate.")
    assert len(g) == n
    assert (iri, RDF.type, PROV.Organization) in g


def test_load_auspices_defaults_unchanged(monkeypatch):
    """Compute-substrate auspices keep their WP4 c6 defaults."""
    for var in (
        "ADCS_OPERATING_ORG_IRI", "ADCS_OPERATING_ORG_LABEL",
        "ADCS_OPERATING_ORG_DESCRIPTION", "ADCS_HOSTING_ORG_IRI",
        "ADCS_HOSTING_ORG_LABEL", "ADCS_HOSTING_ORG_DESCRIPTION",
    ):
        monkeypatch.delenv(var, raising=False)
    a = load_auspices()
    assert str(a.operating_iri) == "urn:adcs:org:local-operator"
    assert str(a.hosting_iri) == "urn:adcs:org:local-operator"
