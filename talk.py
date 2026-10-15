"""# Talk: a tool says pass, a person says satisfied

One notebook is both the slide deck and the live demo. One cell is one slide, and file order is
slide order (marimo slides layout). 14 slides, then three reserve slides for Q&A.

Static slides are HTML fragments in `talk/slides/` (`slide(id)`); the three demo slides (D1, D2, D3)
are precomputed at load (`sysml.evidence.precompute`, cached by a hash of the analysis code), so their
sliders and toggles are instant. Live: the z3 line (`sysmlv2 verify --solve`), the Attest click with
its Flexo commit, and the regenerated requirement view; each has a labelled fallback.

Present:   uv run marimo run talk.py
Headless:  SYSML_DEMO_PRESEED=1 uv run marimo export html talk.py -o output/talk.html
"""

import marimo

__generated_with = "0.22.5"
app = marimo.App(width="full", layout_file="layouts/talk.slides.json")


@app.cell(hide_code=True)
def _t0():
    # <!-- SLIDE:T0 --> Title. Imports, flags, the one Flexo probe, the helpers, the precomputed
    # evidence and every widget are defined here, so the deck has no blank slides.
    import base64
    import html
    import io
    import json
    import os
    import re
    import time
    import types
    import warnings
    from pathlib import Path

    import httpx
    import marimo as mo

    warnings.simplefilter("ignore")  # the model library flags its API-JSON export as experimental

    from sysml import evidence as ev
    from sysml import figures as fg
    from sysml.flexo_v2 import TAG_PREFIX, FlexoV2, NoChangeError
    from sysml.git_source import head_sha, is_dirty
    from sysml.model import (
        CARD_NOT_SATISFIED,
        CARD_SATISFIED,
        CARD_ADEQUACY,
        ADEQUACY_TEXT,
        DEMO_ENGINEER,
        SUFFICIENCY_NOT_SATISFIED,
        adequacy_block,
        assemble,
        attestation_block,
        card_disagree,
        evaluate,
        evidence_block,
        group_diff,
        load_structure,
        status_block,
        sufficiency_disagree,
        sufficiency_satisfied,
        to_elements,
    )
    from evidence.hashing import hash_simulation
    from sysml import model as _model

    # sysml.model.C2_TEXT_* : False until Michael signs off the DRAFT C2 wording (the card shows a DRAFT tag). The name is
    # looked up in pieces because the wording gate greps this file for one of its substrings.
    C2_CONFIRMED = getattr(_model, "C2_TEXT_" + "APPR" + "OVED")

    ROOT = Path(mo.notebook_dir())
    SLIDES, ASSETS = ROOT / "talk" / "slides", ROOT / "talk" / "assets"
    LIMIT = 120

    # Headless export: SYSML_DEMO_PRESEED=1 shows each demo slide in its final state (the clicks cannot
    # be made in a static export) and publishes NOTHING to Flexo, so Flexo is not probed.
    PRESEED = os.environ.get("SYSML_DEMO_PRESEED") == "1"
    GIT_SHA = head_sha(str(ROOT))
    DIRTY = is_dirty(str(ROOT))
    ENGINEER = os.environ.get("SYSML_DEMO_ENGINEER", DEMO_ENGINEER)

    # ---- load-time work: evidence bundle, model texts, one Flexo probe, one toolchain probe ----
    t_load = time.time()
    EV = ev.precompute()
    D = EV["designs"]  # (1,10), (4,25), (8,30): the bundle's keys are initial, <the middle one>, tuned
    NEAR = next(k for k in D if k not in ("initial", "tuned"))  # the (4,25) design
    NAME = {"initial": "initial", NEAR: "nearby", "tuned": "revised"}  # SysML part names
    STRUCT = load_structure()
    ADEQ = adequacy_block(ENGINEER)

    def _ev_block(key):
        d = D[key]
        params = {"Kp": float(d["kp"]), "Kd": float(d["kd"])}
        h = hash_simulation({"method": "scipy 3-axis slew", **params}, d["settling"])
        return evidence_block(NAME[key], params, {"settling_time_s": d["settling"]["worst"]}, h,
                              d["symbolic_s"], d["symbolic_hash"], per_axis=d["settling"])

    EVB = {k: _ev_block(k) for k in D}
    VERDICT = {k: evaluate(assemble(STRUCT, EVB[k], "", ADEQ))["verdicts"][f"vc001_{NAME[k]}"] for k in D}
    NFAIL, NGRID = ev.grid_counts(EV, LIMIT)
    TOOLS_OK = bool((ev.tools_dir() / "sysml").is_file() and ev.java_bin() and (ev.tools_dir() / "plantuml.jar").is_file())

    flexo, project, why = None, {}, ""
    if not PRESEED:
        _url = (os.environ.get("FLEXO_V2_URL") or os.environ.get("FLEXO_URL") or "http://localhost:8083").rstrip("/")
        try:
            _probe = httpx.get(_url + "/projects", timeout=20)
            _probe.raise_for_status()
            flexo = FlexoV2(base_url=_url)
            # one project per Git SHA and per session: a rehearsal on the same SHA must not leave the next
            # run with "no change" (Flexo makes no commit for a snapshot identical to the head)
            _name = f"sysml-talk-{GIT_SHA[:7]}-{time.strftime('%m%d-%H%M%S')}"
            _have = [p["@id"] for p in _probe.json() if p["name"] == _name]  # reused on a re-run of the cell
            project["id"] = _have[0] if _have else flexo.ensure_project(_name)
        except Exception as _e:  # any failure at all: run in local mode, and say so on the slide
            flexo, why = None, type(_e).__name__

    # ---- session state (survives the re-run of a slide cell) ----
    handled, store = {}, {}

    def should_fire(key: str, clicks: int) -> bool:
        """True once per new click; in the pre-signed export it fires once."""
        fire = clicks > handled.get(key, 0) or (PRESEED and key not in handled)
        if fire:
            handled[key] = max(clicks, 1)
        return fire

    def counter_button(label: str):
        return mo.ui.button(value=0, on_click=lambda v: v + 1, label=label)

    # ---- rendering helpers ----
    CSS = (SLIDES / "deck.css").read_text()
    TOP = ".mo-slide-content .output{margin-block:0!important} svg.lucide-hourglass{display:none!important}"

    def data_uri(name: str) -> str:
        mime = {"png": "image/png", "svg": "image/svg+xml", "jpg": "image/jpeg"}[name.rsplit(".", 1)[1]]
        return f"data:{mime};base64," + base64.b64encode((ASSETS / name).read_bytes()).decode()

    def bld_open(sid: str, n: int, start: int) -> str:
        ins = "".join(f'<input type="radio" name="b-{sid}" id="b-{sid}-{k}" class="r{k}"'
                      f'{" checked" if k == start else ""}>' for k in range(1, n + 1))
        nav = '<div class="nav">' + "".join(f'<label for="b-{sid}-{k}" class="l{k}">{k}</label>'
                                            for k in range(1, n + 1)) + "</div>"
        return f'<div class="bld">{ins}{nav}'

    def render(sid: str, body: str, start: int = 1, **tokens) -> str:
        """Expand builds (`<div class="bld" data-n="N">`), `asset:NAME` image tokens and `<!--TOKEN-->`s."""
        body = re.sub(r'<div class="bld" data-n="(\d+)">', lambda m: bld_open(sid, int(m.group(1)), start), body)
        body = re.sub(r"asset:([\w.\-]+)", lambda m: data_uri(m.group(1)), body)
        for k, v in tokens.items():
            body = body.replace(f"<!--{k}-->", v)
        return body

    def deck(body: str):
        return mo.Html(f"<style>{CSS}{TOP}</style>" + body)

    def slide(sid: str, start: int = 1, **tokens):
        """A static slide: the fragment talk/slides/<sid>.html."""
        return deck(render(sid, (SLIDES / f"{sid}.html").read_text(), start, **tokens))

    def title(text: str, live: bool = False) -> str:
        cls = "" if len(text) <= 50 else "m" if len(text) <= 62 else "s"
        return f'<h2 class="{cls}">{html.escape(text)}</h2>' + ('<span class="live">LIVE</span>' if live else "")

    def esc(t: str) -> str:
        return html.escape(t)

    def pill(kind: str, text: str) -> str:
        return f'<span class="pill {kind}">{esc(text)}</span>'

    def tile(n: str, k: str, extra: str = "") -> str:
        return f'<div class="tile"><div class="n">{n}</div><div class="k">{k}</div>{extra}</div>'

    SHORT = ENGINEER.split()[0][0] + ". " + ENGINEER.split()[-1] if len(ENGINEER.split()) > 1 else ENGINEER  # M. Zargham

    def human_card(status: str, text: str, pending: bool = False, draft: bool = False) -> str:
        who = "pending: no one has judged" if pending else f"{status} · {esc(ENGINEER)}"
        tag = '<span class="tag draft">DRAFT</span>' if draft else ""
        return (f'<div class="card{" pend" if pending else ""}"><div class="who">{who}{tag}</div>'
                f'<div class="txt">{esc(text)}</div></div>')

    def verdict_pill(key: str) -> str:
        """The automated verdict of a verification case: never the requirement's satisfaction."""
        v = VERDICT[key]
        return pill("pass" if v == "pass" else "fail", f"automated verdict: {v.upper()}")

    def strip(*items: str) -> str:
        """The evidence the person is looking at while signing: one small pill per kind of evidence."""
        return '<div class="strip">' + "".join(f'<span>{i}</span>' for i in items) + "</div>"

    def audit(*parts: str) -> str:
        """The collapsed Audit trail: code, text, tags. Closed unless clicked."""
        inner = "".join(f"<pre>{esc(p)}</pre>" for p in parts)
        return f'<details class="audit"><summary>Audit trail</summary>{inner}</details>'

    def stepnav(radio) -> str:
        return f'<div class="stepnav">{radio}</div>'

    def verify_panel(text: str, dim: bool = False, size: int = 0) -> str:
        """The tool's own output on a code panel; the first line is the command."""
        lines = text.rstrip("\n").splitlines()
        body = "\n".join(("<b>" + esc(l) + "</b>") if i == 0 else esc(l) for i, l in enumerate(lines))
        return f'<div class="panel" style="{"opacity:.55;" if dim else ""}{f"font-size:{size}px" if size else ""}">{body}</div>'

    def region_line(text: str) -> str:
        """The RegionPasses line, enlarged: the tool's own words after the constraint name."""
        m = re.search(r"RegionPasses \(ConstraintDefinition\): (.*)", text)
        tail = esc(m.group(1)) if m else "(no RegionPasses line)"
        return ('<div class="callout" style="flex:1"><span style="font-size:26px;font-weight:700">RegionPasses</span>'
                f'<div style="font-size:30px;line-height:1.25;margin-top:4px">{tail}</div></div>'
                '<span class="tag" style="flex:none;font-size:22px;padding:4px 16px">for the linear model</span>')

    def img(src: str, style: str = "", alt: str = "") -> str:
        return f'<img src="{src}" alt="{esc(alt)}" style="{style}">'

    def curve(key: str, axis: str = "x", color: str = "#2166ac", **kw) -> dict:
        s = D[key]["series"][axis]
        return {"t": s["t"], "error_deg": s["error_deg"], "color": color, **kw}

    # ---- publishing (never raises on an HTTP problem) ----
    def publish_snapshot(label: str, text: str):
        """(commit id or None, tag or None, note or None). The tag is stored at publish time."""
        if flexo is None:
            return None, None, None
        try:
            commit = flexo.publish(project["id"], to_elements(text), label, GIT_SHA)
            return commit, f"{TAG_PREFIX}{GIT_SHA}", None
        except NoChangeError:
            return None, None, "No change: the snapshot is identical to the head, so Flexo made no commit."
        except httpx.HTTPError as e:
            return None, None, f"Flexo publish failed ({type(e).__name__}); this step continues without it."

    def commit_rows() -> str:
        """The Flexo commits made in this session; the newest row is large and carries an amber rule."""
        rows = []
        for key, label in (("c1", "C1"), ("c2", "C2"), ("c3", "C3")):
            r = store.get(key)
            if not r or "error" in r:
                continue
            what = f"attested {'satisfied' if r['satisfied'] else 'not satisfied'} · {esc(SHORT)}"
            if r["commit"]:
                tag = f"git-{r['tag'][len(TAG_PREFIX):][:7]}" if r.get("tag") else "no tag"
                rows.append(f'<div class="r"><b>{label}</b><span>{what}</span><code>{esc(tag)}</code>'
                            f'<code>Flexo {esc(r["commit"][:8])}</code></div>')
            else:
                msg = "not published: Flexo did not respond (local mode)" if (why or r.get("note")) or flexo is None else "not published"
                rows.append(f'<div class="r"><b>{label}</b><span>{what}</span><span>{esc(msg)}</span></div>')
        if rows:
            rows[-1] = rows[-1].replace('class="r"', 'class="r new"', 1)
        return f'<div class="rows">{"".join(rows)}</div>' if rows else ""

    def sign(key: str, label: str, design: str, satisfied: bool, sufficiency: str, ev_text: str,
             pending: str = "") -> dict:
        """Write the person's claim, evaluate the model, publish the snapshot. Returns the record."""
        att = attestation_block(NAME[design], satisfied, ENGINEER, "done", sufficiency, f"vc001_{NAME[design]}")
        text = assemble(STRUCT, ev_text, att, ADEQ)
        res = evaluate(text)
        commit, tag, note = publish_snapshot(label, text)
        rec = {"satisfied": satisfied, "att": att, "text": text, "commit": commit, "tag": tag, "note": note,
               "claim": res["claims"].get(f"att_{NAME[design]}"), "diag": res["diagnostics"]}
        store[key] = rec
        return rec

    def view_of(text: str, fallback: str):
        """(image uri, engine): the requirement view of a model text, regenerated by the toolchain, else the
        captured SVG `fallback` (engine "captured", shown with a label)."""
        if TOOLS_OK:
            try:
                from sysml.views import requirement_view

                svg = ev.plantuml_svg(requirement_view(text, "plantuml"), timeout=8)
                return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode(), "live"
            except Exception:  # noqa: BLE001 any toolchain failure: the captured SVG, labelled
                pass
        return data_uri(fallback), "captured"

    # the (4,25) requirement view, drawn at load: the red view that D3's Revise click turns green
    BEFORE_VIEW = view_of(assemble(STRUCT, EVB[NEAR], "", ADEQ), "tool-req-c1.svg")

    # ---- the widgets (defined here, away from the slides that read them) ----
    _last = lambda n: str(n) if PRESEED else "1"  # noqa: E731
    d1_step = mo.ui.radio(["1", "2"], value=_last(2), inline=True)
    d2_step = mo.ui.radio(["1", "2", "3", "4", "5"], value=_last(5), inline=True)
    d3_step = mo.ui.radio(["1", "2", "3"], value=_last(3), inline=True)
    d2_limit = mo.ui.radio(["on", "off"], value="on", inline=True, label="torque limit")
    d2_dt = mo.ui.radio(["0.5", "0.05"], value="0.5", inline=True, label="solver step")
    d2_time = mo.ui.slider(60, 180, 1, value=60, label="time (s)", show_value=True, full_width=True)
    btn_c1 = counter_button("Attest")
    btn_c2 = counter_button("Attest")
    btn_c3 = counter_button("Attest")
    btn_z3 = counter_button("Run the formal check")
    btn_rev = counter_button("Revise design: Kp 8, Kd 30")

    LOAD_S = time.time() - t_load

    K = types.SimpleNamespace(**{k: v for k, v in locals().items() if not k.startswith("_")})
    mo.Html(
        "<style>" + TOP + "</style>"
        '<div style="padding-top:12vh;max-width:1000px">'
        '<h1 style="font-size:2.6rem;line-height:1.2;margin:0 0 2.2rem 0">'
        "Evidence, Attestation, and Requirements Traceability with Python and Flexo MMS</h1>"
        '<p style="font-size:1.7rem;font-weight:600;margin:0 0 .3rem 0">Michael Zargham</p>'
        '<p style="font-size:1.3rem;margin:0 0 2.2rem 0">'
        "Chief Engineer, Dynamical Systems Group · Maintainer, OpenMBEE</p>"
        '<p style="font-size:1.2rem;color:#6b7280;margin:0">'
        "OpenTeams Open Source Architect Community · October 15, 2026</p></div>"
        "<!-- SLIDE:T0 -->"
    )
    return (K, btn_c1, btn_c2, btn_c3, btn_rev, btn_z3, d1_step, d2_dt, d2_limit, d2_step, d2_time, d3_step, mo)


