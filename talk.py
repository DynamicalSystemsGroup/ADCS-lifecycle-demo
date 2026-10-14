"""# Talk: a tool says pass, a person says satisfied

One notebook is both the slide deck and the live demo. One cell is one slide, and file order is
slide order. The demo beats (B1 to B5, B7) are a thin presentation layer over `sysml/model.py`
(assemble, evaluate), `sysml/figures.py` and `sysml/lanes.py` (pictures), `sysml/flexo_v2.py`
(publish, diff) and `sysml/git_source.py` (Git SHA, text diff).

Present:   uv run marimo run talk.py
Headless:  SYSML_DEMO_PRESEED=1 uv run marimo export html talk.py -o output/talk.html

Load-time work (simulations, SymPy estimates, figures) happens once in the closing cell; the
button-driven beats only evaluate models and publish.
"""

import marimo

__generated_with = "0.22.5"
app = marimo.App(width="full", layout_file="layouts/talk.slides.json")


@app.cell(hide_code=True)
def _s0():
    # <!-- SLIDE:S0 --> Title and hook. Imports, flags and publishing helpers are folded in here
    # so the deck has no blank slides.
    import html
    import io
    import os
    import re
    import uuid
    import warnings

    import httpx
    import marimo as mo

    warnings.simplefilter("ignore")  # the model library flags its API-JSON export as experimental

    from analysis.load_params import load_params
    from analysis.numerical import run_step_response
    from evidence.hashing import hash_simulation
    from sysml import figures as fg
    from sysml.flexo_v2 import FlexoV2, NoChangeError
    from sysml.git_source import head_sha, is_dirty, text_diff
    from sysml.lanes import lanes_mermaid, sandwich_mermaid, two_store_mermaid
    from sysml.model import (
        ADEQUACY_TEXT,
        CARD_ADEQUACY,
        CARD_NOT_SATISFIED,
        CARD_SATISFIED,
        DEMO_ENGINEER,
        SUFFICIENCY_NOT_SATISFIED,
        assemble,
        attestation_block,
        evaluate,
        evidence_block,
        group_diff,
        load_structure,
        status_block,
        sufficiency_satisfied,
        symbolic_settling,
        to_elements,
    )
    from sysml.model import _in_model as in_model, _lib_reach as lib_reach, _top as top_of  # display only: the names behind the counts

    # Headless export: SYSML_DEMO_PRESEED=1 pre-seeds the human attestations (the Attest buttons
    # cannot be clicked in a static export) and publishes NOTHING to Flexo, even when reachable.
    PRESEED = os.environ.get("SYSML_DEMO_PRESEED") == "1"
    _url = os.environ.get("FLEXO_V2_URL", "http://localhost:8083").rstrip("/")
    try:
        FLEXO_UP = httpx.get(_url + "/projects", timeout=3).status_code == 200
    except (httpx.HTTPError, httpx.InvalidURL):
        FLEXO_UP = False
    FLEXO_PUBLISH = FLEXO_UP and not PRESEED

    GIT_SHA = head_sha(str(mo.notebook_dir()))
    DIRTY = is_dirty(str(mo.notebook_dir()))
    flexo = FlexoV2() if FLEXO_PUBLISH else None

    # Session state. One Flexo project per session (sysml-talk-<random>; never deleted: remove
    # with FlexoV2().delete_project(<id>)). `handled` and `frozen` are the reactivity guards: an
    # edit upstream re-runs a beat cell, and that re-run must never act twice.
    project = {}
    handled = {}  # button key -> click count already acted on
    frozen = {}  # the engineer name recorded with the evidence at the first Attest
    store = {}  # c1, c2, c3: the published snapshots

    def should_fire(key: str, clicks: int) -> bool:
        """True once per new click; the pre-seeded export fires once."""
        fire = clicks > handled.get(key, 0) or (PRESEED and key not in handled)
        if fire:
            handled[key] = clicks
        return fire

    def once(key: str) -> bool:
        """True the first time it is asked for `key` in this session."""
        if key in handled:
            return False
        handled[key] = 1
        return True

    def counter_button(label: str):
        """A button whose value is its click count."""
        return mo.ui.button(value=0, on_click=lambda v: v + 1, label=label)

    def seed_label(action: str):
        """Visible label on every pre-seeded human step (neutral, never amber)."""
        if not PRESEED:
            return mo.md("")
        return mo.callout(
            mo.md(f"**pre-seeded for export: in the live demo the speaker clicks {action}**"),
            kind="neutral",
        )

    def publish_snapshot(label: str, text: str):
        """Return (commit_id or None, note or None). Never raises on an unchanged snapshot."""
        if flexo is None:
            return None, None
        try:
            if "id" not in project:
                project["id"] = flexo.ensure_project(f"sysml-talk-{uuid.uuid4().hex[:8]}")
            return flexo.publish(project["id"], to_elements(text), label, GIT_SHA), None
        except NoChangeError:
            return None, "No change: the snapshot is identical to the head, so Flexo made no commit."
        except httpx.HTTPError as e:
            return None, f"Flexo publish failed ({type(e).__name__}); continuing without it."

    def tag_of(commit_id: str) -> str:
        return f"git-{flexo.git_sha(project['id'], commit_id)}"

    def png(fig, dpi=110):
        """A matplotlib figure as an image: bytes render identically under run and export."""
        _buf = io.BytesIO()
        fig.savefig(_buf, format="png", dpi=dpi)
        return _buf.getvalue()

    def asset(name: str, **kw):
        """A Kotar capture from talk/assets, inlined as bytes (works under run and export)."""
        return mo.image((mo.notebook_dir() / "talk" / "assets" / name).read_bytes(), **kw)

    _MER_INIT = (
        "%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '18px', 'clusterBkg': '#f8fafc', "
        "'clusterBorder': '#cbd5e1', 'lineColor': '#6b7280', 'primaryColor': '#ffffff'}, "
        "'flowchart': {'nodeSpacing': 28, 'rankSpacing': 46, 'wrappingWidth': 520}}}%%\n"
    )

    def mer(diagram: str, h: int = 380, lanes: bool = False, zoom: float = 1.0):
        """A Mermaid diagram scaled to fit a box (width of its slot, at most h px high).
        Mermaid renders in a shadow root that page CSS cannot reach, so a short inline handler sets the
        rendered svg's size from its viewBox; without scripts the diagram shows at natural size.
        `lanes` draws the lanes top to bottom instead of left to right: a view-only change
        that keeps the lanes compact (the diagram text is otherwise unchanged)."""
        if lanes:
            diagram = diagram.replace("flowchart LR", "flowchart TB", 1)
        _mm = mo.mermaid(_MER_INIT + diagram)
        _id = "mer" + uuid.uuid4().hex[:10]
        _js = (
            "(function(){var t=setInterval(function(){var b=document.getElementById('%s');"
            "if(!b){clearInterval(t);return}var m=b.querySelector('marimo-mermaid');"
            "var s=m&&m.shadowRoot&&m.shadowRoot.querySelector('svg');if(!s||!s.viewBox.baseVal.width)return;"
            "clearInterval(t);var v=s.viewBox.baseVal,w=b.clientWidth||900,z=Math.min(%d/v.height,w/v.width,2.2);"
            "s.style.maxWidth='none';s.setAttribute('width',v.width*z);s.setAttribute('height',v.height*z);"
            "s.style.width=v.width*z+'px';s.style.height=v.height*z+'px';s.style.display='block';m.style.display='block';m.style.textAlign='center';"
            "s.style.margin='0 auto'},400)})()"
        ) % (_id, h)
        # An <img onerror> runs when the HTML is inserted; a <script> tag does not run on first render.
        return mo.Html(
            f'<div id="{_id}" style="width:100%;zoom:{zoom}">{_mm.text}</div>'
            f'<img alt="" src="x:" style="display:none" onerror="{html.escape(_js if zoom == 1.0 else "", quote=True)}">'
        )

    def code(text: str):
        return mo.md("```text\n" + text + "\n```")

    def audit(*items):
        """The closed Audit trail accordion that holds code, model text, diffs, hashes and tags."""
        return mo.accordion({"Audit trail": mo.vstack(list(items))})

    def diff_view(patch: str):
        """A unified diff with removed and added lines tinted."""
        # Display only: drop blank context lines at the edges of each hunk. Every +/- line is untouched.
        lines, hunk = [], None
        for line in patch.splitlines() + ["@@ end"]:
            if line.startswith("@@"):
                if hunk is not None:
                    while hunk and not hunk[0].strip():
                        hunk.pop(0)
                    while hunk and not hunk[-1].strip():
                        hunk.pop()
                    lines += hunk
                hunk = []
                lines.append(line)
            elif hunk is None:
                lines.append(line)
            else:
                hunk.append(line)
        lines.pop()  # the sentinel
        rows = []
        for line in lines:
            bg = ("rgba(220,60,60,.18)" if line.startswith("-") and not line.startswith("---")
                  else "rgba(60,170,80,.18)" if line.startswith("+") and not line.startswith("+++")
                  else "transparent")
            rows.append(f'<span style="display:block;background:{bg}">{html.escape(line) or " "}</span>')
        return mo.Html('<pre style="font-size:0.8em;overflow-x:auto">' + "".join(rows) + "</pre>")

    def group_names(old_els, new_els, g: dict) -> dict:
        """Names behind the counts, computed from the two snapshots and checked against the
        counts group_diff returned. A list is left empty when it does not reconcile."""
        old = {e["@id"]: e for e in old_els}
        new = {e["@id"]: e for e in new_els}
        added = new.keys() - old.keys()
        meta = sorted(
            new[x["@id"]]["qualifiedName"].split("::")[-1]
            for i in added
            if in_model(i, new) and top_of(i, new) == i and new[i]["@type"] == "MetadataUsage"
            for x in new[i].get("type", [])
            if x["@id"] in new
        )
        lib = sorted(
            new[i]["qualifiedName"]
            for i in lib_reach({i for i in added if in_model(i, new)}, new) & added
        )
        return {
            "meta": meta if len(meta) == g["att_roots"].get("MetadataUsage", 0) else [],
            "lib": lib if len(lib) == g["lib"] else [],
        }

    # One flag, one set of names for the later two states.
    SHORT = {2: "C2", 3: "C3"} if FLEXO_PUBLISH else {2: "snapshot 2", 3: "snapshot 3"}
    LONG = (
        {2: "C2", 3: "C3 (Flexo commits)"}
        if FLEXO_PUBLISH
        else {2: "snapshot 2 (after retune)", 3: "snapshot 3 (after attestation)"}
    )

    def groups_view(g: dict, names: dict, from_label: str, to_label: str, to_short: str, how: str):
        """The four approved groups as readable lines (live counts, names computed). The closing
        line is shown only when nothing falls outside the groups."""
        roots = g["att_roots"]
        kinds = {"SatisfyRequirementUsage": "satisfy claim", "MetadataUsage": "metadata"}
        pieces = []
        for t, n in sorted(roots.items(), key=lambda kv: (kv[0] != "SatisfyRequirementUsage", kv[0])):
            label = kinds.get(t, t)
            if t == "MetadataUsage" and names["meta"]:
                label += ": " + ", ".join(names["meta"])
            pieces.append(f"{n} {label}")
        att_line = (
            f"Attestation added: {sum(roots.values())} new elements ({' + '.join(pieces)}), "
            f"with {g['att'] - sum(roots.values())} owned sub-elements"
        )
        lib_extra = (
            f" + {g['pending_library']} library definition only it referenced"
            if g["pending_library"] else ""
        )
        pend_line = f"Pending marker removed: {g['pending']} (superseded by the attestation)"
        pend_sub = f"{g['pending_elements']} elements{lib_extra}"
        pkg_line = (
            f"Package now contains the attestation (+{g['pkg']} members)"
            if g["pkg"] else "Package: no attestation members gained"
        )
        lib_names = f" (names: {', '.join(f'`{n}`' for n in names['lib'])})" if names["lib"] else ""
        lib_line = f"Standard-library definitions the attestation uses: {g['lib']}{lib_names}"
        parts = [
            mo.md(
                f"**Element diff {from_label} to {to_label}** ({how}), grouped by what each element is\n\n"
                f"- {att_line}\n"
                f"- {pend_line}  \n  <small>{pend_sub}</small>\n"
                f"- {pkg_line}\n"
                f"- {lib_line}\n\n"
                "Counts include owned sub-elements, because SysML v2 exports every feature and "
                "membership as its own element."
            )
        ]
        if g["other"]:
            outside = ", ".join(f"{k} x{n}" for k, n in sorted(g["other"].items()))
            parts.append(
                mo.callout(
                    mo.md(
                        f"**Warning: not everything in this diff is the attestation, what it "
                        f"references, or the pending marker it supersedes.** Outside the four "
                        f"groups: {outside}. The statement that no evidence or design element "
                        "changed is therefore not made."
                    ),
                    kind="danger",
                )
            )
        elif g["att"]:
            parts.append(
                mo.md(
                    f"Everything new in {to_short} is the human's attestation and what it "
                    "references; the pending marker it supersedes is removed; no evidence or "
                    "design element changed."
                )
            )
        return mo.vstack(parts)

    # The status line is small and neutral: it says which mode this run is in.
    if not FLEXO_UP:
        _status = "Local mode: Flexo not reachable"
    elif PRESEED:
        _status = "Export mode: nothing published to Flexo"
    else:
        _status = f"Flexo reachable · source git {GIT_SHA[:7]}"
    mo.vstack([
        mo.md(
            "# A tool says pass. A person says satisfied.\n\n"
            "- Evidence supports a human judgement.\n"
            "- Written before OpenSysML existed; now it runs on it.\n\n"
            "<!-- SLIDE:S0 -->"
        ),
        mo.md(f"<small><i>{_status}{' · uncommitted source changes' if DIRTY else ''}</i></small>"),
    ])
    return (
        ADEQUACY_TEXT,
        CARD_ADEQUACY,
        CARD_NOT_SATISFIED,
        CARD_SATISFIED,
        DEMO_ENGINEER,
        FLEXO_PUBLISH,
        GIT_SHA,
        LONG,
        PRESEED,
        SHORT,
        SUFFICIENCY_NOT_SATISFIED,
        asset,
        assemble,
        attestation_block,
        audit,
        code,
        counter_button,
        diff_view,
        evaluate,
        evidence_block,
        fg,
        flexo,
        frozen,
        group_diff,
        group_names,
        groups_view,
        hash_simulation,
        lanes_mermaid,
        load_params,
        load_structure,
        mer,
        mo,
        once,
        png,
        project,
        publish_snapshot,
        re,
        run_step_response,
        sandwich_mermaid,
        seed_label,
        should_fire,
        status_block,
        store,
        sufficiency_satisfied,
        symbolic_settling,
        tag_of,
        text_diff,
        to_elements,
        two_store_mermaid,
        uuid,
    )


