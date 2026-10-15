"""# Talk: a tool says pass, a person says satisfied

One notebook is both the slide deck and the live demo. One cell is one slide, and file order is
slide order. The demo beats (B1 to B5, B7) are a thin presentation layer over `sysml/model.py`
(assemble, evaluate), `sysml/figures.py` and `sysml/lanes.py` (pictures), `sysml/flexo_v2.py`
(publish, diff) and `sysml/git_source.py` (Git SHA, text diff).

Present:   uv run marimo run talk.py
Headless:  SYSML_DEMO_PRESEED=1 uv run marimo export html talk.py -o output/talk.html

Load-time work (Flexo probe and project, simulations, SymPy estimates, figures) happens once, in the
first and last cells; the button-driven beats only evaluate models and publish.
"""

import marimo

__generated_with = "0.22.5"
app = marimo.App(width="full", layout_file="layouts/talk.slides.json")


@app.cell(hide_code=True)
def _s0():
    # <!-- SLIDE:S0 --> Title. Imports, flags, the one Flexo probe and the publishing helpers
    # are folded in here so the deck has no blank slides.
    import html
    import io
    import os
    import re
    import warnings

    import httpx
    import marimo as mo

    warnings.simplefilter("ignore")  # the model library flags its API-JSON export as experimental

    from analysis.load_params import load_params
    from analysis.numerical import run_step_response
    from evidence.hashing import hash_simulation
    from sysml import figures as fg
    from sysml.flexo_v2 import TAG_PREFIX, FlexoV2, NoChangeError
    from sysml.git_source import head_sha, is_dirty, text_diff
    from sysml.lanes import lanes_mermaid, stack_mermaid, two_store_mermaid
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

    # Headless export: SYSML_DEMO_PRESEED=1 pre-seeds the human attestations (the Attest buttons
    # cannot be clicked in a static export) and publishes NOTHING to Flexo, so Flexo is not probed.
    PRESEED = os.environ.get("SYSML_DEMO_PRESEED") == "1"
    GIT_SHA = head_sha(str(mo.notebook_dir()))  # the live HEAD at load
    DIRTY = is_dirty(str(mo.notebook_dir()))

    # Session state. `handled` and `frozen` are the reactivity guards: an edit upstream re-runs a
    # beat cell, and that re-run must never act twice.
    project = {}
    handled = {}  # button key -> click count already acted on
    frozen = {}  # the engineer name recorded with the evidence at the first Attest
    store = {}  # c1, c2, c3, b7: results that must survive a re-run of a beat cell

    # One probe, at load, with a timeout that covers the local stack (a listing takes about 3 s).
    # One Flexo project per Git SHA (sysml-talk-<sha7>): reused when it exists, created here at
    # load so that a click only publishes. It is never deleted; remove with FlexoV2().delete_project(id).
    flexo = None
    why = ""
    if not PRESEED:
        _url = os.environ.get("FLEXO_V2_URL", "http://localhost:8083").rstrip("/")
        _name = f"sysml-talk-{GIT_SHA[:7]}"
        try:
            _probe = httpx.get(_url + "/projects", timeout=20)
            _probe.raise_for_status()
            _client = FlexoV2()
            _have = [p["@id"] for p in _probe.json() if p["name"] == _name]
            project["id"] = _have[0] if _have else _client.ensure_project(_name)
            project["name"] = _name
            flexo = _client
        except Exception as _e:  # any failure at all (HTTP, URL, JSON, a missing field): run in local mode
            flexo = None
            why = f" ({type(_e).__name__})"

    if PRESEED:
        STATUS = "Export mode: nothing published to Flexo"
    elif flexo is None:
        STATUS = f"Local mode: Flexo not available{why}"
    else:
        STATUS = f"Flexo reachable · project {project['name']}"
    STATUS += f" · source git {GIT_SHA[:7]}" + (" · uncommitted source changes" if DIRTY else "")

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

    def note_line(note):
        """A publish problem, as one neutral line on the slide (nothing when there is none)."""
        return mo.callout(mo.md(note), kind="neutral") if note else mo.md("")

    def publish_snapshot(label: str, text: str):
        """Return (commit_id or None, tag or None, note or None). Never raises on an HTTP problem.
        The tag is stored here, at publish time, so rendering never calls Flexo. If only the tag
        POST fails, the commit exists: it is returned (it is the branch head) with tag None and a note."""
        if flexo is None:
            return None, None, None
        try:
            commit = flexo.publish(project["id"], to_elements(text), label, GIT_SHA)
            return commit, f"{TAG_PREFIX}{GIT_SHA}", None
        except NoChangeError:
            return None, None, "No change: the snapshot is identical to the head, so Flexo made no commit."
        except httpx.HTTPError as e:
            try:
                _tag_step = e.request.url.path.endswith("/tags")
            except RuntimeError:  # the error carries no request
                _tag_step = False
            if _tag_step:
                try:
                    _head = flexo._json("GET", f"/projects/{project['id']}/branches")[0]["head"]["@id"]
                    return _head, None, f"Published, but Flexo did not tag the commit ({type(e).__name__})."
                except Exception:  # noqa: BLE001 the head is unknown too: report the publish as failed
                    pass
            return None, None, f"Flexo publish failed ({type(e).__name__}); this step continues without it."

    def publish_line(label: str, rec: dict):
        """One neutral line under a beat: "Published C1 to Flexo, tagged git-xxxxxxx", or the note."""
        parts = []
        if rec.get("commit"):
            parts.append(f"Published {label} to Flexo" + (f", tagged `git-{rec['tag'][len(TAG_PREFIX):][:7]}`" if rec.get("tag") else ""))
        if rec.get("note"):
            parts.append(rec["note"])
        return mo.md(f'<small style="color:#6b7280">{" · ".join(parts)}</small>') if parts else mo.md("")

    def tag_text(rec: dict):
        """The tag as shown in an Audit trail: the tag, or a plain sentence when the commit has none."""
        return f"tag `{rec['tag']}`" if rec.get("tag") else "not tagged; see the note"

    def publishing_line(label: str):
        """Shown the moment Attest is clicked, before the slow publish returns."""
        return mo.md(f'<small style="color:#6b7280">Publishing {label} to Flexo…</small>')

    # Top-anchor: marimo centers a slide's content vertically (the output box has auto block
    # margins), so titles would jump from slide to slide. This rule zeroes those margins. It rides
    # inside each slide's title markdown, because a virtual swiper drops far-away slides, and their
    # style tags with them.
    TOP = "<style>.mo-slide-content .output{margin-block:0!important}</style>"

    def head(text: str):
        """A slide's title block: markdown, with the top-anchor rule attached."""
        return mo.md(text + TOP)

    def png(fig, dpi=110):
        """A matplotlib figure as an image: bytes render identically under run and export."""
        _buf = io.BytesIO()
        fig.savefig(_buf, format="png", dpi=dpi)
        return _buf.getvalue()

    def asset(name: str, **kw):
        """A Kotar capture from talk/assets, inlined as bytes (works under run and export)."""
        return mo.image((mo.notebook_dir() / "talk" / "assets" / name).read_bytes(), **kw)

    def mer(diagram: str, width: int = 720):
        """A Mermaid diagram in a centered box of `width` px. The svg lives in the mermaid element's
        shadow root, out of reach of page CSS: it fills the box but never grows past its own natural
        size. So `width` shrinks a diagram that is too big, and a diagram that should read larger is
        enlarged by its font size in `sysml/lanes.py`; for a small diagram set `width` to its natural
        width (about 5 px over) so that the box, and with it the diagram, is centered."""
        return mo.Html(f'<div style="width:{width}px;max-width:100%;margin:0 auto">{mo.mermaid(diagram).text}</div>')

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

    def groups_view(g: dict, from_label: str, to_label: str, to_short: str, how: str):
        """The four approved groups as readable lines (live counts; the names come from
        `group_diff`). The closing line is shown only when nothing falls outside the groups."""
        roots, names = g["att_roots"], g["names"]
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
                        f"**Not everything in this diff is the attestation, what it "
                        f"references, or the pending marker it supersedes.** Outside the four "
                        f"groups: {outside}. The statement that no evidence or design element "
                        "changed is therefore not made."
                    ),
                    kind="neutral",
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

    head(
        '<div style="padding-top:12vh;max-width:1000px">'
        '<h1 style="font-size:2.6rem;line-height:1.2;margin:0 0 2.2rem 0">'
        "Evidence, Attestation, and Requirements Traceability with Python and Flexo MMS</h1>"
        '<p style="font-size:1.7rem;font-weight:600;margin:0 0 .3rem 0">Michael Zargham</p>'
        '<p style="font-size:1.3rem;margin:0 0 2.2rem 0">'
        "Chief Engineer, Dynamical Systems Group · Maintainer, OpenMBEE</p>"
        '<p style="font-size:1.2rem;color:#6b7280;margin:0">'
        "OpenTeams Open Source Architect Community · October 15, 2026</p></div>"
        "<!-- SLIDE:S0 -->"
    )
    return (
        ADEQUACY_TEXT,
        CARD_ADEQUACY,
        CARD_NOT_SATISFIED,
        CARD_SATISFIED,
        DEMO_ENGINEER,
        PRESEED,
        STATUS,
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
        groups_view,
        hash_simulation,
        head,
        httpx,
        lanes_mermaid,
        load_params,
        load_structure,
        mer,
        mo,
        note_line,
        once,
        png,
        project,
        publish_line,
        publish_snapshot,
        publishing_line,
        tag_text,
        re,
        run_step_response,
        seed_label,
        stack_mermaid,
        should_fire,
        status_block,
        store,
        sufficiency_satisfied,
        symbolic_settling,
        text_diff,
        to_elements,
        two_store_mermaid,
    )