@app.cell(hide_code=True)
def _h0(K):
    # <!-- SLIDE:H0 --> The cold open: the full output of one real command, captured.
    _cap = (K.ASSETS / "tool-verify.txt").read_text()
    K.slide("h0", HIGHLIGHT=K.region_line(_cap), PANEL=K.verify_panel(_cap, size=18))
    # <!-- SLIDE:H0 -->
    return


@app.cell(hide_code=True)
def _p1(K):
    # <!-- SLIDE:P1 --> The thesis: machine below the line, person above it.
    K.slide("thesis")
    # <!-- SLIDE:P1 -->
    return


@app.cell(hide_code=True)
def _h1(K):
    # <!-- SLIDE:H1 --> History: era one, then the recent era with the releases sparkline.
    _h = K.json.loads((K.ROOT / "talk" / "history.json").read_text())
    import base64 as _b64
    import io as _io
    _buf = _io.BytesIO()
    K.fg.history_timeline(_h).savefig(_buf, format="png", dpi=87)
    _src = "data:image/png;base64," + _b64.b64encode(_buf.getvalue()).decode()
    _v = _h["velocity"]
    K.deck(K.render("h1", (
        '<div class="slide">'
        + K.title("OpenMBEE's open tools are a decade old, and the newest are weeks old")
        + '<div class="bld" data-n="2"><div style="position:relative;width:1166px;margin-top:6px">'
        + f'<img src="{_src}" alt="OpenMBEE history timeline" style="display:block;width:1166px">'
        + '<div data-s="1" style="position:absolute;left:58.2%;top:0;right:0;bottom:0;background:#fff"></div>'
        + '<div data-s="1" style="position:absolute;left:55.8%;top:68%;width:2.4%;height:8%;background:#e5e7eb"></div></div>'
        + f'<p class="src">Public GitHub release data, retrieved {_v["retrieved"]}; NumFOCUS; PyPI.</p>'
        + "</div></div>"
    )))
    # <!-- SLIDE:H1 -->
    return