@app.cell(hide_code=True)
def _s1(asset, mo):
    mo.hstack([
        mo.vstack([
            mo.md(
                "## OpenMBEE <!-- SLIDE:S1 -->\n\n"
                "- Code since 2014; NumFOCUS 2020\n"
                "- Apache-2.0; pip install opensysml\n"
                "- Task: render API returns data, not pictures"
            ),
            mo.md("<small><i>rendered by Kotar (Planetary Utilities); not colour-coded</i></small>"),
        ], justify="center"),
        asset("toaster-states.png", width=560, rounded=True),
    ], widths=[1, 1], align="center")
    return


@app.cell(hide_code=True)
def _s2(asset, mo):
    _tabs = mo.ui.tabs({
        "Overview": asset("sat-00-overview.png", width=640, rounded=True),
        "Requirement, design, satisfy": asset("sat-01-requirement-design-satisfy.png", width=520, rounded=True),
        "Evidence and approvals": mo.vstack([
            asset("sat-03-evidence-tools.png", width=420, rounded=True),
            asset("sat-04-approvals.png", width=640, rounded=True),
        ]),
    })
    mo.hstack([
        mo.vstack([
            mo.md(
                "## The pattern <!-- SLIDE:S2 -->\n\n"
                "- A machine-checkable requirement\n"
                "- A verdict: pass, fail or inconclusive\n"
                "- A person's named sign-off, with reasons"
            ),
            mo.md("<small><i>rendered by Kotar (Planetary Utilities); not colour-coded</i></small>"),
        ], justify="center"),
        _tabs,
    ], widths=[2, 3], align="center")
    return


