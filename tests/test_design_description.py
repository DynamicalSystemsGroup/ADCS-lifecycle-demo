"""Tests for documents.design_description — the DDVS-001 document compiler.

The document is a deterministic *view* over the RDF dataset: byte-identical
output for identical input quads + identical file bytes. Coverage:

  1. Determinism: two independently parsed Datasets compile to identical bytes
     (catches bnode-label leakage into the rendered output).
  2. Document date comes from the data (MAX prov:generatedAtTime), not wall clock.
  3. Every ADCS requirement gets a detail section; SAT requirements appear
     in the derivation section.
  4. VCRM rows carry the attested EARL outcome + engineer.
  5. GSN adequacy/sufficiency statements are rendered.
  6. Terminology discipline: evidence never "verifies" a requirement.
  7. Dataset fingerprint + all eight named-graph layers in the colophon.
  8. --requirement filter restricts detail sections.
  9. CLI: build writes the file; --check exits 0 when clean, 1 on drift.
"""

from __future__ import annotations

import hashlib
import warnings
from pathlib import Path

import pytest
from rdflib import Dataset
from typer.testing import CliRunner

from documents.design_description import (
    DOC_ID,
    app,
    compile_design_description,
    document_date,
)
from ontology.prefixes import NAMED_GRAPHS
from pipeline.runner import run_pipeline
from traceability.queries import (
    ADCS_REQUIREMENTS,
    ALL_ATTESTATIONS,
    REQUIREMENT_OUTCOMES,
    query_to_dicts,
)

runner = CliRunner()


