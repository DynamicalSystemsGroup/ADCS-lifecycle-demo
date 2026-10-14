"""# From requirement to sign-off (SysML v2 demo)

One requirement, walked from text to a human's sign-off in beats B1 to B7.
This notebook is a thin presentation layer over `sysml/model.py` (assemble, evaluate),
`sysml/flexo_v2.py` (publish, diff) and `sysml/git_source.py` (Git SHA, text diff).

Live:      uv run marimo run sysml_notebook.py
Headless:  SYSML_DEMO_PRESEED=1 uv run marimo export html sysml_notebook.py -o output/sysml-talk-fallback.html
"""

import marimo

__generated_with = "0.22.5"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import html
    import math
    import os
    import re
    import uuid
    import warnings
    from collections import Counter

    import httpx
    import marimo as mo

    warnings.simplefilter("ignore")  # the model library flags its API-JSON export as experimental

    from analysis.load_params import load_params
    from analysis.numerical import run_step_response
    from evidence.hashing import hash_simulation
    from sysml.flexo_v2 import FlexoV2, NoChangeError, diff
    from sysml.git_source import head_sha, text_diff
    from sysml.model import (
        DEFAULT_ADEQUACY,
        PACKAGE,
        assemble,
        attestation_block,
        evaluate,
        evidence_block,
        load_structure,
        status_block,
        to_elements,
    )

    return (
        Counter,
        DEFAULT_ADEQUACY,
        FlexoV2,
        NoChangeError,
        PACKAGE,
        assemble,
        attestation_block,
        diff,
        evaluate,
        evidence_block,
        hash_simulation,
        head_sha,
        html,
        httpx,
        load_params,
        load_structure,
        math,
        mo,
        os,
        re,
        run_step_response,
        status_block,
        text_diff,
        to_elements,
        uuid,
    )


@app.cell(hide_code=True)
def _(head_sha, httpx, mo, os):
    # Headless export: SYSML_DEMO_PRESEED=1 pre-seeds the human attestations (the Attest steps
    # cannot be clicked in a static export) and publishes NOTHING to Flexo, even when it is
    # reachable. The export shows the element diff computed in-process and Git text diffs.
    # Flexo publishing happens live only.
    PRESEED = os.environ.get("SYSML_DEMO_PRESEED") == "1"
    SEED_NAME = "Demo Engineer"

    _url = os.environ.get("FLEXO_V2_URL", "http://localhost:8083").rstrip("/")
    try:
        FLEXO_UP = httpx.get(_url + "/projects", timeout=3).status_code == 200
    except (httpx.HTTPError, httpx.InvalidURL):
        FLEXO_UP = False
    FLEXO_PUBLISH = FLEXO_UP and not PRESEED

    GIT_SHA = head_sha(str(mo.notebook_dir()))

    def seed_label(action: str):
        """Visible label on every pre-seeded human step."""
        if not PRESEED:
            return mo.md("")
        return mo.callout(
            mo.md(f"**pre-seeded for export: in the live demo the speaker clicks {action}**"),
            kind="warn",
        )

    def sfx(n: int) -> str:
        """Heading suffix. A commit is promised only when publishing is live."""
        return f" (Flexo commit C{n})" if FLEXO_PUBLISH else " (Git-only: no Flexo commit)"

    if not FLEXO_UP:
        banner = mo.callout(
            mo.md(
                "**Git-only mode.** The Flexo service is not reachable. B3 and B5 show the "
                "Git text diff in place of the Flexo element diff."
            ),
            kind="warn",
        )
    elif PRESEED:
        banner = mo.callout(
            mo.md(
                "**Export mode.** Human steps are pre-seeded and nothing is published to Flexo. "
                "B3 and B5 show the Git text diff."
            ),
            kind="info",
        )
    else:
        banner = mo.callout(
            mo.md(f"Flexo is reachable. Source Git SHA: `{GIT_SHA[:12]}`."), kind="success"
        )
    banner
    return FLEXO_PUBLISH, GIT_SHA, PRESEED, SEED_NAME, seed_label, sfx


