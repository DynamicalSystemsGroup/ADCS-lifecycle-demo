"""Minimal client for the Flexo SysML v2 API: publish full snapshots, diff by element @id.

Env: FLEXO_V2_URL (default http://localhost:8083), FLEXO_V2_TOKEN (optional bearer).
"""

from __future__ import annotations

import os

import httpx

TAG_PREFIX = "git-"


class NoChangeError(Exception):
    """The snapshot is identical to the branch head, so Flexo creates no commit."""


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

        Each Flexo commit is tagged with the Git SHA (tag `git-<sha>`). Raises NoChangeError
        when the snapshot is identical to the head (the service answers 404, no commit).
        """
        change = [{"@type": "DataVersion", "identity": {"@id": e["@id"]}, "payload": e}
                  for e in elements]
        # `message` is sent as the commit description; the stack does not store it (FLEXO_LOCAL.md).
        r = self._http.post(
            f"/projects/{project_id}/commits", params={"replace": "true"},
            json={"@type": "Commit", "description": message, "change": change},
        )
        if r.status_code == 404:
            raise NoChangeError("snapshot identical to head")
        r.raise_for_status()
        commit = r.json()
        self._json("POST", f"/projects/{project_id}/tags", json={
            "@type": "Tag", "name": f"{TAG_PREFIX}{git_sha}", "taggedCommit": {"@id": commit["@id"]},
        })
        return commit["@id"]

    def elements(self, project_id: str, commit_id: str) -> dict[str, dict]:
        """All elements at a commit, keyed by @id."""
        rows = self._json("GET", f"/projects/{project_id}/commits/{commit_id}/elements")
        return {e["@id"]: e for e in rows}

    def git_sha(self, project_id: str, commit_id: str) -> str | None:
        """Git SHA a commit is tagged with (`git-<sha>`), or None."""
        for t in self._json("GET", f"/projects/{project_id}/tags"):
            if t["taggedCommit"]["@id"] == commit_id and t["name"].startswith(TAG_PREFIX):
                return t["name"][len(TAG_PREFIX):]
        return None

    def delete_project(self, project_id: str) -> None:
        """Delete a project (raises on HTTP error)."""
        self._http.delete(f"/projects/{project_id}").raise_for_status()


def diff(a: dict[str, dict], b: dict[str, dict]) -> dict[str, list[str]]:
    """Element-level diff of two snapshots keyed by @id. Values are compared raw: SysML v2
    features such as ownedRelationship are ordered, so a reorder is a real change."""
    return {
        "added": sorted(b.keys() - a.keys()),
        "removed": sorted(a.keys() - b.keys()),
        "changed": sorted(i for i in a.keys() & b.keys() if a[i] != b[i]),
    }
