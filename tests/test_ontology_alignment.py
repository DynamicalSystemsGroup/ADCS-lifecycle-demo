"""Phase A — confirm the integration ontology declares the expected
subclass / subproperty / equivalence links to upstream standards.

These are pure axiom checks against rtm.ttl. The vendored imports and
ROBOT-built artifact arrive in Phase B; here we verify that the alignment
authoring is correct.
"""

from rdflib import Graph, URIRef
from rdflib.namespace import RDFS, OWL

from ontology.prefixes import (
    RTM, PROV, EARL, GSN, P_PLAN, OSLC_RM, OSLC_QM, SYSML, OMG_SYSML, bind_prefixes,
)


def _load_ontology() -> Graph:
    g = Graph()
    bind_prefixes(g)
    g.parse("ontology/rtm.ttl", format="turtle")
    g.parse("ontology/rtm_individuals.ttl", format="turtle")
    return g


SUBCLASS_AXIOMS = [
    # Attestation is multi-typed
    (RTM.Attestation, EARL.Assertion),
    (RTM.Attestation, GSN.Strategy),
    (RTM.Attestation, PROV.Activity),
    # Evidence is multi-typed
    (RTM.Evidence, PROV.Entity),
    (RTM.Evidence, GSN.Solution),
    (RTM.ProofArtifact, RTM.Evidence),
    (RTM.SimulationResult, RTM.Evidence),
    # Agents
    (RTM.Engineer, EARL.Assertor),
    (RTM.Engineer, PROV.Agent),
    (RTM.ComputationEngine, PROV.SoftwareAgent),
    # Computational activities
    (RTM.SymbolicAnalysis, PROV.Activity),
    (RTM.NumericalSimulation, PROV.Activity),
    # Requirement-as-OSLC for tool interop
    (SYSML.RequirementDefinition, OSLC_RM.Requirement),
]


SUBPROPERTY_AXIOMS = [
    (RTM.attests, EARL.test),
    (RTM.attests, OSLC_QM.validatesRequirement),
    (RTM.hasEvidence, PROV.used),
    (RTM.hasEvidence, GSN.supportedBy),
    (RTM.hasOutcome, EARL.outcome),
    (RTM.attestationMode, EARL.mode),
    (RTM.followedProcedure, PROV.hadPlan),
]


SYSML_EQUIVALENCE_CLASSES = [
    (SYSML.RequirementDefinition, OMG_SYSML.RequirementDefinition),
    (SYSML.RequirementUsage, OMG_SYSML.RequirementUsage),
    (SYSML.SatisfyRequirementUsage, OMG_SYSML.SatisfyRequirementUsage),
    (SYSML.PartDefinition, OMG_SYSML.PartDefinition),
    (SYSML.PartUsage, OMG_SYSML.PartUsage),
    (SYSML.AttributeUsage, OMG_SYSML.AttributeUsage),
]

SYSML_EQUIVALENCE_PROPERTIES = [
    (SYSML.declaredName, OMG_SYSML.declaredName),
    (SYSML.text, OMG_SYSML.text),
    (SYSML.ownedRelationship, OMG_SYSML.ownedRelationship),
]


def test_subclass_alignment():
    g = _load_ontology()
    missing = [(a, b) for a, b in SUBCLASS_AXIOMS if (a, RDFS.subClassOf, b) not in g]
    assert not missing, f"Missing rdfs:subClassOf axioms: {missing}"


def test_subproperty_alignment():
    g = _load_ontology()
    missing = [
        (a, b) for a, b in SUBPROPERTY_AXIOMS if (a, RDFS.subPropertyOf, b) not in g
    ]
    assert not missing, f"Missing rdfs:subPropertyOf axioms: {missing}"


def test_sysml_class_equivalence():
    g = _load_ontology()
    missing = [
        (a, b) for a, b in SYSML_EQUIVALENCE_CLASSES if (a, OWL.equivalentClass, b) not in g
    ]
    assert not missing, f"Missing owl:equivalentClass axioms: {missing}"


def test_sysml_property_equivalence():
    g = _load_ontology()
    missing = [
        (a, b)
        for a, b in SYSML_EQUIVALENCE_PROPERTIES
        if (a, OWL.equivalentProperty, b) not in g
    ]
    assert not missing, f"Missing owl:equivalentProperty axioms: {missing}"


def test_attestation_inverses():
    g = _load_ontology()
    assert (RTM.attests, OWL.inverseOf, RTM.attestedBy) in g
    assert (RTM.addresses, OWL.inverseOf, RTM.addressedBy) in g


def test_role_and_plan_individuals_present():
    g = _load_ontology()
    role = URIRef(str(RTM) + "role-AttestingEngineer")
    plan = URIRef(str(RTM) + "plan-StandardAttestationProcedure-v1")
    assert (role, None, None) in g, "Missing rtm:role-AttestingEngineer individual"
    assert (plan, None, None) in g, "Missing rtm:plan-StandardAttestationProcedure-v1 individual"
