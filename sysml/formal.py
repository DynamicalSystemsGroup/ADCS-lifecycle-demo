"""Formal check of the linear settling model with OpenSysML `solve` (REDK, Z3 backend).

A model-level verification: Z3 searches the gain box for a counterexample to the linear
settling condition. It says nothing about the simulation or the physical spacecraft.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np

import opensysml
from analysis.load_params import load_params
from analysis.symbolic import evaluate_inertia
from sysml.model import VERSION

TEMPLATE = Path(__file__).with_name("linear_region.sysml")
FALLBACK = Path(__file__).resolve().parent.parent / "talk" / "assets" / "formal-fallback.txt"
LABEL = "Z3 finds no counterexample in this box for the linear model"
SLEW_DEG = 10.0


def _z3_binary() -> str | None:
    """The z3 binary shipped by the z3-solver dependency (next to the interpreter's scripts)."""
    exe = "z3.exe" if os.name == "nt" else "z3"
    for d in (Path(sys.executable).parent, Path(sys.prefix) / "bin"):
        if (d / exe).is_file():
            return str(d / exe)
    return shutil.which("z3")


def _source(kp, kd) -> str:
    P = load_params()
    jxx, jyy, jzz = evaluate_inertia(P)
    sub = {"JXX": repr(jxx), "JYY": repr(jyy), "JZZ": repr(jzz),
           "KP_LO": repr(kp[0]), "KP_HI": repr(kp[1]), "KD_LO": repr(kd[0]), "KD_HI": repr(kd[1]),
           "SIN5": repr(round(float(np.sin(np.radians(SLEW_DEG / 2))), 7)),
           "TAUMAX": repr(P["maxTorque"])}
    return re.sub(r"@(\w+)@", lambda m: sub[m.group(1)], TEMPLATE.read_text())


def _fallback() -> dict:
    text = FALLBACK.read_text()
    head, _, raw = text.partition("\n")  # first line "verdict: <v>", the rest is the tool output
    return {"verdict": head.removeprefix("verdict: "), "label": LABEL, "engine": "captured", "raw": raw.rstrip("\n")}


def region_check(kp=(4, 6), kd=(22, 25)) -> dict:
    """{verdict, label, engine, raw}. engine is "z3" for a live run, "captured" for the fallback.

    verdict "no_counterexample" means Z3 found nothing violating the linear settling condition
    in the box. `raw` carries the tool's own output for RegionSettles and, for the audit trail,
    for ValidAndSettles (the linear condition plus no saturation at the slew start)."""
    z3 = os.environ.get("OPENSYSML_SMT") or _z3_binary()
    if not z3 or not Path(z3).is_file():
        return _fallback()
    os.environ["OPENSYSML_SMT"] = z3
    try:
        conn = opensysml.connect(version=VERSION)
        try:
            m = conn.load_from_content(_source(kp, kd), strict=True)
            region = m.verify_constraint("LinearADCS::RegionSettles", question="holds", engine="solve")
            both = m.verify_constraint("LinearADCS::ValidAndSettles", question="satisfiable", engine="solve")
        finally:
            conn.close()
    except Exception:
        return _fallback()
    verdict = "no_counterexample" if region.holds else "counterexample"
    raw = (f"RegionSettles (holds): holds={region.holds} | {region}\n"
           f"ValidAndSettles (satisfiable): holds={both.holds} | {both}")
    return {"verdict": verdict, "label": LABEL, "engine": "z3", "raw": raw.rstrip("\n")}
