"""Tests for sysml/evidence.py: regression pins on the simulated settling times (+-0.2 s)."""

from __future__ import annotations

import pytest

from sysml import evidence as ev

PINS = {  # (kp, kd): (x, y, z); the only hard-coded numbers in the evidence tests
    (4, 30): (78.0, 123.9, 81.4),
    (8, 30): (87.4, 53.8, 85.0),
    (4, 25): (120.5, 96.5, 116.5),
}


@pytest.mark.parametrize("design", sorted(PINS))
def test_slew_settling_per_axis_pins(design):
    r = ev.slew_settling(*design)
    for got, want in zip((r["x"], r["y"], r["z"]), PINS[design]):
        assert got == pytest.approx(want, abs=0.2)
    assert r["worst"] == max(r["x"], r["y"], r["z"]) and r[r["worst_axis"]] == r["worst"]


def test_initial_design_x_pin_and_no_saturation():
    r = ev.slew_settling(*ev.INITIAL)
    assert r["x"] == pytest.approx(310.6, abs=0.2) and r["worst_axis"] == "x"
    assert r["saturated_s"] == 0.0 and r["peak_torque"] < 0.1


def test_tuned_design_is_saturated_then_settles():
    r = ev.slew_settling(*ev.TUNED)
    assert r["worst_axis"] == "x" and r["worst"] == pytest.approx(87.4, abs=0.2)
    assert 0 < r["saturated_s"] < r["worst"] and r["peak_torque"] == pytest.approx(0.1)


def test_symbolic_wraps_symbolic_settling():
    t, h = ev.symbolic(*ev.NEIGHBOUR)
    assert t == pytest.approx(104.7, abs=0.1) and len(h) == 64


def test_grid_is_worst_axis_over_the_box():
    g = ev.grid((4, 5), (25, 30))
    assert set(g) == {(4, 25), (4, 30), (5, 25), (5, 30)}
    assert g[(4, 30)] == pytest.approx(123.9, abs=0.2) and g[(4, 25)] == pytest.approx(120.5, abs=0.2)
    assert (ev.BOX_KP, ev.BOX_KD) == ((4, 5, 6), (22, 23.5, 25))


# In-model REDK action: the step size of the in-model simulation changes the verdict at (4,25).
def test_inmodel_settling_step_size_flips_the_verdict():
    assert ev.inmodel_settling(*ev.NEIGHBOUR, dt=0.5) == pytest.approx(119.5, abs=0.05)   # <= 120 s: pass
    assert ev.inmodel_settling(*ev.NEIGHBOUR, dt=0.05) == pytest.approx(120.5, abs=0.05)  # > 120 s: fail


def test_precompute_bundle_and_cache(tmp_path, monkeypatch):
    import json
    import time
    monkeypatch.setattr(ev, "OUTPUT_DIR", tmp_path)
    t0 = time.time()
    b = ev.precompute()
    cold = time.time() - t0
    t0 = time.time()
    again = ev.precompute()
    warm = time.time() - t0
    assert again == b and warm < 2.0, (cold, warm)
    json.dumps(b)  # plain data
    assert set(b["designs"]) == {"initial", "neighbour", "tuned"}
    n = b["designs"]["neighbour"]
    assert n["settling"]["worst"] == pytest.approx(120.5, abs=0.2)
    for ax in "xyz":
        s = n["series"][ax]
        assert len(s["t"]) <= 600 and len(s["t"]) == len(s["error_deg"]) == len(s["torque"])
    assert len(b["grid"]) == 9 and b["region"]["verdict"] == "no_counterexample"
    assert b["inmodel"]["0.5"] == pytest.approx(119.5, abs=0.05)
    assert b["inmodel"]["0.05"] == pytest.approx(120.5, abs=0.05)


# ---- the numbers the deck shows are computed; these pin them (talk.py reads the same bundle) ----

@pytest.fixture(scope="module")
def deck_bundle():
    return ev.precompute()


def test_deck_numbers_are_pinned(deck_bundle):
    b = deck_bundle
    assert ev.grid_counts(b) == (6, 9)  # "6 of 9 fail" in the simulated gain box
    d = b["designs"]
    assert d["initial"]["symbolic_s"] == pytest.approx(261.7, abs=0.05)  # 262 s
    assert d["initial"]["settling"]["worst"] == pytest.approx(310.6, abs=0.1)  # 311 s
    assert d["neighbour"]["symbolic_s"] == pytest.approx(104.7, abs=0.05)
    assert d["neighbour"]["settling"]["worst"] == pytest.approx(120.5, abs=0.05)
    assert d["neighbour"]["settling"]["worst_axis"] == "x"
    assert d["tuned"]["symbolic_s"] == pytest.approx(87.2, abs=0.05)  # SymPy 87.2 s
    s = d["tuned"]["settling"]
    assert (round(s["x"], 1), round(s["y"], 1), round(s["z"], 1)) == (87.4, 53.8, 85.0)
    assert s["worst"] == s["x"]  # the worst axis governs
    assert b["nolimit"]["settling_s"] == pytest.approx(118.6, abs=0.05)  # torque limit off
    assert b["inmodel"]["0.5"] == pytest.approx(119.5, abs=0.05) and b["inmodel"]["0.05"] == pytest.approx(120.5, abs=0.05)


def test_4_30_fails_on_the_y_axis():
    assert ev.slew_settling(4, 30)["y"] == pytest.approx(123.9, abs=0.05)


def test_tool_verify_is_live_or_labelled_captured(monkeypatch):
    cap = ev.VERIFY_CAPTURE.read_text()
    monkeypatch.setenv("OPENSYSML_SMT", "/nonexistent")  # no z3: the capture, labelled
    assert ev.tool_verify() == {"engine": "captured", "text": cap}
    monkeypatch.delenv("OPENSYSML_SMT")
    monkeypatch.setenv("SYSML_TOOLS_DIR", "/nonexistent")  # no tools directory: the capture
    assert ev.tool_verify()["engine"] == "captured"
    monkeypatch.delenv("SYSML_TOOLS_DIR")
    live = ev.tool_verify()
    if live["engine"] == "live":  # same command, same output as the capture used on the opening slide
        assert live["text"] == cap
