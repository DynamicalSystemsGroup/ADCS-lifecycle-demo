"""Tests for the traceable behavior-model oracle.

Covers the pure evaluation logic (analysis.oracle) and the EARL emitter
(traceability.oracle_assertion). The emitter tests mirror the
test_emit_digest_match_assertion_* style. A dedicated regression test
guards the core principle that the oracle never uses rtm:attests.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdflib import Dataset, URIRef
from rdflib.namespace import RDF

from analysis.oracle import (
    ACCEPTANCE_CRITERIA,
    OUTCOME_CANTTELL,
    OUTCOME_FAILED,
    OUTCOME_PASSED,
    AcceptanceCriterion,
    OracleResult,
    evaluate_behavior_oracle,
    evaluate_requirement_oracle,
)
from ontology.prefixes import ADCS, EARL, G_AUDIT, G_EVIDENCE, PROV, RTM
from traceability.oracle_assertion import (
    BEHAVIOR_ORACLE_TEST,
    emit_oracle_assertion,
)


# ---------------------------------------------------------------------------
# evaluate_behavior_oracle — pure logic
# ---------------------------------------------------------------------------

_REQ001 = AcceptanceCriterion("REQ-001", "settling_time_s", "le", 120.0, "s")


def test_evaluate_pass_le():
    result = evaluate_behavior_oracle(95.0, _REQ001)
    assert result.outcome == OUTCOME_PASSED


def test_evaluate_fail_le():
    result = evaluate_behavior_oracle(262.0, _REQ001)
    assert result.outcome == OUTCOME_FAILED


def test_evaluate_boundary_le_inclusive():
    # le is inclusive: value == threshold passes.
    assert evaluate_behavior_oracle(120.0, _REQ001).outcome == OUTCOME_PASSED


def test_evaluate_boundary_lt_exclusive():
    crit = dataclasses.replace(_REQ001, comparator="lt")
    assert evaluate_behavior_oracle(120.0, crit).outcome == OUTCOME_FAILED


def test_evaluate_negative_threshold_sign():
    # REQ-003: worst_real_part le -0.010 rad/s — guards sign handling.
    crit = ACCEPTANCE_CRITERIA["REQ-003"]
    assert evaluate_behavior_oracle(-0.05, crit).outcome == OUTCOME_PASSED
    assert evaluate_behavior_oracle(-0.005, crit).outcome == OUTCOME_FAILED


def test_evaluate_missing_criterion_cant_tell():
    result = evaluate_behavior_oracle(95.0, None)
    assert result.outcome == OUTCOME_CANTTELL
    assert "criterion" in result.detail


def test_evaluate_missing_metric_cant_tell():
    result = evaluate_behavior_oracle(None, _REQ001)
    assert result.outcome == OUTCOME_CANTTELL
    assert "absent" in result.detail


# ---------------------------------------------------------------------------
# evaluate_requirement_oracle — summary-dict convenience
# ---------------------------------------------------------------------------

def test_evaluate_requirement_from_summary():
    summary = {"settling_time_s": 262.0, "peak_wheel_momentum": 3.0}
    assert evaluate_requirement_oracle(summary, "REQ-001").outcome == OUTCOME_FAILED
    assert evaluate_requirement_oracle(summary, "REQ-002").outcome == OUTCOME_PASSED


def test_evaluate_req004_cant_tell():
    # REQ-004 intentionally has no machine-readable criterion.
    assert "REQ-004" not in ACCEPTANCE_CRITERIA
    result = evaluate_requirement_oracle({"peak_error_deg": 0.0}, "REQ-004")
    assert result.outcome == OUTCOME_CANTTELL


def test_oracle_result_is_frozen():
    result = evaluate_behavior_oracle(95.0, _REQ001)
    assert isinstance(result, OracleResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = OUTCOME_FAILED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# emit_oracle_assertion — RDF emission into <adcs:audit>
# ---------------------------------------------------------------------------

_EVIDENCE = URIRef("urn:adcs:evidence:EV-SIM-REQ-001")
_REQUIREMENT = ADCS["REQ-001"]


def _emit(outcome_metric: float | None, criterion=_REQ001):
    ds = Dataset()
    result = evaluate_behavior_oracle(outcome_metric, criterion)
    assertion = emit_oracle_assertion(ds, _EVIDENCE, _REQUIREMENT, result)
    return ds, assertion, result


def test_emit_oracle_assertion_passed():
    ds, assertion, _ = _emit(95.0)
    g = ds.graph(URIRef(G_AUDIT))
    assert (assertion, RDF.type, RTM.BehaviorOracleAssertion) in g
    assert (assertion, RDF.type, EARL.Assertion) in g
    assert (assertion, RDF.type, PROV.Activity) in g
    assert (assertion, EARL.outcome, EARL.passed) in g
    assert (assertion, EARL.mode, EARL.automatic) in g
    assert (assertion, EARL.subject, _EVIDENCE) in g
    assert (assertion, EARL.test, BEHAVIOR_ORACLE_TEST) in g
    assert (assertion, RTM.evaluatesAgainst, _REQUIREMENT) in g


def test_emit_oracle_assertion_failed():
    ds, assertion, _ = _emit(262.0)
    g = ds.graph(URIRef(G_AUDIT))
    assert (assertion, EARL.outcome, EARL.failed) in g


def test_emit_oracle_assertion_canttell():
    ds, assertion, _ = _emit(95.0, criterion=None)
    g = ds.graph(URIRef(G_AUDIT))
    assert (assertion, EARL.outcome, EARL.cantTell) in g


def test_emit_oracle_does_not_use_attests():
    # Core principle: only human attestation links evidence to satisfaction.
    ds, assertion, _ = _emit(262.0)
    g = ds.graph(URIRef(G_AUDIT))
    assert (assertion, RTM.attests, _REQUIREMENT) not in g


def test_emit_oracle_writes_to_audit_graph_not_default():
    ds, assertion, _ = _emit(95.0)
    audit = ds.graph(URIRef(G_AUDIT))
    evidence = ds.graph(URIRef(G_EVIDENCE))
    assert len(audit) > 0
    assert (assertion, RDF.type, RTM.BehaviorOracleAssertion) not in evidence
