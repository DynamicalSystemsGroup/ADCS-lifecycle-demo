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
