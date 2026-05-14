"""Compute backends — local in-process vs. Docker-emulated remote.

Mirrors the pattern used by pipeline.backends: a Protocol plus a small
factory. LocalCompute runs analysis in-process; DockerCompute runs it
inside a container and captures execution metadata (image digest,
hostname, container ID) for RTM provenance. The captured metadata is
attached to each analysis activity so the attestation records exactly
where and how the evidence was produced.

Public API:
  ComputeBackend       Protocol
  ExecutionMetadata    dataclass returned by every compute run
  get_compute_backend  factory
"""

from compute.base import (  # noqa: F401
    ComputeBackend,
    ExecutionMetadata,
    get_compute_backend,
)