@app.cell(hide_code=True)
def _b1(D, mo, structure):
    # <!-- BEAT:B1 --> only the structure lane is filled.
    mo.vstack([
        mo.md(
            "## A behavioural requirement <!-- BEAT:B1 -->\n\n"
            f"Point within {D['band']:g}° by {D['limit']:.0f} s of a {D['slew']:.0f}° slew. "
            "The design prescribes only Kp and Kd."
        ),
        mer(D["lanes_b1"], 330, lanes=True, zoom=1.5),
        mo.accordion({"Audit trail": mo.md(f"```text\n{structure}\n```")}),
    ])
    return


@app.cell(hide_code=True)
def _b2(
    ADEQUACY_TEXT,
    CARD_ADEQUACY,
    D,
    assemble,
    code,
    audit,
    evaluate,
    evidence_block,
    fg,
    frozen,
    lanes_mermaid,
    mo,
    name_in,
    structure,
    to_elements,
):
    # <!-- BEAT:B2 --> two models, two answers; the person's adequacy judgement.
    _by = frozen.get("by", name_in.value)
    _r = D["runs"][D["first"]]
    mo.stop(
        not _by.strip(),
        mo.callout(mo.md("Enter the engineer name: the adequacy judgement must belong to a named human."), kind="danger"),
    )
    try:
        ev1 = evidence_block("initial", _r["params"], _r["summary"], _r["hash"], ADEQUACY_TEXT, _by,
                             _r["t_sym"], _r["est_hash"])
    except ValueError as _e:
        mo.stop(True, mo.callout(mo.md(str(_e)), kind="danger"))
    model_b2 = assemble(structure, ev1)
    _res = evaluate(model_b2)
    verdict_b2 = _res["verdicts"]["vc001_initial"]
    lanes_b2 = lanes_mermaid(to_elements(model_b2))
    mo.vstack([
        mo.md(
            "## Two models, two answers <!-- BEAT:B2 -->\n\n"
            f"Linear estimate {_r['t_sym']:.0f} s, simulation {_r['t_sim']:.0f} s, limit {D['limit']:.0f} s."
        ),
        mo.hstack([mo.Html(fg.pill(verdict_b2.upper(), verdict_b2))], justify="start"),
        mo.hstack([
            mo.image(D["png"]["b2"], width=700),
            mo.Html(fg.human_card(_by.strip(), "adequacy", CARD_ADEQUACY)),
        ], widths=[3, 2], align="center"),
        audit(
            mo.md("**Evidence block** (generated by Python from the two runs):"),
            code(ev1),
            mo.md(f"Hashes: simulation `sha256:{_r['hash'][:16]}…`, SymPy `sha256:{_r['est_hash'][:16]}…`."),
            mo.md(f"**Adequacy, in full** ({_by.strip()}'s Rationale): {ADEQUACY_TEXT}"),
            mo.md(
                f"OpenSysML evaluates the evidence block: verdict **{verdict_b2}**. "
                "That is verification, an automated check. Nobody has said satisfied."
            ),
        ),
    ])
    return ev1, lanes_b2, model_b2, verdict_b2