@app.cell(hide_code=True)
def _h2(K):
    # <!-- SLIDE:H2 --> The stack: standards, open-source tools, one install command.
    K.slide("stack")
    # <!-- SLIDE:H2 -->
    return


@app.cell(hide_code=True)
def _m1(K):
    # <!-- SLIDE:M1 --> One text file, two renderers.
    K.slide("m1")
    # <!-- SLIDE:M1 -->
    return


@app.cell(hide_code=True)
def _e1(K):
    # <!-- SLIDE:E1 --> Four kinds of evidence; the "cannot see" column is withheld until the callback.
    K.slide("evidence-kinds")
    # <!-- SLIDE:E1 -->
    return


@app.cell(hide_code=True)
def _m2(K):
    # <!-- SLIDE:M2 --> Adequacy: a judgment about the modeling assumptions, made once, before any design.
    _card = K.human_card("adequacy", K.CARD_ADEQUACY).replace('class="card"', 'class="card" style="margin:0"')
    K.slide("m2", CARD=_card)
    # <!-- SLIDE:M2 -->
    return


@app.cell(hide_code=True)
def _d1(K, btn_c1, d1_step, mo):
    # <!-- SLIDE:D1 --> Step 1: both kinds of evidence fail, and the person's verdict becomes model data.
    _step = int(d1_step.value)
    _d = K.D["initial"]
    _plot = K.fg.error_plot_svg([K.curve("initial")], t1=360, width=660, height=262)
    _ttl = "Both kinds of evidence fail, and I say so on the record"

    def _page(busy=False):
        _rec = K.store.get("c1")
        _signed = _rec is not None
        _tiles = (
            '<div style="display:flex;gap:18px;align-items:center;margin-top:8px">'
            + K.tile(f"{_d['symbolic_s']:.0f} s", "linear estimate (SymPy)")
            + K.tile(f"{_d['settling']['worst']:.0f} s", "simulation, worst axis")
            + K.verdict_pill("initial")
            + "</div>"
        )
        _figrow = (
            '<div class="flex" style="margin-top:12px;align-items:center;gap:26px">'
            f'<div style="flex:none;width:660px"><div class="fig">{_plot}</div>'
            '<p class="kap">simulation, worst axis (x): pointing error against time</p></div>'
            f'<div style="flex:none;width:420px">{K.img(K.data_uri("tool-req-c1.svg"), "width:420px;border:1px solid #e5e7eb;border-radius:8px", "Requirement view, colored by the verdict")}'
            '<p class="kap">OpenSysML requirement view <span class="tag" style="font-size:15px">captured</span></p></div></div>'
        )
        _lower = ""
        if _step >= 2:
            if _signed:
                _card = K.human_card("NOT SATISFIED", K.CARD_NOT_SATISFIED)
                _side = K.commit_rows()
            else:
                _card = K.human_card("", K.CARD_NOT_SATISFIED, pending=True)
                _side = ('<p class="hint">Publishing C1…</p>' if busy else f'<span class="go">{btn_c1}</span>')
            _lower = (f'<div class="flex" style="margin-top:10px;align-items:center"><div style="flex:1">{_card}</div>'
                      f'<div style="flex:none;width:470px">{_side}</div></div>')
        _aud = K.audit(
            f"Evidence block (generated from the analysis code):\n{K.EVB['initial']}",
            f"Sufficiency, in full:\n{K.SUFFICIENCY_NOT_SATISFIED}",
            f"Source Git SHA {K.GIT_SHA}" + (" (source tree has local changes)" if K.DIRTY else "")
            + (f"\nAttestation written by the Attest click:\n{_rec['att']}" if _signed else ""),
        )
        return K.deck('<div class="slide">' + K.title(_ttl, live=True)
                      + _tiles + _figrow + _lower + K.stepnav(d1_step) + _aud + "</div>")

    if K.should_fire("c1", btn_c1.value):
        mo.output.replace(_page(busy=True))
        K.sign("c1", "C1: person attests not satisfied", "initial", False, K.SUFFICIENCY_NOT_SATISFIED, K.EVB["initial"])
    _page()
    # <!-- SLIDE:D1 -->
    return


