"""Evidence engine for the demo arc: every number comes from the repo's analysis code.

  slew_settling   scipy simulation (analysis.numerical.simulate_adcs), one 10 degree slew about
                  each body axis; the worst axis governs
  symbolic        SymPy linear estimate (sysml.model.symbolic_settling)
  grid            worst-axis settling over a gain box
  inmodel_settling the same slew as a SysML v2 action, executed by OpenSysML (sysml/slew_sim.sysml)

These are observations of models. Whether they are sufficient is a human judgement.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

import opensysml
from analysis import numerical
from analysis.load_params import load_params
from analysis.numerical import make_config_from_params, simulate_adcs
from analysis.symbolic import evaluate_inertia
from sysml.model import VERSION, symbolic_settling

INITIAL = (1, 10)
NEIGHBOUR = (4, 25)
TUNED = (8, 30)
BOX_KP = (4, 5, 6)
BOX_KD = (22, 23.5, 25)
AXES = "xyz"
SLEW_DEG = 10.0
T_END = 360.0
BAND_FRACTION = 0.01  # simulation settling band, as in SimResult.summary

SLEW_SIM = Path(__file__).with_name("slew_sim.sysml")


def _params(kp, kd) -> dict:
    return dict(load_params(), Kp=float(kp), Kd=float(kd))


def _sim(kp, kd, axis: int):
    """One 10 degree slew about body axis `axis` (0, 1, 2): the SimResult."""
    cfg = make_config_from_params(_params(kp, kd), t_end=T_END, initial_error_deg=SLEW_DEG)
    half = np.radians(SLEW_DEG) / 2
    q0 = [0.0, 0.0, 0.0, float(np.cos(half))]
    q0[axis] = float(np.sin(half))
    cfg.q0 = tuple(q0)
    return simulate_adcs(cfg)


def _sim_nolimit(kp, kd, axis: int = 0):
    """The same slew with the torque limit switched off (the actuator can deliver any command)."""
    cfg = make_config_from_params(_params(kp, kd), t_end=T_END, initial_error_deg=SLEW_DEG)
    cfg.max_torque = 1e9
    half = np.radians(SLEW_DEG) / 2
    q0 = [0.0, 0.0, 0.0, float(np.cos(half))]
    q0[axis] = float(np.sin(half))
    cfg.q0 = tuple(q0)
    return simulate_adcs(cfg)


def _axis_run(res) -> dict:
    """Settling time, last time the torque limit was active, peak command, for one SimResult."""
    sat = np.any(np.abs(res.tau_ctrl) >= res.config.max_torque - 1e-12, axis=1)
    s = res.summary()
    return {"settling_s": s["settling_time_s"],
            "saturated_s": float(res.t[sat][-1]) if sat.any() else 0.0,
            "peak_torque": s["peak_control_torque"]}


def _combine(runs: list) -> dict:
    t = [r["settling_s"] for r in runs]
    w = int(np.argmax(t))
    return {"x": t[0], "y": t[1], "z": t[2], "worst": t[w], "worst_axis": AXES[w],
            "saturated_s": max(r["saturated_s"] for r in runs),
            "peak_torque": max(r["peak_torque"] for r in runs)}


def slew_settling(kp, kd) -> dict:
    """Simulated settling for a 10 degree slew about each body axis.
    {x, y, z, worst, worst_axis, saturated_s, peak_torque}; saturated_s is the last time the
    torque limit was active on any axis, peak_torque the largest command (N m)."""
    return _combine([_axis_run(_sim(kp, kd, a)) for a in range(3)])


def symbolic(kp, kd) -> tuple[float, str]:
    """The SymPy linear settling estimate and its evidence hash."""
    return symbolic_settling(_params(kp, kd))


def grid(kps=BOX_KP, kds=BOX_KD) -> dict:
    """Worst-axis simulated settling for every (kp, kd) in the box: {(kp, kd): seconds}."""
    return {(kp, kd): slew_settling(kp, kd)["worst"] for kp in kps for kd in kds}


def inmodel_settling(kp, kd, dt: float, axis: str = "x") -> float:
    """Settling of a single-axis slew as a SysML v2 action executed by OpenSysML.
    Explicit Euler steps of `dt`; the in-model simulation's step size changes the verdict."""
    p = _params(kp, kd)
    theta = float(np.radians(SLEW_DEG))
    sub = {"J": repr(evaluate_inertia(p)[AXES.index(axis)]), "KP": repr(float(kp)), "KD": repr(float(kd)),
           "TAUMAX": repr(p["maxTorque"]), "DT": repr(float(dt)), "THETA0": repr(theta),
           "TEND": repr(T_END), "BAND": repr(BAND_FRACTION * theta)}
    src = re.sub(r"@(\w+)@", lambda m: sub[m.group(1)], SLEW_SIM.read_text())
    conn = opensysml.connect(version=VERSION)
    try:
        model = conn.load_from_content(src, strict=True)
        return float(model.execute_action("SlewSim::slew")["tSettle"])
    finally:
        conn.close()