@app.cell(hide_code=True)
def _b3(
    CARD_NOT_SATISFIED,
    D,
    SUFFICIENCY_NOT_SATISFIED,
    assemble,
    attestation_block,
    audit,
    btn_b3,
    code,
    diff_view,
    ev1,
    fg,
    frozen,
    lanes_b2,
    lanes_mermaid,
    mo,
    model_b2,
    name_in,
    publish_snapshot,
    seed_label,
    should_fire,
    store,
    structure,
    tag_of,
    text_diff,
    to_elements,
    verdict_b2,
):
    # <!-- BEAT:B3 --> a person says not satisfied; Flexo commit C1.
    if should_fire("b3", btn_b3.value):
        try:
            _who = name_in.value.strip()
            _att = attestation_block("initial", False, _who, "done", SUFFICIENCY_NOT_SATISFIED, "vc001_initial")
            _text = assemble(structure, ev1, _att)
            frozen.setdefault("by", _who)  # the evidence is fixed from the first Attest on
            _commit, _note = publish_snapshot("C1: human attests not satisfied", _text)
            store["c1"] = {"who": _who, "att": _att, "text": _text, "commit": _commit, "note": _note,
                           "lanes": lanes_mermaid(to_elements(_text))}
        except ValueError as _e:
            store["c1"] = {"error": str(_e)}
    c1 = store.get("c1")
    _parts = [
        mo.md(
            "## A person says not satisfied <!-- BEAT:B3 -->\n\n"
            f"The tool said {verdict_b2}. I say not satisfied, and here is why."
        ),
    ]
    _trail = [mo.md("The attestation block is written only by the Attest click, under the name below. "
                    "The sufficiency text is the approved wording, not editable here.")]
    if c1 is None or "error" in c1:
        _parts.append(mo.hstack([mer(lanes_b2, 340, lanes=True), mo.image(D["png"]["b2"], width=320)], widths=[3, 1], align="center"))
        if c1 is not None:
            _parts.append(mo.callout(mo.md(f"Not recorded: {c1['error']}"), kind="danger"))
        _parts.append(mo.hstack([name_in, btn_b3, seed_label("Attest")], justify="start", align="end"))
    else:
        _parts.append(mo.hstack([mer(c1["lanes"], 340, lanes=True), mo.image(D["png"]["b2"], width=320)], widths=[3, 1], align="center"))
        _parts.append(mo.Html(fg.human_card(c1["who"], "NOT SATISFIED", CARD_NOT_SATISFIED)))
        _trail += [
            mo.md(f"**Attestation block** written by {c1['who']}:"),
            code(c1["att"]),
            mo.md(f"**Sufficiency, in full:** {SUFFICIENCY_NOT_SATISFIED}"),
        ]
        if c1["commit"]:
            _trail.append(mo.md(
                "Published to Flexo as **C1**. Each Flexo commit is tagged with the Git SHA of the "
                f"source that produced it: tag `{tag_of(c1['commit'])}`."))
        else:
            _trail += [mo.md("Text diff of the model, B2 model to B3 model:"),
                       diff_view(text_diff(model_b2, c1["text"]))]
        if c1["note"]:
            _trail.append(mo.callout(mo.md(c1["note"]), kind="warn"))
        _trail.insert(0, mo.hstack([name_in, seed_label("Attest")], justify="start", align="end"))
    _parts.append(audit(*_trail))
    mo.vstack(_parts)
    return (c1,)