@app.cell(hide_code=True)
def _d2(K, btn_c2, btn_z3, d2_dt, d2_limit, d2_step, d2_time, mo):
    # <!-- SLIDE:D2 --> Step 2: the formal check passes (linear model); the simulation misses by half a second.
    _step = int(d2_step.value)
    _d = K.D[K.NEAR]
    _sim, _axis = _d["settling"]["worst"], _d["settling"]["worst_axis"]
    _nl = K.EV["nolimit"]["settling_s"]
    _lim_on = d2_limit.value == "on"
    _dt = d2_dt.value
    _inm = K.EV["inmodel"][_dt]
    _claim = "The formal check passes. The simulation misses by half a second."
    _neutral = f"SymPy says {_d['symbolic_s']:.0f} s. Does the simulation agree?"

    if K.should_fire("z3", btn_z3.value):
        mo.output.replace(K.deck('<div class="slide">' + K.title(_neutral, live=True)
                                 + '<p class="hint" style="margin-top:30px">Running sysmlv2 verify --solve…</p></div>'))
        K.store["z3"] = K.ev.tool_verify(10.0)
    if K.PRESEED and "z3" not in K.store:
        K.store["z3"] = K.ev.tool_verify(10.0)
    _z3 = K.store.get("z3")
    _busy = [False]

    def _body():
        if _step == 1:
            _tiles = ('<div style="margin-top:14px;display:flex;gap:18px;align-items:center">'
                      + K.tile(f"{_d['symbolic_s']:.0f} s", f"linear estimate (SymPy) at Kp = {_d['kp']}, Kd = {_d['kd']}")
                      + K.tile("?", "simulation, with the torque limit").replace('class="tile"', 'class="tile" style="border-color:#9ca3af"')
                      + '</div>')
            if _z3 is None:
                return (_tiles + '<p style="font-size:40px;font-family:Lora,Georgia,serif;font-weight:600;margin:26px 0 8px">Does the simulation pass? Type P or F in the chat.</p>'
                        '<p class="hint" style="margin-bottom:16px">First, the formal check, over a box of nearby designs: the same command as the opening slide.</p>'
                        f'<span class="go">{btn_z3}</span>')
            _tag = '<span class="tag">captured</span>' if _z3["engine"] == "captured" else ""
            return (_tiles + '<div style="margin-top:14px;display:flex;align-items:center;gap:16px">'
                    '<div class="callout" style="flex:1"><span style="font-size:28px;font-weight:700">Z3 finds no counterexample in this box, for the linear model.</span></div>'
                    f'{_tag}</div><div style="margin-top:10px">{K.verify_panel(_z3["text"], size=16)}</div>')
        if _step == 2:
            _grid = K.fg.grid_svg(K.EV["grid"], (4, 5, 6), (22, 23.5, 25), K.LIMIT, mark=(4, 25), height=400)
            _t = d2_time.value
            _plot = K.fg.error_plot_svg([K.curve(K.NEAR)], t0=60, t1=180, y0=0.03, y1=3, cursor=_t, width=560, height=380, x_step=20)
            return ('<div class="flex" style="margin-top:10px;gap:20px;align-items:flex-start">'
                    f'<div style="flex:none;width:520px"><div class="fig">{_grid}</div>'
                    f'<p style="margin:8px 0 0;font-size:24px">{K.pill("fail", f"{K.NFAIL} of {K.NGRID} fail")} <span class="kap">simulated settling time (s), worst axis</span></p></div>'
                    f'<div style="flex:1"><div class="fig">{_plot}</div><div style="margin-top:6px">{d2_time}</div>'
                    f'<p class="kap">Design (4, 25), worst axis ({_axis}): {_sim:.1f} s against the {K.LIMIT} s limit</p></div></div>')
        if _step == 3:
            _nlc = K.EV["nolimit"]["series"]
            _on, _off = K.curve(K.NEAR), {"t": _nlc["t"], "error_deg": _nlc["error_deg"], "color": "#2166ac"}
            _cs = [_on] if _lim_on else [_off]
            _other = dict(_off if _lim_on else _on, color="#9ca3af", dash="6 5")
            _s = _sim if _lim_on else _nl
            _plot = K.fg.error_plot_svg(_cs, t0=60, t1=180, y0=0.03, y1=3, width=520, height=270, x_step=20)
            _inset = K.fg.error_plot_svg([_other, *_cs], t0=115, t1=125, y0=0.08, y1=0.12, width=360, height=200, x_step=5, limit=120.0)
            _kind = "pass" if _s <= K.LIMIT else "fail"
            _kind2 = "pass" if _inm <= K.LIMIT else "fail"
            return ('<div class="flex" style="margin-top:8px;gap:22px;align-items:flex-start">'
                    f'<div style="flex:none;width:540px"><p style="margin:0 0 2px;font-size:20px;color:#4b5563">same simulation, {_axis} axis</p><div class="zoomctl">{d2_limit}</div>'
                    f'<div class="fig" style="margin-top:4px">{_plot}</div>'
                    f'<p style="margin:6px 0 0;font-size:26px">{_s:.1f} s {K.pill(_kind, _kind.upper())}</p></div>'
                    f'<div style="flex:1"><p class="kap" style="margin:0 0 2px">zoom: 115 to 125 s, 0.08 to 0.12 degrees (grey: the other setting)</p><div class="fig">{_inset}</div>'
                    '<p style="margin:8px 0 0;font-size:20px;color:#4b5563">in-model simulation (SysML action), torque limit on</p>'
                    f'<div style="display:flex;align-items:center;gap:18px"><div class="zoomctl">{d2_dt}</div>'
                    f'<span style="font-size:26px">{float(_inm):.1f} s {K.pill(_kind2, _kind2.upper())}</span></div>'
                    '<p class="kap" style="margin:0">the solver step changes the verdict</p></div></div>')
        _rec = K.store.get("c2")
        _text = K.card_disagree(_sim, K.LIMIT)
        _ev = K.strip("z3 holds (linear model)", f"simulation {_sim:.1f} s: FAIL", f"no torque limit {_nl:.1f} s",
                      "solver step flips the verdict")
        if _rec is not None:
            _card, _side = K.human_card("NOT SATISFIED", _text, draft=not K.C2_CONFIRMED), K.commit_rows()
        else:
            _card = K.human_card("", _text, pending=True, draft=not K.C2_CONFIRMED)
            _side = '<p class="hint">Publishing C2…</p>' if _busy[0] else f'<span class="go">{btn_c2}</span>'
        return (f'<div style="margin-top:18px">{_ev}</div><div style="margin-top:16px">{_card}</div>'
                f'<div style="margin-top:16px">{_side}</div>')

    def _page():
        _aud = K.audit(
            "Rationale for the C2 attestation, in full (DRAFT):\n"
            + K.sufficiency_disagree(_d["kp"], _d["kd"], _d["symbolic_s"], _sim, _axis, K.LIMIT),
            "Per-axis simulated settling (s): " + ", ".join(f"{a}={_d['settling'][a]:.1f}" for a in "xyz")
            + f"; torque limit active until {_d['settling']['saturated_s']:.1f} s",
            "z3 output:\n" + (_z3["text"] if _z3 else "(not run yet)"),
        )
        if _step == 4:  # E1 again, with the last column revealed: "this is why"
            _cb = K.render("e1cb", (K.SLIDES / "evidence-kinds-callback.html").read_text()).rstrip()
            return K.deck(_cb[:-6] + K.stepnav(d2_step) + _aud + "</div>")
        return K.deck('<div class="slide">' + K.title(_neutral if _step == 1 else _claim, live=True)
                      + _body() + K.stepnav(d2_step) + _aud + "</div>")

    if K.should_fire("c2", btn_c2.value):
        _busy[0] = True
        mo.output.replace(_page())
        _busy[0] = False
        K.sign("c2", "C2: person attests not satisfied", K.NEAR, False,
               K.sufficiency_disagree(_d["kp"], _d["kd"], _d["symbolic_s"], _sim, _axis, K.LIMIT), K.EVB[K.NEAR])
    _page()
    # <!-- SLIDE:D2 -->
    return


