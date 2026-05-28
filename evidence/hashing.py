"""Deterministic SHA-256 hashing for model identity and proof binding.

Pure functions — no state.

Evidence chain:
    structural graph (canonical N-Triples)
        -> hash_structural_model() -> model_hash
             -> hash_proof(script, model_hash) -> proof_hash
             -> hash_simulation(config, summary) -> sim_hash
                  -> hash_evidence(model_hash, proof_hash, sim_hash) -> evidence_hash

Reference: gds-proof/gds_proof/identity/hashing.py
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import sympy
from rdflib import Graph

if TYPE_CHECKING:
    from analysis.proof_scripts import ProofScript


# Default ignore patterns for hash_docker_image()'s build-context walk.
# Filenames matched by ANY of these globs are excluded from the manifest.
# Path components anywhere in the relative path also match — `.git/index`
# is excluded because its first component `.git` matches `.git`.
DOCKER_BUILD_CONTEXT_DEFAULT_IGNORES: tuple[str, ...] = (
    ".git",
    "__pycache__",
    "*.pyc",
    ".venv",
    "venv",
    "node_modules",
    ".docker-ipc",
    "output",
    ".DS_Store",
    ".pytest_cache",
    ".ruff_cache",
)


def _serialize_for_hash(data: dict) -> str:
    """JSON-serialize a dict deterministically for hashing."""
    return json.dumps(data, sort_keys=True, default=str)


def _ignored(rel_path: str, ignore_patterns: tuple[str, ...]) -> bool:
    """True if any path component (or the leaf) matches any ignore glob."""
    parts = rel_path.split(os.sep)
    for pat in ignore_patterns:
        # Match against the leaf (so `*.pyc` works), against each
        # intermediate component (so `.git` excludes `.git/index`), and
        # against the whole relative path (so `output/foo.txt` works).
        if fnmatch.fnmatch(parts[-1], pat):
            return True
        for part in parts[:-1]:
            if fnmatch.fnmatch(part, pat):
                return True
        if fnmatch.fnmatch(rel_path, pat):
            return True
    return False


def hash_docker_image(
    dockerfile_path: str | Path,
    build_context_root: str | Path,
    *,
    ignore_patterns: tuple[str, ...] = DOCKER_BUILD_CONTEXT_DEFAULT_IGNORES,
) -> tuple[str, str]:
    """Compute deterministic hashes for Docker build inputs.

    Returns ``(dockerfile_hash, build_context_hash)`` where:

    - ``dockerfile_hash`` is the SHA-256 of the Dockerfile bytes.
    - ``build_context_hash`` is the SHA-256 of a sorted manifest of
      ``<relative-path>\\t<file-sha256>`` lines for every file under
      ``build_context_root`` that is NOT matched by ``ignore_patterns``.

    These pin the **build inputs** — they're independent of the runtime
    image digest the Docker daemon assigns after build. The pair plus
    the resolved base-image digest are what makes a Docker image
    reproducibly identifiable.

    The manifest format is intentionally simple. If the demo adopts
    SLSA / in-toto envelopes in the future signing work item, that
    becomes the canonical envelope and this hash stays as a fast
    self-check.

    Raises ``FileNotFoundError`` if ``dockerfile_path`` does not exist.
    """
    dockerfile = Path(dockerfile_path)
    if not dockerfile.is_file():
        raise FileNotFoundError(f"Dockerfile not found: {dockerfile}")
    dockerfile_hash = hashlib.sha256(dockerfile.read_bytes()).hexdigest()

    context = Path(build_context_root).resolve()
    manifest_lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(context):
        # Prune ignored directories so we don't recurse into them.
        rel_dir = os.path.relpath(dirpath, context)
        dirnames[:] = [
            d for d in dirnames
            if not _ignored(
                d if rel_dir == "." else os.path.join(rel_dir, d),
                ignore_patterns,
            )
        ]
        for fname in filenames:
            rel = fname if rel_dir == "." else os.path.join(rel_dir, fname)
            if _ignored(rel, ignore_patterns):
                continue
            abs_path = Path(dirpath) / fname
            try:
                file_sha = hashlib.sha256(abs_path.read_bytes()).hexdigest()
            except (PermissionError, OSError):
                # Unreadable files (sockets, broken symlinks) are skipped;
                # their absence from the manifest is part of the hash's
                # determinism guarantee on the current host.
                continue
            # Normalize separator to forward-slash so the manifest is
            # the same on macOS/Linux/WSL.
            rel_posix = rel.replace(os.sep, "/")
            manifest_lines.append(f"{rel_posix}\t{file_sha}")

    manifest_lines.sort()
    manifest = "\n".join(manifest_lines) + "\n"
    build_context_hash = hashlib.sha256(manifest.encode("utf-8")).hexdigest()
    return dockerfile_hash, build_context_hash


def hash_structural_model(graph: Graph) -> str:
    """Deterministic SHA-256 hash of the structural RDF model.

    Produces a canonical hash by:
    1. Extracting all triples as (s, p, o) N-Triples strings
    2. Replacing blank node identifiers with a content-based hash of
       all non-blank triples reachable from that blank node
    3. Sorting and hashing the result

    For simplicity, we flatten blank-node subgraphs: triples involving
    blank nodes are replaced by their grounded content (the non-blank
    subjects/objects they ultimately connect).
    """
    from rdflib import BNode, URIRef, Literal

    # Collect grounded triples (no blank nodes) directly
    grounded_lines: list[str] = []

    # For blank-node triples, collect the chain of properties
    # and serialize as: subject -> predicate chain -> leaf values
    def _nt_term(term):
        if isinstance(term, URIRef):
            return f"<{term}>"
        if isinstance(term, Literal):
            if term.datatype:
                return f'"{term}"^^<{term.datatype}>'
            return f'"{term}"'
        return f"_:blank"  # placeholder, will be skipped

    def _collect_bnode_properties(bnode, visited=None):
        """Recursively collect all property-value pairs from a blank node."""
        if visited is None:
            visited = set()
        if bnode in visited:
            return []
        visited.add(bnode)
        pairs = []
        for p, o in graph.predicate_objects(bnode):
            if isinstance(o, BNode):
                sub_pairs = _collect_bnode_properties(o, visited)
                for sp_, so_ in sub_pairs:
                    pairs.append((f"{_nt_term(p)}/{sp_}", so_))
            else:
                pairs.append((_nt_term(p), _nt_term(o)))
        return sorted(pairs)

    for s, p, o in graph:
        if isinstance(s, BNode) and isinstance(o, BNode):
            continue  # skip pure blank-to-blank (will be captured via parent)
        if isinstance(s, BNode):
            continue  # blank subjects are captured when their parent references them
        if isinstance(o, BNode):
            # Inline the blank node's content
            props = _collect_bnode_properties(o)
            for prop_path, value in props:
                grounded_lines.append(f"{_nt_term(s)} {_nt_term(p)}/{prop_path} {value} .")
        else:
            grounded_lines.append(f"{_nt_term(s)} {_nt_term(p)} {_nt_term(o)} .")

    canonical = "\n".join(sorted(grounded_lines))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_proof(script: ProofScript, model_hash: str) -> str:
    """Deterministic SHA-256 binding a proof script to a model version.

    Hashes lemma chain content together with model_hash.
    """
    lemma_records: list[dict[str, Any]] = []
    for lemma in script.lemmas:
        lemma_records.append(
            {
                "name": lemma.name,
                "kind": lemma.kind.value,
                "expr": sympy.srepr(lemma.expr),
                "expected": (
                    sympy.srepr(lemma.expected)
                    if lemma.expected is not None
                    else None
                ),
                "assumptions": lemma.assumptions,
                "depends_on": sorted(lemma.depends_on),
            }
        )
    data: dict[str, Any] = {
        "model_hash": model_hash,
        "target_invariant": script.target_invariant,
        "lemmas": lemma_records,
    }
    serialized = _serialize_for_hash(data)
    return hashlib.sha256(serialized.encode()).hexdigest()


def hash_simulation(
    sim_config: dict[str, Any],
    results_summary: dict[str, Any],
) -> str:
    """SHA-256 hash of simulation configuration + summary results."""
    data = {
        "config": sim_config,
        "results_summary": results_summary,
    }
    serialized = _serialize_for_hash(data)
    return hashlib.sha256(serialized.encode()).hexdigest()


def hash_evidence(
    model_hash: str,
    proof_hash: str | None = None,
    sim_hash: str | None = None,
) -> str:
    """Combined evidence hash from model, proof, and simulation hashes."""
    data: dict[str, str | None] = {
        "model_hash": model_hash,
        "proof_hash": proof_hash,
        "sim_hash": sim_hash,
    }
    serialized = _serialize_for_hash(data)
    return hashlib.sha256(serialized.encode()).hexdigest()
