"""RTM graph visualization using graphviz.

Renders the traceability graph as a directed graph with nodes color-coded
by type and edge labels showing relationship types.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from ontology.prefixes import PROV, RTM, SYSML
from traceability.queries import query_to_dicts

# Color scheme
_COLORS = {
    "requirement": "#4A90D9",      # blue
    "sat_requirement": "#7FB3DE",  # light blue
    "design_element": "#7BC67E",   # green
    "proof": "#F5A623",            # orange
    "simulation": "#F5D423",       # yellow
    "attestation": "#D94A4A",      # red
    "engine": "#999999",           # gray
    "engineer": "#C49BD9",         # purple
}


def build_dot(graph: Graph) -> str:
    """Build a Graphviz DOT string from the RTM graph."""
    lines = [
        'digraph RTM {',
        '  rankdir=LR;',
        '  node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=8];',
        '',
    ]

    # Satellite-level requirements
    q = """
    SELECT ?name WHERE {
        ?req a sysml:RequirementDefinition ;
             sysml:declaredName ?name .
        FILTER(STRSTARTS(?name, "SAT-"))
    }
    """
    for row in query_to_dicts(graph, q):
        n = row["name"]
        lines.append(f'  "{n}" [fillcolor="{_COLORS["sat_requirement"]}", '
                     f'label="{n}\\n(satellite)"];')

    # ADCS requirements
    q = """
    SELECT ?name WHERE {
        ?req a sysml:RequirementDefinition ;
             sysml:declaredName ?name .
        FILTER(STRSTARTS(?name, "REQ-"))
    }
    """
    for row in query_to_dicts(graph, q):
        n = row["name"]
        lines.append(f'  "{n}" [fillcolor="{_COLORS["requirement"]}"];')

    # Derivation edges
    q = """
    SELECT ?child ?parent WHERE {
        ?c sysml:declaredName ?child ;
           rtm:derivedFrom ?p .
        ?p sysml:declaredName ?parent .
    }
    """
    for row in query_to_dicts(graph, q):
        lines.append(f'  "{row["parent"]}" -> "{row["child"]}" [label="derivedFrom"];')

    # Design elements (from satisfy links)
    q = """
    SELECT DISTINCT ?elementName WHERE {
        ?rel a sysml:SatisfyRequirementUsage ;
             sysml:satisfyingElement ?el .
        ?el sysml:declaredName ?elementName .
    }
    """
    for row in query_to_dicts(graph, q):
        n = row["elementName"]
        lines.append(f'  "{n}" [fillcolor="{_COLORS["design_element"]}"];')

    # Satisfy edges
    q = """
    SELECT ?reqName ?elementName WHERE {
        ?req sysml:declaredName ?reqName ;
             sysml:ownedRelationship ?rel .
        ?rel a sysml:SatisfyRequirementUsage ;
             sysml:satisfyingElement ?el .
        ?el sysml:declaredName ?elementName .
        FILTER(STRSTARTS(?reqName, "REQ-"))
    }
    """
    for row in query_to_dicts(graph, q):
        lines.append(f'  "{row["reqName"]}" -> "{row["elementName"]}" [label="satisfiedBy"];')

    # Evidence nodes
    q = """
    SELECT ?ev ?type ?hash ?reqName WHERE {
        ?ev a ?type ;
            rtm:contentHash ?hash ;
            prov:wasGeneratedBy ?act .
        ?act prov:used ?req .
        ?req sysml:declaredName ?reqName .
        FILTER(?type IN (rtm:ProofArtifact, rtm:SimulationResult))
    }
    """
    for row in query_to_dicts(graph, q):
        ev_type = row["type"].split("#")[-1]
        short_hash = row["hash"][:8]
        node_id = f"ev_{short_hash}"
        color = _COLORS["proof"] if ev_type == "ProofArtifact" else _COLORS["simulation"]
        label = f"{ev_type}\\n{short_hash}..."
        lines.append(f'  "{node_id}" [fillcolor="{color}", label="{label}"];')
        lines.append(f'  "{row["reqName"]}" -> "{node_id}" [label="evidence", style=dashed];')

    # Attestation nodes
    q = """
    SELECT ?reqName ?engineer ?timestamp WHERE {
        ?att a rtm:Attestation ;
             rtm:attests ?req ;
             prov:wasAssociatedWith ?agent ;
             prov:generatedAtTime ?timestamp .
        ?agent rdfs:label ?engineer .
        ?req sysml:declaredName ?reqName .
    }
    """
    for row in query_to_dicts(graph, q):
        att_id = f"att_{row['reqName']}"
        ts = row["timestamp"][:10] if row["timestamp"] else ""
        label = f"Attestation\\n{row['engineer']}\\n{ts}"
        lines.append(f'  "{att_id}" [fillcolor="{_COLORS["attestation"]}", '
                     f'fontcolor=white, label="{label}"];')
        lines.append(f'  "{att_id}" -> "{row["reqName"]}" [label="attests", '
                     f'color="{_COLORS["attestation"]}"];')

    lines.append('}')
    return '\n'.join(lines)


def render_rtm(
    graph: Graph,
    output_path: str | Path = "output/rtm_graph",
    fmt: str = "svg",
) -> Path:
    """Render the RTM graph to a file.

    Requires graphviz to be installed on the system.
    Returns the path to the rendered file.
    """
    import graphviz as gv

    dot_str = build_dot(graph)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    src = gv.Source(dot_str)
    rendered = src.render(str(output_path), format=fmt, cleanup=True)
    return Path(rendered)