@pytest.fixture(scope="module")
def rtm_trig(tmp_path_factory) -> Path:
    """A fully attested pipeline run, persisted to TriG."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        ds = run_pipeline(auto_attest=True)
    path = tmp_path_factory.mktemp("ddvs") / "rtm.trig"
    ds.serialize(destination=path, format="trig")
    return path


def _parse(path: Path) -> Dataset:
    ds = Dataset(default_union=True)
    ds.parse(path, format="trig")
    return ds


@pytest.fixture(scope="module")
def dataset(rtm_trig) -> Dataset:
    return _parse(rtm_trig)


@pytest.fixture(scope="module")
def document(rtm_trig, dataset) -> str:
    return compile_design_description(dataset, dataset_path=rtm_trig)


# ---------------------------------------------------------------------------
# 1. Determinism — byte-identical across independent parses
# ---------------------------------------------------------------------------

def test_compile_twice_byte_identical(rtm_trig):
    """Two fresh parses (fresh bnode labels) must compile identically."""
    doc_a = compile_design_description(_parse(rtm_trig), dataset_path=rtm_trig)
    doc_b = compile_design_description(_parse(rtm_trig), dataset_path=rtm_trig)
    assert doc_a.encode("utf-8") == doc_b.encode("utf-8")
    assert doc_a.endswith("\n") and not doc_a.endswith("\n\n")


# ---------------------------------------------------------------------------
# 2. Document date is data-derived, never wall clock
# ---------------------------------------------------------------------------

def test_document_date_from_data_not_wall_clock(dataset, document):
    rows = query_to_dicts(
        dataset,
        "SELECT (MAX(?t) AS ?m) WHERE { ?s prov:generatedAtTime ?t }",
    )
    max_time = rows[0]["m"]
    assert max_time, "fixture dataset must carry prov:generatedAtTime"
    assert document_date(dataset) == max_time
    assert max_time in document


# ---------------------------------------------------------------------------
# 3. Requirement coverage
# ---------------------------------------------------------------------------

def test_all_requirements_have_sections(dataset, document):
    reqs = query_to_dicts(dataset, ADCS_REQUIREMENTS)
    assert reqs, "fixture dataset must contain ADCS requirements"
    for r in reqs:
        assert f"### {r['name']}" in document
    for sat in ("SAT-REQ-POINTING", "SAT-REQ-MOMENTUM",
                "SAT-REQ-STABILITY", "SAT-REQ-DISTURBANCE"):
        assert sat in document


# ---------------------------------------------------------------------------
# 4. VCRM carries attested outcome + engineer
# ---------------------------------------------------------------------------

def test_vcrm_renders_attested_outcomes(dataset, document):
    outcomes = query_to_dicts(dataset, REQUIREMENT_OUTCOMES)
    # Scope to §5 — the allocation table (§4) also has rows starting
    # with the requirement name, and must not satisfy these assertions.
    vcrm_section = document.split("## 5.")[1].split("## 6.")[0]
    vcrm_rows = [
        line for line in vcrm_section.splitlines() if line.startswith("| REQ-")
    ]
    assert vcrm_rows, "expected VCRM table rows starting with '| REQ-'"
    by_req = {line.split("|")[1].strip(): line for line in vcrm_rows}
    for o in outcomes:
        assert o["reqName"] in by_req
        if o["outcomeShort"]:
            assert o["outcomeShort"] in by_req[o["reqName"]]
            assert "ADCS Engineer" in by_req[o["reqName"]]


# ---------------------------------------------------------------------------
# 5. GSN adequacy / sufficiency statements rendered
# ---------------------------------------------------------------------------

def test_gsn_statements_rendered(dataset, document):
    atts = query_to_dicts(dataset, ALL_ATTESTATIONS)
    assert atts, "fixture dataset must contain attestations"
    flat_doc = " ".join(document.split())
    for a in atts:
        assert " ".join(a["adequacy"].split()) in flat_doc
        assert " ".join(a["sufficiency"].split()) in flat_doc


# ---------------------------------------------------------------------------
# 6. Terminology discipline — evidence never "verifies" a requirement
# ---------------------------------------------------------------------------

def test_terminology_discipline(document):
    lowered = " ".join(document.lower().split())
    for phrase in (
        "verified by evidence",
        "evidence verifies",
        "verified by simulation",
        "verified by proof",
    ):
        assert phrase not in lowered
    assert (
        "evidence informs attestation; it does not by itself establish "
        "requirement status" in lowered
    )


# ---------------------------------------------------------------------------
# 7. Fingerprint + colophon
# ---------------------------------------------------------------------------

def test_fingerprint_and_colophon(rtm_trig, document):
    digest = hashlib.sha256(rtm_trig.read_bytes()).hexdigest()
    assert document.count(digest) >= 2  # front matter + colophon
    for layer in NAMED_GRAPHS:
        assert layer in document
    assert DOC_ID in document


# ---------------------------------------------------------------------------
# 8. --requirement filter
# ---------------------------------------------------------------------------

def test_requirement_filter(rtm_trig, dataset):
    doc = compile_design_description(
        dataset, dataset_path=rtm_trig, requirement="REQ-003"
    )
    sections = [
        line for line in doc.splitlines() if line.startswith("### REQ-")
    ]
    assert len(sections) == 1
    assert sections[0].startswith("### REQ-003")


# ---------------------------------------------------------------------------
# 9. CLI — build + --check drift gate
# ---------------------------------------------------------------------------

def test_cli_build_then_check_clean_then_drift(rtm_trig, tmp_path):
    out = tmp_path / "design_description.md"

    result = runner.invoke(
        app, ["--input", str(rtm_trig), "--output", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "AUTO-GENERATED" in out.read_text(encoding="utf-8")

    result = runner.invoke(
        app, ["--input", str(rtm_trig), "--output", str(out), "--check"]
    )
    assert result.exit_code == 0, result.output

    with out.open("a", encoding="utf-8") as fh:
        fh.write("hand edit\n")
    result = runner.invoke(
        app, ["--input", str(rtm_trig), "--output", str(out), "--check"]
    )
    assert result.exit_code == 1


def test_cli_check_missing_output_exits_2(rtm_trig, tmp_path):
    result = runner.invoke(
        app,
        ["--input", str(rtm_trig),
         "--output", str(tmp_path / "never-built.md"), "--check"],
    )
    assert result.exit_code == 2


def test_cli_stdout_prints_document(rtm_trig, tmp_path):
    out = tmp_path / "unwritten.md"
    result = runner.invoke(
        app, ["--input", str(rtm_trig), "--output", str(out), "--stdout"]
    )
    assert result.exit_code == 0
    assert DOC_ID in result.stdout
    assert not out.exists()


def test_cli_check_rejects_requirement_and_stdout(rtm_trig, tmp_path):
    """--check verifies the full default artifact; a filtered or
    stdout-only recompile can never byte-match it, so the combinations
    are usage errors rather than guaranteed-spurious drift reports."""
    out = tmp_path / "design_description.md"
    result = runner.invoke(app, ["--input", str(rtm_trig), "--output", str(out)])
    assert result.exit_code == 0
    for extra in (["--requirement", "REQ-003"], ["--stdout"]):
        result = runner.invoke(
            app,
            ["--input", str(rtm_trig), "--output", str(out), "--check", *extra],
        )
        assert result.exit_code == 2, result.output


def test_cli_unknown_requirement_exits_2_without_writing(rtm_trig, tmp_path):
    """A typo'd --requirement must not silently overwrite the document
    with one whose detail section is empty."""
    out = tmp_path / "design_description.md"
    result = runner.invoke(
        app,
        ["--input", str(rtm_trig), "--output", str(out),
         "--requirement", "REQ-03"],
    )
    assert result.exit_code == 2
    assert not out.exists()


def test_cli_check_is_a_byte_gate(rtm_trig, tmp_path):
    """CRLF-converted output differs in bytes and must register as drift
    even though universal-newline text reads would normalize it away."""
    out = tmp_path / "design_description.md"
    result = runner.invoke(app, ["--input", str(rtm_trig), "--output", str(out)])
    assert result.exit_code == 0
    out.write_bytes(out.read_bytes().replace(b"\n", b"\r\n"))
    result = runner.invoke(
        app, ["--input", str(rtm_trig), "--output", str(out), "--check"]
    )
    assert result.exit_code == 1


def test_evidence_without_gentime_still_listed(rtm_trig):
    """Evidence lacking prov:generatedAtTime must still appear in the
    document (with '-' for the timestamp), not silently vanish while the
    attestation's cited-evidence list still names it."""
    from rdflib import URIRef

    from ontology.prefixes import ADCS, PROV

    ds = _parse(rtm_trig)
    ev = URIRef(str(ADCS) + "EV-PROOF-REQ-001")
    assert (ev, PROV.generatedAtTime, None) in ds
    ds.remove((ev, PROV.generatedAtTime, None))
    doc = compile_design_description(ds, dataset_path=rtm_trig)
    req_001 = doc.split("### REQ-001")[1].split("### REQ-")[0]
    evidence_table = req_001.split("#### Evidence artifacts")[1].split("####")[0]
    assert "| EV-PROOF-REQ-001 |" in evidence_table
    assert "| - |" in evidence_table  # missing timestamp renders as '-'