@app.cell(hide_code=True)
def _(
    Counter,
    FLEXO_PUBLISH,
    FlexoV2,
    GIT_SHA,
    NoChangeError,
    PACKAGE,
    PRESEED,
    diff,
    html,
    httpx,
    mo,
    to_elements,
    uuid,
):
    # Publishing glue and the B5 grouping. No model logic: the element export is
    # sysml.model.to_elements, the diff is sysml.flexo_v2.diff.
    flexo = FlexoV2() if FLEXO_PUBLISH else None

    # One Flexo project per notebook session, created on the first publish and reused after.
    # The projects are named sysml-talk-<random>; they are NOT deleted, so every earlier
    # session leaves one behind. Remove them with FlexoV2().delete_project(<id>).
    project = {}

    # Reactivity guards. Editing a text area re-runs the cells that read it; these two dicts
    # make sure that re-run never acts again.
    handled = {}  # button key -> click count already acted on (a re-run with the same count is a no-op)
    frozen = {}  # the adequacy text as recorded at the first Attest; later edits do not change evidence

    def should_fire(key: str, clicks: int) -> bool:
        """True once per new click (clicks > last handled); pre-seeded export fires once."""
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

    def diff_view(patch: str):
        """A unified diff with removed and added lines tinted."""
        rows = []
        for line in patch.splitlines():
            bg = ("rgba(220,60,60,.18)" if line.startswith("-") and not line.startswith("---")
                  else "rgba(60,170,80,.18)" if line.startswith("+") and not line.startswith("+++")
                  else "transparent")
            rows.append(f'<span style="display:block;background:{bg}">{html.escape(line) or " "}</span>')
        return mo.Html('<pre style="font-size:0.8em;overflow-x:auto">' + "".join(rows) + "</pre>")

    def tag_of(commit_id: str) -> str:
        return f"git-{flexo.git_sha(project['id'], commit_id)}"

    def by_id(elements: list[dict]) -> dict[str, dict]:
        return {e["@id"]: e for e in elements}

    def _owner(e: dict):
        return (e.get("owner") or {}).get("@id")

    def group_diff(old: dict, new: dict) -> dict:
        """Group the element diff of two snapshots (keyed by @id), from @type and ownership:
        user-model elements are those whose owner chain reaches the model package, the rest
        are standard-library definitions. Nothing is typed in by hand."""
        d = diff(old, new)

        def in_user_model(i, snap):
            for _ in range(200):
                if i == PACKAGE:
                    return True
                i = _owner(snap[i]) if i in snap else None
                if i is None:
                    return False
            return False

        def top_element(i, snap):
            """The user-model element directly under the package that holds `i`; a membership
            is resolved to the element it owns."""
            for _ in range(200):
                o = _owner(snap[i])
                if o == PACKAGE or o is None or o not in snap:
                    break
                i = o
            e = snap[i]
            if e["@type"] == "OwningMembership":
                i = e["memberElement"]["@id"]
            return snap[i]

        att, att_roots, lib, other = [], Counter(), [], Counter()
        for i in d["added"]:
            if not in_user_model(i, new):
                lib.append(i)
                continue
            root = top_element(i, new)
            targets = [new[t["@id"]] for t in root.get("annotatedElement", []) if t["@id"] in new]
            is_att = root["@type"] == "SatisfyRequirementUsage" or (
                root["@type"] == "MetadataUsage"
                and any(t["@type"] == "SatisfyRequirementUsage" and t["@id"] in d["added"] for t in targets)
            )
            if is_att:
                att.append(i)
                if root["@id"] == i:
                    att_roots[root["@type"]] += 1
            else:
                other[f"added {new[i]['@type']}"] += 1
        pkg_grew = 0
        for i in d["changed"]:
            members_old = {m["@id"] for m in old[i].get("ownedRelationship", [])}
            members_new = {m["@id"] for m in new[i].get("ownedRelationship", [])}
            if i == PACKAGE and members_old < members_new:
                pkg_grew = len(members_new - members_old)
            else:
                other[f"changed {new[i]['@type']}"] += 1
        for i in d["removed"]:
            other[f"removed {old[i]['@type']}"] += 1
        return {"att": len(att), "att_roots": att_roots, "pkg_grew": pkg_grew,
                "lib": len(lib), "other": other}

    def groups_view(g: dict, c_from: str, c_to: str, how: str):
        """The three approved groups, live counts only. The closing line is shown only when
        nothing falls outside them."""
        roots = ", ".join(f"{t} x{n}" for t, n in sorted(g["att_roots"].items())) or "none"
        parts = [
            mo.md(
                f"**Element diff {c_from} to {c_to}** ({how}), grouped by what each element is\n\n"
                f"- attestation elements added: {g['att']} (top-level: {roots})\n"
                f"- owning package changed (member list grew): {1 if g['pkg_grew'] else 0}"
                f" (+{g['pkg_grew']} members)\n"
                f"- standard-library definitions referenced by the attestation metadata: {g['lib']}"
            )
        ]
        if g["other"]:
            outside = ", ".join(f"{k} x{n}" for k, n in sorted(g["other"].items()))
            parts.append(
                mo.callout(
                    mo.md(
                        f"**Warning: not everything in this diff is the attestation or what it "
                        f"references.** Outside the three groups: {outside}. The statement that no "
                        "evidence or design element changed is therefore not made."
                    ),
                    kind="danger",
                )
            )
        else:
            parts.append(
                mo.md(
                    f"Everything new in {c_to} is the human's attestation and what it "
                    "references; no evidence or design element changed."
                )
            )
        return mo.vstack(parts)

    return (
        by_id,
        counter_button,
        diff_view,
        flexo,
        frozen,
        group_diff,
        groups_view,
        once,
        project,
        publish_snapshot,
        should_fire,
        tag_of,
    )


