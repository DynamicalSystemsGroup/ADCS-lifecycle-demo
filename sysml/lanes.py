"""Three-lane Mermaid flowchart of the assembled model, built from already-evaluated API elements.

`lanes_mermaid(to_elements(text))` opens no OpenSysML connection. Structure (hand-authored), evidence
(generated from scipy) and attestation (written only by a human) are three subgraphs. Amber marks
what a person wrote; a `not satisfy` claim and a pending marker are drawn differently from a
`satisfy`. Verdicts are deliberately absent: they are verification output, not part of the lanes.
"""

from __future__ import annotations

from sysml.figures import PALETTE
from sysml.model import PACKAGE

_STRUCTURE_TITLE = "STRUCTURE · in Git"
_EVIDENCE_TITLE = "EVIDENCE · from scipy"
_ATTESTATION_TITLE = "ATTESTATION · human-written"


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


def lanes_mermaid(elements: list[dict]) -> str:
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
    edges, cls = [], {}
    for e in top:
        i, t = e["@id"], e["@type"]
        n = _nid(i)
        if t == "PartDefinition":
            lane["S"].append(f'{n}["<b>{name(i)}</b><br/>part def"]')
            cls[n] = "struct"
        elif t == "RequirementUsage":
            lane["S"].append(f'{n}["<b>{name(i)}</b><br/>requirement"]')
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
            lane["A"].append(f'{n}{{{{"<b>{word}</b><br/>{name(i)}"}}}}')
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
                lane["E"].append(f'{n}["ToolExecution<br/>{_clip(txt[0] if txt else "", 30)}"]')
                cls[n] = "machine"
            elif kind == "StatusInfo":
                status = _status(i, s) or "?"
                if txt:
                    lane["A"].append(f'{n}["StatusInfo<br/>status={status}<br/>by {_clip(txt[0], 24)}"]')
                    cls[n] = "human"
                else:  # no person has acted: the pending marker
                    lane["A"].append(f'{n}["tbc<br/><i>no one has judged</i>"]')
                    cls[n] = "pending"
            elif kind == "Rationale":
                role = "sufficiency" if set(about) & satisfies else "adequacy"
                lane["A"].append(f'{n}["Rationale ({role})<br/><i>{_clip(txt[0] if txt else "", 40)}</i>"]')
                cls[n] = "human" if set(about) & named_about else "machine"
            else:
                continue
            for a in about:
                edges.append(f"{n} -. about .-> {_nid(a)}")

    out = ["flowchart LR"]
    for k, title in (("S", _STRUCTURE_TITLE), ("E", _EVIDENCE_TITLE), ("A", _ATTESTATION_TITLE)):
        out.append(f'  subgraph {k}["{title}"]')
        out.append("    direction TB")
        out += ["    " + x for x in lane[k]]
        out.append("  end")
    out += ["  " + x for x in edges]
    h, m, p = PALETTE["human"], PALETTE["machine"], PALETTE["prescribed"]
    out += [
        f"  classDef req fill:#e8f0fe,stroke:{m},stroke-width:2px",
        "  classDef struct fill:#f1f3f4,stroke:#5f6368",
        "  classDef machine fill:#f1f3f4,stroke:#5f6368,stroke-dasharray:4 3",
        f"  classDef human fill:#fff4d6,stroke:{h},stroke-width:4px",
        # a negated claim is still a person's act (amber), but filled solid and struck through
        f"  classDef negated fill:#fbd38d,stroke:{h},stroke-width:4px,color:{p},text-decoration:line-through",
        f"  classDef pending fill:#ffffff,stroke:{h},stroke-width:3px,stroke-dasharray:6 4",
    ]
    out += [f"  class {k} {c}" for k, c in cls.items()]
    return "\n".join(out)
