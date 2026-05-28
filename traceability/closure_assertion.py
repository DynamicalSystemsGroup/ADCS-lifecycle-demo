"""Emit rtm:ClosureRuleAssertion (earl:Assertion subclass) for Stage 6.5.

WP4 §"EARL-wrapped verification outcomes" — the SHACL closure-rule
check is an automated, fully-specified outcome and fits the EARL
assertion pattern. WP4 persists it as RDF in <adcs:audit> so the
technical-trust witness is queryable beside the human-attestation
witness (rtm:Attestation, which also subclasses earl:Assertion).

Discipline: earl:mode is always earl:automatic for these (automated
check) — distinct from earl:manual / earl:semiAuto for human
attestation. Validation = judgement (attestation); verification =
automated outcome (this).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF, XSD

from ontology.prefixes import (
    EARL,
    G_AUDIT,
    PROV,
    RTM,
)

if TYPE_CHECKING:
    from traceability.verification import VerificationReport


CLOSURE_RULE_CHECKER_AGENT = URIRef("urn:adcs:agent:closure-rule-checker")
CLOSURE_RULE_TEST = URIRef("urn:adcs:test:shacl-closure-rules")


def emit_closure_assertion(ds: Dataset, report: "VerificationReport") -> URIRef:
    """Persist one rtm:ClosureRuleAssertion summarizing the Stage 6.5 check.

    Emitted into <adcs:audit>. One assertion per run summarizing the
    aggregate SHACL + re-verification result; per-shape-check
    granularity is a future refinement (see WP4 open question Q9).

    Returns the assertion IRI.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    # IRI is stable per-second timestamp; suitable for a single-run summary.
    suffix = now_iso.replace(":", "-").replace("+", "-").replace(".", "-")
    assertion = URIRef(f"urn:adcs:assertion:closure-{suffix}")

    g = ds.graph(URIRef(G_AUDIT))

    g.add((assertion, RDF.type, RTM.ClosureRuleAssertion))
    g.add((assertion, RDF.type, EARL.Assertion))
    g.add((assertion, RDF.type, PROV.Activity))

    # EARL: subject + test + outcome + mode + assertor
    g.add((assertion, EARL.subject, URIRef(G_AUDIT)))  # the audit graph itself
    g.add((assertion, EARL.test, CLOSURE_RULE_TEST))
    g.add((
        assertion, EARL.outcome,
        EARL.passed if report.conforms else EARL.failed,
    ))
    g.add((assertion, EARL.mode, EARL.automatic))

    # PROV: who ran it + when
    g.add((assertion, PROV.wasAssociatedWith, CLOSURE_RULE_CHECKER_AGENT))
    g.add((assertion, PROV.atTime,
           Literal(now_iso, datatype=XSD.dateTime)))

    # Violation count (helpful for the trust query)
    violation_count = len(report.shape_violations) + len(report.reverification_mismatches)
    g.add((assertion, RTM.violationCount,
           Literal(violation_count, datatype=XSD.nonNegativeInteger)))

    return assertion