@app.cell(hide_code=True)
def _s1_history(audit, fg, head, mo, png):
    # <!-- SLIDE:S1 --> OpenMBEE history: the picture is the slide. Every label is read from
    # talk/history.json; the audit trail lists each row's public source.
    import json as _json

    _h = _json.loads((mo.notebook_dir() / "talk" / "history.json").read_text())
    _v = _h["velocity"]
    _src = "\n".join(f"- {e['date']} {e['label']}: {e['source']}" for e in _h["events"])
    _org = "\n".join(f"- {o['name']} ({o['era']}; {o['role']}): {o['source']}" for o in _h["orgs"])
    mo.vstack([
        head(
            "## OpenMBEE: a decade of open engineering tools <!-- SLIDE:S1 -->\n\n"
            f"{_h['orgs_heading']}, by era"
        ),
        mo.image(png(fg.history_timeline(_h), dpi=87)),
        audit(mo.md(
            f"**Releases per month.** {_v['metric']} Source: {_v['source']}; retrieved {_v['retrieved']}.\n\n"
            f"**Milestones.**\n\n{_src}\n\n**{_h['orgs_heading']}.**\n\n{_org}"
        )),
    ], gap=0.4)
    return


@app.cell(hide_code=True)
def _s1(head, mer, mo, stack_mermaid):
    mo.vstack([
        head("## OpenSysML in the stack <!-- SLIDE:S1 -->\n\nApache-2.0 (Pilot: EPL-2.0)"),
        mer(stack_mermaid(), 760),
    ], gap=0.4)
    return


