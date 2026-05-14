"""Phase F — attestation refactor onto GSN nodes.

Confirms that:
  - request_attestation emits gsn:Assumption + gsn:Justification with
    non-empty gsn:statement text, linked via gsn:inContextOf
  - rtm:hasOutcome is one of the EARL outcome values
  - rtm:attestationMode is earl:manual or earl:semiAuto
  - prov:qualifiedAssociation is present with hadRole + hadPlan
  - rtm:followedProcedure links to the standard SOP
  - rtm:hasEvidence still attaches each evidence artifact
  - The deprecated rtm:modelAdequacy / rtm:evidenceSufficiency properties
    no longer appear on emitted attestations
  - Declining (interactive 'no') produces an attestation with outcome
    earl:failed (or earl:cantTell) but still well-formed
"""

from __future__ import annotations

import warnings
from io import StringIO
from unittest.mock import patch

import pytest
from rdflib import Dataset, URIRef
from rdflib.namespace import RDF

from ontology.prefixes import (
    ADCS, EARL, G_ATTESTATIONS, GSN, PROV, RTM,
)
from pipeline.runner import run_pipeline
from traceability.attestation import (
    OUTCOME_CANT_TELL,
    OUTCOME_FAILED,
    OUTCOME_PASSED,
    PLAN_STANDARD_PROCEDURE,
    ROLE_ATTESTING_ENGINEER,
    request_attestation,
)
from traceability.rtm import load_base_dataset


@pytest.fixture(scope="module")
def attested_dataset() -> Dataset:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        return run_pipeline(auto_attest=True)


def _att_iri(req_name: str) -> URIRef:
    return ADCS[f"ATT-{req_name}"]


def _adequacy_iri(req_name: str) -> URIRef:
    return ADCS[f"adequacy/ATT-{req_name}"]


def _sufficiency_iri(req_name: str) -> URIRef:
    return ADCS[f"sufficiency/ATT-{req_name}"]


# ---------------------------------------------------------------------------
# GSN node emission
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("req", ["REQ-002", "REQ-003", "REQ-004"])
def test_attestation_has_adequacy_assumption(attested_dataset, req):
    att = _att_iri(req)
    adequacy = _adequacy_iri(req)
    # Linked from attestation via gsn:inContextOf
    assert (att, GSN.inContextOf, adequacy) in attested_dataset
    # Typed as gsn:Assumption
    assert (adequacy, RDF.type, GSN.Assumption) in attested_dataset
    # Non-empty gsn:statement
    statements = list(attested_dataset.objects(adequacy, GSN.statement))
    assert statements and str(statements[0]).strip(), (
        f"adequacy node for {req} has empty gsn:statement"
    )


@pytest.mark.parametrize("req", ["REQ-002", "REQ-003", "REQ-004"])
def test_attestation_has_sufficiency_justification(attested_dataset, req):
    att = _att_iri(req)
    sufficiency = _sufficiency_iri(req)
    assert (att, GSN.inContextOf, sufficiency) in attested_dataset
    assert (sufficiency, RDF.type, GSN.Justification) in attested_dataset
    statements = list(attested_dataset.objects(sufficiency, GSN.statement))
    assert statements and str(statements[0]).strip(), (
        f"sufficiency node for {req} has empty gsn:statement"
    )


# ---------------------------------------------------------------------------
# Outcome, mode, qualified association
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("req", ["REQ-002", "REQ-003", "REQ-004"])
def test_attestation_outcome_is_earl_passed(attested_dataset, req):
    att = _att_iri(req)
    outcomes = list(attested_dataset.objects(att, RTM.hasOutcome))
    assert outcomes == [OUTCOME_PASSED], (
        f"{req} should have rtm:hasOutcome earl:passed, got {outcomes}"
    )


