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
    import json
    import os
    import uuid
    import warnings
    from collections import Counter

    import httpx
    import marimo as mo
    import opensysml

    warnings.simplefilter("ignore")  # opensysml flags its API-JSON export as experimental

    from analysis.load_params import load_params
    from analysis.numerical import run_step_response
    from evidence.hashing import hash_simulation
    from sysml.flexo_v2 import FlexoV2, NoChangeError, diff
    from sysml.git_source import head_sha, text_diff
    from sysml.model import (
        DEFAULT_ADEQUACY,
        NOT_A_HUMAN,
        VERSION,
        assemble,
        attestation_block,
        evaluate,
        evidence_block,
        load_structure,
    )

    return (
        Counter,
        DEFAULT_ADEQUACY,
        FlexoV2,
        NOT_A_HUMAN,
        NoChangeError,
        VERSION,
        assemble,
        attestation_block,
        diff,
        evaluate,
        evidence_block,
        hash_simulation,
        head_sha,
        httpx,
        json,
        load_params,
        load_structure,
        mo,
        opensysml,
        os,
        run_step_response,
        text_diff,
        uuid,
    )


@app.cell(hide_code=True)
def _(head_sha, httpx, mo, os):
    # Headless export: SYSML_DEMO_PRESEED=1 pre-seeds the human attestations (the Attest steps
    # cannot be clicked in a static export) and publishes NOTHING to Flexo, even when it is
    # reachable. The export shows Git text diffs instead. Flexo publishing happens live only.
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
    return FLEXO_PUBLISH, GIT_SHA, PRESEED, SEED_NAME, seed_label


@app.cell(hide_code=True)
def _(FLEXO_PUBLISH, FlexoV2, GIT_SHA, NoChangeError, VERSION, httpx, json, opensysml, uuid):
    # Publishing glue only. Which elements go to Flexo comes from OpenSysML's API JSON export;
    # sysml/model.py has no helper for that yet (reported as a gap).
    flexo = FlexoV2() if FLEXO_PUBLISH else None
    project = {}

    def snapshot(text: str) -> list[dict]:
        conn = opensysml.connect(version=VERSION)
        try:
            return json.loads(conn.load_from_content(text, strict=True).to_api_json().content)
        finally:
            conn.close()

    def publish_snapshot(label: str, text: str):
        """Return (commit_id or None, note or None). Never raises on an unchanged snapshot."""
        if flexo is None:
            return None, None
        try:
            if "id" not in project:
                project["id"] = flexo.ensure_project(f"sysml-talk-{uuid.uuid4().hex[:8]}")
            return flexo.publish(project["id"], snapshot(text), label, GIT_SHA), None
        except NoChangeError:
            return None, "No change: the snapshot is identical to the head, so Flexo made no commit."
        except httpx.HTTPError as e:
            return None, f"Flexo publish failed ({type(e).__name__}); continuing without it."

    return flexo, project, publish_snapshot


