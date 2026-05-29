"""WP3: rtm:DockerImage as tracked evidence — issue #4 ACs 1-6, 9.

Hash-determinism + graph-structure tests run without Docker. The
end-to-end pipeline integration tests (image emission, evidence link
back to image, SHACL closure rule) require a live Docker daemon and
are marked @pytest.mark.live — opted-in via `uv run pytest -m live`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence.hashing import (
    DOCKER_BUILD_CONTEXT_DEFAULT_IGNORES,
    hash_docker_image,
)


# ---------------------------------------------------------------------------
# AC2: hash_docker_image determinism + sensitivity
# ---------------------------------------------------------------------------

def _setup_minimal_context(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal Dockerfile + 3-file context under tmp_path. Returns
    (dockerfile, context_root)."""
    df = tmp_path / "Dockerfile"
    df.write_text(
        "FROM python:3.12-slim\n"
        "WORKDIR /work\n"
        "COPY . .\n"
        'CMD ["python", "-m", "pipeline.runner"]\n'
    )
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "a.py").write_text("x = 1\n")
    (ctx / "b.py").write_text("y = 2\n")
    sub = ctx / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("z = 3\n")
    return df, ctx


def test_hash_docker_image_is_deterministic(tmp_path):
    df, ctx = _setup_minimal_context(tmp_path)
    h1 = hash_docker_image(df, ctx)
    h2 = hash_docker_image(df, ctx)
    assert h1 == h2
    assert isinstance(h1[0], str) and len(h1[0]) == 64
    assert isinstance(h1[1], str) and len(h1[1]) == 64


def test_hash_docker_image_detects_dockerfile_change(tmp_path):
    df, ctx = _setup_minimal_context(tmp_path)
    h_before = hash_docker_image(df, ctx)
    df.write_text(df.read_text() + "\n# trailing comment\n")
    h_after = hash_docker_image(df, ctx)
    assert h_before[0] != h_after[0]
    assert h_before[1] == h_after[1]


def test_hash_docker_image_detects_context_change(tmp_path):
    df, ctx = _setup_minimal_context(tmp_path)
    h_before = hash_docker_image(df, ctx)
    (ctx / "a.py").write_text("x = 999\n")
    h_after = hash_docker_image(df, ctx)
    assert h_before[0] == h_after[0]
    assert h_before[1] != h_after[1]


def test_hash_docker_image_detects_new_file_in_context(tmp_path):
    df, ctx = _setup_minimal_context(tmp_path)
    h_before = hash_docker_image(df, ctx)
    (ctx / "d.py").write_text("w = 4\n")
    h_after = hash_docker_image(df, ctx)
    assert h_before[1] != h_after[1]