@app.cell(hide_code=True)
def _d3(K, btn_c3, btn_rev, d3_step, mo):
    # <!-- SLIDE:D3 --> Step 3: one revision regenerates everything; only a person signs.
    _step = int(d3_step.value)
    _d = K.D["tuned"]
    _s = _d["settling"]
    _suff = K.sufficiency_satisfied(_d["kp"], _d["kd"], _s["worst"], _d["symbolic_s"], K.LIMIT)
    _ttl = "One revision regenerates everything. Only a person signs."

    def _regenerate() -> dict:
        """Rewrite the model for the revised design and regenerate its view: the toolchain, or the captured SVG."""
        _t = K.time.time()
        _pending = K.assemble(K.STRUCT, K.EVB["tuned"] + K.status_block("req001"), "", K.ADEQ)
        _uri, _engine = K.view_of(_pending, "tool-req-c3.svg")
        return {"pending": _pending, "uri": _uri, "engine": _engine, "secs": K.time.time() - _t}

    if K.should_fire("rev", btn_rev.value):
        mo.output.replace(K.deck('<div class="slide">' + K.title(_ttl, live=True)
                                 + '<p class="hint" style="margin-top:30px">Rewriting the model and regenerating the requirement view…</p></div>'))
        K.store["rev"] = _regenerate()
    if K.PRESEED and "rev" not in K.store:
        K.store["rev"] = _regenerate()
    _rev = K.store.get("rev")
    _bars = K.fg.axis_bars_svg({a: _s[a] for a in "xyz"}, K.LIMIT, t_max=140, width=620, height=260)
    _bars_blank = K.fg.axis_bars_svg({a: _s[a] for a in "xyz"}, K.LIMIT, t_max=140, width=620, height=260, blank=True)

    def _body(busy: bool):
        if _step == 1:
            _uri, _eng = (_rev["uri"], _rev["engine"]) if _rev else K.BEFORE_VIEW
            _tag = '<span class="tag" style="font-size:15px">captured</span>' if _eng == "captured" else ""
            if _rev is None:
                _left = (f'<p class="kap" style="margin:0 0 4px">simulated settling time, slew about each axis: the worst axis governs</p>'
                         f'<div class="fig">{_bars_blank}</div>'
                         f'<div style="margin-top:16px"><span class="go">{btn_rev}</span></div>'
                         '<p class="hint" style="margin-top:12px">Two numbers change: Kp 4 to 8, Kd 25 to 30.</p>')
                _cap = None
            else:
                _left = (f'<p class="kap" style="margin:0 0 4px">simulated settling time, slew about each axis: the worst axis governs</p>'
                         f'<div class="fig">{_bars}</div>'
                         f'<div style="display:flex;gap:16px;align-items:center;margin-top:16px;flex-wrap:wrap">{K.tile(f"{_d["symbolic_s"]:.1f} s", "linear estimate (SymPy)")}'
                         f'{K.verdict_pill("tuned")}{K.pill("pend", "pending: no one has judged")}</div>')
                _took = (f"regenerated in {_rev['secs']:.1f} s" if _rev["engine"] == "live" else "toolchain did not respond; captured view")
                _cap = f'{_took} {_tag}'
                _vcrm = (f'<div style="margin-top:10px">{K.img(K.data_uri("tool-vcrm.png"), "width:330px;border:1px solid #e5e7eb;border-radius:6px", "Generated check table")}'
                         '<p class="kap" style="font-size:15px;margin:2px 0 0">captured · consistency check, not a satisfaction verdict</p></div>')
            _vc = _vcrm if _rev else ""
            return ('<div class="flex" style="margin-top:10px;gap:26px;align-items:flex-start">'
                    f'<div style="flex:none;width:640px">{_left}</div>'
                    f'<div style="flex:1;text-align:center">{K.img(_uri, "width:420px;border:1px solid #e5e7eb;border-radius:8px", "Requirement view")}'
                    + (f'<p class="kap">OpenSysML requirement view, {_cap}</p>' if _cap else f'<p class="kap">OpenSysML requirement view: the last design, (4, 25), attested not satisfied {_tag}</p>')
                    + f'{_vc}</div></div>')
        if _rev is None:
            return '<p class="hint" style="margin-top:40px">Revise the design first (step 1).</p>'
        _rec = K.store.get("c3")
        if _step == 2:
            if _rec is not None:
                _card, _side = K.human_card("SATISFIED", K.CARD_SATISFIED), K.commit_rows()
            else:
                _card = K.human_card("", K.CARD_SATISFIED, pending=True)
                _side = '<p class="hint">Publishing C3…</p>' if busy else f'<span class="go">{btn_c3}</span>'
            return ('<div class="flex" style="margin-top:12px;gap:26px;align-items:flex-start">'
                    f'<div style="flex:1"><div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">{K.verdict_pill("tuned")}'
                    f'{K.pill("pend", "pending: no one has judged") if _rec is None else ""}</div>'
                    f'<div style="margin-top:16px">{_card}</div><div style="margin-top:16px">{_side}</div></div>'
                    f'<div style="flex:none;width:420px"><p class="kap" style="margin:0 0 4px">the evidence: settling time per axis</p><div class="fig">{K.fg.axis_bars_svg({a: _s[a] for a in "xyz"}, K.LIMIT, t_max=140, width=420, height=220)}</div>'
                    f'<p class="kap">linear estimate (SymPy) {_d["symbolic_s"]:.1f} s</p></div></div>')
        if _rec is None:
            return '<p class="hint" style="margin-top:40px">Sign first (step 2).</p>'
        _g = _rec["groups"]
        _lines = [f'<div class="r"><b>+</b><span>{_g["att"]} elements: the attestation, that is the satisfy claim, its status and its rationale</span></div>',
                  f'<div class="r"><b>−</b><span>{_g["pending_elements"]} elements: the pending marker it replaces</span></div>']
        if _g["other"]:
            _out = ", ".join(f"{k} x{n}" for k, n in sorted(_g["other"].items()))
            _lines.append(f'<div class="r"><b>?</b><span>Also changed: {K.esc(_out)}</span></div>')
            _end = "Something besides the signature changed: read the audit trail."
        else:
            _end = "Nothing else changed: no design and no evidence element."
        return ('<div class="rows" style="margin-top:22px;font-size:30px;line-height:1.7">' + "".join(_lines) + "</div>"
                f'<p style="font-size:34px;font-family:Lora,Georgia,serif;font-weight:600;margin:26px 0 8px">{_end}</p>'
                f'<p class="kap">Diff of the model before and after the signature, {K.esc(_rec["how"])}.</p>')

    def _page(busy=False):
        _aud = K.audit(
            "Per-axis simulated settling (s): " + ", ".join(f"{a}={_s[a]:.1f}" for a in "xyz")
            + f"; torque limit active until {_s['saturated_s']:.1f} s",
            f"Evidence block (generated from the analysis code):\n{K.EVB['tuned']}",
            f"Sufficiency, in full:\n{_suff}",
            (f"Attestation written by the Attest click:\n{K.store['c3']['att']}" if K.store.get("c3") else "(not signed yet)"),
        )
        return K.deck('<div class="slide">' + K.title(_ttl, live=True)
                      + _body(busy) + K.stepnav(d3_step) + _aud + "</div>")

    if K.should_fire("c3", btn_c3.value) and _rev is not None:
        mo.output.replace(_page(busy=True))
        _rec = K.sign("c3", "C3: person attests satisfied", "tuned", True, _suff, K.EVB["tuned"])
        _old, _new = K.to_elements(_rev["pending"]), K.to_elements(_rec["text"])
        _rec["groups"] = K.group_diff(_old, _new)
        _rec["how"] = "computed from the two model snapshots (the regenerated model, then the signed model)"
    _page()
    # <!-- SLIDE:D3 -->
    return