@app.cell(hide_code=True)
def _(mo):
    get_c1, set_c1 = mo.state(None)
    get_c2, set_c2 = mo.state(None)
    get_c3, set_c3 = mo.state(None)
    get_b6, set_b6 = mo.state(None)
    get_b7, set_b7 = mo.state(None)
    return get_b6, get_b7, get_c1, get_c2, get_c3, set_b6, set_b7, set_c1, set_c2, set_c3


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # From requirement to human sign-off

    *requirement → evidence → automated verdict → human attestation.*
    A tool can say **pass**. Only a person can say **satisfied**.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## BEAT:B1 · One file, three blocks, three owners
    """)
    return


@app.cell(hide_code=True)
def _(load_structure, mo, re):
    structure = load_structure()
    _blocks = []
    for _req, _usage in (("REQ-001", "req001 : SettlingRequirement;"), ("REQ-004", "req004 : DisturbanceRequirement;")):
        _m = re.search(rf"// {_req}\..*?requirement {re.escape(_usage)}", structure, re.S)
        _blocks.append(_m.group(0) if _m else f"// {_req}: block not found")
    mo.vstack(
        [
            mo.md(
                "satisfy = a person's claim that a requirement is met; "
                "StatusInfo = who and status (tbc = pending, done = attested); "
                "Rationale = the person's reasons"
            ),
            mo.md("**Structure** (hand-authored, versioned in Git): REQ-001 and REQ-004"),
            mo.md("```text\n" + "\n\n".join(_blocks) + "\n```"),
            mo.accordion({"Full structure listing (sysml/satellite.sysml)": mo.md(f"```text\n{structure}\n```")}),
            mo.md("**Evidence** (written by Python from the simulation): not yet written"),
            mo.md("**Attestation** (written only by a human): not yet written"),
        ]
    )
    return (structure,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## BEAT:B2 · Python computes, we hash, OpenSysML evaluates
    """)
    return


