"""StoreBackend protocol and factory."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from rdflib import Dataset


@runtime_checkable
class StoreBackend(Protocol):
    """Persistence target for the runtime RTM Dataset.

    Implementations:
      - LocalBackend  (default): writes .ttl + .trig files to a directory
      - FlexoBackend           : POSTs each named graph to Flexo MMS
      - FuskeiBackend          : PUTs each named graph via SPARQL Graph
                                  Store Protocol against Apache Jena Fuseki

    The runtime always builds the Dataset locally first. The backend is
    invoked at the end of the pipeline to persist results.
    """

    name: str

    def persist(self, ds: Dataset, output_dir: Path) -> dict:
        """Push `ds` to the persistence target.

        Returns a dict of {graph_iri: count_of_triples_persisted} for
        reporting / verification. `output_dir` is used by LocalBackend
        for file outputs; other backends may ignore it (but should still
        return the per-graph counts).
        """
        ...

    def describe(self) -> str:
        """Single-line human description for the Stage-0 narrative banner
        (e.g. 'Local filesystem at /path/to/output' or
        'Flexo MMS at http://localhost:8080/...')."""
        ...


def get_backend(name: str, **kwargs) -> StoreBackend:
    """Backend factory. Imports lazily so backend-specific dependencies
    (httpx for Flexo/Fuseki) aren't loaded when not needed."""
    if name == "local":
        from pipeline.backends.local import LocalBackend
        return LocalBackend(**kwargs)
    if name == "flexo":
        from pipeline.backends.flexo import FlexoBackend
        return FlexoBackend(**kwargs)
    if name == "fuseki":
        from pipeline.backends.fuseki import FuskeiBackend
        return FuskeiBackend(**kwargs)
    raise ValueError(f"Unknown backend {name!r}. Choose: local | flexo | fuseki")
