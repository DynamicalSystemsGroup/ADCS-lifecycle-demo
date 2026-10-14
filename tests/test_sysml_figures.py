"""Tests for sysml/figures.py: every figure builds on real simulation data; the numbers it draws are the inputs."""

from __future__ import annotations

import matplotlib.text
import numpy as np
import pytest
from matplotlib.figure import Figure

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from analysis.symbolic import run_symbolic_analysis
from sysml import figures as F

LIMIT_S, BAND = 120.0, 0.1


def _run(kp, kd):
    p = dict(load_params(), Kp=kp, Kd=kd)
    return p, run_symbolic_analysis(p).pointing_budget["settling_time_s"], run_step_response(p)


@pytest.fixture(scope="module")
def runs():
    return {(1.0, 10.0): _run(1.0, 10.0), (4.0, 30.0): _run(4.0, 30.0)}


def _texts(fig):
    return [t for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text().strip()]


def _assert_screen_legible(fig):
    small = [(t.get_text(), t.get_fontsize()) for t in _texts(fig) if t.get_fontsize() < 15]
    assert small == []


def test_palette_has_the_six_roles():
    assert set(F.PALETTE) == {"human", "machine", "prescribed", "pass", "fail", "inconclusive"}
    assert len(set(F.PALETTE.values())) == 6


def test_pointing_error_deg_starts_at_the_slew(runs):
    err = F.pointing_error_deg(runs[(1.0, 10.0)][2])
    assert err[0] == pytest.approx(10.0, rel=2e-3)


def test_commanded_torque_exceeds_the_clip_and_delivered_does_not(runs):
    p, _, sim = runs[(4.0, 30.0)]
    cmd = F.commanded_torque(sim, 4.0, 30.0)
    assert np.max(np.abs(cmd)) == pytest.approx(0.174, abs=0.002)
    assert np.max(np.abs(sim.tau_ctrl)) <= p["maxTorque"] + 1e-12
    assert p["maxTorque"] == pytest.approx(0.1)


@pytest.mark.parametrize("case", [(1.0, 10.0), (4.0, 30.0)])
def test_settling_figure(runs, case):
    p, t_sym, sim = runs[case]
    fig = F.settling_figure(sim, t_sym, LIMIT_S, BAND, title=f"Kp={case[0]:g}, Kd={case[1]:g}")
    assert isinstance(fig, Figure)
    labels = " | ".join(t.get_text() for t in _texts(fig))
    assert f"SymPy: {t_sym:.0f} s" in labels
    t_sim = sim.summary()["settling_time_s"]  # the one settling definition: the evidence value
    assert f"simulation: {t_sim:.0f} s" in labels
    dot = [l for l in fig.axes[0].get_lines() if l.get_marker() == "o"][0]
    assert dot.get_xdata()[0] == pytest.approx(t_sim)
    assert f"{LIMIT_S:g} s limit" in labels
    _assert_screen_legible(fig)


def test_overlay_figure(runs):
    fig = F.overlay_figure(runs[(1.0, 10.0)][2], runs[(4.0, 30.0)][2], ["Kp=1, Kd=10", "Kp=4, Kd=30"], LIMIT_S, BAND)
    assert isinstance(fig, Figure)
    lines = fig.axes[0].get_lines()
    alphas = [l.get_alpha() for l in lines if l.get_label() in ("Kp=1, Kd=10", "Kp=4, Kd=30")]
    assert alphas == [0.3, None]  # first faded, second solid
    _assert_screen_legible(fig)


def test_neighbour_strip():
    rows = [("Kp=4, Kd=30", 80.0, 60.0, True), ("Kp=4, Kd=25", 90.0, 130.0, False)]
    fig = F.neighbour_strip(rows, LIMIT_S)
    assert isinstance(fig, Figure)
    labels = " | ".join(t.get_text() for t in _texts(fig))
    assert "within 120 s" in labels and "over 120 s" in labels
    _assert_screen_legible(fig)


def test_neighbour_strip_tints_the_over_limit_region():
    fig = F.neighbour_strip([("a", 80.0, 60.0, True), ("b", 90.0, 130.0, False)], LIMIT_S)
    span = [p for p in fig.axes[0].patches if p.get_alpha()]
    assert len(span) == 1
    assert span[0].get_x() == pytest.approx(LIMIT_S) and span[0].get_width() > 0


def test_neighbour_strip_on_real_neighbours():
    rows = []
    for kp, kd in [(4, 30), (4, 25), (6, 25), (3, 30), (4, 40)]:
        _, t_sym, sim = _run(float(kp), float(kd))
        rows.append((f"Kp={kp}, Kd={kd}", t_sym, sim.summary()["settling_time_s"], (kp, kd) == (4, 30)))
    assert isinstance(F.neighbour_strip(rows, LIMIT_S), Figure)


@pytest.mark.parametrize("case", [(1.0, 10.0), (4.0, 30.0)])
def test_torque_figure(runs, case):
    p, _, sim = runs[case]
    fig = F.torque_figure(sim, *case, p["maxTorque"])
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 2 and fig.axes[0].get_shared_x_axes().joined(fig.axes[0], fig.axes[1])
    delivered = max(l.get_ydata().max() for l in fig.axes[0].get_lines() if l.get_label() == "delivered (clipped)")
    assert delivered <= p["maxTorque"] + 1e-12
    _assert_screen_legible(fig)


def test_torque_flat_top_is_drawn_over_the_limit_line_and_annotated(runs):
    p, _, sim = runs[(4.0, 30.0)]
    fig = F.torque_figure(sim, 4.0, 30.0, p["maxTorque"])
    ax = fig.axes[0]
    limit_line = [l for l in ax.get_lines() if l.get_linestyle() == "--" and set(l.get_ydata()) == {p["maxTorque"]}][0]
    delivered = [l for l in ax.get_lines() if l.get_label() == "delivered (clipped)"][0]
    commanded = [l for l in ax.get_lines() if l.get_label() == "commanded by the control law"][0]
    assert limit_line.get_zorder() < delivered.get_zorder()
    assert delivered.get_linewidth() > commanded.get_linewidth() and delivered.get_linewidth() > limit_line.get_linewidth()
    labels = " | ".join(t.get_text() for t in _texts(fig))
    assert "clipped, " in labels and "commanded peak 0.174" in labels


def test_torque_figure_without_saturation_has_no_clipped_label(runs):
    p, _, sim = runs[(1.0, 10.0)]
    cmd = np.max(np.abs(F.commanded_torque(sim, 1.0, 10.0)))
    fig = F.torque_figure(sim, 1.0, 10.0, p["maxTorque"])
    assert ("clipped, " in " | ".join(t.get_text() for t in _texts(fig))) == (cmd > p["maxTorque"])


def test_pill_kinds_and_escaping():
    for kind in ("pass", "fail", "inconclusive", "tbc"):
        assert f"pill-{kind}" in F.pill("x", kind)
    assert "dashed" in F.pill("tbc · no one has judged", "tbc")
    assert "&lt;b&gt;" in F.pill("<b>", "pass")
    with pytest.raises(ValueError):
        F.pill("x", "warn")


def test_cards():
    h = F.human_card("Ada", "done", "text <here>", "evidence 1")
    assert F.PALETTE["human"] in h and "Ada · done" in h and "&lt;here&gt;" in h and "evidence 1" in h
    m = F.machine_card("computed")
    assert F.PALETTE["machine"] in m and F.PALETTE["human"] not in m
