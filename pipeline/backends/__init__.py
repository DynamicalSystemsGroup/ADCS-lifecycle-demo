"""Pluggable persistence backends for the RTM Dataset.

The runtime always builds the Dataset locally (in-memory rdflib). The
backend's job is to *persist* that dataset — writing to disk for the
local case, posting named graphs to Flexo MMS for the production case,
or PUTting via SPARQL Graph Store Protocol to bare Apache Jena Fuseki.

The choice of backend is transparent to every other stage: SPARQL
queries, SHACL validation, and the audit module all continue to run
against the local Dataset. Backend integration is the persistence step
at the end of the pipeline.

Selection: `--backend={local,flexo,fuseki}` on the CLI (default: local).
"""

from pipeline.backends.base import StoreBackend, get_backend  # noqa: F401
