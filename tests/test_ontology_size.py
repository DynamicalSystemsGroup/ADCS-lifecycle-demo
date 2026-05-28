"""Triple-count budget gate for the committed `ontology/rtm.ttl`.

WP2 §4.C. Mirrors the gate in `scripts/build_ontology.py` so the
budget is verifiable without invoking the build script — a build-
time bypass (`uv run python -c "..."` writing directly to the
artifact) is caught here too.

The single source of truth for the budget is
`scripts.build_ontology.TRIPLE_BUDGET`; this test imports it rather
than duplicating the number.
"""

from __future__ import annotations

import json
from pathlib import Path

from rdflib import Graph

from scripts.build_ontology import TRIPLE_BUDGET

ROOT = Path(__file__).resolve().parent.parent
RTM_TTL = ROOT / "ontology" / "rtm.ttl"
MANIFEST = ROOT / "ontology" / "assembly_manifest.json"


def test_rtm_ttl_within_triple_budget():
    """The committed artifact obeys the parsimony budget."""
    g = Graph()
    g.parse(RTM_TTL, format="turtle")
    actual = len(g)
    assert actual <= TRIPLE_BUDGET, (
        f"rtm.ttl exceeds triple budget: {actual} > {TRIPLE_BUDGET}. "
        f"Bump TRIPLE_BUDGET in scripts/build_ontology.py with a "
        f"rationale comment, then rebuild with `make ontology`."
    )


def test_manifest_records_triple_budget():
    """The build manifest pins the budget + rationale so the gate is
    visible to anyone reading the manifest without sources."""
    manifest = json.loads(MANIFEST.read_text())
    budget_block = manifest.get("triple_budget")
    assert budget_block is not None, "triple_budget block missing from manifest"
    assert budget_block["value"] == TRIPLE_BUDGET
    assert "rationale" in budget_block and budget_block["rationale"]
    assert "headroom" in budget_block


def test_manifest_triple_count_matches_artifact():
    """Sanity: the manifest's recorded triple count matches the
    parsed rtm.ttl. Catches a stale manifest committed without
    re-running the build."""
    manifest = json.loads(MANIFEST.read_text())
    recorded = manifest["artifact"]["total_triples"]
    g = Graph()
    g.parse(RTM_TTL, format="turtle")
    assert recorded == len(g), (
        f"Manifest claims {recorded} triples but rtm.ttl has {len(g)}. "
        f"Rebuild with `make ontology` to refresh the manifest."
    )
