"""Phase H — audit module tests.

The critical property under test is INDEPENDENCE: forward and backward
checks run separately and emit separate failure lists, so error
messages identify which direction broke (and why). Bidirectional is a
derived predicate, never a primary check.

Coverage:
  - Positive: nominal pipeline passes forward, backward, bidirectional.
  - Negative #1 (forward-fail, backward-pass): remove an attestation;
    forward fails but backward still passes (still consistent with the
    remaining structural state).
  - Negative #2 (backward-fail, forward-pass): emit a spurious
    attestation that references evidence not addressing the
    requirement; backward fails but forward still passes.
  - Both-fail: combine both perturbations; bidirectional reports both
    failing directions.
  - Orphans: requirement without evidence, evidence without requirement,
    attestation with broken reference.
  - Coverage matrix: REQ-001 cells show covered+failed (matches the
    intentional declination); REQ-002/3/4 show covered+passed.
  - Render formats: csv / md / json all produce non-empty output.
  - <adcs:audit> graph receives a report resource after Stage 7a.
"""

from __future__ import annotations

import json
import warnings

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF

from ontology.prefixes import (
    ADCS, EARL, G_ATTESTATIONS, G_AUDIT, G_EVIDENCE, RTM,
)
from pipeline.runner import run_pipeline
from traceability.audit import (
    AuditReport,
    Failure,
    audit,
    backward_trace,
    bidirectional_trace,
    coverage_matrix,
    forward_trace,
    orphans,
    render_report,
)


@pytest.fixture(scope="module")
def nominal_dataset() -> Dataset:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        return run_pipeline(auto_attest=True)


def _copy(ds: Dataset) -> Dataset:
    new = Dataset(default_union=True)
    for s, p, o, c in ds.quads():
        new.add((s, p, o, c))
    return new


# ---------------------------------------------------------------------------
# Positive: nominal pipeline passes all checks
# ---------------------------------------------------------------------------

def test_nominal_forward_passes(nominal_dataset):
    result = forward_trace(nominal_dataset)
    assert result.passed, f"forward failures: {[f.reason for f in result.failures]}"
    assert result.checked_count == 4  # REQ-001..REQ-004


def test_nominal_backward_passes(nominal_dataset):
    result = backward_trace(nominal_dataset)
    assert result.passed, f"backward failures: {[f.reason for f in result.failures]}"
    # 4 attestations — REQ-001 declined + REQ-002/3/4 passed
    assert result.checked_count == 4


def test_nominal_bidirectional_passes(nominal_dataset):
    result = bidirectional_trace(nominal_dataset)
    assert result.passed
    assert result.forward.passed
    assert result.backward.passed


def test_nominal_no_orphans(nominal_dataset):
    report = orphans(nominal_dataset)
    assert not report.any, (
        f"orphans found: reqs={report.requirements_without_evidence}, "
        f"ev={report.evidence_without_requirement}, "
        f"att={report.attestations_with_broken_refs}"
    )


# ---------------------------------------------------------------------------
# Independence — failure modes named separately by direction
# ---------------------------------------------------------------------------

def test_forward_fail_backward_pass(nominal_dataset):
    """Remove REQ-002's attestation: forward fails (no attestation),
    backward still passes (no spurious attestation either)."""
    ds = _copy(nominal_dataset)
    att_g = ds.graph(URIRef(G_ATTESTATIONS))
    att = ADCS["ATT-REQ-002"]
    for s, p, o in list(att_g.triples((att, None, None))):
        att_g.remove((s, p, o))

    fwd = forward_trace(ds)
    bwd = backward_trace(ds)
    assert not fwd.passed, "forward should fail with REQ-002 attestation removed"
    assert bwd.passed, (
        f"backward should still pass; got failures: {[f.reason for f in bwd.failures]}"
    )
    # The failure message names REQ-002 specifically
    assert any("REQ-002" in f.subject for f in fwd.failures), (
        f"forward failures didn't name REQ-002: {[f.subject for f in fwd.failures]}"
    )


def test_backward_fail_forward_pass(nominal_dataset):
    """Emit a spurious attestation referencing evidence that doesn't
    address its requirement: backward fails, forward still passes."""
    ds = _copy(nominal_dataset)
    att_g = ds.graph(URIRef(G_ATTESTATIONS))
    # Forge an attestation for REQ-002 that claims EV-PROOF-REQ-003 as its evidence.
    spurious = ADCS["ATT-SPURIOUS-REQ-002"]
    att_g.add((spurious, RDF.type, RTM.Attestation))
    att_g.add((spurious, RTM.attests, ADCS["REQ-002"]))
    att_g.add((spurious, RTM.hasEvidence, ADCS["EV-PROOF-REQ-003"]))

    fwd = forward_trace(ds)
    bwd = backward_trace(ds)
    assert fwd.passed, (
        f"forward should still pass (REQ-002's original attestation still present); "
        f"got: {[f.reason for f in fwd.failures]}"
    )
    assert not bwd.passed, "backward should fail on the spurious attestation"
    # Failure names the spurious attestation
    assert any("SPURIOUS" in f.subject for f in bwd.failures), (
        f"backward failures didn't name the spurious attestation: "
        f"{[f.subject for f in bwd.failures]}"
    )