@app.cell(hide_code=True)
def _(DEFAULT_ADEQUACY, mo):
    adequacy = mo.ui.text_area(
        value=DEFAULT_ADEQUACY,
        label="Model adequacy: the human's draft, carried with the evidence as a Rationale",
        full_width=True,
        rows=3,
    )
    adequacy
    return (adequacy,)


@app.cell(hide_code=True)
def _(
    adequacy,
    assemble,
    evaluate,
    evidence_block,
    frozen,
    hash_simulation,
    load_params,
    mo,
    run_step_response,
    structure,
):
    # Inputs of the first design. The adequacy text is the one recorded at the first Attest,
    # once there is one; editing the box afterwards does not change the evidence.
    KP1, KD1 = 1.0, 10.0
    params1 = dict(load_params(), Kp=KP1, Kd=KD1)
    sim1 = run_step_response(params1)
    summary1 = sim1.summary()
    hash1 = hash_simulation(sim1.config.to_dict(), summary1)
    ev1 = evidence_block("initial", params1, summary1, hash1, frozen.get("adequacy", adequacy.value))
    model_b2 = assemble(structure, ev1)
    res_b2 = evaluate(model_b2)
    verdict_b2 = res_b2["verdicts"]["vc001_initial"]

    mo.vstack(
        [
            mo.md(
                f"Step response at Kp={KP1}, Kd={KD1}. Computed settling time: "
                f"**{summary1['settling_time_s']:.1f} s** (requirement: at most 120 s). "
                f"Evidence hash: `sha256:{hash1[:16]}...`"
            ),
            mo.md(f"```text\n{ev1}\n```"),
            mo.callout(
                mo.md(
                    f"OpenSysML evaluates the evidence block: verdict **{verdict_b2}**. "
                    "That is verification, an automated check. Nobody has said satisfied."
                ),
                kind="danger" if verdict_b2 == "fail" else "success",
            ),
        ]
    )
    return ev1, model_b2


@app.cell(hide_code=True)
def _(mo, sfx):
    mo.md(f"""
    ## BEAT:B3 · The human attests *not satisfied*{sfx(1)}
    """)
    return


@app.cell(hide_code=True)
def _(PRESEED, SEED_NAME, counter_button, mo, seed_label):
    name_in = mo.ui.text(
        value=SEED_NAME if PRESEED else "", label="Engineer name", full_width=True
    )
    suff_b3 = mo.ui.text_area(
        value=(
            "One step-response simulation. Enough to say the requirement is not met; "
            "not enough to say it would be met on the real satellite."
        ),
        label="Evidence sufficiency (a justification): the human's draft",
        full_width=True,
        rows=3,
    )
    btn_b3 = counter_button("Attest: not satisfied")
    mo.vstack(
        [
            mo.md("Adequacy is the text from B2 above. The attestation block is written only by this click."),
            name_in,
            suff_b3,
            btn_b3,
            seed_label("Attest"),
        ]
    )
    return btn_b3, name_in, suff_b3


@app.cell(hide_code=True)
def _(
    adequacy,
    assemble,
    attestation_block,
    btn_b3,
    ev1,
    frozen,
    mo,
    name_in,
    publish_snapshot,
    set_c1,
    should_fire,
    structure,
    suff_b3,
):
    mo.stop(not should_fire("b3", btn_b3.value))
    try:
        _att = attestation_block(
            "initial", False, name_in.value, "done", suff_b3.value, "vc001_initial"
        )
        _text = assemble(structure, ev1, _att)
        frozen.setdefault("adequacy", adequacy.value)  # evidence is fixed from the first Attest on
        _commit, _note = publish_snapshot("C1: human attests not satisfied", _text)
        set_c1(
            {"who": name_in.value.strip(), "att": _att, "text": _text,
             "commit": _commit, "note": _note}
        )
    except ValueError as _e:
        set_c1({"error": str(_e)})
    return