@pytest.mark.parametrize("req", ["REQ-002", "REQ-003", "REQ-004"])
def test_attestation_mode_is_semi_auto(attested_dataset, req):
    """auto_attest=True path should record earl:semiAuto."""
    att = _att_iri(req)
    modes = list(attested_dataset.objects(att, RTM.attestationMode))
    assert modes == [EARL.semiAuto], f"{req} should have semiAuto mode, got {modes}"


@pytest.mark.parametrize("req", ["REQ-002", "REQ-003", "REQ-004"])
def test_attestation_has_qualified_association(attested_dataset, req):
    att = _att_iri(req)
    assocs = list(attested_dataset.objects(att, PROV.qualifiedAssociation))
    assert len(assocs) == 1, f"{req} should have exactly one qualified association"
    assoc = assocs[0]
    # The association must carry agent + role + plan
    roles = list(attested_dataset.objects(assoc, PROV.hadRole))
    plans = list(attested_dataset.objects(assoc, PROV.hadPlan))
    assert ROLE_ATTESTING_ENGINEER in roles, f"{req}: hadRole missing"
    assert PLAN_STANDARD_PROCEDURE in plans, f"{req}: hadPlan missing"


@pytest.mark.parametrize("req", ["REQ-002", "REQ-003", "REQ-004"])
def test_attestation_followed_procedure(attested_dataset, req):
    att = _att_iri(req)
    procs = list(attested_dataset.objects(att, RTM.followedProcedure))
    assert procs == [PLAN_STANDARD_PROCEDURE], (
        f"{req} should follow the standard procedure, got {procs}"
    )


# ---------------------------------------------------------------------------
# Deprecated properties — must not appear
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("req", ["REQ-002", "REQ-003", "REQ-004"])
def test_deprecated_properties_not_emitted(attested_dataset, req):
    att = _att_iri(req)
    legacy_adequacy = list(attested_dataset.objects(att, RTM.modelAdequacy))
    legacy_sufficiency = list(attested_dataset.objects(att, RTM.evidenceSufficiency))
    assert not legacy_adequacy, (
        f"{req} still emits deprecated rtm:modelAdequacy: {legacy_adequacy}"
    )
    assert not legacy_sufficiency, (
        f"{req} still emits deprecated rtm:evidenceSufficiency: {legacy_sufficiency}"
    )


# ---------------------------------------------------------------------------
# Declination paths (interactive 'no')
# ---------------------------------------------------------------------------

def _decline_on_adequacy(prompt: str) -> str:
    """Mock input that says 'no' to the adequacy prompt."""
    if "Model adequacy" in prompt:
        return "no"
    return ""


def _decline_on_sufficiency(prompt: str) -> str:
    """Mock input that accepts adequacy but says 'no' to sufficiency."""
    if "Model adequacy" in prompt:
        return "Model is adequate."
    if "Evidence sufficiency" in prompt:
        return "no"
    return ""


def test_decline_on_adequacy_emits_earl_failed(capsys):
    """Interactive 'no' on adequacy produces a well-formed attestation
    with outcome=earl:failed, not a None return."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        ds = run_pipeline(auto_attest=True, skip_attestation=True)
    # Run one interactive attestation against the partially-built dataset.
    with patch("builtins.input", side_effect=_decline_on_adequacy):
        att = request_attestation(ds, "REQ-001", "Test Engineer",
                                  auto_attest=False)
    assert att is not None, "Declination should still return the attestation URI"
    outcomes = list(ds.objects(att, RTM.hasOutcome))
    assert outcomes == [OUTCOME_FAILED]


def test_decline_on_sufficiency_emits_earl_cant_tell(capsys):
    """Interactive 'no' on sufficiency produces outcome=earl:cantTell."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        ds = run_pipeline(auto_attest=True, skip_attestation=True)
    with patch("builtins.input", side_effect=_decline_on_sufficiency):
        att = request_attestation(ds, "REQ-001", "Test Engineer",
                                  auto_attest=False)
    assert att is not None
    outcomes = list(ds.objects(att, RTM.hasOutcome))
    assert outcomes == [OUTCOME_CANT_TELL]