@app.cell(hide_code=True)
def _b4(
    ADEQUACY_TEXT,
    D,
    assemble,
    audit,
    c1,
    code,
    diff_view,
    evaluate,
    evidence_block,
    fg,
    frozen,
    lanes_mermaid,
    mo,
    name_in,
    once,
    publish_snapshot,
    status_block,
    store,
    structure,
    tag_of,
    text_diff,
    to_elements,
):
    # <!-- BEAT:B4 --> retune: the evidence changed, so the prior attestation is removed. Flexo C2.
    _r = D["runs"][D["tuned"]]
    _by = frozen.get("by", name_in.value)
    try:
        ev2 = evidence_block("tuned", _r["params"], _r["summary"], _r["hash"], ADEQUACY_TEXT, _by,
                             _r["t_sym"], _r["est_hash"])
    except ValueError as _e:
        mo.stop(True, mo.callout(mo.md(str(_e)), kind="danger"))
    # Pending marker: StatusInfo tbc about req001, no originator, no rationale. Python writes it,
    # so it names no person: no person has acted.
    pending = status_block("req001")
    model_b4 = assemble(structure, ev2 + pending)
    verdict_b4 = evaluate(model_b4)["verdicts"]["vc001_tuned"]
    lanes_b4 = lanes_mermaid(to_elements(model_b4))
    # Live mode only (publish_snapshot is a no-op without Flexo). Runs once, after C1 exists, so
    # C2 always follows C1 and there is no separate click.
    if c1 is not None and "error" not in c1 and once("c2"):
        _commit, _note = publish_snapshot("C2: retune, attestation removed, status pending", model_b4)
        store["c2"] = {"commit": _commit, "note": _note}
    c2 = store.get("c2")
    _trail = [
        mo.md("**Generated by Python** (not written by a person): the pending status"),
        code(pending),
        mo.md(f"Evidence block for the tuned design:"),
        code(ev2),
        mo.md(f"Hashes: simulation `sha256:{_r['hash'][:16]}…`, SymPy `sha256:{_r['est_hash'][:16]}…`."),
        mo.md(
            "The evidence changed, so the prior attestation no longer applies and is removed. "
            f"The verdict is **{verdict_b4}**. Status is pending: no person has judged the new evidence yet."
        ),
    ]
    if c1 is not None and "error" not in c1:
        _trail += [mo.md("Text diff of the model, B3 model to this model. The `not satisfy` line is gone:"),
                   diff_view(text_diff(c1["text"], model_b4))]
    if c2 and c2["commit"]:
        _trail.append(mo.md(f"Published to Flexo as **C2**, tagged `{tag_of(c2['commit'])}`."))
    if c2 and c2["note"]:
        _trail.append(mo.callout(mo.md(c2["note"]), kind="warn"))
    _a, _b = D["runs"][D["first"]], _r
    mo.vstack([
        mo.md(
            "## Retune: old attestation removed <!-- BEAT:B4 -->\n\n"
            f"Both under the limit: {_b['t_sym']:.0f} s and {_b['t_sim']:.0f} s."
        ),
        mo.hstack([
            mo.Html(fg.pill(verdict_b4.upper(), verdict_b4)),
            mo.Html(fg.pill("tbc · no one has judged", "tbc")),
        ], justify="start"),
        mo.hstack([mo.image(D["png"]["b4"], width=600), mer(lanes_b4, 340, lanes=True)], widths=[1, 1], align="center"),
        audit(*_trail),
    ])
    return c2, ev2, lanes_b4, model_b4, verdict_b4