def test_hash_docker_image_ignores_default_patterns(tmp_path):
    """.git, __pycache__, *.pyc, .venv, output, .DS_Store are excluded."""
    df, ctx = _setup_minimal_context(tmp_path)
    h_clean = hash_docker_image(df, ctx)

    (ctx / ".git").mkdir()
    (ctx / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (ctx / "__pycache__").mkdir()
    (ctx / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00\x01\x02")
    (ctx / "a.pyc").write_bytes(b"\xab\xcd")
    (ctx / ".venv").mkdir()
    (ctx / ".venv" / "pyvenv.cfg").write_text("home = /usr/local/bin\n")
    (ctx / "node_modules").mkdir()
    (ctx / "node_modules" / "lib.js").write_text("module.exports = {}\n")
    (ctx / "output").mkdir()
    (ctx / "output" / "report.md").write_text("# stale output\n")
    (ctx / ".DS_Store").write_bytes(b"\x00" * 16)

    h_with_noise = hash_docker_image(df, ctx)
    assert h_clean == h_with_noise, (
        "Default ignore patterns failed to filter junk; clean vs noise hashes diverged."
    )


def test_hash_docker_image_custom_ignore_pattern(tmp_path):
    df, ctx = _setup_minimal_context(tmp_path)
    (ctx / "secret.env").write_text("API_KEY=xxx\n")
    h_with_secret = hash_docker_image(df, ctx)
    h_excluding_secret = hash_docker_image(
        df, ctx, ignore_patterns=DOCKER_BUILD_CONTEXT_DEFAULT_IGNORES + ("*.env",),
    )
    assert h_with_secret != h_excluding_secret


def test_hash_docker_image_missing_dockerfile_raises(tmp_path):
    nonexistent = tmp_path / "nope.Dockerfile"
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    with pytest.raises(FileNotFoundError):
        hash_docker_image(nonexistent, ctx)


def test_hash_docker_image_against_repo_dockerfile():
    """Smoke test against the repo's actual compute/Dockerfile + project
    root. Catches obviously broken paths (e.g., empty manifest)."""
    ROOT = Path(__file__).resolve().parent.parent
    df = ROOT / "compute" / "Dockerfile"
    if not df.exists():
        pytest.skip("Repo Dockerfile not present (unexpected on this branch)")
    dockerfile_hash, context_hash = hash_docker_image(df, ROOT)
    assert len(dockerfile_hash) == 64
    assert len(context_hash) == 64
    assert dockerfile_hash != context_hash


# ---------------------------------------------------------------------------
# AC5: evidence_by_image SPARQL helper
# ---------------------------------------------------------------------------

def _build_image_evidence_dataset():
    """Synthesize a minimal dataset with two images and three evidence
    nodes — two derived from image A, one from image B — plus one
    evidence node with no wasDerivedFrom edge (negative case)."""
    from rdflib import Dataset, Literal, URIRef
    from rdflib.namespace import RDF
    from ontology.prefixes import ADCS, PROV, RTM, bind_prefixes

    ds = Dataset(default_union=True)
    bind_prefixes(ds)
    g = ds.graph(URIRef("urn:adcs:test-evidence"))

    img_a = URIRef("urn:adcs:docker-image:sha256-aaaa")
    img_b = URIRef("urn:adcs:docker-image:sha256-bbbb")
    for img, digest in [(img_a, "sha256:aaaa"), (img_b, "sha256:bbbb")]:
        g.add((img, RDF.type, RTM.DockerImage))
        g.add((img, RDF.type, PROV.Entity))
        g.add((img, RTM.contentHash, Literal(digest)))

    def _add_ev(ev_iri, ev_type, model_hash, content_hash, derived_from=None):
        g.add((ev_iri, RDF.type, ev_type))
        g.add((ev_iri, RTM.modelHash, Literal(model_hash)))
        g.add((ev_iri, RTM.contentHash, Literal(content_hash)))
        if derived_from is not None:
            g.add((ev_iri, PROV.wasDerivedFrom, derived_from))

    _add_ev(ADCS["EV-PROOF-001"], RTM.ProofArtifact, "m1", "c1", img_a)
    _add_ev(ADCS["EV-SIM-001"], RTM.SimulationResult, "m1", "c2", img_a)
    _add_ev(ADCS["EV-PROOF-002"], RTM.ProofArtifact, "m1", "c3", img_b)
    # Unlinked: not derived from any image (local-compute style).
    _add_ev(ADCS["EV-PROOF-003"], RTM.ProofArtifact, "m1", "c4", None)
    return ds


def test_evidence_by_image_returns_linked_evidence():
    from traceability.queries import evidence_by_image
    ds = _build_image_evidence_dataset()
    rows_a = evidence_by_image(ds, "sha256:aaaa")
    # Image A has 2 derived evidence nodes; image B has 1; unlinked is
    # invisible to all queries.
    assert len(rows_a) == 2, f"expected 2 rows for image A, got {len(rows_a)}: {rows_a}"
    contents = {r["evContentHash"] for r in rows_a}
    assert contents == {"c1", "c2"}


def test_evidence_by_image_isolates_by_digest():
    from traceability.queries import evidence_by_image
    ds = _build_image_evidence_dataset()
    rows_b = evidence_by_image(ds, "sha256:bbbb")
    assert len(rows_b) == 1
    assert rows_b[0]["evContentHash"] == "c3"


def test_evidence_by_image_miss_returns_empty_list():
    from traceability.queries import evidence_by_image
    ds = _build_image_evidence_dataset()
    rows = evidence_by_image(ds, "sha256:does-not-exist")
    assert rows == []


def test_evidence_by_image_skips_unlinked_evidence():
    """Evidence with no prov:wasDerivedFrom must never appear in any
    image's result set — even if the digest filter would match
    something else. EV-PROOF-003 in the fixture has no edge."""
    from traceability.queries import evidence_by_image
    ds = _build_image_evidence_dataset()
    # Try every present digest; EV-PROOF-003's contentHash ("c4") must
    # never appear.
    for digest in ("sha256:aaaa", "sha256:bbbb"):
        rows = evidence_by_image(ds, digest)
        assert all(r["evContentHash"] != "c4" for r in rows)
