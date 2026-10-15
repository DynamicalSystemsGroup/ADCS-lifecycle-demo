"""Three-lane Mermaid flowchart of the assembled model, built from already-evaluated API elements.

`lanes_mermaid(to_elements(text))` opens no OpenSysML connection. Structure (hand-authored), evidence
(generated from scipy) and attestation (written only by a human) are three subgraphs. Amber marks
what a person wrote; a `not satisfy` claim and a pending marker are drawn differently from a
`satisfy`. Verdicts are deliberately absent: they are verification output, not part of the lanes.

Colour: amber = a person said it; blue = the machine computed it (ToolExecution and the design
part holding its computed values); neutral grey = prescribed or unattributed. A StatusInfo is
pending when its status is `tbc`: dashed amber if a person is named on it, dashed grey if not.
"""

from __future__ import annotations

from sysml.figures import PALETTE
from sysml.model import PACKAGE

_STRUCTURE_TITLE = "STRUCTURE · in Git"
_EVIDENCE_TITLE = "EVIDENCE · computed (scipy, SymPy)"
_ATTESTATION_TITLE = "ATTESTATION · a person's judgement, or its absence"


def _nid(i: str) -> str:
    return "n" + "".join(c if c.isalnum() else "_" for c in i)


def _clip(text: str, n: int = 44) -> str:
    text = " ".join(text.split()).replace('"', "'")
    return text if len(text) <= n else text[: n - 1] + "…"


def _strings(i: str, s: dict, out: list) -> list:
    """LiteralString values under element `i`, in document order."""
    e = s[i]
    if e["@type"] == "LiteralString":
        out.append(e.get("value") or "")
    for key in ("ownedRelationship", "ownedRelatedElement", "ownedMember"):
        for r in e.get(key, []):
            if r["@id"] in s:
                _strings(r["@id"], s, out)
    return out


def _status(i: str, s: dict) -> str | None:
    """'tbc' or 'done' etc.: the StatusKind literal a StatusInfo refers to."""
    def walk(j):
        e = s[j]
        m = e.get("memberElement")
        if e["@type"] == "Membership" and m and m["@id"] in s:
            q = s[m["@id"]].get("qualifiedName") or ""
            if "StatusKind::" in q:
                return q.rsplit("::", 1)[-1]
        for key in ("ownedRelationship", "ownedRelatedElement", "ownedMember"):
            for r in e.get(key, []):
                if r["@id"] in s and (found := walk(r["@id"])):
                    return found
        return None
    return walk(i)


