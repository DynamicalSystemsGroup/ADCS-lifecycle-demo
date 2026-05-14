"""Phase D — Stage 0 (Ontology Assembly) tests.

Covers:
  - Happy path: run_stage_0() loads ontology + emits p-plan:Activity
  - Manifest verification: a hash mismatch raises Stage0Error
  - Banner content: key narrative lines appear in stdout
  - The dataset has the expected shape (ontology graph populated, nothing
    in structural yet — Stage 1 owns that).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest
from rdflib import Dataset, URIRef

from ontology.prefixes import G_ONTOLOGY, G_PLAN_EXECUTION, G_STRUCTURAL, P_PLAN
from pipeline.stage0_assembly import (
    ARTIFACT_PATH,
    MANIFEST_PATH,
    STAGE0_STEP_IRI,
    Stage0Error,
    run_stage_0,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def stage0_run(capsys):
    """Run Stage 0 and capture its output for inspection."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        ds = run_stage_0(rebuild=False)
    captured = capsys.readouterr()
    return ds, captured.out


def test_returns_dataset(stage0_run):
    ds, _ = stage0_run
    assert isinstance(ds, Dataset)


def test_ontology_graph_populated(stage0_run):
    ds, _ = stage0_run
    onto_size = len(list(ds.quads((None, None, None, URIRef(G_ONTOLOGY)))))
    assert onto_size > 100, f"<rtm:ontology> should be populated, got {onto_size} quads"


def test_structural_graph_empty_after_stage_0(stage0_run):
    """Stage 0 must not load structural data — that is Stage 1's job."""
    ds, _ = stage0_run
    struct_size = len(list(ds.quads((None, None, None, URIRef(G_STRUCTURAL)))))
    assert struct_size == 0, (
        f"Stage 0 unexpectedly populated <adcs:structural> with {struct_size} quads"
    )


def test_plan_execution_activity_emitted(stage0_run):
    """Stage 0 records its execution as a p-plan:Activity in
    <adcs:plan-execution>, correspondsToStep -> rtm:plan/step/OntologyAssembly."""
    ds, _ = stage0_run
    activities = list(
        ds.quads((None, P_PLAN.correspondsToStep, STAGE0_STEP_IRI, URIRef(G_PLAN_EXECUTION)))
    )
    assert len(activities) == 1, (
        f"Expected exactly one p-plan:Activity for Stage 0, got {len(activities)}"
    )


def test_banner_contains_expected_lines(stage0_run):
    _, out = stage0_run
    expected_substrings = [
        "[Stage 0/8] Ontology Assembly",
        "Loading assembled rtm.ttl",
        "Imports resolved:",
        "PROV-O",
        "EARL",
        "OntoGSN",
        "P-PLAN",
        "OSLC RM",
        "OSLC QM",
        "SysMLv2 equivalence axioms:",
        "Loaded into <rtm:ontology>:",
        "Closure-rule suite registered:",
    ]
    missing = [s for s in expected_substrings if s not in out]
    assert not missing, f"Banner missing expected substrings: {missing}"


def test_manifest_drift_raises(tmp_path, monkeypatch):
    """If rtm.ttl is altered without rebuilding the manifest, Stage 0
    fails with a clear remediation message."""
    # Build a fake manifest that disagrees with the actual rtm.ttl hash.
    fake_manifest = json.loads(MANIFEST_PATH.read_text())
    fake_manifest["artifact"]["sha256"] = "0" * 64
    fake_path = tmp_path / "fake_manifest.json"
    fake_path.write_text(json.dumps(fake_manifest))

    # Point Stage 0 at the fake manifest by monkey-patching MANIFEST_PATH.
    import pipeline.stage0_assembly as s0
    monkeypatch.setattr(s0, "MANIFEST_PATH", fake_path)

    with pytest.raises(Stage0Error, match="hash mismatch"):
        run_stage_0(rebuild=False)
