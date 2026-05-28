"""StoreBackend protocol and factory."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from rdflib import Dataset


class BackendUnavailable(RuntimeError):
    """Preflight probe detected the backend is unreachable / misconfigured.

    Raised by `StoreBackend.probe()`. The runner catches this at startup,
    prints the backend's `describe()` output + the cause, and exits
    with code 2 (matches WP2's ROBOT fail-fast shape — the integration
    story must not silently degrade).
    """


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

    def probe(self) -> None:
        """Preflight reachability check; raise BackendUnavailable on failure.

        Called by the runner before Stage 1 so failure is fast and clear
        rather than discovered at the last stage. Implementations should
        be cheap (target seconds, not minutes) and report concrete causes
        (HTTP status, missing path, missing credentials).
        """
        ...

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
