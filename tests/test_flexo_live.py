"""Phase J — opt-in live Flexo test.

Skips cleanly when there is no reachable Flexo instance. When the
demo is configured against a live Flexo (remote starforge via
FLEXO_TOKEN, or local Compose at FLEXO_URL=http://localhost:8080),
this test runs the full pipeline with --backend=flexo and verifies
that data lands by querying the loaded branches back.

Run explicitly:

    # Against the remote starforge collaboration target:
    export FLEXO_TOKEN="eyJhbGci..."
    uv run pytest tests/test_flexo_live.py -v

    # Against a local Compose stack:
    export FLEXO_URL=http://localhost:8080
    export FLEXO_AUTH_URL=http://localhost:8082
    unset FLEXO_TOKEN
    uv run pytest tests/test_flexo_live.py -v
"""

from __future__ import annotations

import os
import warnings

import httpx
import pytest

from pipeline.runner import run_pipeline

FLEXO_URL = os.environ.get("FLEXO_URL", "https://try-layer1.starforge.app").rstrip("/")
FLEXO_AUTH_URL = os.environ.get("FLEXO_AUTH_URL", "http://localhost:8082").rstrip("/")
FLEXO_TOKEN = os.environ.get("FLEXO_TOKEN", "")
FLEXO_USER = os.environ.get("FLEXO_USER", "user01")
FLEXO_PASS = os.environ.get("FLEXO_PASS", "password1")
FLEXO_ORG = os.environ.get("FLEXO_ORG", "adcs-demo")
FLEXO_REPO = os.environ.get("FLEXO_REPO", "lifecycle")


def _resolve_token() -> str | None:
    """Return a working bearer token, or None if no auth path succeeds."""
    if FLEXO_TOKEN:
        return FLEXO_TOKEN
    # Fall back to local-Compose login
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{FLEXO_AUTH_URL}/login", auth=(FLEXO_USER, FLEXO_PASS))
            if r.status_code == 200:
                return r.json().get("token")
    except (httpx.RequestError, ValueError):
        return None
    return None


def _flexo_reachable() -> bool:
    """Quick HEAD check to decide whether to skip live tests."""
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.head(FLEXO_URL)
            return r.status_code < 500
    except httpx.RequestError:
        return False


pytestmark = pytest.mark.skipif(
    not (_resolve_token() and _flexo_reachable()),
    reason=(
        f"No Flexo target reachable (URL={FLEXO_URL}, "
        f"token={'set' if FLEXO_TOKEN else 'unset'}). "
        "Set FLEXO_TOKEN (remote) or run a local Compose stack to enable."
    ),
)


@pytest.fixture(scope="module")
def token() -> str:
    t = _resolve_token()
    assert t, "_resolve_token should have produced a token by skipif"
    return t


@pytest.fixture(scope="module")
def pipeline_run():
    """Run the full pipeline against the live Flexo and return the
    Dataset for further inspection."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        return run_pipeline(auto_attest=True, backend="flexo")


def test_pipeline_completes_against_flexo(pipeline_run):
    """The pipeline returned without raising — backend persisted
    everything successfully."""
    assert pipeline_run is not None


def test_branches_visible_in_flexo(token):
    """Query Flexo's /branches endpoint and confirm our named graphs
    are present as branches in adcs-demo/lifecycle."""
    expected_branches = {"master", "ontology", "structural", "evidence",
                         "attestations", "plan-execution", "audit"}
    with httpx.Client(timeout=30.0) as client:
        r = client.get(
            f"{FLEXO_URL}/orgs/{FLEXO_ORG}/repos/{FLEXO_REPO}/branches",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "text/turtle"},
        )
        assert r.status_code == 200, f"GET /branches: {r.status_code} {r.text[:200]}"
        body = r.text
    missing = [b for b in expected_branches if b not in body]
    assert not missing, f"Branches not visible in Flexo: {missing}"


def test_attestation_data_visible_in_flexo(token):
    """Run a SPARQL query against the attestations branch and confirm
    the attestation we emitted for REQ-003 is reachable."""
    sparql = """
    PREFIX rtm: <http://example.org/ontology/rtm#>
    PREFIX adcs: <http://example.org/adcs-demo/>
    ASK { adcs:ATT-REQ-003 a rtm:Attestation }
    """
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{FLEXO_URL}/orgs/{FLEXO_ORG}/repos/{FLEXO_REPO}"
            f"/branches/attestations/query",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/sparql-query",
                     "Accept": "application/json"},
            content=sparql,
        )
        assert r.status_code == 200, f"SPARQL ASK: {r.status_code} {r.text[:200]}"
        data = r.json()
    assert data.get("boolean") is True, (
        f"ATT-REQ-003 not visible in attestations branch on Flexo: {data}"
    )