ROOT = Path(__file__).resolve().parent.parent
VERIFY_MODEL = "sysml/linear_region_toolkit.sysml"
VERIFY_CAPTURE = ROOT / "talk" / "assets" / "tool-verify.txt"


def _z3_dir() -> str | None:
    """Directory holding a z3 binary, or None. $OPENSYSML_SMT, when set, names the binary (the same
    variable the opensysml API reads); a path that does not exist means no z3."""
    exe = "z3.exe" if os.name == "nt" else "z3"
    env = os.environ.get("OPENSYSML_SMT")
    if env:
        return str(Path(env).parent) if Path(env).is_file() else None
    for d in (Path(sys.executable).parent, Path(sys.prefix) / "bin"):
        if (d / exe).is_file():
            return str(d)
    found = shutil.which("z3")
    return str(Path(found).parent) if found else None


def tools_dir() -> Path:
    return Path(os.environ.get("SYSML_TOOLS_DIR") or ROOT / ".tools")


def tool_verify(timeout: float = 10.0) -> dict:
    """Run `sysmlv2 verify sysml/linear_region_toolkit.sysml --solve` (sysml-toolkit with z3).

    Returns {engine, text}: engine "live" with the tool's own output (command line first, as in the
    capture), or "captured" with talk/assets/tool-verify.txt when the tool or z3 is missing, times
    out or prints nothing recognisable. `verify` exits nonzero when a constraint is violated; that is
    a verdict, not a failure."""
    cmd = ["sysmlv2", "verify", VERIFY_MODEL, "--solve"]
    exe, z3 = tools_dir() / "sysmlv2", _z3_dir()
    if exe.is_file() and z3:
        try:
            env = dict(os.environ, PATH=f"{z3}{os.pathsep}{os.environ.get('PATH', '')}")
            done = subprocess.run([str(exe), *cmd[1:]], cwd=ROOT, env=env, capture_output=True, text=True,
                                  timeout=timeout)
            out = done.stdout + done.stderr
            if done.returncode in (0, 1) and "RegionPasses" in out and "z3" in out:
                return {"engine": "live", "text": "$ " + " ".join(cmd) + "\n" + out}
        except (OSError, subprocess.SubprocessError):
            pass
    return {"engine": "captured", "text": VERIFY_CAPTURE.read_text()}


def java_bin() -> str | None:
    """A working `java` (macOS's /usr/bin/java is a stub): $JAVA_HOME, PATH, then Homebrew's openjdk."""
    cands = [Path(os.environ["JAVA_HOME"]) / "bin" / "java"] if os.environ.get("JAVA_HOME") else []
    cands += [Path(c) for c in (shutil.which("java"), "/opt/homebrew/opt/openjdk/bin/java",
                                "/usr/local/opt/openjdk/bin/java") if c]
    for c in cands:
        try:
            if c.is_file() and subprocess.run([str(c), "-version"], capture_output=True, timeout=10).returncode == 0:
                return str(c)
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def plantuml_svg(source: str, timeout: float = 20.0) -> str:
    """Render PlantUML source to SVG with .tools/plantuml.jar; raises RuntimeError when it cannot."""
    jar, java = tools_dir() / "plantuml.jar", java_bin()
    if not jar.is_file() or not java:
        raise RuntimeError("plantuml or java not available")
    done = subprocess.run([java, "-Djava.awt.headless=true", "-jar", str(jar), "-tsvg", "-pipe"],
                          input=source.encode(), capture_output=True, timeout=timeout)
    if done.returncode != 0 or not done.stdout:
        raise RuntimeError(f"plantuml failed ({done.returncode})")
    return done.stdout.decode()