@app.cell(hide_code=True)
def _(adequacy, diff_view, frozen, get_c1, mo, model_b2, tag_of, text_diff):
    _c1 = get_c1()
    if _c1 is None:
        _out = mo.md("*Attestation pending: nothing written yet.*")
    elif "error" in _c1:
        _out = mo.callout(mo.md(f"Not recorded: {_c1['error']}"), kind="danger")
    else:
        _parts = [
            mo.md(
                f"**Attestation block** written by {_c1['who']}: a named `satisfy` that says "
                "*not satisfied*, with status `done` and the sufficiency Rationale."
            ),
            mo.md(f"```text\n{_c1['att']}\n```"),
        ]
        if _c1["commit"]:
            _parts.append(
                mo.md(
                    "Published to Flexo as **C1**. Each Flexo commit is tagged with the Git SHA "
                    f"of the source that produced it: tag `{tag_of(_c1['commit'])}`."
                )
            )
        else:
            _parts += [
                mo.md("Git text diff of this change (B2 model to B3 model):"),
                diff_view(text_diff(model_b2, _c1["text"])),
            ]
        if _c1["note"]:
            _parts.append(mo.callout(mo.md(_c1["note"]), kind="warn"))
        if frozen.get("adequacy") not in (None, adequacy.value):
            _parts.append(
                mo.callout(
                    mo.md("The adequacy text was edited after Attest. The recorded evidence and "
                          "any published commit keep the text as it was at Attest."),
                    kind="warn",
                )
            )
        _out = mo.vstack(_parts)
    _out
    return


@app.cell(hide_code=True)
def _(mo, sfx):
    mo.md(f"""
    ## BEAT:B4 · Retune, re-evaluate: the attestation is removed, status is pending{sfx(2)}
    """)
    return


@app.cell(hide_code=True)
def _(
    adequacy,
    assemble,
    evaluate,
    evidence_block,
    frozen,
    hash_simulation,
    load_params,
    mo,
    run_step_response,
    status_block,
    structure,
):
    # The retune is one fixed, explicit change.
    KP2, KD2 = 4.0, 30.0
    params2 = dict(load_params(), Kp=KP2, Kd=KD2)
    sim2 = run_step_response(params2)
    summary2 = sim2.summary()
    hash2 = hash_simulation(sim2.config.to_dict(), summary2)
    ev2 = evidence_block("tuned", params2, summary2, hash2, frozen.get("adequacy", adequacy.value))
    # Pending marker: StatusInfo tbc about req001, no originator, no rationale. Python writes it,
    # so it sits in the generated block; no person has acted, so it names no person.
    pending = status_block("req001")
    model_b4 = assemble(structure, ev2 + pending)
    res_b4 = evaluate(model_b4)
    verdict_b4 = res_b4["verdicts"]["vc001_tuned"]

    mo.vstack(
        [
            mo.md(
                f"Retuned to Kp={KP2}, Kd={KD2}. Re-run, re-hash, re-evaluate. "
                f"Computed settling time: **{summary2['settling_time_s']:.1f} s**. "
                f"Evidence hash: `sha256:{hash2[:16]}...`"
            ),
            mo.callout(
                mo.md(
                    "The evidence changed, so the prior attestation no longer applies and is "
                    f"removed. The verdict is **{verdict_b4}**. Status is pending: no person has "
                    "judged the new evidence yet."
                ),
                kind="success" if verdict_b4 == "pass" else "danger",
            ),
            mo.md("**Generated by Python** (not written by a person): the pending status"),
            mo.md(f"```text\n{pending}\n```"),
        ]
    )
    return ev2, model_b4, params2, res_b4, summary2, verdict_b4


