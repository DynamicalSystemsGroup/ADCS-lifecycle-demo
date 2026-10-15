"""Load structural parameters from RDF via SPARQL.

Reads all sysml:AttributeUsage values from the structural graph and returns
them as a flat dictionary keyed by sysml:declaredName.
"""

from __future__ import annotations

import threading
from pathlib import Path

from rdflib import Graph

from ontology.prefixes import SYSML, bind_prefixes

STRUCTURAL_DIR = Path(__file__).resolve().parent.parent / "structural"

# rdflib's SPARQL parser (pyparsing) is not thread-safe: two sessions loading at once in one
# process (e.g. two browser tabs on `marimo run`) can raise a spurious ParseException.
_QUERY_LOCK = threading.Lock()

_PARAM_QUERY = """
SELECT ?name ?value ?unit WHERE {
    ?attr a sysml:AttributeUsage ;
          sysml:declaredName ?name ;
          sysml:value ?value .
    OPTIONAL { ?attr sysml:unit ?unit }
}
"""


def load_structural_graph() -> Graph:
    """Parse all .ttl files in structural/ into a single graph."""
    g = Graph()
    bind_prefixes(g)
    for ttl in sorted(STRUCTURAL_DIR.glob("*.ttl")):
        g.parse(ttl, format="turtle")
    return g


def load_params(graph: Graph | None = None) -> dict[str, float]:
    """Extract all structural parameters as {name: float_value}.

    If *graph* is None, loads from the structural/ directory.
    """
    if graph is None:
        graph = load_structural_graph()

    params: dict[str, float] = {}
    with _QUERY_LOCK:
        rows = list(graph.query(_PARAM_QUERY, initNs={"sysml": SYSML}))
    for row in rows:
        params[str(row.name)] = float(row.value)
    return params


def load_params_with_units(graph: Graph | None = None) -> dict[str, tuple[float, str]]:
    """Extract all structural parameters as {name: (value, unit)}."""
    if graph is None:
        graph = load_structural_graph()

    params: dict[str, tuple[float, str]] = {}
    for row in graph.query(_PARAM_QUERY, initNs={"sysml": SYSML}):
        unit = str(row.unit) if row.unit else ""
        params[str(row.name)] = (float(row.value), unit)
    return params