@app.cell(hide_code=True)
def _b5(
    CARD_SATISFIED,
    D,
    LONG,
    SHORT,
    assemble,
    attestation_block,
    audit,
    btn_b5,
    c1,
    c2,
    code,
    diff_view,
    ev2,
    fg,
    flexo,
    group_diff,
    group_names,
    groups_view,
    lanes_mermaid,
    mo,
    model_b4,
    name_in,
    project,
    publish_snapshot,
    seed_label,
    should_fire,
    store,
    structure,
    sufficiency_satisfied,
    tag_of,
    text_diff,
    to_elements,
):
    # <!-- BEAT:B5 --> the neighbourhood, then the human clicks Attest. Flexo C3.
    _r = D["runs"][D["tuned"]]
    _suff = sufficiency_satisfied(f"{_r['params']['Kp']:g}", f"{_r['params']['Kd']:g}",
                                  _r["t_sim"], _r["t_sym"], f"{D['limit']:g}")
    if should_fire("b5", btn_b5.value):
        try:
            _who = name_in.value.strip()
            _att = attestation_block("tuned", True, _who, "done", _suff, "vc001_tuned")
            _text = assemble(structure, ev2, _att)
            _commit, _note = publish_snapshot("C3: human attests satisfied", _text)
            if _commit and c2 and c2["commit"]:
                _old = list(flexo.elements(project["id"], c2["commit"]).values())
                _new = list(flexo.elements(project["id"], _commit).values())
                _how = "from the two Flexo commits"
            else:  # export, local mode, or C2/C3 not both committed: diff the two snapshots in-process
                _old, _new = to_elements(model_b4), to_elements(_text)
                _how = "computed in-process from the two model snapshots; nothing published"
            _g = group_diff(_old, _new)
            store["c3"] = {"who": _who, "att": _att, "text": _text, "commit": _commit, "note": _note,
                           "groups": _g, "names": group_names(_old, _new, _g), "how": _how,
                           "lanes": lanes_mermaid(_new)}
        except ValueError as _e:
            store["c3"] = {"error": str(_e)}
    c3 = store.get("c3")
    _parts = [
        mo.md(
            "## Judging the neighbourhood <!-- BEAT:B5 -->\n\n"
            f"Tuned design: both under the limit. Neighbours where they split: {D['n_flip']} of {D['n_nb']}."
        ),
    ]
    _trail = [mo.md("The attestation block is written only by the Attest click, under the engineer name from B3. "
                    "The sufficiency text is the approved wording with live numbers.")]
    if c3 is None or "error" in c3:
        _parts.append(mo.image(D["png"]["b5"], width=760))
        _parts.append(mo.hstack([mo.Html(fg.pill("tbc · no one has judged", "tbc")), btn_b5, seed_label("Attest")],
                                justify="start", align="center"))
        if c3 is not None:
            _parts.append(mo.callout(mo.md(f"Not recorded: {c3['error']}"), kind="danger"))
        _trail.append(mo.md(f"Attesting as: {name_in.value.strip() or '(enter the engineer name in B3)'}"))
    else:
        _parts.append(mo.hstack([mo.image(D["png"]["b5"], width=520), mer(c3["lanes"], 330, lanes=True)],
                                widths=[1, 1], align="center"))
        _parts.append(mo.Html(fg.human_card(c3["who"], "SATISFIED", CARD_SATISFIED)))
        _trail += [
            mo.md(f"**Attestation block** written by {c3['who']}:"),
            code(c3["att"]),
            mo.md(f"**Sufficiency, in full:** {_suff}"),
        ]
        if c3["commit"]:
            _tags = [f"- {_n}: tag `{tag_of(_s['commit'])}`"
                     for _n, _s in (("C1", c1), ("C2", c2), ("C3", c3)) if _s and _s.get("commit")]
            _shas = {t.split("`")[1] for t in _tags}
            _same = ("\n\nThe tags are the same Git SHA because the source did not change during the demo."
                     if len(_tags) > 1 and len(_shas) == 1 else "")
            _trail.append(mo.md("Each Flexo commit is tagged with the Git SHA of the source that produced it:\n\n"
                                + "\n".join(_tags) + _same))
        else:
            _trail += [mo.md("Text diff of the model, B4 model to B5 model:"),
                       diff_view(text_diff(model_b4, c3["text"]))]
        _trail.append(groups_view(c3["groups"], c3["names"], LONG[2], LONG[3], SHORT[3], c3["how"]))
        if c3["note"]:
            _trail.append(mo.callout(mo.md(c3["note"]), kind="warn"))
    _parts.append(audit(*_trail))
    mo.vstack(_parts)
    return (c3,)