@app.cell(hide_code=True)
def _(mo):
    get_c1, set_c1 = mo.state(None)
    get_c2, set_c2 = mo.state(None)
    get_c3, set_c3 = mo.state(None)
    get_b6, set_b6 = mo.state(None)
    return get_b6, get_c1, get_c2, get_c3, set_b6, set_c1, set_c2, set_c3


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
def _(load_structure, mo):
    structure = load_structure()
    mo.vstack(
        [
            mo.md("**Structure** (hand-authored, versioned in Git): `sysml/satellite.sysml`"),
            mo.md(f"```text\n{structure}\n```"),
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
    hash_simulation,
    load_params,
    mo,
    run_step_response,
    structure,
):
    # Inputs of the first design.
    KP1, KD1 = 1.0, 10.0
    params1 = dict(load_params(), Kp=KP1, Kd=KD1)
    sim1 = run_step_response(params1)
    summary1 = sim1.summary()
    hash1 = hash_simulation(sim1.config.to_dict(), summary1)
    ev1 = evidence_block("initial", params1, summary1, hash1, adequacy.value)
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
    return ev1, model_b2, summary1


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## BEAT:B3 · The human attests *not satisfied* (Flexo commit C1)
    """)
    return


@app.cell(hide_code=True)
def _(PRESEED, SEED_NAME, mo, seed_label):
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
    btn_b3 = mo.ui.run_button(label="Attest: not satisfied")
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
    PRESEED,
    assemble,
    attestation_block,
    btn_b3,
    ev1,
    evaluate,
    mo,
    name_in,
    publish_snapshot,
    set_c1,
    structure,
    suff_b3,
):
    mo.stop(not (btn_b3.value or PRESEED))
    try:
        _att = attestation_block(
            "initial", False, name_in.value, "done", suff_b3.value, "vc001_initial"
        )
        _text = assemble(structure, ev1, _att)
        _res = evaluate(_text)
        _commit, _note = publish_snapshot("C1: human attests not satisfied", _text)
        set_c1(
            {"who": name_in.value.strip(), "att": _att, "text": _text, "res": _res,
             "commit": _commit, "note": _note}
        )
    except ValueError as _e:
        set_c1({"error": str(_e)})
    return


@app.cell(hide_code=True)
def _(flexo, get_c1, mo, model_b2, project, text_diff):
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
            _sha = flexo.git_sha(project["id"], _c1["commit"])
            _parts.append(
                mo.md(f"Published to Flexo as **C1**. Each Flexo commit is tagged with the Git SHA of the source that produced it: tag `git-{_sha[:12]}`.")
            )
        else:
            _parts.append(
                mo.md("Git text diff of this change (B2 model to B3 model):\n\n"
                      f"```diff\n{text_diff(model_b2, _c1['text'])}\n```")
            )
        if _c1["note"]:
            _parts.append(mo.callout(mo.md(_c1["note"]), kind="warn"))
        _out = mo.vstack(_parts)
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## BEAT:B4 · Retune, re-evaluate: the attestation resets to pending (Flexo commit C2)
    """)
    return


@app.cell(hide_code=True)
def _(
    FLEXO_PUBLISH,
    adequacy,
    assemble,
    evaluate,
    evidence_block,
    hash_simulation,
    load_params,
    mo,
    run_step_response,
    structure,
):
    # The retune is one fixed, explicit change.
    KP2, KD2 = 4.0, 30.0
    params2 = dict(load_params(), Kp=KP2, Kd=KD2)
    sim2 = run_step_response(params2)
    summary2 = sim2.summary()
    hash2 = hash_simulation(sim2.config.to_dict(), summary2)
    ev2 = evidence_block("tuned", params2, summary2, hash2, adequacy.value)
    model_b4 = assemble(structure, ev2)
    res_b4 = evaluate(model_b4)
    verdict_b4 = res_b4["verdicts"]["vc001_tuned"]

    btn_c2 = mo.ui.run_button(label="Publish C2")
    mo.vstack(
        [
            mo.md(
                f"Retuned to Kp={KP2}, Kd={KD2}. Re-run, re-hash, re-evaluate. "
                f"Computed settling time: **{summary2['settling_time_s']:.1f} s**. "
                f"Evidence hash: `sha256:{hash2[:16]}...`"
            ),
            mo.callout(
                mo.md(f"Automated verdict: **{verdict_b4}**."),
                kind="success" if verdict_b4 == "pass" else "danger",
            ),
            mo.md(
                "The earlier attestation was about the earlier design. For this design the "
                "attestation is pending (`tbc`): no `satisfy` is written."
            ),
            btn_c2 if FLEXO_PUBLISH else mo.md(""),
        ]
    )
    return (
        btn_c2,
        ev2,
        model_b4,
        params2,
        res_b4,
        summary2,
        verdict_b4,
    )


