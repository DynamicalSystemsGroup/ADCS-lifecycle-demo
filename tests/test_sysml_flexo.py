"""Flexo SysML v2 client + Git helper. Offline tests run by default; `-m live` needs the
local stack (see sysml/FLEXO_LOCAL.md)."""

from __future__ import annotations

import subprocess
import uuid

import httpx
import pytest

from sysml.flexo_v2 import FlexoV2, NoChangeError, diff
from sysml.git_source import head_sha, text_diff

# ---------- offline: diff ----------

def el(i, name, **kw):
    return {"@id": i, "@type": "PartUsage", "declaredName": name, **kw}


def test_diff_added_removed_changed():
    a = {"1": el("1", "A"), "2": el("2", "B"), "3": el("3", "C")}
    b = {"1": el("1", "A"), "2": el("2", "B2"), "4": el("4", "D")}
    assert diff(a, b) == {"added": ["4"], "removed": ["3"], "changed": ["2"]}


def test_diff_identical_is_empty():
    a = {"1": el("1", "A")}
    assert diff(a, dict(a)) == {"added": [], "removed": [], "changed": []}


def test_diff_compares_raw_values_so_reorder_is_a_change():
    r = lambda *ids: [{"@id": i} for i in ids]
    a = {"1": el("1", "A", ownedMember=r("x", "y", "z"))}
    b = {"1": el("1", "A", ownedMember=r("z", "x", "y"))}
    assert diff(a, b)["changed"] == ["1"]


def test_publish_identical_snapshot_raises_no_change():
    def handler(request):
        return httpx.Response(404)
    flexo = FlexoV2("http://x")
    flexo._http = httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))
    with pytest.raises(NoChangeError, match="snapshot identical to head"):
        flexo.publish("p", [el("1", "A")], "m", "0" * 40)


# ---------- offline: git_source ----------

def test_text_diff():
    d = text_diff("a\nb\n", "a\nc\n")
    assert d.startswith("--- a/satellite.sysml\n+++ b/satellite.sysml\n")
    assert "-b\n" in d and "+c\n" in d
    assert text_diff("same\n", "same\n") == ""


def test_head_sha(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", *a], check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "f").write_text("x")
    git("add", "f")
    git("commit", "-q", "-m", "c")
    sha = head_sha(str(tmp_path))
    expected = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    assert sha == expected and len(sha) == 40


# ---------- live: C1 -> C2 -> C3 round trip ----------

@pytest.mark.live
def test_c1_c2_c3_round_trip():
    flexo = FlexoV2()
    name = f"wp3-test-{uuid.uuid4().hex[:8]}"
    pid = flexo.ensure_project(name)
    assert flexo.ensure_project(name) == pid  # idempotent
    try:
        ids = [str(uuid.uuid4()) for _ in range(6)]
        sat, adcs, wheel, tracker, mass, spare = ids
        ref = lambda i: {"@id": i}
        # Child lists in deliberately non-sorted order, to expose any reordering by the store.
        members = [ref(i) for i in (wheel, tracker, adcs)]
        c1_els = [
            el(sat, "Satellite", ownedMember=members),
            el(adcs, "ADCS", owner=ref(sat)),
            el(wheel, "Wheel", owner=ref(sat), mass=2.0),
            el(tracker, "Tracker", owner=ref(sat)),
        ]
        c2_els = [dict(e) for e in c1_els]
        c2_els[2] = el(wheel, "Wheel", owner=ref(sat), mass=3.5)        # changed
        c2_els.append(el(mass, "MassBudget", owner=ref(sat)))            # added
        c3_els = [dict(e) for e in c2_els if e["@id"] != tracker]        # removed
        c3_els[0] = el(sat, "Satellite", ownedMember=[ref(wheel), ref(adcs), ref(mass)])  # changed
        c3_els.append(el(spare, "Spare", owner=ref(sat)))                # added
        c3_els[1] = el(adcs, "ADCS", owner=ref(sat), declaredShortName="A")  # changed

        shas = [uuid.uuid4().hex + "0" * 8 for _ in range(3)]
        commits = [flexo.publish(pid, els, f"C{n}", sha)
                   for n, (els, sha) in enumerate(zip((c1_els, c2_els, c3_els), shas), 1)]
        assert len(set(commits)) == 3

        snaps = [flexo.elements(pid, c) for c in commits]
        # Full-snapshot semantics: each commit reads back exactly what was published.
        assert [set(s) for s in snaps] == [{e["@id"] for e in els} for els in (c1_els, c2_els, c3_els)]
        # Git SHA is recoverable per commit.
        assert [flexo.git_sha(pid, c) for c in commits] == shas

        assert diff(snaps[0], snaps[1]) == {
            "added": [mass], "removed": [], "changed": sorted([wheel])}
        # C2 -> C3: exactly the elements we touched; the untouched ones (wheel) are not reported.
        assert diff(snaps[1], snaps[2]) == {
            "added": [spare], "removed": [tracker], "changed": sorted([sat, adcs])}
        # Re-reading the same commit twice is stable (no store-side noise).
        assert diff(snaps[1], flexo.elements(pid, commits[1])) == {
            "added": [], "removed": [], "changed": []}
    finally:
        flexo.delete_project(pid)
