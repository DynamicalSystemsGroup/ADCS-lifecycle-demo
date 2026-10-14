"""Minimal client for the Flexo SysML v2 API: publish full snapshots, diff by element @id.

Env: FLEXO_V2_URL (default http://localhost:8083), FLEXO_V2_TOKEN (optional bearer).
"""

from __future__ import annotations

import json
import os

import httpx

TAG_PREFIX = "git-"


class FlexoV2:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        base_url = base_url or os.environ.get("FLEXO_V2_URL", "http://localhost:8083")
        token = token or os.environ.get("FLEXO_V2_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=60)

    def _json(self, method: str, path: str, **kw):
        r = self._http.request(method, path, **kw)
        r.raise_for_status()
        return r.json()

    def ensure_project(self, name: str) -> str:
        """Id of the project called `name`; created if absent."""
        for p in self._json("GET", "/projects"):
            if p["name"] == name:
                return p["@id"]
        return self._json("POST", "/projects", json={"@type": "Project", "name": name})["@id"]

    def publish(self, project_id: str, elements: list[dict], message: str, git_sha: str) -> str:
        """Commit `elements` as the complete model (?replace=true); return the commit id.

        The Git SHA goes in the commit description (`"<message> [git:<sha>]"`) and in a
        tag `git-<sha>` on the commit. The tag is the reliable carrier: the stack's
        commit description is dropped (see FLEXO_LOCAL.md).
        """
        change = [{"@type": "DataVersion", "identity": {"@id": e["@id"]}, "payload": e}
                  for e in elements]
        commit = self._json(
            "POST", f"/projects/{project_id}/commits", params={"replace": "true"},
            json={"@type": "Commit", "description": f"{message} [git:{git_sha}]", "change": change},
        )
        self._json("POST", f"/projects/{project_id}/tags", json={
            "@type": "Tag", "name": f"{TAG_PREFIX}{git_sha}", "taggedCommit": {"@id": commit["@id"]},
        })
        return commit["@id"]

    def elements(self, project_id: str, commit_id: str) -> dict[str, dict]:
        """All elements at a commit, keyed by @id."""
        rows = self._json("GET", f"/projects/{project_id}/commits/{commit_id}/elements")
        return {e["@id"]: e for e in rows}

    def git_sha(self, project_id: str, commit_id: str) -> str | None:
        """Git SHA recorded for a commit: from its description if present, else its tag."""
        c = self._json("GET", f"/projects/{project_id}/commits/{commit_id}")
        d = c.get("description") or ""
        if "[git:" in d:
            return d.rsplit("[git:", 1)[1].rstrip("]")
        for t in self._json("GET", f"/projects/{project_id}/tags"):
            if t["taggedCommit"]["@id"] == commit_id and t["name"].startswith(TAG_PREFIX):
                return t["name"][len(TAG_PREFIX):]
        return None


def _norm(v):
    """Canonical form: the store keeps multi-valued properties as RDF sets, so list
    order (and duplicates) are not meaningful. Sort lists, recursively."""
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return sorted({json.dumps(_norm(x), sort_keys=True) for x in v})
    return v


def diff(a: dict[str, dict], b: dict[str, dict]) -> dict[str, list[str]]:
    """Element-level diff of two snapshots keyed by @id."""
    return {
        "added": sorted(b.keys() - a.keys()),
        "removed": sorted(a.keys() - b.keys()),
        "changed": sorted(i for i in a.keys() & b.keys() if _norm(a[i]) != _norm(b[i])),
    }