@app.cell(hide_code=True)
def _s2(head):
    head(
        "## A tool says pass. A person says satisfied. <!-- SLIDE:S2 -->\n\n"
        "- Evidence supports a human judgment.\n"
        "- The pattern predates OpenSysML; today it runs on OpenSysML.\n\n"
        "### The pattern\n\n"
        "- A machine-checkable requirement\n"
        "- A verdict: pass, fail or inconclusive\n"
        "- A person's named sign-off, with reasons"
    )
    return


@app.cell(hide_code=True)
def _b1(D, STATUS, asset, head, mer, mo, structure):
    # <!-- BEAT:B1 --> only the structure band is filled.
    mo.vstack([
        head(
            "## A behavioral requirement <!-- BEAT:B1 -->\n\n"
            f"Point within {D['band']:g}° by {D['limit']:.0f} s of a {D['slew']:.0f}° slew. "
            "The design prescribes only Kp and Kd."
        ),
        mer(D["lanes_b1"], 600),
        mo.accordion({"Audit trail": mo.vstack([
            mo.md(f"```text\n{structure}\n```"),
            mo.md("<small><i>the final model, rendered by Kotar (Planetary Utilities)</i></small>"),
            asset("sat-00-overview.png", width=900),
        ])}),
        mo.md(f'<small style="color:#6b7280">{STATUS}</small>'),
    ])
    return


