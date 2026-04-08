"""RDF namespace constants for the ADCS lifecycle demo.

Three layers:
- Layer 1: W3C standards (PROV-O, Dublin Core)
- Layer 2: SysMLv2 vocabulary (structural blocks, requirements, satisfy)
- Layer 3: Custom RTM ontology (evidence, attestation, traceability)
"""

from rdflib import Namespace

# Layer 1 — W3C Standards
# PROV-O and Dublin Core are built into rdflib, but we define them
# explicitly for clarity in SPARQL prefixes and graph binding.
PROV = Namespace("http://www.w3.org/ns/prov#")
DCTERMS = Namespace("http://purl.org/dc/terms/")

# Layer 2 — SysMLv2
SYSML = Namespace("https://www.omg.org/spec/SysML/2.0/")

# Layer 3 — Custom RTM + Instance data
RTM = Namespace("http://example.org/ontology/rtm#")
ADCS = Namespace("http://example.org/adcs-demo/")
SAT = Namespace("http://example.org/adcs-demo/satellite/")

# All prefixes for graph binding
PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "prov": str(PROV),
    "dcterms": str(DCTERMS),
    "sysml": str(SYSML),
    "rtm": str(RTM),
    "adcs": str(ADCS),
    "sat": str(SAT),
}


def bind_prefixes(graph):
    """Bind all project prefixes to an rdflib Graph."""
    for prefix, uri in PREFIXES.items():
        graph.bind(prefix, uri)
    return graph