def lanes_mermaid(elements: list[dict], compact: bool = False, terms: dict | None = None) -> str:
    """The three lanes. `compact=True` is the presentation mode (projector scale): one node per
    human judgement, one per evidence source, the design part and the requirement; the elements
    behind each node are not drawn (the audit trail lists them). `terms` ({"S": .., "E": .., "A": ..},
    compact mode only) adds a third line to a band's header, so a label sits level with its band."""
    if compact:
        return _compact(elements, terms or {})
    s = {e["@id"]: e for e in elements}
    top = [e for e in elements if (e.get("owner") or {}).get("@id") == PACKAGE
           and e["@type"] not in ("OwningMembership", "NamespaceImport")]
    name = lambda i: s[i].get("declaredName") or s[i].get("qualifiedName") or i  # noqa: E731
    lib = lambda e: [s[t["@id"]].get("qualifiedName", "") for t in e.get("type", []) if t["@id"] in s]  # noqa: E731

    satisfies = {e["@id"] for e in top if e["@type"] == "SatisfyRequirementUsage"}
    meta = [e for e in top if e["@type"] == "MetadataUsage"]
    # a person is named on a StatusInfo; a Rationale is theirs when a named StatusInfo is about the same element
    named_about = set()
    for e in meta:
        if any(q.endswith("StatusInfo") for q in lib(e)) and any(_strings(e["@id"], s, [])):
            named_about |= {a["@id"] for a in e.get("annotatedElement", [])}

    lane = {"S": [], "E": [], "A": []}
    edges, cls, about_edges = [], {}, []
    for e in top:
        i, t = e["@id"], e["@type"]
        n = _nid(i)
        if t == "PartDefinition":
            lane["S"].append(f'{n}["<b>{name(i)}</b><br/>part def"]')
            cls[n] = "struct"
        elif t == "RequirementUsage":
            lane["S"].append(f'{n}(["<b>{name(i)}</b><br/>requirement"])')  # stadium: prescribed, set apart by shape
            cls[n] = "req"
        elif t == "PartUsage":
            lane["E"].append(f'{n}["<b>{name(i)}</b> : ADCS"]')
            cls[n] = "machine"
            for ty in e.get("type", []):
                if ty["@id"] in s and s[ty["@id"]]["@type"] == "PartDefinition":
                    edges.append(f"{n} -. typed by .-> {_nid(ty['@id'])}")
        elif t == "SatisfyRequirementUsage":
            neg = bool(e.get("isNegated"))
            word = "not satisfy" if neg else "satisfy"
            head = "NOT satisfied" if neg else word
            lane["A"].append(f'{n}{{{{"<b>{head}</b><br/>{name(i)}"}}}}')
            cls[n] = "negated" if neg else "human"
            if e.get("subsets"):
                edges.append(f"{n} {'-. ' + word + ' .->' if neg else '== ' + word + ' ==>'} {_nid(e['subsets']['@id'])}")
            if e.get("subject"):
                edges.append(f"{n} -- by --> {_nid(e['subject']['@id'])}")
        elif t == "MetadataUsage":
            kind = (lib(e) or [""])[0].split("::")[-1]
            about = [a["@id"] for a in e.get("annotatedElement", []) if a["@id"] in s]
            txt = _strings(i, s, [])
            if kind == "ToolExecution":
                tool = (txt[0] if txt else "").split(" (")[0]  # "scipy solve_ivp (analysis/...)" -> "scipy solve_ivp"
                lane["E"].append(f'{n}["ToolExecution<br/>{_clip(tool, 30)}"]')
                cls[n] = "machine"
            elif kind == "StatusInfo":
                status = _status(i, s) or "?"
                who = _clip(txt[0], 24) if txt else None
                if status == "tbc":  # pending is a status, not an absence; the colour says whether a person is named
                    lane["A"].append(f'{n}["tbc · by {who}"]' if who else f'{n}["tbc · no one has judged"]')
                    cls[n] = "pendingNamed" if who else "pending"
                elif who:
                    lane["A"].append(f'{n}["StatusInfo<br/>status={status}<br/>by {who}"]')
                    cls[n] = "human"
                else:
                    lane["A"].append(f'{n}["StatusInfo<br/>status={status}<br/><i>no originator</i>"]')
                    cls[n] = "neutral"
            elif kind == "Rationale":
                kinds = {s[a]["@type"] for a in about}
                role = ("sufficiency" if set(about) & satisfies else
                        "adequacy" if "PartUsage" in kinds else None)
                head = f"Rationale ({role})" if role else "Rationale"
                lane["A"].append(f'{n}["{head}<br/><i>{_clip(txt[0] if txt else "", 40)}</i>"]')
                cls[n] = "human" if set(about) & named_about else "neutral"  # unattributed: nobody's words
            else:
                continue
            about_edges += [(n, a) for a in about]

    drawn = {x.split("[")[0].split("(")[0].split("{")[0] for k in lane for x in lane[k]}

    def target(a):  # an annotated attribute is not a node: attach the edge to the nearest drawn owner
        while a and _nid(a) not in drawn:
            a = (s.get(a, {}).get("owner") or {}).get("@id")
        return a

    for n, a in about_edges:
        if (t := target(a)):
            edges.append(f"{n} -. about .-> {_nid(t)}")

    out = ["flowchart LR"]
    for k, title in (("S", _STRUCTURE_TITLE), ("E", _EVIDENCE_TITLE), ("A", _ATTESTATION_TITLE)):
        out.append(f'  subgraph {k}["{title}"]')
        out.append("    direction TB")
        out += ["    " + x for x in lane[k]]
        out.append("  end")
    out += ["  " + x for x in edges]
    out += _CLASSDEFS
    out += [f"  class {k} {c}" for k, c in cls.items()]
    return "\n".join(out)


_H, _M, _P = PALETTE["human"], PALETTE["machine"], PALETTE["prescribed"]
_CLASSDEFS = [
    # prescribed: neutral grey fill, the neutral stroke, thick, and a different shape (stadium)
    f"  classDef req fill:#f1f3f4,stroke:{_P},stroke-width:3px",
    "  classDef struct fill:#f1f3f4,stroke:#5f6368",
    "  classDef neutral fill:#ffffff,stroke:#9ca3af",
    # blue only for machine output
    f"  classDef machine fill:#e8f0fe,stroke:{_M},stroke-width:2px",
    f"  classDef human fill:#fff4d6,stroke:{_H},stroke-width:4px",
    # a negated claim is still a person's act (amber), but filled solid, label prefixed NOT satisfied
    f"  classDef negated fill:#fbd38d,stroke:{_H},stroke-width:4px,color:{_P}",
    # pending (status tbc): dashed. Amber when a person is named on it, grey when no one is.
    f"  classDef pendingNamed fill:#ffffff,stroke:{_H},stroke-width:3px,stroke-dasharray:6 4",
    "  classDef pending fill:#ffffff,stroke:#6b7280,stroke-width:3px,stroke-dasharray:6 4",
]


