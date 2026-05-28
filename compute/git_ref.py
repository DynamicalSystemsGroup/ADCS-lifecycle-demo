"""Capture the current git ref as a URI pointing at a file at a commit.

WP4 §4.3 — the `rtm:DockerImage` node's `rtm:gitRef` property points at
the Dockerfile (or any file) in the source tree at the exact commit the
image was built from. This is the "code remote" half of the three-remote
provenance chain: image content → git ref → reproducer can `git checkout`
and rebuild to verify the recorded digest matches.

Shape produced (when remote configured):

    git+https://github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo@<sha>#<path>

Fallback shapes (graceful degrade rather than failing the build):
    git+file://<repo_root>@<sha>#<path>     when no remote configured
    git+local://unknown@<sha>#<path>        when running outside a git repo
    git+local://unknown@uncommitted#<path>  when not in a git repo at all
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> str | None:
    """Run a git subcommand; return stripped stdout or None on failure."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None


def _normalize_remote_url(url: str) -> str:
    """Turn `git@github.com:Org/Repo.git` into `https://github.com/Org/Repo`.

    The literal-URI form we emit is the https one so downstream consumers
    can resolve it without an ssh key.
    """
    if url.startswith("git@"):
        host_and_path = url[4:]  # strip "git@"
        if ":" in host_and_path:
            host, path = host_and_path.split(":", 1)
            url = f"https://{host}/{path}"
    if url.endswith(".git"):
        url = url[:-4]
    return url


def current_git_ref(repo_root: Path | str, file_path: str = "") -> str:
    """Return the git+URI literal for the file at the current HEAD commit.

    `file_path` is the repo-relative path of the file the URI fragment
    should point at (e.g. "compute/Dockerfile"). Empty string means
    "no specific file" — the URI points at the repo root at this commit.
    """
    repo_root = Path(repo_root).resolve()
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if sha is None:
        # Not a git repo or git not installed
        suffix = f"#{file_path}" if file_path else ""
        return f"git+local://unknown@uncommitted{suffix}"

    remote = _run(["git", "config", "--get", "remote.origin.url"], cwd=repo_root)
    suffix = f"#{file_path}" if file_path else ""

    if remote is None:
        # Repo exists but no remote configured — fall back to file://
        return f"git+file://{repo_root}@{sha}{suffix}"

    base = _normalize_remote_url(remote)
    return f"git+{base}@{sha}{suffix}"