def grid_counts(bundle: dict, limit: float = 120.0) -> tuple[int, int]:
    """(points over the limit, points) in the precomputed gain box, from the simulation results."""
    pts = bundle["grid"]
    return sum(p["worst"] > limit for p in pts), len(pts)


# ---- precomputed bundle for the deck (heavy work at load, instant sliders on stage) ------------

DESIGNS = {"initial": INITIAL, "neighbour": NEIGHBOUR, "tuned": TUNED}
INMODEL_DTS = (0.5, 0.05)
SERIES_POINTS = 600
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
_CODE = ("analysis/numerical.py", "analysis/symbolic.py", "analysis/load_params.py", "sysml/evidence.py",
         "sysml/formal.py", "sysml/linear_region.sysml", "sysml/slew_sim.sysml", "sysml/model.py")


def _series(res, axis: int) -> dict:
    """error (deg), and the slew-axis torque (N m), resampled to SERIES_POINTS on a uniform grid."""
    t = np.linspace(0.0, float(res.t[-1]), SERIES_POINTS)
    err = np.degrees(2 * np.linalg.norm(res.q[:, :3], axis=1))
    return {"t": t.tolist(), "error_deg": np.interp(t, res.t, err).tolist(),
            "torque": np.interp(t, res.t, res.tau_ctrl[:, axis]).tolist()}


def _precompute_key() -> str:
    root = Path(__file__).resolve().parent.parent
    h = hashlib.sha256()
    for f in _CODE:
        h.update((root / f).read_bytes())
    h.update(json.dumps(load_params(), sort_keys=True).encode())
    return h.hexdigest()[:24]


def precompute(use_cache: bool = True) -> dict:
    """Everything the deck needs, as plain data (JSON-serialisable):
    designs[name] = {kp, kd, settling (slew_settling dict), symbolic_s, symbolic_hash,
                     series[axis] = {t, error_deg, torque}},
    nolimit = {settling_s, series} (design NEIGHBOUR, x axis, torque limit off),
    grid = [{kp, kd, worst}], region = region_check(), inmodel = {dt: seconds at NEIGHBOUR}.
    Cached under output/ keyed by a hash of the analysis code and the parameters."""
    f = OUTPUT_DIR / f"precompute_{_precompute_key()}.json"
    if use_cache and f.exists():
        return json.loads(f.read_text())
    from sysml.formal import region_check
    designs = {}
    for name, (kp, kd) in DESIGNS.items():
        sims = [_sim(kp, kd, a) for a in range(3)]
        t_sym, h = symbolic(kp, kd)
        designs[name] = {"kp": kp, "kd": kd, "settling": _combine([_axis_run(r) for r in sims]),
                         "symbolic_s": t_sym, "symbolic_hash": h,
                         "series": {AXES[a]: _series(sims[a], a) for a in range(3)}}
    nl = _sim_nolimit(*NEIGHBOUR)
    nolimit = {"settling_s": nl.summary()["settling_time_s"], "series": _series(nl, 0)}
    out = {"designs": designs, "nolimit": nolimit,
           "grid": [{"kp": kp, "kd": kd, "worst": w} for (kp, kd), w in grid().items()],
           "region": region_check(),
           "inmodel": {str(dt): inmodel_settling(*NEIGHBOUR, dt=dt) for dt in INMODEL_DTS}}
    OUTPUT_DIR.mkdir(exist_ok=True)
    f.write_text(json.dumps(out))
    return out
