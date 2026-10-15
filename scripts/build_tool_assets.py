"""Regenerate the talk's tool-output assets (talk/assets/tool-*) from the OpenSysML toolchain.

    bash scripts/fetch_tools.sh                       # once: sysml, sysmlv2, plantuml.jar into .tools/
    uv run python scripts/build_tool_assets.py

Every asset is tool output, written as the tool produced it (the PNG is cropped, nothing else is
edited). Models come from sysml/model.py via sysml.views.design_model. Fails if a tool is missing
or fails; nothing is faked. Commands and versions are listed in talk/assets/TOOLS.md.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from sysml.views import STRUCTURE_VIEW, VIEWS_PATH, design_model, render_view  # noqa: E402

TOOLS = ROOT / ".tools"
ASSETS = ROOT / "talk" / "assets"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
LINEAR_MODEL = "sysml/linear_region_toolkit.sysml"
VERIFY_CMD = ["sysmlv2", "verify", LINEAR_MODEL, "--solve"]

# The two design states, (Kp, Kd): (1,10) not satisfied, (8,30) satisfied.
C1 = ("initial", 1.0, 10.0, False)
C3 = ("final", 8.0, 30.0, True)

# The VCRM document definition, generated for the design it reports on. The table is the
# REDK `Verdicts` query over the design: the checks that apply to it, with their verdicts.
DOCUMENT = """\
package TalkDocs {{
    private import DocumentQueries::*;
    private import KerML::Root::Element;
    private import GeoSatADCS::*;
    calc def Checks :> Query {{
        in root : Element;
        Project(source = Verdicts(source = root), properties = ("name", "verdict", "reason"))
    }}
    part def VCRM :> Document {{
        attribute redefines title = "REQ-001 verification cross-reference";
        part intro : Paragraph {{
            attribute redefines text = "Generated from the model. The verdicts are automated checks. Whether REQ-001 is satisfied is a person's judgement.";
        }}
        part checks : Table {{
            attribute redefines caption = "Checks on design {design}";
            calc rows : Checks {{ in root = {design}; }}
        }}
    }}
}}
"""


def java() -> str:
    """A working java: $JAVA_HOME, PATH, or a Homebrew openjdk (macOS's /usr/bin/java is a stub)."""
    cands = [Path(os.environ["JAVA_HOME"], "bin", "java")] if os.environ.get("JAVA_HOME") else []
    cands += [Path(p) for p in (shutil.which("java"), "/opt/homebrew/opt/openjdk/bin/java",
                                "/usr/local/opt/openjdk/bin/java") if p]
    for c in cands:
        if c.is_file() and subprocess.run([str(c), "-version"], capture_output=True).returncode == 0:
            return str(c)
    sys.exit("build_tool_assets: no working java (needed for PlantUML)")


def run(cmd, **kw) -> subprocess.CompletedProcess:
    done = subprocess.run(cmd, capture_output=True, **kw)
    if done.returncode != 0:
        sys.exit(f"build_tool_assets: {' '.join(map(str, cmd[:3]))} failed ({done.returncode}):\n"
                 f"{done.stderr.decode(errors='replace')}")
    return done


def plantuml(source: str, fmt: str) -> bytes:
    """PlantUML jar, source on stdin, image on stdout (-t<fmt>)."""
    return run([java(), "-Djava.awt.headless=true", "-jar", str(TOOLS / "plantuml.jar"), f"-t{fmt}", "-pipe"],
               input=source.encode()).stdout


def write(name: str, data: bytes) -> None:
    (ASSETS / name).write_bytes(data)
    print(f"  {name:22} {len(data):>8} bytes")


def requirement_svgs(cli: str) -> None:
    for name, (design, kp, kd, sat) in (("tool-req-c1.svg", C1), ("tool-req-c3.svg", C3)):
        model = design_model(design, kp, kd, sat)
        puml = render_view(model, "TalkViews::requirementView", "plantuml", overlay=True, cli=cli)
        write(name, plantuml(puml, "svg"))


def structure_svg(cli: str) -> None:
    puml = render_view((ROOT / "sysml" / "satellite.sysml").read_text(), STRUCTURE_VIEW, "plantuml", cli=cli)
    write("tool-structure.svg", plantuml(puml, "svg"))


def verify_txt() -> None:
    """`sysmlv2 verify --solve` with z3 from the z3-solver wheel (not a project dependency)."""
    cmd = VERIFY_CMD if shutil.which("z3") else ["uv", "run", "--no-project", "--with", "z3-solver", "--"] + VERIFY_CMD
    env = dict(os.environ, PATH=f"{TOOLS}{os.pathsep}{os.environ['PATH']}")
    # verify exits nonzero when a constraint is violated; that is a verdict, not a failure.
    done = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if done.returncode not in (0, 1) or "z3" not in done.stdout:
        sys.exit(f"build_tool_assets: verify --solve failed ({done.returncode}):\n{done.stdout}{done.stderr}")
    write("tool-verify.txt", ("$ " + " ".join(VERIFY_CMD) + "\n" + done.stdout + done.stderr).encode())


def vcrm_png(cli: str) -> None:
    design, kp, kd, sat = C3
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "model.sysml").write_text(design_model(design, kp, kd, sat))
        (tmp / "doc.sysml").write_text(DOCUMENT.format(design=design))
        page = tmp / "vcrm.html"
        run([cli, str(tmp / "model.sysml"), str(tmp / "doc.sysml"), "-render-document", "TalkDocs::VCRM",
             "-doc-form", "html", "-o", str(page)])
        shot = tmp / "vcrm.png"
        run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
             "--window-size=900,500", f"--screenshot={shot}", page.as_uri()])
        img = Image.open(shot).convert("RGB")
    # Crop to the table with its caption: the last block of non-white rows.
    ink = (np.asarray(img) != 255).any(axis=2)  # True where a pixel is not white
    rows = np.flatnonzero(ink.any(axis=1))
    start = end = int(rows[-1])
    for y in rows[-2::-1]:
        if start - y > 40:
            break
        start = int(y)
    cols = np.flatnonzero(ink[start:end + 1].any(axis=0))
    pad = 16
    crop = img.crop((max(int(cols[0]) - pad, 0), max(start - pad, 0), min(int(cols[-1]) + pad, img.width), end + pad))
    buf = io.BytesIO()
    crop.save(buf, "PNG")
    write("tool-vcrm.png", buf.getvalue())


def main() -> None:
    cli = str(TOOLS / "sysml")
    for tool in (cli, TOOLS / "sysmlv2", TOOLS / "plantuml.jar", CHROME):
        if not Path(tool).exists():
            sys.exit(f"build_tool_assets: {tool} not found (run bash scripts/fetch_tools.sh)")
    ASSETS.mkdir(parents=True, exist_ok=True)
    print(f"views: {VIEWS_PATH.relative_to(ROOT)}")
    requirement_svgs(cli)
    structure_svg(cli)
    verify_txt()
    vcrm_png(cli)


if __name__ == "__main__":
    main()