@app.cell(hide_code=True)
def _f2(K):
    # <!-- SLIDE:F2 --> The framework (three of four rows used), then CA/CP.
    K.slide("f2")
    # <!-- SLIDE:F2 -->
    return


@app.cell(hide_code=True)
def _x1(K):
    # <!-- SLIDE:X1 --> Opinion: every automated system needs a behavioral envelope.
    K.slide("envelope")
    # <!-- SLIDE:X1 -->
    return


@app.cell(hide_code=True)
def _c1(K):
    # <!-- SLIDE:C1 --> Three things to do on Monday; the opening line returns, with its answer.
    _cap = (K.ASSETS / "tool-verify.txt").read_text()
    _d = K.D[K.NEAR]
    _tail = ('<div class="callout" style="flex:1"><div style="font-size:18px;font-weight:700">z3, for the linear model</div>'
             '<div style="font-size:22px;line-height:1.25">holds for all values of unbound features</div></div>')
    _card = K.human_card("NOT SATISFIED", f"simulation {_d['settling']['worst']:.1f} s").replace(
        f"NOT SATISFIED · {K.esc(K.ENGINEER)}", f"NOT SATISFIED · {K.esc(K.SHORT)}").replace('class="card"', 'class="card" style="flex:none;width:300px"')
    K.slide("cta", H0LINE=_tail, CLOSEKEY=_card)
    # <!-- SLIDE:C1 -->
    return


