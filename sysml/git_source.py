"""Git helper: the source side of the Git/Flexo split. Git versions the .sysml text."""

from __future__ import annotations

import difflib
import subprocess


def head_sha(path: str = ".") -> str:
    """Full SHA of HEAD for the repository containing `path`."""
    return subprocess.run(
        ["git", "-C", path, "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def text_diff(old: str, new: str, name: str = "satellite.sysml", n: int = 3) -> str:
    """Unified diff of two source texts (`n` context lines); empty string when identical."""
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{name}", tofile=f"b/{name}", n=n,
    ))


def is_dirty(path: str = ".") -> bool:
    """True when the source files (`sysml/`, `talk.py`) have uncommitted changes."""
    return bool(subprocess.run(
        ["git", "-C", path, "status", "--porcelain", "--", "sysml", "talk.py"],
        check=True, capture_output=True, text=True,
    ).stdout.strip())
