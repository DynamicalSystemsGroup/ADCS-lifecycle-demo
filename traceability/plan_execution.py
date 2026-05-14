"""Per-stage P-PLAN activity emission.

Every pipeline stage records its execution as a p-plan:Activity in
<adcs:plan-execution> with correspondsToStep pointing at the matching
p-plan:Step from pipeline/plan.ttl. This makes the construction process
queryable: SPARQL can confirm every required step executed and that
ordering was preserved.

The closure-rule shape rtm:PlanInstantiationShape (Phase G) enforces
well-formedness:
  - every p-plan:Activity correspondsToStep exactly one p-plan:Step
  - prov:startedAtTime is set
  - (predecessor-ordering check is a runtime SPARQL ASK, not SHACL)

Usage:
    with plan_step(rtm_ds, "SymbolicAnalysis"):
        ...stage body...

    # Or imperatively, for stages that span multiple phases:
    activity = start_step(rtm_ds, "BindEvidence")
    ...
    end_step(rtm_ds, activity)
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF, XSD

from ontology.prefixes import ADCS, P_PLAN, PROV, RTM
from pipeline.dataset import graph_for


# Mapping from stage short-name to the step IRI fragment in plan.ttl.
# Keep this in sync with pipeline/plan.ttl.
STEP_NAMES = {
    "OntologyAssembly",
    "LoadStructural",
    "SymbolicAnalysis",
    "NumericalSimulation",
    "BindEvidence",
    "AssembleRTM",
    "Attest",
    "ValidateShapes",
    "AuditTrace",
    "Report",
    "Interrogate",
}


def step_iri(step_name: str) -> URIRef:
    """Resolve a step short-name to its plan.ttl IRI."""
    if step_name not in STEP_NAMES:
        raise KeyError(
            f"Unknown plan step {step_name!r}. "
            f"Valid steps: {sorted(STEP_NAMES)}"
        )
    return URIRef(f"{RTM}plan/step/{step_name}")


def start_step(ds: Dataset, step_name: str) -> URIRef:
    """Begin recording an activity for `step_name`. Returns its IRI."""
    started = datetime.now(timezone.utc)
    activity_id = f"exec/{step_name}-{started.strftime('%Y%m%dT%H%M%S%fZ')}"
    activity = ADCS[activity_id]

    plan_g = graph_for(ds, "plan_execution")
    plan_g.add((activity, RDF.type, P_PLAN.Activity))
    plan_g.add((activity, RDF.type, PROV.Activity))
    plan_g.add((activity, P_PLAN.correspondsToStep, step_iri(step_name)))
    plan_g.add((activity, PROV.startedAtTime,
                Literal(started.isoformat(), datatype=XSD.dateTime)))
    return activity


def end_step(ds: Dataset, activity: URIRef) -> None:
    """Record completion of `activity` (sets prov:endedAtTime)."""
    plan_g = graph_for(ds, "plan_execution")
    plan_g.add((activity, PROV.endedAtTime,
                Literal(datetime.now(timezone.utc).isoformat(),
                        datatype=XSD.dateTime)))


@contextmanager
def plan_step(ds: Dataset, step_name: str) -> Iterator[URIRef]:
    """Context manager wrapping start_step / end_step.

    Always records endedAtTime on exit, even if the body raises — so the
    plan-execution record stays consistent for diagnostics.
    """
    activity = start_step(ds, step_name)
    try:
        yield activity
    finally:
        end_step(ds, activity)


def emit_stage_activity(ds: Dataset, step_name: str) -> URIRef:
    """One-shot activity emission for callers that don't want a context
    manager. Used by pipeline/runner.py to mark each stage's execution
    without re-indenting the existing stage bodies.

    Sets startedAtTime only; the runtime ordering of these activities is
    what the predecessor check (Phase G) validates.
    """
    return start_step(ds, step_name)