_COMPACT_INIT = (
    "%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '24px', 'lineColor': '#6b7280', "
    "'clusterBkg': '#f8fafc', 'clusterBorder': '#cbd5e1', 'edgeLabelBackground': '#ffffff'}, "
    "'flowchart': {'nodeSpacing': 14, 'rankSpacing': 26, 'padding': 8, 'wrappingWidth': 700}}}%%"
)
_TOOL_NAMES = (("scipy", "scipy<br/>simulation"), ("sympy", "SymPy<br/>estimate"))


def _first_id(node: str) -> str:
    return node.split("[")[0].split("(")[0].split("{")[0]


def _compact(elements: list[dict], terms: dict) -> str:
    """Presentation mode. Three horizontal bands, top to bottom: structure, evidence, attestation.
    Each band has a header node (its title on its own line, so no node can overlap it). Invisible
    links order the bands; the visible links join a judgement to the element it is about and are
    drawn without arrowheads so that they do not fight the band order."""
    s = {e["@id"]: e for e in elements}
    top = [e for e in elements if (e.get("owner") or {}).get("@id") == PACKAGE
           and e["@type"] not in ("OwningMembership", "NamespaceImport")]
    name = lambda i: s[i].get("declaredName") or s[i].get("qualifiedName") or i  # noqa: E731
    lib = lambda e: [s[t["@id"]].get("qualifiedName", "") for t in e.get("type", []) if t["@id"] in s]  # noqa: E731
    about_of = lambda e: [a["@id"] for a in e.get("annotatedElement", []) if a["@id"] in s]  # noqa: E731
    kind_of = lambda e: (lib(e) or [""])[0].split("::")[-1]  # noqa: E731

    meta = [e for e in top if e["@type"] == "MetadataUsage"]
    satisfies = {e["@id"] for e in top if e["@type"] == "SatisfyRequirementUsage"}
    # A StatusInfo that names a person is that person's judgement. The Rationale about the same
    # element is folded into the same node; so is a StatusInfo about a `satisfy` claim.
    judged = {}  # annotated element id -> (who, status)
    for e in meta:
        if kind_of(e) == "StatusInfo":
            txt = _strings(e["@id"], s, [])
            status = _status(e["@id"], s) or "?"
            for a in about_of(e):
                if txt and status != "tbc":
                    judged[a] = (_clip(txt[0], 30), status)

    lane = {"S": [], "E": [], "A": []}
    edges, cls, about_edges, claims = [], {}, [], []
    for e in top:
        i, t = e["@id"], e["@type"]
        n = _nid(i)
        if t == "PartDefinition":
            lane["S"].append(f'{n}["<b>{name(i)}</b><br/>part def"]')
            cls[n] = "struct"
        elif t == "RequirementUsage":
            lane["S"].append(f'{n}(["<b>{name(i)}</b><br/>requirement"])')
            cls[n] = "req"
        elif t == "PartUsage":
            lane["E"].append(f'{n}["<b>{name(i)}</b><br/>the design"]')
            cls[n] = "machine"
        elif t == "SatisfyRequirementUsage":
            neg = bool(e.get("isNegated"))
            who = judged.get(i, ("", ""))[0]
            lane["A"].append(f'{n}{{{{"{"<b>" + who + "</b><br/>" if who else ""}{"NOT satisfied" if neg else "satisfied"}"}}}}')
            cls[n] = "negated" if neg else "human"
            if e.get("subsets"):  # a person's claim: drawn in amber (see `_bands`), dotted when negated
                edges.append(f"{_nid(e['subsets']['@id'])} {'-.-' if neg else '==='} {n}")
                claims.append(len(edges) - 1)
        elif t == "MetadataUsage":
            kind, about, txt = kind_of(e), about_of(e), _strings(i, s, [])
            if kind == "ToolExecution":
                tool = (txt[0] if txt else "").split(" (")[0]
                label = next((v for k, v in _TOOL_NAMES if tool.lower().startswith(k)), _clip(tool, 24))
                lane["E"].append(f'{n}["{label}"]')
                cls[n] = "machine"
                continue
            if kind == "StatusInfo":
                status = _status(i, s) or "?"
                who = _clip(txt[0], 30) if txt else None
                if status == "tbc":
                    lane["A"].append(f'{n}["tbc · by {who}"]' if who else f'{n}["tbc · no one has judged"]')
                    cls[n] = "pendingNamed" if who else "pending"
                elif set(about) & satisfies:
                    continue
                elif who:
                    lane["A"].append(f'{n}["<b>{who}</b><br/>{status} · adequacy"]')
                    cls[n] = "human"
                else:
                    lane["A"].append(f'{n}["status={status}<br/><i>no originator</i>"]')
                    cls[n] = "neutral"
            elif kind == "Rationale":
                if set(about) & set(judged):
                    continue
                lane["A"].append(f'{n}["Rationale<br/><i>{_clip(txt[0] if txt else "", 30)}</i>"]')
                cls[n] = "neutral"
            else:
                continue
            about_edges += [(n, a) for a in about]

    drawn = {_first_id(x) for k in lane for x in lane[k]}

    def target(a):
        while a and _nid(a) not in drawn:
            a = (s.get(a, {}).get("owner") or {}).get("@id")
        return a

    for n, a in about_edges:
        if (t := target(a)) and t not in satisfies:
            edges.append(f"{_nid(t)} -.- {n}")
    return _bands(lane, edges, cls, claims, terms)


