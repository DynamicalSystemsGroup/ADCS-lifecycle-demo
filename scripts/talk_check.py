"""Talk integrity check: the invariant that holds the talk modules together.

The talk is split into modules (``private/talk/modules/S*.md``) that cite facts
(``private/talk/facts.md``) and demo beats (``BEAT:Bn`` markers in the demo
notebook). Each module can be edited on its own; this check says whether the
pieces still fit. The private directory is gitignored and may be absent, in
which case every check reports ``open``.

Checks (statuses: passed | failed | open):

  facts     every fact a module cites exists and has a source
  beats     every demo beat a module cites exists as a marker in the notebook
  handoff   each module's ``hands_off`` equals the next module's ``receives``
  minutes   module minutes sum to at most the budget
  public    no non-public fact (id or claim) appears in a tracked repo file

Usage:
    uv run python scripts/talk_check.py
    uv run python scripts/talk_check.py --private ../elsewhere/private
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parent.parent
FACT_ID = re.compile(r"\bF-\d{2,3}\b")
BEAT_ID = re.compile(r"\bB\d+\b")
BEAT_MARKER = re.compile(r"BEAT:(B\d+)")

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


@dataclass
class Fact:
    id: str
    claim: str
    source: str
    verified: str
    public: bool


@dataclass
class Module:
    path: Path
    meta: dict[str, object]
    body: str

    @property
    def id(self) -> str:
        return str(self.meta.get("id", self.path.stem.split("-")[0]))

    def cited_facts(self) -> set[str]:
        listed = set(_as_list(self.meta.get("needs_facts")))
        return listed | set(FACT_ID.findall(self.body))

    def cited_beats(self) -> set[str]:
        return {b for b in _as_list(self.meta.get("needs_beats")) if BEAT_ID.fullmatch(b)}


@dataclass
class Result:
    check: str
    status: str  # passed | failed | open
    details: list[str] = field(default_factory=list)


def _as_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _parse_scalar(raw: str) -> object:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [v.strip().strip("\"'") for v in inner.split(",") if v.strip()] if inner else []
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def parse_module(path: Path) -> Module:
    """Read a module: ``---`` frontmatter of ``key: value`` lines, then a body."""
    text = path.read_text()
    meta: dict[str, object] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line and not line.lstrip().startswith("#"):
                    key, _, raw = line.partition(":")
                    meta[key.strip()] = _parse_scalar(raw)
            body = text[end + 4 :]
    return Module(path, meta, body)


def parse_facts(path: Path) -> dict[str, Fact]:
    """Read ``| F-xx | claim | source | verified | public y/n |`` table rows."""
    facts: dict[str, Fact] = {}
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and FACT_ID.fullmatch(cells[0]):
            facts[cells[0]] = Fact(
                cells[0], cells[1], cells[2], cells[3], cells[4].lower().startswith("y")
            )
    return facts


def check_facts(modules: list[Module], facts: dict[str, Fact]) -> Result:
    res = Result("facts", "passed")
    for m in modules:
        for fid in sorted(m.cited_facts()):
            fact = facts.get(fid)
            if fact is None:
                res.details.append(f"{m.id}: cites {fid}, which is not in facts.md")
            elif not fact.source or fact.source in {"-", "TODO", "?"}:
                res.details.append(f"{m.id}: cites {fid}, which has no source")
    if res.details:
        res.status = "failed"
    return res


def check_beats(modules: list[Module], notebook: Path) -> Result:
    cited = {(m.id, b) for m in modules for b in m.cited_beats()}
    if not cited:
        return Result("beats", "passed", ["no module cites a demo beat"])
    if not notebook.exists():
        return Result("beats", "open", [f"notebook not found: {notebook.name}"])
    present = set(BEAT_MARKER.findall(notebook.read_text()))
    missing = [f"{mid}: cites {b}, no BEAT:{b} marker in {notebook.name}" for mid, b in sorted(cited) if b not in present]
    return Result("beats", "failed" if missing else "passed", missing)


def check_handoff(modules: list[Module]) -> Result:
    res = Result("handoff", "passed")
    for prev, nxt in zip(modules, modules[1:]):
        out = str(prev.meta.get("hands_off", "")).strip()
        inp = str(nxt.meta.get("receives", "")).strip()
        if out != inp:
            res.details.append(f"{prev.id} -> {nxt.id}: hands_off {out!r} != receives {inp!r}")
    if res.details:
        res.status = "failed"
    return res


def check_minutes(modules: list[Module], budget: float) -> Result:
    total = 0.0
    bad: list[str] = []
    for m in modules:
        try:
            total += float(str(m.meta.get("minutes", "0")))
        except ValueError:
            bad.append(f"{m.id}: minutes is not a number: {m.meta.get('minutes')!r}")
    detail = [f"total {total:g} of {budget:g} min"] + bad
    return Result("minutes", "failed" if bad or total > budget else "passed", detail)


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:  # not a git checkout: nothing is tracked
        return []
    return [root / p for p in out.stdout.splitlines() if p and not p.startswith("private/")]


def check_public(facts: dict[str, Fact], root: Path) -> Result:
    secret = [f for f in facts.values() if not f.public]
    if not secret:
        return Result("public", "passed", ["no non-public facts registered"])
    hits: list[str] = []
    for path in tracked_files(root):
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for f in secret:
            if re.search(rf"\b{re.escape(f.id)}\b", text) or (len(f.claim) > 12 and f.claim in text):
                hits.append(f"{path.relative_to(root)}: contains non-public fact {f.id}")
    return Result("public", "failed" if hits else "passed", hits)


def run_checks(private: Path, notebook: Path, budget: float, root: Path = ROOT) -> list[Result]:
    talk = private / "talk"
    mod_dir, facts_path = talk / "modules", talk / "facts.md"
    if not mod_dir.is_dir() or not facts_path.exists():
        why = f"private talk directory not found under {private}"
        return [Result(c, "open", [why]) for c in ("facts", "beats", "handoff", "minutes", "public")]
    modules = sorted((parse_module(p) for p in mod_dir.glob("S*.md")), key=lambda m: int(m.id[1:]))
    facts = parse_facts(facts_path)
    return [
        check_facts(modules, facts),
        check_beats(modules, notebook),
        check_handoff(modules),
        check_minutes(modules, budget),
        check_public(facts, root),
    ]


@app.command()
def main(
    private: Path = typer.Option(ROOT / "private", help="Private context directory."),
    notebook: Path = typer.Option(ROOT / "sysml_notebook.py", help="Demo notebook with BEAT:Bn markers."),
    budget: float = typer.Option(50.0, help="Talk minutes budget, excluding Q&A."),
) -> None:
    """Run every check; exit 1 if any check failed (open is not a failure)."""
    results = run_checks(private, notebook, budget)
    for r in results:
        typer.echo(f"[{r.status:>6}] {r.check}")
        for d in r.details:
            typer.echo(f"         {d}")
    raise typer.Exit(1 if any(r.status == "failed" for r in results) else 0)


if __name__ == "__main__":
    app()
