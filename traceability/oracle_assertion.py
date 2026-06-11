"""Emit rtm:BehaviorOracleAssertion (earl:Assertion subclass) for the oracle.

The behavior-model oracle (analysis.oracle) compares a model-output metric
to a requirement's machine-readable acceptance criterion. Its outcome is an
automated, fully-specified verification result and fits the EARL assertion
pattern exactly like the two siblings persisted in <adcs:audit>:
rtm:ClosureRuleAssertion (Stage 6.5 SHACL outcome) and
rtm:DigestMatchAssertion (image-digest reproduction outcome).

Discipline: earl:mode is always earl:automatic — verification, not human
validation. The assertion links to:

  earl:subject        -> the EVIDENCE node tested (the model output)
  rtm:evaluatesAgainst -> the REQUIREMENT whose criterion was computed over

It deliberately NEVER uses rtm:attests, which is reserved for human
rtm:Attestation. The oracle verifies a model-level claim; only attestation
connects evidence to physical requirement satisfaction. A regression test
guards this (tests/test_oracle.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF, XSD

from ontology.prefixes import EARL, G_AUDIT, PROV, RTM

if TYPE_CHECKING:
    from analysis.oracle import OracleResult


BEHAVIOR_ORACLE_AGENT = URIRef("urn:adcs:agent:behavior-oracle")
BEHAVIOR_ORACLE_TEST = URIRef("urn:adcs:test:behavior-oracle")

_OUTCOME_IRI = {
    "passed": EARL.passed,
    "failed": EARL.failed,
    "cantTell": EARL.cantTell,
}


def emit_oracle_assertion(
    ds: Dataset,
    evidence_iri: URIRef,
    requirement_iri: URIRef,
    result: "OracleResult",
) -> URIRef:
    """Persist one rtm:BehaviorOracleAssertion in <adcs:audit>.

    Mirrors emit_closure_assertion / emit_digest_match_assertion. Returns
    the assertion IRI.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    suffix = now_iso.replace(":", "-").replace("+", "-").replace(".", "-")
    assertion = URIRef(
        f"urn:adcs:assertion:oracle-{result.requirement_id or 'unknown'}-{suffix}"
    )
    g = ds.graph(URIRef(G_AUDIT))

    g.add((assertion, RDF.type, RTM.BehaviorOracleAssertion))
    g.add((assertion, RDF.type, EARL.Assertion))
    g.add((assertion, RDF.type, PROV.Activity))

    # EARL: subject (evidence under test) + test + outcome + mode + assertor
    g.add((assertion, EARL.subject, evidence_iri))
    g.add((assertion, EARL.test, BEHAVIOR_ORACLE_TEST))
    g.add((assertion, EARL.outcome, _OUTCOME_IRI[result.outcome]))
    g.add((assertion, EARL.mode, EARL.automatic))

    # Requirement link — NOT rtm:attests (reserved for human attestation).
    g.add((assertion, RTM.evaluatesAgainst, requirement_iri))

    # PROV: who ran it + when
    g.add((assertion, PROV.wasAssociatedWith, BEHAVIOR_ORACLE_AGENT))
    g.add((assertion, PROV.atTime, Literal(now_iso, datatype=XSD.dateTime)))

    # Model-level comparison provenance (mirrors rtm:violationCount on the
    # closure assertion). Omitted on cantTell where values may be absent.
    g.add((assertion, RTM.metricKey, Literal(result.metric_key)))
    if result.metric_value is not None:
        g.add((assertion, RTM.metricValue,
               Literal(result.metric_value, datatype=XSD.decimal)))
    if result.threshold is not None:
        g.add((assertion, RTM.thresholdValue,
               Literal(result.threshold, datatype=XSD.decimal)))

    return assertion
