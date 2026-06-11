"""Traceable behavior-model oracle — automated, model-level verification.

A "traceable oracle" compares one model-output metric (from a SymPy/scipy
behavior model) against a requirement's machine-readable acceptance
criterion and returns a fully-specified EARL outcome.

Verification, NOT validation. The oracle verifies a *model-level claim*
("the simulated settling time exceeds the 120 s budget, within the
model") — a deterministic comparison over model outputs. It does NOT
assert that the physical requirement is satisfied. Per the project's core
principle, only human attestation (gsn:Assumption adequacy +
gsn:Justification sufficiency) connects evidence to requirement
satisfaction. The oracle outcome is an *input* to that judgment, never a
substitute for it.

Naming discipline: this module uses `evaluate` / `oracle` throughout —
never `validate` (validation = human judgement; see
traceability.attestation).

This module is pure Python (no rdflib). The RDF side — persisting the
outcome as an earl:Assertion — lives in
traceability.oracle_assertion.emit_oracle_assertion, mirroring the split
between traceability.verification and traceability.closure_assertion.
"""

from __future__ import annotations

from dataclasses import dataclass

# EARL outcome lattice values the oracle can emit. cantTell is first-class:
# the oracle returns it whenever the comparison is not fully specified
# (no machine-readable criterion, or the metric is absent from the model
# output) rather than fabricating a pass/fail it cannot compute.
OUTCOME_PASSED = "passed"
OUTCOME_FAILED = "failed"
OUTCOME_CANTTELL = "cantTell"

# Comparators a criterion may use. Kept tiny and explicit so the
# comparison is auditable.
_COMPARATORS = {
    "le": lambda v, t: v <= t,
    "lt": lambda v, t: v < t,
    "ge": lambda v, t: v >= t,
    "gt": lambda v, t: v > t,
}


@dataclass(frozen=True)
class AcceptanceCriterion:
    """Machine-readable, model-level acceptance criterion for one requirement.

    A criterion is a fully-specified comparison: pull ``metric_key`` from a
    behavior model's summary dict and compare it to ``threshold`` using
    ``comparator``. It mirrors a numeric bound stated in the requirement's
    ``sysml:text`` — it does not introduce new intent.
    """

    requirement_id: str          # "REQ-001"
    metric_key: str              # key into a SimResult.summary()-style dict
    comparator: str              # "le" | "lt" | "ge" | "gt"
    threshold: float
    units: str = ""
    label: str = ""


@dataclass(frozen=True)
class OracleResult:
    """Outcome of one model-level verification of a metric against a criterion."""

    requirement_id: str
    metric_key: str
    metric_value: float | None      # None when the metric is absent
    comparator: str | None
    threshold: float | None
    outcome: str                    # OUTCOME_PASSED | OUTCOME_FAILED | OUTCOME_CANTTELL
    detail: str


# Single source of truth for the demo's acceptance criteria. Each mirrors a
# numeric bound from the corresponding requirement's sysml:text in
# structural/satellite.ttl.
#
# REQ-004 is intentionally absent: its requirement text states no single
# scalar budget, so the oracle returns cantTell rather than manufacturing a
# verdict — a deliberate illustration that the oracle refuses to compute a
# comparison the model does not fully specify.
ACCEPTANCE_CRITERIA: dict[str, AcceptanceCriterion] = {
    "REQ-001": AcceptanceCriterion(
        "REQ-001", "settling_time_s", "le", 120.0, "s",
        "settling time within budget (model-level)",
    ),
    "REQ-002": AcceptanceCriterion(
        "REQ-002", "peak_wheel_momentum", "le", 4.0, "N.m.s",
        "peak wheel momentum within rated capacity (model-level)",
    ),
    "REQ-003": AcceptanceCriterion(
        "REQ-003", "worst_real_part", "le", -0.010, "rad/s",
        "dominant closed-loop eigenvalue real part (model-level)",
    ),
}


def evaluate_behavior_oracle(
    metric_value: float | None,
    criterion: AcceptanceCriterion | None,
) -> OracleResult:
    """Compare one model metric to one model-level criterion.

    Fully-specified and automatic. Returns ``cantTell`` when the criterion
    or the metric is absent — the oracle never fabricates a verdict it
    cannot compute. This verifies a MODEL claim, never physical requirement
    satisfaction.
    """
    if criterion is None:
        return OracleResult(
            requirement_id="", metric_key="", metric_value=metric_value,
            comparator=None, threshold=None, outcome=OUTCOME_CANTTELL,
            detail="no machine-readable acceptance criterion for this requirement",
        )
    if metric_value is None:
        return OracleResult(
            requirement_id=criterion.requirement_id,
            metric_key=criterion.metric_key, metric_value=None,
            comparator=criterion.comparator, threshold=criterion.threshold,
            outcome=OUTCOME_CANTTELL,
            detail=f"metric {criterion.metric_key!r} absent from model output",
        )

    passed = _COMPARATORS[criterion.comparator](metric_value, criterion.threshold)
    verdict = "pass" if passed else "fail"
    return OracleResult(
        requirement_id=criterion.requirement_id,
        metric_key=criterion.metric_key,
        metric_value=metric_value,
        comparator=criterion.comparator,
        threshold=criterion.threshold,
        outcome=OUTCOME_PASSED if passed else OUTCOME_FAILED,
        detail=(
            f"{criterion.metric_key} = {metric_value:g} {criterion.comparator} "
            f"{criterion.threshold:g} {criterion.units} -> {verdict} (model-level)"
        ),
    )


def evaluate_requirement_oracle(
    summary: dict[str, float],
    requirement_id: str,
    criteria: dict[str, AcceptanceCriterion] = ACCEPTANCE_CRITERIA,
) -> OracleResult:
    """Evaluate a requirement by pulling its metric from a model summary dict.

    ``summary`` is a SimResult.summary()-style mapping (numerical oracle) or
    any dict carrying the criterion's ``metric_key`` (e.g. the symbolic
    oracle's ``{"worst_real_part": ...}`` for REQ-003).
    """
    criterion = criteria.get(requirement_id)
    metric = summary.get(criterion.metric_key) if criterion else None
    return evaluate_behavior_oracle(metric, criterion)