@app.cell(hide_code=True)
def _b2(
    ADEQUACY_TEXT,
    CARD_ADEQUACY,
    D,
    assemble,
    audit,
    code,
    evaluate,
    evidence_block,
    fg,
    frozen,
    head,
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
        mo.callout(mo.md("Enter the engineer name: the adequacy judgement must belong to a named human."), kind="neutral"),
    )
    try:
        ev1 = evidence_block("initial", _r["params"], _r["summary"], _r["hash"], ADEQUACY_TEXT, _by,
                             _r["t_sym"], _r["est_hash"])
    except ValueError as _e:
        mo.stop(True, mo.callout(mo.md(str(_e)), kind="neutral"))
    model_b2 = assemble(structure, ev1)
    _res = evaluate(model_b2)
    verdict_b2 = _res["verdicts"]["vc001_initial"]
    lanes_b2 = lanes_mermaid(to_elements(model_b2), compact=True)
    mo.vstack([
        head(
            "## Two models, two numbers <!-- BEAT:B2 -->\n\n"
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
            mo.md(
                "Settling time in the figure is the last time the pointing error exceeds 1% of the "
                f"initial error ({0.01 * D['slew']:g}° for the {D['slew']:.0f}° slew). "
                "The simulation value is the one recorded as evidence."
            ),
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
    flexo,
    head,
    lanes_b2,
    lanes_mermaid,
    mer,
    mo,
    model_b2,
    name_in,
    publish_line,
    publish_snapshot,
    publishing_line,
    tag_text,
    seed_label,
    should_fire,
    store,
    structure,
    text_diff,
    to_elements,
    verdict_b2,
):
    # <!-- BEAT:B3 --> a person says not satisfied; Flexo commit C1.
    _thumb = mo.image(D["png"]["b2t"], width=440)
    _controls = mo.hstack([name_in, btn_b3, seed_label("Attest")], justify="start", align="end")
    _pre = [
        head(f"## A person judges the design <!-- BEAT:B3 -->\n\nThe tool said {verdict_b2}."),
        mo.hstack([mer(lanes_b2, 740), _thumb], widths=[3, 2], align="center"),
    ]
    if should_fire("b3", btn_b3.value):
        if flexo is not None:  # no dead air: say so at once, before the publish returns
            mo.output.replace(mo.vstack([*_pre, _controls, publishing_line("C1")]))
        try:
            _who = name_in.value.strip()
            _att = attestation_block("initial", False, _who, "done", SUFFICIENCY_NOT_SATISFIED, "vc001_initial")
            _text = assemble(structure, ev1, _att)
            frozen.setdefault("by", _who)  # the evidence is fixed from the first Attest on
            _commit, _tag, _note = publish_snapshot("C1: human attests not satisfied", _text)
            store["c1"] = {"who": _who, "att": _att, "text": _text, "commit": _commit, "tag": _tag, "note": _note,
                           "lanes": lanes_mermaid(to_elements(_text), compact=True)}
        except ValueError as _e:
            store["c1"] = {"error": str(_e)}
    c1 = store.get("c1")
    _done = c1 is not None and "error" not in c1
    _trail = [mo.md("The attestation block is written only by the Attest click, under the name below. "
                    "The sufficiency text is the approved wording, not editable here.")]
    if not _done:
        _parts = list(_pre)
        if c1 is not None:
            _parts.append(mo.callout(mo.md(f"Not recorded: {c1['error']}"), kind="neutral"))
        _parts.append(_controls)
    else:
        _parts = [
            head(
                "## A person says not satisfied <!-- BEAT:B3 -->\n\n"
                f"The tool said {verdict_b2}. I say not satisfied, and here is why."
            ),
            mo.hstack([mer(c1["lanes"], 680), _thumb], widths=[3, 2], align="center"),
            mo.hstack([mo.Html(fg.human_card(c1["who"], "NOT SATISFIED", CARD_NOT_SATISFIED)),
                       publish_line("C1", c1)], widths=[4, 1], align="center"),
        ]
        _trail += [
            mo.md(f"**Attestation block** written by {c1['who']}:"),
            code(c1["att"]),
            mo.md(f"**Sufficiency, in full:** {SUFFICIENCY_NOT_SATISFIED}"),
        ]
        if c1["commit"]:
            _trail.append(mo.md(
                "Published to Flexo as **C1**. Each Flexo commit is tagged with the Git SHA of the "
                f"source that produced it: {tag_text(c1)}." + (f" Note: {c1['note']}" if c1.get("note") else "")))
        else:
            _trail += [mo.md("Text diff of the model, B2 model to B3 model:"),
                       diff_view(text_diff(model_b2, c1["text"]))]
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
    head,
    mo,
    name_in,
    once,
    publish_line,
    publish_snapshot,
    status_block,
    tag_text,
    store,
    structure,
    text_diff,
):
    # <!-- BEAT:B4 --> retune: the evidence changed, so the prior attestation is removed. Flexo C2.
    _r = D["runs"][D["tuned"]]
    _by = frozen.get("by", name_in.value)
    try:
        ev2 = evidence_block("tuned", _r["params"], _r["summary"], _r["hash"], ADEQUACY_TEXT, _by,
                             _r["t_sym"], _r["est_hash"])
    except ValueError as _e:
        mo.stop(True, mo.callout(mo.md(str(_e)), kind="neutral"))
    # Pending marker: StatusInfo tbc about req001, no originator, no rationale. Python writes it,
    # so it names no person: no person has acted.
    pending = status_block("req001")
    model_b4 = assemble(structure, ev2 + pending)
    verdict_b4 = evaluate(model_b4)["verdicts"]["vc001_tuned"]
    # Live mode only (publish_snapshot is a no-op without Flexo). Runs once, after C1 exists, so
    # C2 always follows C1 and there is no separate click.
    if c1 is not None and "error" not in c1 and once("c2"):
        _commit, _tag, _note = publish_snapshot("C2: retune, attestation removed, status pending", model_b4)
        store["c2"] = {"commit": _commit, "tag": _tag, "note": _note}
    c2 = store.get("c2")
    _trail = [
        mo.md("**Generated by Python** (not written by a person): the pending status"),
        code(pending),
        mo.md("Evidence block for the tuned design:"),
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
        _trail.append(mo.md(f"Published to Flexo as **C2**: {tag_text(c2)}." + (f" Note: {c2['note']}" if c2.get("note") else "")))
    mo.vstack([
        head(
            "## Retune: old attestation removed <!-- BEAT:B4 -->\n\n"
            f"Tuned design: estimate {_r['t_sym']:.0f} s, simulation {_r['t_sim']:.0f} s, "
            f"both under {D['limit']:.0f} s."
        ),
        mo.hstack([
            mo.Html(fg.pill(verdict_b4.upper(), verdict_b4)),
            mo.Html(fg.pill("tbc · no one has judged", "tbc")),
        ], justify="start"),
        mo.hstack([mo.image(D["png"]["b4"], width=780)], justify="center"),
        publish_line("C2", c2) if c2 else mo.md(""),
        audit(*_trail),
    ])
    return c2, ev2, model_b4


@app.cell(hide_code=True)
def _b5(
    CARD_SATISFIED,
    D,
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
    groups_view,
    head,
    httpx,
    lanes_mermaid,
    mer,
    mo,
    model_b4,
    name_in,
    project,
    publish_line,
    publish_snapshot,
    publishing_line,
    tag_text,
    seed_label,
    should_fire,
    store,
    structure,
    sufficiency_satisfied,
    text_diff,
    to_elements,
):
    # <!-- BEAT:B5 --> the neighborhood, then the human clicks Attest. Flexo C3.
    _r = D["runs"][D["tuned"]]
    _suff = sufficiency_satisfied(f"{_r['params']['Kp']:g}", f"{_r['params']['Kd']:g}",
                                  _r["t_sim"], _r["t_sym"], f"{D['limit']:g}")
    _strip = mo.image(D["png"]["b5"], width=780)
    _head = (
        "## Judging the neighborhood <!-- BEAT:B5 -->\n\n"
        f"Tuned design: both under the limit. Neighbors where they split: {D['n_flip']} of {D['n_nb']}."
    )
    _pill_row = mo.hstack([mo.Html(fg.pill("tbc · no one has judged", "tbc")), btn_b5, seed_label("Attest")],
                          justify="start", align="center")
    if should_fire("b5", btn_b5.value):
        if flexo is not None:  # no dead air: say so at once, before the publish returns
            mo.output.replace(mo.vstack([head(_head), mo.hstack([_strip], justify="center"), _pill_row,
                                         publishing_line("C3")]))
        try:
            _who = name_in.value.strip()
            _att = attestation_block("tuned", True, _who, "done", _suff, "vc001_tuned")
            _text = assemble(structure, ev2, _att)
            _commit, _tag, _note = publish_snapshot("C3: human attests satisfied", _text)
            # The diff is in-process unless both commits exist and Flexo answers for both; the
            # labels say which one it was.
            _old, _new = to_elements(model_b4), to_elements(_text)
            _labels = ("snapshot 2 (after retune)", "snapshot 3 (after attestation)", "snapshot 3")
            _how = "computed in-process from the two model snapshots; nothing published"
            if _commit and c2 and c2["commit"]:
                try:
                    _flexo_old = list(flexo.elements(project["id"], c2["commit"]).values())
                    _flexo_new = list(flexo.elements(project["id"], _commit).values())
                    _old, _new = _flexo_old, _flexo_new
                    _labels, _how = ("C2", "C3 (Flexo commits)", "C3"), "from the two Flexo commits"
                except httpx.HTTPError as _e:
                    _diff_note = f"Flexo diff unavailable ({type(_e).__name__}); the diff is computed in-process."
                    _note = f"{_note} {_diff_note}" if _note else _diff_note
                    _how = "computed in-process from the two model snapshots; Flexo did not answer"
            store["c3"] = {"who": _who, "att": _att, "text": _text, "commit": _commit, "tag": _tag, "note": _note,
                           "groups": group_diff(_old, _new), "labels": _labels, "how": _how,
                           "lanes": lanes_mermaid(to_elements(_text), compact=True)}
        except ValueError as _e:
            store["c3"] = {"error": str(_e)}
    c3 = store.get("c3")
    _done = c3 is not None and "error" not in c3
    _trail = [mo.md("The attestation block is written only by the Attest click, under the engineer name from B3. "
                    "The sufficiency text is the approved wording with live numbers.")]
    if not _done:
        _parts = [head(_head), mo.hstack([_strip], justify="center"), _pill_row]
        if c3 is not None:
            _parts.append(mo.callout(mo.md(f"Not recorded: {c3['error']}"), kind="neutral"))
        _trail.append(mo.md(f"Attesting as: {name_in.value.strip() or '(enter the engineer name in B3)'}"))
    else:
        _parts = [
            head(_head),
            # the lanes at C3 are primary (60%); the strip the judgement rests on is the 40% thumbnail
            mo.hstack([mer(c3["lanes"], 640), mo.image(D["png"]["b5t"], width=520)], widths=[11, 9], align="center"),
            mo.hstack([mo.Html(fg.human_card(c3["who"], "SATISFIED", CARD_SATISFIED)),
                       publish_line("C3", c3)], widths=[4, 1], align="center"),
        ]
        _trail += [
            mo.md("The neighborhood the judgement rests on:"),
            _strip,
            mo.md(f"**Attestation block** written by {c3['who']}:"),
            code(c3["att"]),
            mo.md(f"**Sufficiency, in full:** {_suff}"),
        ]
        if c3["commit"]:
            _recs = [(_n, _s) for _n, _s in (("C1", c1), ("C2", c2), ("C3", c3)) if _s and _s.get("commit")]
            _tags = [f"- {_n}: {tag_text(_s)}" for _n, _s in _recs]
            _shas = {_s["tag"] for _n, _s in _recs if _s.get("tag")}
            _same = ("\n\nThe tags are the same Git SHA because the source did not change during the demo."
                     if len(_shas) == 1 and sum(1 for _n, _s in _recs if _s.get("tag")) > 1 else "")
            _trail.append(mo.md("Each Flexo commit is tagged with the Git SHA of the source that produced it:\n\n"
                                + "\n".join(_tags) + _same))
        else:
            _trail += [mo.md("Text diff of the model, B4 model to B5 model:"),
                       diff_view(text_diff(model_b4, c3["text"]))]
        _trail.append(groups_view(c3["groups"], *c3["labels"], c3["how"]))
    _parts.append(audit(*_trail))
    mo.vstack(_parts)
    return (c3,)


@app.cell(hide_code=True)
def _b7(PRESEED, btn_b7, c3, evaluate, fg, head, mo, seed_label, store):
    # <!-- BEAT:B7 --> (optional, cut first) checking the claim: verification of the claim, not attestation.
    # The result is kept in `store`, so a re-run of this cell shows it again instead of clearing it.
    _ready = c3 is not None and "error" not in c3
    if _ready and (btn_b7.value or PRESEED) and "b7" not in store:
        store["b7"] = evaluate(c3["text"])["claims"]["att_tuned"]["holds"]
    _holds = store.get("b7") if _ready else None
    _body = [head("## Checking the claim <!-- BEAT:B7 -->")]
    if _holds is None:
        _body += [
            mo.md("Check the attested claim against the evaluated model."
                  if _ready else "Attest in B5 first: there is no claim to check yet."),
            btn_b7,
        ]
    else:
        _body += [
            mo.Html(fg.machine_card(
                f"CONSISTENCY CHECK · {'consistent' if _holds else 'not consistent'} with the evaluated "
                "model. That is not attestation.")),
            seed_label("Check the claim"),
        ]
    _body.append(mo.accordion({"Audit trail": mo.md(
        "`verify_satisfaction` on the attested `satisfy` claim, evaluated against the model. "
        "It says nothing about the physical satellite."
        + (f"\n\n```text\n{c3['att']}\n```" if _ready else ""))}))
    mo.vstack(_body)
    return


@app.cell(hide_code=True)
def _s4(D, head, mer, mo):
    mo.vstack([
        head(
            "## Git: source. Flexo: model. <!-- SLIDE:S4 -->\n\n"
            "- Git merged two individually valid changes into an invalid design\n"
            "- Flexo stored any type unchecked\n"
            "- Flexo commits carry the Git SHA"
        ),
        mer(D["two_store"], 925),
    ])
    return


@app.cell(hide_code=True)
def _s5(c3, head, lanes_mermaid, mer, mo, model_b4, to_elements):
    # The lanes diagram at C3 again. Each band's header carries its RDF term, so the label is level
    # with its band by construction.
    _text = c3["text"] if c3 is not None and "text" in c3 else model_b4
    _lanes = lanes_mermaid(to_elements(_text), compact=True,
                           terms={"S": "≈ sysml:", "E": "≈ prov:", "A": "≈ earl:, gsn:"})
    mo.vstack([
        head(
            "## First built in RDF <!-- SLIDE:S5 -->\n\n"
            "- PROV (provenance), EARL (test outcomes), GSN (assurance arguments): the same pattern\n"
            "- Opinion: SysML v2 is the better home now"
        ),
        mer(_lanes, 760),
        mo.md('<small style="color:#6b7280">≈ means corresponds to</small>'),
    ])
    return


@app.cell(hide_code=True)
def _s6(head):
    head("""
    ## The pattern beyond satellites <!-- SLIDE:S6 -->

    - AI-generated work: machine-verified, human-validated
    - Tool testing. Opinion: exit 0 is not a verdict
    - Gaps become upstream issues
    """)
    return


@app.cell(hide_code=True)
def _s7(asset, head, mo):
    mo.vstack([
        head("## Our framework <!-- SLIDE:S7 -->\n\nDeclaration to realization"),
        mo.hstack([asset("framework-layers.png", width=1000)], justify="center"),
    ], gap=0.4)
    return


@app.cell(hide_code=True)
def _s8(
    DEMO_ENGINEER,
    head,
    assemble,
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
    symbolic_settling,
    to_elements,
    two_store_mermaid,
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
            # the thumbnail keeps the 15 pt text: a smaller canvas at lower dpi, shown at its natural 440 px
            "b2t": png(fg.settling_figure(_a["sim"], _a["t_sym"], _limit, title="", figsize=(6.4, 4.4)), dpi=69),
            # sized in inches so that the PNG's natural width is its display width: 15 pt text stays 18 px
            "b4": png(fg.overlay_figure(_a["sim"], _b["sim"], (_name(FIRST), _name(TUNED)), _limit, _band,
                                        figsize=(9, 4.2)), dpi=87),
            "b5": png(fg.neighbour_strip(_rows, _limit, figsize=(9, 3.9)), dpi=87),
            "b5t": png(fg.neighbour_strip(_rows, _limit, figsize=(5.4, 3.4)), dpi=96),
        },
        # a neighbour "splits" when exactly one of the two estimates is within the limit
        "n_flip": sum((r[1] <= _limit) != (r[2] <= _limit) for r in _rows[1:]),
        "n_nb": len(NEIGHBOURS),
        "lanes_b1": lanes_mermaid(to_elements(assemble(structure)), compact=True),
        "two_store": two_store_mermaid(),
    }

    name_in = mo.ui.text(value=DEMO_ENGINEER, label="Attesting as", full_width=False)
    btn_b3 = counter_button("Attest: not satisfied")
    btn_b5 = counter_button("Attest: satisfied")
    btn_b7 = mo.ui.run_button(label="Check the claim")

    head(
        "# Use it. Help build it. <!-- SLIDE:S8 -->\n\n"
        "- pip install opensysml\n"
        "- Replicate or fix three open issues:\n"
        "    - [github.com/Open-MBEE/sysmlv2-testing/issues/3](https://github.com/Open-MBEE/sysmlv2-testing/issues/3)\n"
        "    - [github.com/Open-MBEE/sysmlv2-testing/issues/4](https://github.com/Open-MBEE/sysmlv2-testing/issues/4)\n"
        "    - [github.com/Open-MBEE/OpenSysML/issues/1125](https://github.com/Open-MBEE/OpenSysML/issues/1125)\n"
        "- Join: openmbee.org. Demo: github.com/DynamicalSystemsGroup/ADCS-lifecycle-demo"
    )
    return D, btn_b3, btn_b5, btn_b7, name_in, structure


if __name__ == "__main__":
    app.run()
