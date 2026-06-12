"""DDVS-001 — ADCS Design Description & Verification Status compiler.

Compiles a classic engineering document as a deterministic *view* over the
persisted RDF dataset (output/rtm.trig). The compiler is a pure function:
identical input quads + identical input file bytes produce byte-identical
Markdown. Nothing here consults the wall clock — the document date is the
maximum prov:generatedAtTime in the dataset, and the dataset fingerprint is
the sha256 of the raw input file bytes (the dataset contains blank nodes,
which rdflib relabels on every parse, so a re-serialization hash would not
be stable).

Term discipline: the VCRM "outcome" column and the per-requirement status
lines report the human attestation judgement. Evidence informs attestation;
it does not by itself establish requirement status.
"""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

import typer
from rdflib import Dataset, URIRef

from ontology.prefixes import NAMED_GRAPHS
from traceability.queries import (
    ADCS_REQUIREMENTS,
    ATTESTATION_DETAIL,
    EVIDENCE_DETAIL,
    REQUIREMENT_ALLOCATION,
    REQUIREMENT_DERIVATION,
    SAT_REQUIREMENTS,
    query_to_dicts,
)

DOC_ID = "DDVS-001"
DOC_TITLE = "ADCS Design Description & Verification Status"
SHORT_HASH = 12

_MAX_GENERATED_AT_Q = """
SELECT (MAX(?t) AS ?maxTime) WHERE { ?s prov:generatedAtTime ?t }
"""

_BASELINE_COMMITS_Q = """
SELECT DISTINCT ?commit WHERE {
    ?att a rtm:Attestation ;
         rtm:gitCommit ?commit .
}
ORDER BY ?commit
"""


# ---------------------------------------------------------------------------
# Deterministic building blocks
# ---------------------------------------------------------------------------