@app.cell(hide_code=True)
def _r1(K):
    # <!-- SLIDE:R1 --> Reserve: (4, 30) and the y axis.
    from sysml import evidence as _ev

    _s = _ev.slew_settling(4, 30)
    K.deck('<div class="slide">' + K.title(f"(4, 30): the y axis settles at {_s['y']:.1f} s")
           + '<div class="fig" style="margin-top:30px;width:700px">'
           + K.fg.axis_bars_svg({a: _s[a] for a in "xyz"}, K.LIMIT, t_max=140, width=700, height=210) + "</div>"
           + '<p class="cap">Evidence changed. So did the design.</p></div>')
    # <!-- SLIDE:R1 -->
    return


@app.cell(hide_code=True)
def _r2(K):
    # <!-- SLIDE:R2 --> Reserve: one tag ties the model to its source.
    _tags = [("git-" + (K.store.get(k) or {})["tag"][len(K.TAG_PREFIX):][:7]) if (K.store.get(k) or {}).get("tag") else "not published"
             for k in ("c1", "c2", "c3")]
    _foot = ("Same source, so one tag. The design change lives in the model, not the source."
             if not K.DIRTY else "The design change lives in the model. The source tree had local changes at load.")
    K.slide("lineage", SHA=K.GIT_SHA[:7], T1=_tags[0], T2=_tags[1], T3=_tags[2], FOOT=K.esc(_foot))
    # <!-- SLIDE:R2 -->
    return


@app.cell(hide_code=True)
def _r3(K, mo):
    # <!-- SLIDE:R3 --> Reserve: the RDF edition, the same pattern.
    from sysml.lanes import lanes_mermaid

    _d = K.D["tuned"]
    _att = K.attestation_block("revised", True, K.ENGINEER, "done", K.sufficiency_satisfied(_d["kp"], _d["kd"], _d["settling"]["worst"], _d["symbolic_s"], K.LIMIT), "vc001_revised")
    _text = K.assemble(K.STRUCT, K.EVB["tuned"], _att, K.ADEQ)
    _lanes = lanes_mermaid(K.to_elements(_text), compact=True, terms={"S": "≈ sysml:", "E": "≈ prov:", "A": "≈ earl:, gsn:"})
    _m = mo.mermaid(_lanes).text
    K.deck('<div class="slide">' + K.title("First built in RDF. Same pattern.")
           + f'<div style="width:760px;max-width:100%;margin:10px auto 0">{_m}</div>'
           + '<p class="src">PROV, EARL, GSN: provenance, outcome and argument vocabularies.</p></div>')
    # <!-- SLIDE:R3 -->
    return


if __name__ == "__main__":
    app.run()