@app.cell(hide_code=True)
def _(diff_view, get_c1, mo, model_b4, text_diff):
    _c1 = get_c1()
    if _c1 is None or "error" in _c1:
        _out = mo.md("*The text diff from the C1 model appears after the attestation in B3.*")
    else:
        _out = mo.vstack(
            [
                mo.md("Git text diff, C1 model to this model. The `not satisfy` line is gone:"),
                diff_view(text_diff(_c1["text"], model_b4)),
            ]
        )
    _out
    return


@app.cell(hide_code=True)
def _(get_c1, model_b4, once, publish_snapshot, set_c2):
    # Live mode only (publish_snapshot is a no-op without Flexo). Runs once, after C1 exists, so
    # C2 always follows C1 and there is no separate click. Later re-runs (edits upstream) do not
    # publish again.
    _c1 = get_c1()
    if _c1 is not None and "error" not in _c1 and once("c2"):
        _commit, _note = publish_snapshot("C2: retune, attestation removed, status pending", model_b4)
        set_c2({"commit": _commit, "note": _note})
    return


@app.cell(hide_code=True)
def _(get_c2, mo, tag_of):
    _c2 = get_c2()
    _parts = []
    if _c2 and _c2["commit"]:
        _parts.append(mo.md(f"Published to Flexo as **C2**, tagged `{tag_of(_c2['commit'])}`."))
    if _c2 and _c2["note"]:
        _parts.append(mo.callout(mo.md(_c2["note"]), kind="warn"))
    mo.vstack(_parts)
    return


@app.cell(hide_code=True)
def _(mo, sfx):
    mo.md(f"""
    ## BEAT:B5 · The human clicks Attest{sfx(3)}
    """)
    return


@app.cell(hide_code=True)
def _(counter_button, mo, name_in, seed_label):
    suff_b5 = mo.ui.text_area(
        value=(
            "One step-response simulation within the stated model. Enough for me to "
            "attest that the settling-time requirement is met; adequacy is recorded separately."
        ),
        label="Evidence sufficiency (a justification): the human's draft",
        full_width=True,
        rows=3,
    )
    btn_b5 = counter_button("Attest: satisfied")
    mo.vstack(
        [
            mo.md(f"Attesting as: {name_in.value.strip() or '(enter the engineer name in B3)'}"),
            suff_b5,
            btn_b5,
            seed_label("Attest"),
        ]
    )
    return btn_b5, suff_b5


@app.cell(hide_code=True)
def _(
    assemble,
    attestation_block,
    btn_b5,
    by_id,
    ev2,
    flexo,
    get_c2,
    group_diff,
    mo,
    model_b4,
    name_in,
    project,
    publish_snapshot,
    set_c3,
    should_fire,
    structure,
    suff_b5,
    to_elements,
):
    mo.stop(not should_fire("b5", btn_b5.value))
    try:
        _att = attestation_block(
            "tuned", True, name_in.value, "done", suff_b5.value, "vc001_tuned"
        )
        _text = assemble(structure, ev2, _att)
        _commit, _note = publish_snapshot("C3: human attests satisfied", _text)
        _c2 = get_c2()
        if _commit and _c2 and _c2["commit"]:
            _old = flexo.elements(project["id"], _c2["commit"])
            _new = flexo.elements(project["id"], _commit)
            _how = "from the two Flexo commits"
        else:  # export, Git-only mode, or C2/C3 not both committed: diff the two snapshots in-process
            _old = by_id(to_elements(model_b4))
            _new = by_id(to_elements(_text))
            _how = "computed in-process from the two model snapshots; nothing published"
        set_c3(
            {"who": name_in.value.strip(), "att": _att, "text": _text, "commit": _commit,
             "note": _note, "groups": group_diff(_old, _new), "how": _how}
        )
    except ValueError as _e:
        set_c3({"error": str(_e)})
    return


