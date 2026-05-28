"""Organizational auspices for the three-remote provenance chain.

WP4 §"Organizational auspices" — every run carries two organization
identities:

- **operating org**: who runs the container / authors the work
  (default: urn:adcs:org:local-operator)
- **hosting org**: who operates the substrate (host machine + Docker
  daemon). Defaults to the operating org for the single-operator
  demo; configurable to demonstrate the Starforge future state where
  Planetary Utilities hosts but the operator is a different org.

Both IRIs are emitted into <adcs:context> as `prov:Organization`
nodes the first time they're referenced; the IRIs themselves are
stable, so cross-run references accumulate cleanly.

Edge contract (wired in evidence/binding.py):

  <container> prov:wasAttributedTo  <operating-org>
  <host>      rtm:operatedBy        <hosting-org>
  <executor>  prov:actedOnBehalfOf  <operating-org>
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from ontology.prefixes import DCTERMS, PROV

DEFAULT_OPERATING_ORG = "urn:adcs:org:local-operator"
DEFAULT_OPERATING_ORG_LABEL = "Local Operator"
DEFAULT_OPERATING_ORG_DESCRIPTION = (
    "Single-operator workstation; no hosted substrate. "
    "The default auspices when neither ADCS_OPERATING_ORG_IRI nor "
    "ADCS_HOSTING_ORG_IRI is set."
)


@dataclass(frozen=True)
class Auspices:
    """Operating + hosting organization IRIs + their display strings."""
    operating_iri: URIRef
    operating_label: str
    operating_description: str
    hosting_iri: URIRef
    hosting_label: str
    hosting_description: str


def load_auspices() -> Auspices:
    """Read the four ADCS_*_ORG_* env vars and build an Auspices record.

    Defaults: operating + hosting both = `urn:adcs:org:local-operator`.
    When the user sets ADCS_HOSTING_ORG_IRI to a different value (e.g.
    `urn:adcs:org:planetary-utilities`), the demo's auspices chain
    splits: operating stays local-operator, hosting flips to PU.
    """
    operating_iri = URIRef(
        os.environ.get("ADCS_OPERATING_ORG_IRI", DEFAULT_OPERATING_ORG)
    )
    operating_label = os.environ.get(
        "ADCS_OPERATING_ORG_LABEL",
        DEFAULT_OPERATING_ORG_LABEL if str(operating_iri) == DEFAULT_OPERATING_ORG
        else str(operating_iri),
    )
    operating_description = os.environ.get(
        "ADCS_OPERATING_ORG_DESCRIPTION",
        DEFAULT_OPERATING_ORG_DESCRIPTION if str(operating_iri) == DEFAULT_OPERATING_ORG
        else "Operating organization for this run (from ADCS_OPERATING_ORG_IRI).",
    )

    hosting_iri_str = os.environ.get("ADCS_HOSTING_ORG_IRI")
    if hosting_iri_str is None:
        hosting_iri = operating_iri
        hosting_label = operating_label
        hosting_description = operating_description
    else:
        hosting_iri = URIRef(hosting_iri_str)
        hosting_label = os.environ.get(
            "ADCS_HOSTING_ORG_LABEL", str(hosting_iri),
        )
        hosting_description = os.environ.get(
            "ADCS_HOSTING_ORG_DESCRIPTION",
            "Hosting organization for this run (from ADCS_HOSTING_ORG_IRI).",
        )

    return Auspices(
        operating_iri=operating_iri,
        operating_label=operating_label,
        operating_description=operating_description,
        hosting_iri=hosting_iri,
        hosting_label=hosting_label,
        hosting_description=hosting_description,
    )


def emit_org_nodes(graph: Graph, auspices: Auspices) -> None:
    """Emit prov:Organization typing + labels for both org IRIs.

    Idempotent at the RDF level (re-adding the same triple is a no-op
    in rdflib). Run once per pipeline run at startup; downstream edges
    reference these IRIs without re-emitting the nodes.
    """
    for iri, label, desc in (
        (auspices.operating_iri, auspices.operating_label, auspices.operating_description),
        (auspices.hosting_iri, auspices.hosting_label, auspices.hosting_description),
    ):
        graph.add((iri, RDF.type, PROV.Organization))
        graph.add((iri, RDFS.label, Literal(label)))
        if desc:
            graph.add((iri, DCTERMS.description, Literal(desc)))
