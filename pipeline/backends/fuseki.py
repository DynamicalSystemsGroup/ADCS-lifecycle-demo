"""FuskeiBackend — push each named graph to a bare Apache Jena Fuseki
via SPARQL 1.1 Graph Store Protocol.

This backend exists as the no-Docker fallback: Fuseki is what Flexo MMS
wraps under the hood, and exercising the same persistence path against
a bare Fuseki proves the design is not coupled to Flexo's specific
auth / org hierarchy.

Configuration via environment / kwargs:
  - FUSEKI_URL      base URL, e.g. http://localhost:3030/adcs
  - FUSEKI_USER     optional basic-auth username
  - FUSEKI_PASS     optional basic-auth password

SPARQL Graph Store Protocol: PUT <baseURL>/data?graph=<iri> with
Content-Type: text/turtle.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from rdflib import Dataset, URIRef

from pipeline.dataset import triples_by_graph


class FuskeiBackend:
    name = "fuseki"

    def __init__(
        self,
        url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.url = (url or os.environ.get("FUSEKI_URL", "http://localhost:3030/adcs")).rstrip("/")
        self.user = user or os.environ.get("FUSEKI_USER")
        self.password = password or os.environ.get("FUSEKI_PASS")
        self.timeout = timeout

    def _auth(self) -> tuple[str, str] | None:
        if self.user is not None and self.password is not None:
            return (self.user, self.password)
        return None

    def persist(self, ds: Dataset, output_dir: Path) -> dict:
        """PUT each non-empty named graph via SPARQL Graph Store Protocol."""
        counts = triples_by_graph(ds)
        persisted: dict[str, int] = {}
        with httpx.Client(timeout=self.timeout, auth=self._auth()) as client:
            for graph_iri, count in counts.items():
                turtle_bytes = ds.graph(URIRef(graph_iri)).serialize(format="turtle")
                if isinstance(turtle_bytes, str):
                    turtle_bytes = turtle_bytes.encode("utf-8")
                response = client.put(
                    f"{self.url}/data",
                    params={"graph": graph_iri},
                    headers={"Content-Type": "text/turtle"},
                    content=turtle_bytes,
                )
                response.raise_for_status()
                persisted[graph_iri] = count
        return persisted

    def describe(self) -> str:
        return f"Apache Jena Fuseki at {self.url} (SPARQL 1.1 Graph Store Protocol)"