def test_both_directions_fail_when_both_broken(nominal_dataset):
    """Combine both perturbations: both directions fail, bidirectional
    reports the union of failures with each direction labeled."""
    ds = _copy(nominal_dataset)
    att_g = ds.graph(URIRef(G_ATTESTATIONS))
    # Remove REQ-002's attestation (forward break)
    for s, p, o in list(att_g.triples((ADCS["ATT-REQ-002"], None, None))):
        att_g.remove((s, p, o))
    # Add a spurious attestation referencing wrong evidence (backward break)
    spurious = ADCS["ATT-SPURIOUS-REQ-003"]
    att_g.add((spurious, RDF.type, RTM.Attestation))
    att_g.add((spurious, RTM.attests, ADCS["REQ-003"]))
    att_g.add((spurious, RTM.hasEvidence, ADCS["EV-PROOF-REQ-004"]))

    result = bidirectional_trace(ds)
    assert not result.passed
    assert not result.forward.passed
    assert not result.backward.passed
    assert result.forward.failures
    assert result.backward.failures
    summary = result.summary()
    assert "forward" in summary and "backward" in summary


# ---------------------------------------------------------------------------
# Orphan detection
# ---------------------------------------------------------------------------

def test_orphan_requirement_detected():
    """Build a tiny graph with a requirement that has no evidence."""
    ds = Dataset(default_union=True)
    struct = ds.graph(URIRef("http://example.org/adcs-demo/graph/structural"))
    sysml_ns = "https://www.omg.org/spec/SysML/2.0/"
    req = ADCS["REQ-ORPHAN"]
    struct.add((req, RDF.type, URIRef(f"{sysml_ns}RequirementDefinition")))
    struct.add((req, URIRef(f"{sysml_ns}declaredName"), Literal("REQ-ORPHAN")))

    rep = orphans(ds)
    assert "REQ-ORPHAN" in rep.requirements_without_evidence


def test_orphan_evidence_detected():
    """Evidence without rtm:addresses gets reported."""
    ds = Dataset(default_union=True)
    ev_g = ds.graph(URIRef(G_EVIDENCE))
    ev = ADCS["EV-DETACHED"]
    ev_g.add((ev, RDF.type, RTM.ProofArtifact))
    # No rtm:addresses link

    rep = orphans(ds)
    assert any("EV-DETACHED" in iri for iri in rep.evidence_without_requirement)


# ---------------------------------------------------------------------------
# Coverage matrix
# ---------------------------------------------------------------------------

def test_coverage_matrix_includes_failed_outcomes(nominal_dataset):
    """REQ-001's cells should be `covered+failed` reflecting the
    earl:failed attestation."""
    cells = coverage_matrix(nominal_dataset)
    req001_cells = [c for c in cells if c.requirement == "REQ-001"]
    assert req001_cells, "REQ-001 not in coverage matrix"
    assert all(c.status == "covered+failed" for c in req001_cells), (
        f"REQ-001 cells should be covered+failed, got: "
        f"{[(c.evidence, c.status) for c in req001_cells]}"
    )


def test_coverage_matrix_includes_passed_outcomes(nominal_dataset):
    """REQ-002 / REQ-003 / REQ-004 cells should be `covered+passed`."""
    cells = coverage_matrix(nominal_dataset)
    for req in ("REQ-002", "REQ-003", "REQ-004"):
        req_cells = [c for c in cells if c.requirement == req]
        assert req_cells, f"{req} not in coverage matrix"
        assert all(c.status == "covered+passed" for c in req_cells), (
            f"{req} cells should be covered+passed, got: "
            f"{[(c.evidence, c.status) for c in req_cells]}"
        )


# ---------------------------------------------------------------------------
# Render formats
# ---------------------------------------------------------------------------

def test_render_csv_nonempty(nominal_dataset):
    report = audit(nominal_dataset)
    out = render_report(report, fmt="csv")
    assert "requirement,evidence,status" in out
    assert "REQ-001" in out


def test_render_markdown_nonempty(nominal_dataset):
    report = audit(nominal_dataset)
    out = render_report(report, fmt="md")
    assert "# RTM Traceability Audit" in out
    assert "## Direction summary" in out
    assert "## Coverage matrix" in out


def test_render_json_parses(nominal_dataset):
    report = audit(nominal_dataset)
    out = render_report(report, fmt="json")
    parsed = json.loads(out)
    assert parsed["passed"] is True
    assert parsed["forward"]["passed"] is True
    assert parsed["backward"]["passed"] is True
    assert parsed["bidirectional"]["passed"] is True
    assert len(parsed["coverage"]) >= 4


# ---------------------------------------------------------------------------
# <adcs:audit> graph receives the report after Stage 7a
# ---------------------------------------------------------------------------

def test_audit_graph_populated_after_pipeline(nominal_dataset):
    """Stage 7a emits a report resource into <adcs:audit>."""
    audit_g_quads = list(nominal_dataset.quads(
        (None, None, None, URIRef(G_AUDIT))
    ))
    assert audit_g_quads, "<adcs:audit> should be populated by Stage 7a"
    # Confirm a forwardPassed triple is present
    fp_triples = [q for q in audit_g_quads if str(q[1]).endswith("forwardPassed")]
    assert fp_triples, "Expected rtm:forwardPassed in audit graph"
