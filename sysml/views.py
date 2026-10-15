"""Render the REQ-001 requirement view of an assembled GeoSatADCS model, with verdicts.

`requirement_view` is the live step-3 call. It renders `TalkViews::requirementView`
(sysml/views.sysml) in the REDK requirement rendering with the `verdicts` overlay and the
okabe-ito palette: the requirement is coloured by the verdicts of the verification cases
that verify it. The overlay is verification only (a computed verdict); a person's
attestation is not drawn here.

Two paths, same text shape:
  1. the `sysml` CLI (OpenSysML release asset, fetched by scripts/fetch_tools.sh), found at
     $SYSML_CLI, `.tools/sysml` or on PATH. This is the REDK renderer itself.
  2. otherwise the uv environment's opensysml API. Its `render_view` has no overlay or
     palette option, so the Mermaid is drawn here from the same nodes and edges, with each
     verification case's verdict from `run_analysis`. It reproduces the CLI's overlay
     convention; it is not the CLI's output. Only form="mermaid" is available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import opensysml

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from evidence.hashing import hash_simulation
from sysml.model import (ADEQUACY_TEXT, DEMO_ENGINEER, SUFFICIENCY_NOT_SATISFIED, VERSION, assemble,
                         attestation_block, evidence_block, load_structure, sufficiency_satisfied,
                         symbolic_settling)

VIEWS_PATH = Path(__file__).with_name("views.sysml")
REQUIREMENT_VIEW = "TalkViews::requirementView"
STRUCTURE_VIEW = "TalkViews::structureView"
FORMS = ("mermaid", "plantuml", "dot", "d2")

# okabe-ito, as the REDK renderer fills them: verdict pass / fail, then the two node families.
_PASS, _FAIL = ("#99D8C7", "#009E73"), ("#EEBF99", "#D55E00")
_DEF, _USE = ("#CC79A7", "#CC79A7"), ("#EBC9DC", "#CC79A7")


def design_model(design: str, Kp: float, Kd: float, satisfied: bool) -> str:
    """The full GeoSatADCS model for one design: structure, its evidence (scipy settling time
    and the SymPy estimate, via model.py) and the engineer's attestation, which is the
    caller's `satisfied`, not computed."""
    params = dict(load_params(), Kp=Kp, Kd=Kd)
    sim = run_step_response(params)
    summary = sim.summary()
    t_est, est_hash = symbolic_settling(params)
    evidence = evidence_block(design, params, summary, hash_simulation(sim.config.to_dict(), summary),
                              ADEQUACY_TEXT, DEMO_ENGINEER, t_est, est_hash)
    sufficiency = (sufficiency_satisfied(Kp, Kd, summary["settling_time_s"], t_est, 120)
                   if satisfied else SUFFICIENCY_NOT_SATISFIED)
    attestation = attestation_block(design, satisfied, DEMO_ENGINEER, "done", sufficiency, f"vc001_{design}")
    return assemble(load_structure(), evidence, attestation)


def sysml_cli() -> str | None:
    """Path of the REDK `sysml` CLI, or None when it is not installed."""
    root = Path(__file__).resolve().parent.parent
    for cand in (os.environ.get("SYSML_CLI"), root / ".tools" / "sysml", shutil.which("sysml")):
        if cand and Path(cand).is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def render_view(model_text: str, view: str, form: str = "mermaid", overlay: bool = False,
                cli: str | None = None) -> str:
    """Run `sysml -render <view>` over the model plus views.sysml (palette okabe-ito)."""
    if form not in FORMS:
        raise ValueError(f"form must be one of {FORMS}, got {form!r}")
    with tempfile.TemporaryDirectory() as tmp:
        model = Path(tmp, "model.sysml")
        model.write_text(model_text)
        cmd = [cli, str(model), str(VIEWS_PATH), "-render", view, "-render-form", form,
               "-render-palette", "okabe-ito"] + (["-render-overlay", "verdicts"] if overlay else [])
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if done.returncode != 0:
        raise RuntimeError(f"sysml -render failed ({done.returncode}): {done.stderr.strip()}")
    return done.stdout


def _mermaid_from_api(model_text: str) -> str:
    """Mermaid for the requirement view from the opensysml API (no CLI): REDK nodes and edges,
    each requirement coloured and labelled by the verdicts of the cases verifying it."""
    conn = opensysml.connect(version=VERSION)
    try:
        model = conn.parse_sources([("model.sysml", model_text), ("views.sysml", VIEWS_PATH.read_text())],
                                   strict=True)
        rv = model.render_view(REQUIREMENT_VIEW)
        verdict = {n.id: model.run_analysis(n.name).verifications[0].kind
                   for n in rv.nodes if n.kind == "verification"}
        by_req: dict[str, list[tuple[str, str]]] = {}
        for e in rv.edges:
            if e.kind == "verify" and e.from_id in verdict:
                by_req.setdefault(e.to_id, []).append((verdict[e.from_id], next(
                    n.name for n in rv.nodes if n.id == e.from_id)))
        typed = lambda n: f" : {n.type.split('::')[-1]}" if n.type else ""  # noqa: E731
        lines, styles = ["flowchart TD"], []
        for n in rv.nodes:
            label = f"*«{n.kind}»*\n**{n.name.split('::')[-1]}{typed(n)}**" + (f"\n{n.detail}" if n.detail else "")
            seen = by_req.get(n.id)
            if seen:
                label += "\nverdict " + ", ".join(f"{k} by {name}" for k, name in seen)
            shape = '["`{}`"]' if n.kind.endswith(" def") else '("`{}`")'
            lines.append(f"  {n.id}{shape.format(label)}")
            if seen:
                kinds = {k for k, _ in seen}
                fill = _PASS if kinds == {"pass"} else _FAIL if "fail" in kinds else ("#DDDDDD", "#6b7280")
            else:
                fill = _DEF if n.kind.endswith(" def") else _USE
            styles.append(f"  style {n.id} fill:{fill[0]},stroke:{fill[1]}")
        lines += [f"  {e.from_id} -.->|\"{e.kind}\"| {e.to_id}" for e in rv.edges] + styles
        return "\n".join(lines) + "\n"
    finally:
        conn.close()


def requirement_view(model_text: str, form: str = "mermaid") -> str:
    """The REQ-001 requirement view of `model_text` (an assembled GeoSatADCS package), with
    the verdict overlay and the okabe-ito palette, as `form` (mermaid, plantuml, dot or d2)."""
    cli = sysml_cli()
    if cli:
        return render_view(model_text, REQUIREMENT_VIEW, form, overlay=True, cli=cli)
    if form != "mermaid":
        raise RuntimeError(f"form={form!r} needs the sysml CLI (run scripts/fetch_tools.sh); "
                           "without it only mermaid is available")
    return _mermaid_from_api(model_text)