@app.cell(hide_code=True)
def _b7(btn_b7, c3, evaluate, fg, mo, PRESEED, seed_label):
    # <!-- BEAT:B7 --> (optional, cut first) checking the claim: verification of the claim, not attestation.
    _holds = None
    if c3 is not None and "error" not in c3 and (btn_b7.value or PRESEED):
        _holds = evaluate(c3["text"])["claims"]["att_tuned"]["holds"]
    _head = mo.md("## Checking the claim <!-- BEAT:B7 -->")
    if _holds is None:
        _body = [
            mo.md("Check the attested claim against the evaluated model."
                  if c3 is not None and "error" not in c3 else "Attest in B5 first: there is no claim to check yet."),
            btn_b7,
        ]
    else:
        _body = [
            mo.md(f"{'Consistent' if _holds else 'Not consistent'} with the evaluated model. "
                  "That is not attestation."),
            mo.Html(fg.machine_card("CONSISTENCY CHECK")),
            seed_label("Check the claim"),
        ]
    mo.vstack([_head, *_body, mo.accordion({"Audit trail": mo.md(
        "`verify_satisfaction` on the attested `satisfy` claim, evaluated against the model. "
        "It says nothing about the physical satellite."
        + (f"\n\n```text\n{c3['att']}\n```" if c3 is not None and 'att' in c3 else ""))})])
    return


@app.cell(hide_code=True)
def _s4(D, mo):
    mo.vstack([
        mo.md(
            "## Git: source. Flexo: model. <!-- SLIDE:S4 -->\n\n"
            "- Git merged a power overrun cleanly\n"
            "- Flexo stored any type unvalidated\n"
            "- Each Flexo commit is tagged with its Git SHA"
        ),
        mer(D["two_store"], 420),
    ])
    return


@app.cell(hide_code=True)
def _s5(D, c3, lanes_b4, mo):
    # The lanes diagram at C3 again, with the RDF terms labelling the same three lanes.
    _lanes = c3["lanes"] if c3 is not None and "lanes" in c3 else lanes_b4
    mo.vstack([
        mo.md(
            "## First built in RDF <!-- SLIDE:S5 -->\n\n"
            "- PROV, EARL, GSN: the same pattern\n"
            "- Opinion: SysML v2 is the better home now"
        ),
        mer(_lanes, 270, lanes=True, zoom=0.5),
        mo.hstack([
            mo.md("**Structure** ≈ `sysml:`"),
            mo.md("**Evidence** ≈ `prov:`"),
            mo.md("**Attestation** ≈ `earl:`, `gsn:`"),
        ], justify="space-around"),
    ])
    return