@app.cell(hide_code=True)
def _(btn_c2, mo, model_b4, publish_snapshot, set_c2):
    mo.stop(not btn_c2.value)
    _commit, _note = publish_snapshot("C2: retune, attestation pending", model_b4)
    set_c2({"commit": _commit, "note": _note})
    return


@app.cell(hide_code=True)
def _(flexo, get_c2, mo, project):
    _c2 = get_c2()
    if _c2 is None:
        _out = mo.md("")
    else:
        _parts = []
        if _c2["commit"]:
            _sha = flexo.git_sha(project["id"], _c2["commit"])
            _parts.append(mo.md(f"Published to Flexo as **C2**, tagged `git-{_sha[:12]}`."))
        if _c2["note"]:
            _parts.append(mo.callout(mo.md(_c2["note"]), kind="warn"))
        _out = mo.vstack(_parts)
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## BEAT:B5 · The human clicks Attest (Flexo commit C3)
    """)
    return


@app.cell(hide_code=True)
def _(mo, name_in, seed_label):
    suff_b5 = mo.ui.text_area(
        value=(
            "One step-response simulation within the stated model. Enough for me to "
            "attest that the settling-time requirement is met; adequacy is recorded separately."
        ),
        label="Evidence sufficiency (a justification): the human's draft",
        full_width=True,
        rows=3,
    )
    btn_b5 = mo.ui.run_button(label="Attest: satisfied")
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
    Counter,
    PRESEED,
    assemble,
    attestation_block,
    btn_b5,
    diff,
    ev2,
    evaluate,
    flexo,
    get_c2,
    mo,
    name_in,
    project,
    publish_snapshot,
    set_c3,
    structure,
    suff_b5,
):
    mo.stop(not (btn_b5.value or PRESEED))
    try:
        _att = attestation_block(
            "tuned", True, name_in.value, "done", suff_b5.value, "vc001_tuned"
        )
        _text = assemble(structure, ev2, _att)
        _res = evaluate(_text)
        _commit, _note = publish_snapshot("C3: human attests satisfied", _text)
        _delta = None
        _c2 = get_c2()
        if _commit and _c2 and _c2["commit"]:
            _a = flexo.elements(project["id"], _c2["commit"])
            _b = flexo.elements(project["id"], _commit)
            _d = diff(_a, _b)
            _delta = {
                "added": dict(Counter(_b[i]["@type"] for i in _d["added"])),
                "removed": len(_d["removed"]),
                "changed": [(i, _b[i]["@type"]) for i in _d["changed"]],
            }
        set_c3(
            {"who": name_in.value.strip(), "att": _att, "text": _text, "res": _res,
             "commit": _commit, "note": _note, "delta": _delta}
        )
    except ValueError as _e:
        set_c3({"error": str(_e)})
    return


@app.cell(hide_code=True)
def _(flexo, get_c1, get_c2, get_c3, mo, model_b4, project, text_diff):
    _c3 = get_c3()
    if _c3 is None:
        _out = mo.md("*Attestation pending (`tbc`): nothing written yet.*")
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
            _tags = []
            for _n, _s in (("C1", get_c1()), ("C2", get_c2()), ("C3", _c3)):
                if _s and _s.get("commit"):
                    _sha = flexo.git_sha(project["id"], _s["commit"])
                    _tags.append(f"- {_n}: tag `git-{_sha[:12]}`")
            _parts.append(mo.md("Each Flexo commit is tagged with the Git SHA of the source that produced it:\n\n" + "\n".join(_tags)))
            _d = _c3["delta"]
            if _d:
                _added = ", ".join(f"{_k}: {_v}" for _k, _v in sorted(_d["added"].items()))
                _chg = ", ".join(f"{_t} `{_i}`" for _i, _t in _d["changed"])
                _parts.append(
                    mo.md(
                        "**Flexo diff C2 to C3** (by element id)\n\n"
                        f"- added, by type: {_added}\n"
                        f"- changed: {_chg or 'none'}\n"
                        f"- removed: {_d['removed']}"
                    )
                )
            else:
                _parts.append(mo.md("*Flexo diff C2 to C3 needs both commits; publish C2 in B4 first.*"))
        else:
            _parts.append(
                mo.md("Git text diff of this change (B4 model to B5 model):\n\n"
                      f"```diff\n{text_diff(model_b4, _c3['text'])}\n```")
            )
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
def _(mo, seed_label, structure):
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
    btn_b6 = mo.ui.run_button(label="Record (status stays tbc)")
    mo.vstack([margin_in, btn_b6, seed_label("Record")])
    return btn_b6, margin_in, req004_text


@app.cell(hide_code=True)
def _(
    NOT_A_HUMAN,
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
    structure,
):
    mo.stop(not (btn_b6.value or PRESEED))
    _who = name_in.value.strip() or SEED_NAME if PRESEED else name_in.value.strip()
    if not _who or _who.lower() in NOT_A_HUMAN:
        set_b6({"error": "Enter the engineer name in B3: the margin must be recorded by a named human."})
    else:
        # Local helper: sysml/model.py has no block for a pending (tbc) status without a
        # `satisfy`. Same standard constructs only: StatusInfo and Rationale (reported as a gap).
        _q = lambda s: s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        _block = (
            f'    metadata : ModelingMetadata::StatusInfo about req004 {{\n'
            f'        originator = "{_q(_who)}";\n'
            f'        status = StatusKind::tbc;\n'
            f'    }}\n'
            f'    metadata : ModelingMetadata::Rationale about req004 {{\n'
            f'        text = "{_q(margin_in.value)}";\n'
            f'    }}\n'
        )
        _c3 = get_c3()
        _prior = _c3["att"] if _c3 and "att" in _c3 else ""
        _text = assemble(structure, ev2, _prior + _block)
        set_b6({"who": _who, "block": _block, "res": evaluate(_text)})
    return


@app.cell(hide_code=True)
def _(get_b6, mo, params2, req004_text, res_b4, summary2):
    _peak = summary2["peak_control_torque"]
    _limit = params2["maxTorque"]
    _verdict = res_b4["verdicts"]["vc004_tuned"]
    _holds = res_b4["req"]["req004(tuned)"]
    _rel = "equals" if _peak == _limit else "differs from"
    _parts = [
        mo.md(f"REQ-004, verbatim: *{req004_text}*"),
        mo.callout(
            mo.md(
                f"OpenSysML verdict: **{_verdict}**. No automated verdict was declared, by "
                "design: the method is analysis requiring judgment."
            ),
            kind="neutral",
        ),
        mo.md(
            f"The constraint evaluates {_holds}, but peak torque ({_peak:.3g} N·m) {_rel} the "
            f"actuator limit ({_limit:.3g} N·m) because the simulation clips torque "
            "(`np.clip`). The model cannot represent an over-capacity command. That is a "
            "model-adequacy question, recorded as a Rationale (an assumption), not evidence "
            "of satisfaction."
        ),
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
def _(SEED_NAME, assemble, attestation_block, ev1, evaluate, mo, structure):
    # A deliberately contradicting claim: "satisfied" on the design whose verdict is fail.
    # Illustrative only; it is never published.
    _claim = attestation_block(
        "initial", True, SEED_NAME, "tbc", "Illustrative claim for the check only.", "vc001_initial"
    )
    _res = evaluate(assemble(structure, ev1, _claim))
    _holds = _res["claims"]["att_initial"]["holds"]
    _body = mo.vstack(
        [
            mo.md(f"```text\n{_claim}\n```"),
            mo.md(f"`verify_satisfaction` on this illustrative claim: consistent with the evaluated model = **{_holds}**."),
            mo.md(
                "The tool checks that the human's claim is consistent with the evaluated model. "
                "That is verification of the claim. It is not the attestation, and it says "
                "nothing about the physical satellite."
            ),
        ]
    )
    mo.accordion({"Show the check": _body})
    return


if __name__ == "__main__":
    app.run()
