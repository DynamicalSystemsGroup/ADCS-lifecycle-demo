"""Phase E — P-PLAN process ontology + per-stage activity emission tests.

Covers:
  - pipeline/plan.ttl parses as Turtle and contains the expected steps.
  - Stage 0 loads plan.ttl into <rtm:plan>.
  - Every step in the plan is reachable from rtm:plan/AdcsLifecycle.
  - Predecessor relations form a valid DAG (no cycles).
  - At pipeline run time, each stage emits a p-plan:Activity into
    <adcs:plan-execution> with correspondsToStep pointing at a known step.
  - Activities fire in the right order (predecessors before successors).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from rdflib import Dataset, Graph, URIRef
from rdflib.namespace import RDF

from ontology.prefixes import G_PLAN, G_PLAN_EXECUTION, P_PLAN, PROV, RTM
from pipeline.runner import run_pipeline
from traceability.plan_execution import STEP_NAMES, step_iri

ROOT = Path(__file__).resolve().parent.parent
PLAN_TTL = ROOT / "pipeline" / "plan.ttl"

PLAN_IRI = URIRef(f"{RTM}plan/AdcsLifecycle")


@pytest.fixture(scope="module")
def plan_graph() -> Graph:
    g = Graph()
    g.parse(PLAN_TTL, format="turtle")
    return g


@pytest.fixture(scope="module")
def pipeline_dataset() -> Dataset:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        return run_pipeline(auto_attest=True)


# ---------------------------------------------------------------------------
# Plan TTL structure
# ---------------------------------------------------------------------------

def test_plan_ttl_parses_and_is_nonempty(plan_graph):
    assert len(plan_graph) > 50, "plan.ttl looks suspiciously thin"


def test_plan_has_root_plan_individual(plan_graph):
    assert (PLAN_IRI, RDF.type, P_PLAN.Plan) in plan_graph


def test_every_known_step_appears_in_plan(plan_graph):
    """STEP_NAMES from plan_execution.py must each have a corresponding
    p-plan:Step in plan.ttl, isStepOfPlan AdcsLifecycle."""
    declared_steps = {
        str(s) for s in plan_graph.subjects(P_PLAN.isStepOfPlan, PLAN_IRI)
    }
    missing = [
        name for name in STEP_NAMES
        if str(step_iri(name)) not in declared_steps
    ]
    assert not missing, f"plan.ttl missing steps referenced by code: {missing}"


def test_predecessor_relations_form_dag(plan_graph):
    """isPrecededBy must be acyclic (DAG)."""
    edges: dict[URIRef, set[URIRef]] = {}
    for s, _, o in plan_graph.triples((None, P_PLAN.isPrecededBy, None)):
        edges.setdefault(s, set()).add(o)

    # Standard cycle detection via DFS
    visiting: set[URIRef] = set()
    visited: set[URIRef] = set()

    def dfs(node: URIRef) -> None:
        if node in visiting:
            raise AssertionError(f"Predecessor cycle through {node}")
        if node in visited:
            return
        visiting.add(node)
        for nxt in edges.get(node, ()):
            dfs(nxt)
        visiting.remove(node)
        visited.add(node)

    for n in list(edges):
        dfs(n)


# ---------------------------------------------------------------------------
# Runtime plan-execution emissions
# ---------------------------------------------------------------------------

def test_plan_loaded_into_rtm_plan_graph(pipeline_dataset):
    """Stage 0 loads plan.ttl into <rtm:plan>."""
    plan_quads = list(pipeline_dataset.quads((None, None, None, URIRef(G_PLAN))))
    assert len(plan_quads) > 50, (
        f"<rtm:plan> not populated by Stage 0; only {len(plan_quads)} quads"
    )


def test_each_stage_emits_one_activity(pipeline_dataset):
    """Each substantive stage (0-7) emits exactly one p-plan:Activity
    correspondsToStep its step. Stage 8 (Interrogate) is emitted but
    after stage-7 export, so we only require 8 stages here."""
    pe = URIRef(G_PLAN_EXECUTION)
    activities_per_step: dict[str, int] = {}
    for _, _, step, ctx in pipeline_dataset.quads(
        (None, P_PLAN.correspondsToStep, None, pe)
    ):
        local = str(step).replace(f"{RTM}plan/step/", "")
        activities_per_step[local] = activities_per_step.get(local, 0) + 1

    expected_stages = [
        "OntologyAssembly", "LoadStructural", "SymbolicAnalysis",
        "NumericalSimulation", "BindEvidence", "AssembleRTM",
        "Attest", "Report",
    ]
    missing = [s for s in expected_stages if s not in activities_per_step]
    assert not missing, f"No p-plan:Activity recorded for stages: {missing}"
    duplicated = [s for s, n in activities_per_step.items() if n > 1]
    assert not duplicated, f"Multiple activities for same step: {duplicated}"


def test_activities_have_started_at_time(pipeline_dataset):
    """Every p-plan:Activity has prov:startedAtTime (required by Phase G shape)."""
    pe = URIRef(G_PLAN_EXECUTION)
    activities = [
        s for s, _, _, _ in
        pipeline_dataset.quads((None, RDF.type, P_PLAN.Activity, pe))
    ]
    missing_time = [
        a for a in activities
        if not list(pipeline_dataset.quads((a, PROV.startedAtTime, None, pe)))
    ]
    assert not missing_time, (
        f"{len(missing_time)} activities lack prov:startedAtTime"
    )


def test_activities_fire_in_predecessor_order(pipeline_dataset, plan_graph):
    """For every predecessor relation in the plan, the predecessor's
    activity timestamp must be earlier than the successor's."""
    pe = URIRef(G_PLAN_EXECUTION)

    # Build {step -> startedAtTime} for every emitted activity.
    times: dict[URIRef, str] = {}
    for s, _, step, _ in pipeline_dataset.quads(
        (None, P_PLAN.correspondsToStep, None, pe)
    ):
        for _, _, t, _ in pipeline_dataset.quads((s, PROV.startedAtTime, None, pe)):
            times[step] = str(t)

    # Check every predecessor edge in plan.ttl.
    for step, _, predecessor in plan_graph.triples(
        (None, P_PLAN.isPrecededBy, None)
    ):
        if step in times and predecessor in times:
            assert times[predecessor] < times[step], (
                f"Order violation: {predecessor} fired at {times[predecessor]} "
                f"but successor {step} fired at {times[step]}"
            )