@app.cell(hide_code=True)
def _(diff_view, get_c1, get_c2, get_c3, groups_view, mo, model_b4, tag_of, text_diff):
    _c3 = get_c3()
    if _c3 is None:
        _out = mo.md("*Status is pending (`tbc`): no attestation written yet.*")
    elif "error" in _c3:
        _out = mo.callout(mo.md(f"Not recorded: {_c3['error']}"), kind="danger")
    else:
        _parts = [
            mo.md(
                f"**Attestation block** written by {_c3['who']}: a named `satisfy` "
                "with status `done`."
            ),
            mo.md(f"```text\n{_c3['att']}\n```"),
        ]
        if _c3["commit"]:
            _tags = [
                f"- {_n}: tag `{tag_of(_s['commit'])}`"
                for _n, _s in (("C1", get_c1()), ("C2", get_c2()), ("C3", _c3))
                if _s and _s.get("commit")
            ]
            _shas = {t.split("`")[1] for t in _tags}
            _same = (
                "\n\nThe tags are the same Git SHA because the source did not change during the demo."
                if len(_tags) > 1 and len(_shas) == 1
                else ""
            )
            _parts.append(
                mo.md(
                    "Each Flexo commit is tagged with the Git SHA of the source that produced it:\n\n"
                    + "\n".join(_tags) + _same
                )
            )
        else:
            _parts += [
                mo.md("Git text diff of this change (B4 model to B5 model):"),
                diff_view(text_diff(model_b4, _c3["text"])),
            ]
        _parts.append(groups_view(_c3["groups"], "C2", "C3", _c3["how"]))
        if _c3["note"]:
            _parts.append(mo.callout(mo.md(_c3["note"]), kind="warn"))
        _out = mo.vstack(_parts)
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## BEAT:B6 · REQ-004 stays inconclusive: only a human can close it
    """)
    return


@app.cell(hide_code=True)
def _(counter_button, mo, seed_label, structure):
    import re as _re

    _doc = _re.search(r"requirement def DisturbanceRequirement \{\s*doc /\*(.*?)\*/", structure, _re.S)
    req004_text = " ".join(_doc.group(1).split())
    margin_in = mo.ui.text_area(
        value=(
            "Residual uncertainty: the model clips torque at the actuator limit, so the "
            "margin to the real limit is not known from this evidence."
        ),
        label="Saturation margin, recorded by the human as residual uncertainty",
        full_width=True,
        rows=3,
    )
    btn_b6 = counter_button("Record (status stays tbc)")
    mo.vstack([margin_in, btn_b6, seed_label("Record")])
    return btn_b6, margin_in, req004_text


@app.cell(hide_code=True)
def _(
    PRESEED,
    SEED_NAME,
    assemble,
    btn_b6,
    ev2,
    evaluate,
    get_c3,
    margin_in,
    mo,
    name_in,
    set_b6,
    should_fire,
    status_block,
    structure,
):
    mo.stop(not should_fire("b6", btn_b6.value))
    _who = (name_in.value.strip() or SEED_NAME) if PRESEED else name_in.value.strip()
    try:
        _block = status_block("req004", originator=_who, rationale=margin_in.value)
        _c3 = get_c3()
        _prior = _c3["att"] if _c3 and "att" in _c3 else ""
        _text = assemble(structure, ev2, _prior + _block)
        set_b6({"who": _who, "block": _block, "res": evaluate(_text)})
    except ValueError:
        set_b6({"error": "Enter the engineer name in B3: the margin must be recorded by a named human."})
    return


@app.cell(hide_code=True)
def _(get_b6, math, mo, params2, req004_text, res_b4, summary2):
    _peak = summary2["peak_control_torque"]
    _limit = params2["maxTorque"]
    _verdict = res_b4["verdicts"]["vc004_tuned"]
    _holds = res_b4["req"]["req004(tuned)"]
    if math.isclose(_peak, _limit, rel_tol=1e-9):
        _why = (
            f"The constraint holds because peak torque ({_peak:.3g} N·m) equals the actuator "
            f"limit ({_limit:.3g} N·m): the simulation clips torque (`np.clip`). The model "
            "cannot represent an over-capacity command. That is a model-adequacy question, "
            "recorded as a Rationale (an assumption), not evidence of satisfaction."
        )
    else:
        _why = (
            f"Peak torque ({_peak:.3g} N·m) differs from the actuator limit ({_limit:.3g} N·m) "
            f"in this run, and the constraint evaluates {_holds}. The torque-clipping "
            "explanation does not apply here."
        )
    _parts = [
        mo.md(f"REQ-004, verbatim: *{req004_text}*"),
        mo.callout(
            mo.md(
                f"OpenSysML verdict: **{_verdict}**. No automated verdict was declared, by "
                "design: the method is analysis requiring judgment."
            ),
            kind="neutral",
        ),
        mo.md(_why),
    ]
    _b6 = get_b6()
    if _b6 is None:
        _parts.append(mo.md("*Margin not yet recorded. Status: `tbc`.*"))
    elif "error" in _b6:
        _parts.append(mo.callout(mo.md(_b6["error"]), kind="danger"))
    else:
        _parts += [
            mo.md(f"Recorded by {_b6['who']}. Status stays `tbc`; no `satisfy` is written for REQ-004."),
            mo.md(f"```text\n{_b6['block']}\n```"),
            mo.md(f"Verdict after recording: **{_b6['res']['verdicts']['vc004_tuned']}**."),
        ]
    mo.vstack(_parts)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## BEAT:B7 · (optional) Checking a human's claim for consistency
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    btn_b7 = mo.ui.run_button(label="Write a contradicting claim")
    return (btn_b7,)


@app.cell(hide_code=True)
def _(
    PRESEED,
    SEED_NAME,
    assemble,
    attestation_block,
    btn_b7,
    ev1,
    evaluate,
    mo,
    name_in,
    set_b7,
    structure,
):
    mo.stop(not (btn_b7.value or PRESEED))
    # "Satisfied" on the design whose verdict is fail, under the human's own name from the form.
    # Illustrative only; it is never published.
    _who = (name_in.value.strip() or SEED_NAME) if PRESEED else name_in.value.strip()
    try:
        _claim = attestation_block(
            "initial", True, _who, "tbc", "Illustrative claim for the check only.", "vc001_initial"
        )
        _res = evaluate(assemble(structure, ev1, _claim))
        set_b7({"claim": _claim, "holds": _res["claims"]["att_initial"]["holds"]})
    except ValueError:
        set_b7({"error": "Enter the engineer name in B3: the claim is written under a named human."})
    return


@app.cell(hide_code=True)
def _(PRESEED, btn_b7, get_b7, mo, seed_label):
    _b7 = get_b7()
    if _b7 is None:
        _result = mo.md("")
    elif "error" in _b7:
        _result = mo.callout(mo.md(_b7["error"]), kind="danger")
    else:
        _result = mo.vstack(
            [
                seed_label("Write a contradicting claim"),
                mo.md(f"```text\n{_b7['claim']}\n```"),
                mo.md(
                    "`verify_satisfaction` on this illustrative claim: consistent with the "
                    f"evaluated model = **{_b7['holds']}**."
                ),
                mo.md(
                    "The tool checks that the human's claim is consistent with the evaluated model. "
                    "That is verification of the claim. It is not the attestation, and it says "
                    "nothing about the physical satellite."
                ),
            ]
        )
    _intro = mo.md("A `satisfy` of *satisfied* on the design whose verdict is fail, under your name from B3.")
    if PRESEED:  # static export: the result sits inside the accordion
        _out = mo.accordion({"Show the check": mo.vstack([_intro, btn_b7, _result])})
    else:  # live: the accordion would re-collapse on every update, so the result sits below it
        _out = mo.vstack([mo.accordion({"Show the check": mo.vstack([_intro, btn_b7])}), _result])
    _out
    return


if __name__ == "__main__":
    app.run()