def dataset_fingerprint(path: Path) -> str:
    """sha256 hex digest of the raw dataset file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document_date(ds: Dataset) -> str:
    """Maximum prov:generatedAtTime in the union graph (data-derived)."""
    rows = query_to_dicts(ds, _MAX_GENERATED_AT_Q)
    max_time = rows[0]["maxTime"] if rows else None
    return max_time or "-"


def baseline_commit(ds: Dataset) -> str:
    """Distinct rtm:gitCommit values across attestations, sorted."""
    commits = sorted(
        r["commit"] for r in query_to_dicts(ds, _BASELINE_COMMITS_Q) if r["commit"]
    )
    return ", ".join(commits) if commits else "-"


def graph_quad_counts(ds: Dataset) -> list[tuple[str, str, int]]:
    """(layer, graph IRI, triple count) per named graph, sorted by layer."""
    return [
        (layer, iri, len(ds.graph(URIRef(iri))))
        for layer, iri in sorted(NAMED_GRAPHS.items())
    ]


def _local(iri: str | None) -> str:
    """Local name after the last '#' or '/'; '-' for missing values."""
    if not iri:
        return "-"
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _one_line(text: str | None) -> str:
    """Collapse all whitespace runs (incl. newlines) to single spaces."""
    return " ".join(text.split()) if text else "-"


def _join(values: Iterable[str]) -> str:
    """Deduplicated, sorted, comma-joined cell value; '-' when empty."""
    return ", ".join(sorted(set(values))) or "-"


def _cell(text: str | None) -> str:
    """Escape a value for use inside a Markdown pipe-table cell."""
    return _one_line(text).replace("|", "\\|")


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Unpadded pipe table (padding invites width-dependent diffs)."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(" --- " for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

def compile_design_description(
    ds: Dataset,
    *,
    dataset_path: Path | None = None,
    requirement: str | None = None,
) -> str:
    """Compile the DDVS-001 Markdown document from the dataset.

    Pure function of (union quads, input file bytes): every collection is
    explicitly sorted, all timestamps come from the data, and the output
    ends in exactly one newline. ``requirement`` restricts the detail
    sections (§6) to one ADCS requirement; the document-wide tables keep
    full coverage so the view stays honest about overall status.
    """
    reqs = sorted(query_to_dicts(ds, ADCS_REQUIREMENTS), key=lambda r: r["name"])
    sats = sorted(query_to_dicts(ds, SAT_REQUIREMENTS), key=lambda r: r["name"])
    derivation = sorted(
        query_to_dicts(ds, REQUIREMENT_DERIVATION),
        key=lambda r: (r["adcsName"], r["satName"]),
    )
    allocation = sorted(
        query_to_dicts(ds, REQUIREMENT_ALLOCATION),
        key=lambda r: (r["reqName"], r["elementName"]),
    )
    evidence = sorted(
        query_to_dicts(ds, EVIDENCE_DETAIL),
        key=lambda r: (r["reqName"], r["ev"]),
    )
    attestations = sorted(
        query_to_dicts(ds, ATTESTATION_DETAIL),
        key=lambda r: (r["reqName"], r["att"]),
    )

    derived_from: dict[str, list[str]] = {}
    for row in derivation:
        derived_from.setdefault(row["adcsName"], []).append(row["satName"])
    allocated_to: dict[str, list[str]] = {}
    for row in allocation:
        allocated_to.setdefault(row["reqName"], []).append(row["elementName"])
    evidence_by_req: dict[str, list[dict[str, str]]] = {}
    for row in evidence:
        evidence_by_req.setdefault(row["reqName"], []).append(row)
    atts_by_req: dict[str, list[dict[str, str]]] = {}
    for row in attestations:
        atts_by_req.setdefault(row["reqName"], []).append(row)

    fingerprint = dataset_fingerprint(dataset_path) if dataset_path else "-"
    counts = graph_quad_counts(ds)
    total_quads = sum(n for _, _, n in counts)

    lines: list[str] = [
        "<!-- AUTO-GENERATED ARTIFACT - DO NOT EDIT.",
        "     This document is a deterministic view compiled from the RDF",
        "     dataset by documents/design_description.py. Edit the dataset",
        "     (re-run the pipeline), then rebuild:",
        "       uv run python -m documents.design_description -->",
        "",
        f"# {DOC_ID} — {DOC_TITLE}",
        "",
        "## 1. Front matter",
        "",
    ]
    lines.extend(_md_table(
        ["Field", "Value"],
        [
            ["Document ID", DOC_ID],
            ["Baseline git commit", baseline_commit(ds)],
            ["Dataset", dataset_path.as_posix() if dataset_path else "-"],
            ["Dataset SHA-256", fingerprint],
            ["Quad count", str(total_quads)],
            ["Document date", document_date(ds)],
            ["Compiler", "documents/design_description.py"],
        ],
    ))
    lines.extend([
        "",
        "## 2. Scope and terminology",
        "",
        "This document is a compiled view over the requirements-traceability",
        "dataset; it introduces no content of its own. Automated checks",
        "(SHACL closure rules, content-hash re-verification, the behavior",
        "oracle) are *verification*: computations whose results are fully",
        "specified. Requirement status is *validation*: a human engineer's",
        "attestation, recorded with its adequacy assumption and sufficiency",
        "justification. Evidence informs attestation; it does not by itself",
        "establish requirement status.",
        "",
        "## 3. Requirement derivation (satellite → ADCS)",
        "",
    ])
    lines.extend(_md_table(
        ["Satellite requirement", "Statement", "Derived ADCS requirement(s)"],
        [
            [
                sat["name"],
                _cell(sat["text"]),
                _join(
                    adcs for adcs, parents in derived_from.items()
                    if sat["name"] in parents
                ),
            ]
            for sat in sats
        ],
    ))
    lines.extend([
        "",
        "## 4. Requirement allocation (ADCS requirement → component)",
        "",
    ])
    lines.extend(_md_table(
        ["Requirement", "Allocated component(s)"],
        [
            [r["name"], _join(allocated_to.get(r["name"], []))]
            for r in reqs
        ],
    ))
    lines.extend([
        "",
        "## 5. Verification Cross-Reference Matrix (VCRM)",
        "",
        "The outcome column is the recorded human attestation judgement",
        "(EARL outcome), not an automated result.",
        "",
    ])
    vcrm_rows: list[list[str]] = []
    for r in reqs:
        name = r["name"]
        evs = evidence_by_req.get(name, [])
        atts = atts_by_req.get(name, [])
        outcomes = sorted({a["outcomeShort"] for a in atts if a["outcomeShort"]})
        vcrm_rows.append([
            name,
            _join(allocated_to.get(name, [])),
            _join(_local(e["method"]) for e in evs if e["method"]),
            str(len(evs)),
            "; ".join(outcomes) if outcomes else "not attested",
            _join(a["engineer"] for a in atts if a["engineer"]),
            _join(_local(a["mode"]) for a in atts if a["mode"]),
        ])
    lines.extend(_md_table(
        ["Requirement", "Component(s)", "Evidence method(s)", "Evidence count",
         "Attested outcome", "Attested by", "Mode"],
        vcrm_rows,
    ))
    lines.extend([
        "",
        "## 6. Requirement detail",
        "",
    ])

    detail_reqs = [r for r in reqs if requirement is None or r["name"] == requirement]
    for r in detail_reqs:
        name = r["name"]
        lines.extend([
            f"### {name}",
            "",
            f"**Statement.** {_one_line(r['text'])}",
            "",
            f"- Derived from: {_join(derived_from.get(name, []))}",
            f"- Allocated to: {_join(allocated_to.get(name, []))}",
            "",
            "#### Evidence artifacts",
            "",
        ])
        evs = evidence_by_req.get(name, [])
        if evs:
            lines.extend(_md_table(
                ["Artifact", "Type", "Method", "Content hash", "Model hash",
                 "Generated at", "Summary"],
                [
                    [
                        _local(e["ev"]),
                        _local(e["type"]),
                        _local(e["method"]),
                        _cell(e["contentHash"]),
                        _cell(e["modelHash"]),
                        _cell(e["genTime"]),
                        _cell(e["summary"]),
                    ]
                    for e in evs
                ],
            ))
        else:
            lines.append("No evidence artifacts address this requirement.")
        lines.extend(["", "#### Attestation", ""])
        atts = atts_by_req.get(name, [])
        if not atts:
            lines.extend([
                "Status: not attested. No engineer has attested this",
                "requirement; evidence alone does not establish status.",
            ])
        for a in atts:
            cited = _join(
                _local(ev) for ev in (a["evidence"] or "").split("|") if ev
            )
            lines.extend([
                f"- Attestation: {_local(a['att'])}",
                f"- Outcome: {a['outcomeShort']}",
                f"- Attested by: {a['engineer']}",
                f"- Mode: {_local(a['mode'])}",
                f"- Git commit: {a['gitCommit'] or '-'}",
                f"- Timestamp: {a['timestamp']}",
                f"- Evidence cited: {cited}",
                "",
                "#### Assurance context (GSN)",
                "",
                f"> **Adequacy assumption:** {_one_line(a['adequacy'])}",
                ">",
                f"> **Sufficiency justification:** {_one_line(a['sufficiency'])}",
            ])
        lines.append("")

    lines.extend([
        "## 7. Colophon",
        "",
    ])
    lines.extend(_md_table(
        ["Layer", "Named graph", "Triples"],
        [[layer, f"`{iri}`", str(n)] for layer, iri, n in counts],
    ))
    lines.extend([
        "",
        f"Dataset SHA-256: `{fingerprint}`",
        "",
        "Rebuild and drift-check:",
        "",
        "```bash",
        "uv run python -m documents.design_description"
        + (f" --input {dataset_path.as_posix()}" if dataset_path else ""),
        "uv run python -m documents.design_description --check",
        "```",
    ])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=False,
    help=(
        f"Compile {DOC_ID} ({DOC_TITLE}) — a deterministic Markdown view "
        "over the persisted RTM dataset."
    ),
    no_args_is_help=False,
)


@app.command()
def cli(
    input: Annotated[Path, typer.Option(
        "--input", help="TriG dataset to compile from.",
    )] = Path("output/rtm.trig"),
    output: Annotated[Path, typer.Option(
        "--output", help="Markdown file to (re)build.",
    )] = Path("output/design_description.md"),
    requirement: Annotated[str | None, typer.Option(
        "--requirement",
        help="Restrict the detail sections to one requirement (e.g. REQ-003).",
    )] = None,
    check: Annotated[bool, typer.Option(
        "--check",
        help=(
            "Recompile and diff against --output without writing; "
            "exit 1 on drift, 2 if the output is missing."
        ),
    )] = False,
    stdout: Annotated[bool, typer.Option(
        "--stdout", help="Print the document instead of writing --output.",
    )] = False,
) -> None:
    """Build (or drift-check) the design-description document."""
    if check and (requirement is not None or stdout):
        typer.echo(
            "--check verifies the full document artifact; it cannot be "
            "combined with --requirement or --stdout.", err=True,
        )
        raise typer.Exit(code=2)
    if not input.exists():
        typer.echo(f"Input not found: {input}.", err=True)
        raise typer.Exit(code=2)
    ds = Dataset(default_union=True)
    ds.parse(input, format="trig")
    if requirement is not None:
        known = sorted(
            r["name"] for r in query_to_dicts(ds, ADCS_REQUIREMENTS)
        )
        if requirement not in known:
            typer.echo(
                f"Unknown requirement: {requirement}. "
                f"Known requirements: {', '.join(known)}.", err=True,
            )
            raise typer.Exit(code=2)
    doc = compile_design_description(
        ds, dataset_path=input, requirement=requirement
    )
    if check:
        if not output.exists():
            typer.echo(f"Output not found: {output}. Build it first.", err=True)
            raise typer.Exit(code=2)
        # Byte comparison, deliberately: read_text() would normalize
        # CRLF away and pass a file that violates byte-identity.
        current = output.read_bytes()
        if current == doc.encode("utf-8"):
            typer.echo(f"{output} is up to date.")
            return
        diff = difflib.unified_diff(
            current.decode("utf-8", errors="replace").splitlines(),
            doc.splitlines(),
            fromfile=str(output), tofile="recompiled", lineterm="",
        )
        for line in list(diff)[:40]:
            typer.echo(line, err=True)
        typer.echo(f"{output} has drifted from the dataset.", err=True)
        raise typer.Exit(code=1)
    if stdout:
        typer.echo(doc, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(doc.encode("utf-8"))
    typer.echo(f"Wrote {output} ({len(doc.encode('utf-8'))} bytes).")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