def _bands(lane, edges, cls, claims, terms) -> str:
    out = [_COMPACT_INIT, "flowchart TB"]
    order, prev = [], None
    for k, title in (("S", "STRUCTURE<br/>in Git"), ("E", "EVIDENCE<br/>computed"), ("A", "ATTESTATION<br/>a person")):
        ids = [f"h{k}"] + [_first_id(x) for x in lane[k]]
        out.append(f'  subgraph {k}[" "]')
        out.append(f'    h{k}["{title}{"<br/><i>" + terms[k] + "</i>" if terms.get(k) else ""}"]')
        out += ["    " + x for x in lane[k]]
        out.append("  end")
        order += [f"{prev} ~~~ {b}" for b in ids] if prev else []  # a band is one rank, below the last
        prev = f"h{k}"
    out += ["  " + x for x in order + edges]
    out += [f"  linkStyle {len(order) + i} stroke:{_H},stroke-width:4px" for i in claims]
    out += _CLASSDEFS + ["  classDef hdr fill:none,stroke:none,color:#374151,font-weight:bold"]
    out += [f"  class {k} {c}" for k, c in cls.items()]
    out.append("  class hS,hE,hA hdr")
    return "\n".join(out)


# ---------- generated diagrams for slides without a figure (DL-24) ----------

def _label(text: str) -> str:
    return " ".join(str(text).split()).replace('"', "'")


def two_store_mermaid() -> str:
    """S4: Git holds the source, OpenSysML evaluates it, Flexo holds the evaluated model with
    each commit tagged by the Git SHA. The engineer reads the source side."""
    m, p = PALETTE["machine"], PALETTE["prescribed"]
    return "\n".join([
        "%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '24px', 'lineColor': '#6b7280', "
        "'clusterBkg': '#f8fafc', 'clusterBorder': '#cbd5e1'}, "
        "'flowchart': {'nodeSpacing': 24, 'rankSpacing': 36, 'padding': 8}}}%%",
        "flowchart LR",
        '  subgraph G["GIT · source"]',
        '    g1["<b>.sysml</b> text<br/>analysis code<br/>notebook"]',
        "  end",
        '  X{{"<b>OpenSysML</b><br/>evaluates"}}',
        '  subgraph F["FLEXO · model"]',
        '    f1["model elements<br/>tagged <b>git-&lt;sha&gt;</b>"]',
        "  end",
        '  rg["engineer reads<br/>diffs, history"]',
        "  G --> X --> F",
        "  rg -.-> G",
        f"  classDef src fill:#f1f3f4,stroke:{p},stroke-width:3px",
        f"  classDef machine fill:#e8f0fe,stroke:{m},stroke-width:2px",
        "  classDef reader fill:#ffffff,stroke:#9ca3af",
        "  class g1 src",
        "  class X,f1 machine",
        "  class rg reader",
    ])


def sandwich_mermaid(layers) -> str:
    """S7: three stacked layers, top to bottom, labels passed in."""
    layers = [_label(x) for x in layers]
    if len(layers) != 3 or not all(layers):
        raise ValueError(f"sandwich_mermaid takes exactly three non-empty labels, got {layers!r}")
    p = PALETTE["prescribed"]
    out = ["%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '26px', 'lineColor': '#6b7280'}, "
           "'flowchart': {'rankSpacing': 36, 'wrappingWidth': 700}}}%%",
           "flowchart TB"]
    out += [f'  L{i}["{x}"]' for i, x in enumerate(layers)]
    out += ["  L0 --- L1 --- L2", f"  classDef layer fill:#f1f3f4,stroke:{p},stroke-width:3px",
            "  class L0,L1,L2 layer"]
    return "\n".join(out)
