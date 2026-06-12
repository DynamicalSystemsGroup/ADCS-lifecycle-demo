"""Organizational auspices for the three-remote provenance chain.

WP4 §"Organizational auspices" — auspices are **per substrate**: each
service/host carries the auspices of the organization that actually
operates it, configured by separate env-var groups:

- **operating org** (`ADCS_OPERATING_ORG_*`): who runs the pipeline /
  authors the work (default: urn:adcs:org:local-operator).
- **hosting org** (`ADCS_HOSTING_ORG_*`): who operates the **compute
  substrate** — the machine (and Docker daemon) the analysis ran on.
  Defaults to the operating org for the single-operator demo.
- **Flexo hosting org** (`ADCS_FLEXO_HOSTING_ORG_*`): who operates the
  remote Flexo MMS substrate (e.g. Planetary Utilities for the
  Starforge instance). Unset = unknown — the service node is still
  emitted, just without an auspices edge. NOTE: `FLEXO_ORG` is the
  Flexo MMS org *slug* (a REST path segment like `adcs-demo`), not an
  auspices IRI; the two are unrelated.
- **txnlog hosting org** (`ADCS_TXNLOG_HOSTING_ORG_*`): who operates
  the transaction-log store; defaults to the compute-substrate hosting
  org (the demo's CouchDB runs on the local machine).

All org IRIs are emitted into <adcs:context> as `prov:Organization`
nodes the first time they're referenced; the IRIs themselves are
stable, so cross-run references accumulate cleanly.

Edge contract (compute edges wired in evidence/binding.py; service
edges in each backend's emit_service_node):

  <container>      prov:wasAttributedTo  <operating-org>
  <compute-host>   rtm:operatedBy        <hosting-org>
  <executor>       prov:actedOnBehalfOf  <operating-org>
  <flexo-service>  rtm:operatedBy        <flexo-hosting-org>
  <txnlog-service> rtm:operatedBy        <txnlog-hosting-org>
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
class OrgRef:
    """One organization: IRI + display strings."""
    iri: URIRef
    label: str
    description: str


@dataclass(frozen=True)
class Auspices:
    """Compute-substrate operating + hosting organization IRIs."""
    operating_iri: URIRef
    operating_label: str
    operating_description: str
    hosting_iri: URIRef
    hosting_label: str
    hosting_description: str


def _load_org(env_prefix: str) -> OrgRef | None:
    """Read <prefix>_IRI/_LABEL/_DESCRIPTION; None when the IRI is unset."""
    iri_str = os.environ.get(f"{env_prefix}_IRI")
    if iri_str is None:
        return None
    return OrgRef(
        iri=URIRef(iri_str),
        label=os.environ.get(f"{env_prefix}_LABEL", iri_str),
        description=os.environ.get(
            f"{env_prefix}_DESCRIPTION",
            f"Organization for this run (from {env_prefix}_IRI).",
        ),
    )


def load_flexo_hosting_org() -> OrgRef | None:
    """Auspices of the Flexo MMS substrate (ADCS_FLEXO_HOSTING_ORG_*).

    None when unset — the Flexo service node is still emitted, just
    without an rtm:operatedBy edge (honest "unknown" beats a wrong
    default). Not to be confused with FLEXO_ORG, the Flexo MMS org
    slug used in REST paths.
    """
    return _load_org("ADCS_FLEXO_HOSTING_ORG")


def load_txnlog_hosting_org(fallback: OrgRef) -> OrgRef:
    """Auspices of the txnlog substrate (ADCS_TXNLOG_HOSTING_ORG_*).

    Defaults to the compute-substrate hosting org — the demo's CouchDB
    runs on the local machine.
    """
    return _load_org("ADCS_TXNLOG_HOSTING_ORG") or fallback


def load_auspices() -> Auspices:
    """Read the compute-substrate ADCS_*_ORG_* env vars.

    Defaults: operating + hosting both = `urn:adcs:org:local-operator`.
    ADCS_HOSTING_ORG_IRI only changes who operates the **compute**
    substrate (the machine the analysis runs on); the Flexo and txnlog
    substrates have their own loaders above.
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


def emit_org_node(graph: Graph, iri: URIRef, label: str, description: str) -> None:
    """Emit one prov:Organization node (typing + labels).

    Idempotent at the RDF level (re-adding the same triple is a no-op
    in rdflib).
    """
    graph.add((iri, RDF.type, PROV.Organization))
    graph.add((iri, RDFS.label, Literal(label)))
    if description:
        graph.add((iri, DCTERMS.description, Literal(description)))


def emit_org_nodes(graph: Graph, auspices: Auspices) -> None:
    """Emit prov:Organization typing + labels for both compute-substrate
    org IRIs. Run once per pipeline run at startup; downstream edges
    reference these IRIs without re-emitting the nodes.
    """
    emit_org_node(graph, auspices.operating_iri,
                  auspices.operating_label, auspices.operating_description)
    emit_org_node(graph, auspices.hosting_iri,
                  auspices.hosting_label, auspices.hosting_description)