@app.cell(hide_code=True)
def _s6(mo):
    mo.md("""
    ## The pattern beyond satellites <!-- SLIDE:S6 -->

    - AI evaluation (CAIE): machine-verified or human-validated
    - Tool testing. Opinion: exit 0 is not a verdict
    - Gaps become upstream issues
    """)
    return


@app.cell(hide_code=True)
def _s7(D, mo):
    mo.vstack([
        mo.md("## Dynamical Systems Group: executable across the board <!-- SLIDE:S7 -->"),
        mer(D["sandwich"], 460, zoom=1.7),
    ])
    return


@app.cell(hide_code=True)
def _s8(
    DEMO_ENGINEER,
    counter_button,
    fg,
    hash_simulation,
    lanes_mermaid,
    load_params,
    load_structure,
    mo,
    png,
    re,
    run_step_response,
    sandwich_mermaid,
    symbolic_settling,
    to_elements,
    two_store_mermaid,
    assemble,
    flexo,
    project,
    uuid,
):
    # <!-- SLIDE:S8 --> Closing slide. The UI elements and ALL the heavy load-time work are
    # defined here, so the beats display and consume them and the live clicks stay cheap.
    structure = load_structure()
    _limit = float(re.search(r"settlingTime\s*<=\s*([\d.]+)\s*\[s\]", structure).group(1))
    _band = float(re.search(r"within\s+([\d.]+)\s+degrees", structure).group(1))

    FIRST, TUNED = (1.0, 10.0), (4.0, 30.0)
    NEIGHBOURS = [(4.0, 25.0), (6.0, 25.0), (3.0, 30.0), (4.0, 40.0)]
    runs = {}
    for _kp, _kd in [FIRST, TUNED, *NEIGHBOURS]:
        _p = dict(load_params(), Kp=_kp, Kd=_kd)
        _sim = run_step_response(_p)
        _sum = _sim.summary()
        _t_sym, _est_hash = symbolic_settling(_p)
        runs[(_kp, _kd)] = {
            "params": _p, "sim": _sim, "summary": _sum, "hash": hash_simulation(_sim.config.to_dict(), _sum),
            "t_sim": float(_sum["settling_time_s"]), "t_sym": _t_sym, "est_hash": _est_hash,
        }

    def _name(d):
        return f"Kp={d[0]:g}, Kd={d[1]:g}"

    _a, _b = runs[FIRST], runs[TUNED]
    _slew = float(fg.pointing_error_deg(_a["sim"])[0])
    _rows = [(_name(TUNED) + " (tuned)", _b["t_sym"], _b["t_sim"], True)] + [
        (_name(d), runs[d]["t_sym"], runs[d]["t_sim"], False) for d in NEIGHBOURS
    ]
    D = {
        "limit": _limit, "band": _band, "slew": round(_slew), "runs": runs, "first": FIRST, "tuned": TUNED,
        "png": {
            "b2": png(fg.settling_figure(_a["sim"], _a["t_sym"], _limit)),
            "b4": png(fg.overlay_figure(_a["sim"], _b["sim"], (_name(FIRST), _name(TUNED)), _limit, _band)),
            "b5": png(fg.neighbour_strip(_rows, _limit)),
        },
        # a neighbour "splits" when exactly one of the two estimates is within the limit
        "n_flip": sum((r[1] <= _limit) != (r[2] <= _limit) for r in _rows[1:]),
        "n_nb": len(NEIGHBOURS),
        "lanes_b1": lanes_mermaid(to_elements(assemble(structure))),
        "two_store": two_store_mermaid(),
        "sandwich": sandwich_mermaid([
            "Systems engineering: SysML v2, OpenSysML", "Modeling and analysis", "Governed compute"]),
    }

    # Creating the Flexo project takes seconds: do it here, at load, so the first click only publishes.
    if flexo is not None and "id" not in project:
        try:
            project["id"] = flexo.ensure_project(f"sysml-talk-{uuid.uuid4().hex[:8]}")
        except Exception:  # publish_snapshot reports it when a beat needs it
            pass

    name_in = mo.ui.text(value=DEMO_ENGINEER, label="Attesting as", full_width=False)
    btn_b3 = counter_button("Attest: not satisfied")
    btn_b5 = counter_button("Attest: satisfied")
    btn_b7 = mo.ui.run_button(label="Check the claim")

    mo.md(
        "# Use it. Help build it. <!-- SLIDE:S8 -->\n\n"
        "- pip install opensysml\n"
        "- Replicate or fix three open issues\n"
        "- Join: openmbee.org. Demo: github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo"
    )
    return D, btn_b3, btn_b5, btn_b7, name_in, structure


if __name__ == "__main__":
    app.run()
