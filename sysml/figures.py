"""Figures and HTML snippets for the SysML talk notebook.

Plain functions: computed data in, a matplotlib Figure (or an HTML string) out. Nothing here runs a
simulation or makes a judgement. Every number drawn or written in a label is interpolated from the
arguments, never typed in.

Colour meaning (talk/FOUNDATIONS section 7): amber = a human said it, and nothing else uses amber;
blue = the machine computed it; neutral = prescribed by the design; green / red / grey = verdict
pills only (so no figure uses them).
"""

from __future__ import annotations

import html
from contextlib import contextmanager

import matplotlib as mpl
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

PALETTE = {
    "human": "#d97706",         # amber: a person said it
    "machine": "#2166ac",       # blue: the machine computed it
    "prescribed": "#111111",    # neutral: set by the design or the requirement
    "pass": "#1a7f37",          # green  \
    "fail": "#b2182b",          # red     } verdict pills only
    "inconclusive": "#6b7280",  # grey   /
}
_GRID = "#e5e7eb"
_MUTED = "#4b5563"  # secondary text and de-emphasised neutral marks

MIN_FONT_PT = 15


@contextmanager
def screen_style():
    """rcParams for a Zoom screen share: no text below 15 pt, light grid, no top/right spines."""
    with mpl.rc_context({
        "font.size": MIN_FONT_PT, "axes.titlesize": 18, "axes.labelsize": MIN_FONT_PT,
        "xtick.labelsize": MIN_FONT_PT, "ytick.labelsize": MIN_FONT_PT, "legend.fontsize": MIN_FONT_PT,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.color": _GRID, "grid.linewidth": 0.8, "lines.linewidth": 2.5,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    }):
        yield


def _new(figsize, **kw):
    return Figure(figsize=figsize, layout="constrained", **kw)


def _finish(fig: Figure) -> Figure:
    """Draw once inside the style context so lazily built tick labels take the screen sizes."""
    FigureCanvasAgg(fig).draw()
    return fig


# ---------- computed series (functions of a SimResult) ----------

def pointing_error_deg(sim) -> np.ndarray:
    """Pointing error in degrees: 2*|q_vec| (the small-angle form `SimResult.summary` uses)."""
    return np.degrees(2 * np.linalg.norm(sim.q[:, :3], axis=1))


def commanded_torque(sim, Kp: float, Kd: float) -> np.ndarray:
    """The control law the simulation applies, before the actuator clip: (N, 3) in N*m.
    Same form as `analysis.numerical._pd_control`, without `np.clip`."""
    return -Kp / 2 * sim.q[:, :3] - Kd * sim.omega


# ---------- figures ----------

def _error_axes(ax, errs, t_limit, band_deg):
    """Shared furniture: log pointing-error axis, band, requirement line."""
    ax.set_yscale("log")
    ax.axhspan(ax.get_ylim()[0], band_deg, color=PALETTE["prescribed"], alpha=0.07, lw=0)
    ax.axhline(band_deg, color=_MUTED, lw=1.2)
    ax.axvline(t_limit, color=PALETTE["prescribed"], ls="--", lw=2)
    ax.set_xlabel("time after slew [s]")
    ax.set_ylabel("pointing error [deg]")
    top = max(float(np.max(e)) for e in errs)
    ax.set_ylim(band_deg / 100, top * 2)


def settling_figure(sim, t_sym: float, t_limit: float = 120,
                    title: str = "Pointing error after the slew", caption: str | None = None,
                    figsize: tuple[float, float] = (11, 5.4)) -> Figure:
    """Simulated pointing error (log scale) with the band, the requirement line, the simulated
    settling point (dot) and the SymPy estimate (dashed tick). No decay envelope. The band is
    1% of the initial error, drawn where `sim.summary()` measures settling. `caption` is an
    optional one-line note under the axis.

    There is one settling definition: the dot is `sim.summary()["settling_time_s"]`, the value
    recorded as evidence (last time the error exceeds 1% of the initial error; that is
    `band_deg` for the 10 deg slew). Error is the small-angle metric 2*|q_vec|, so it is
    approximate for large angles. `figsize` (inches) lets a thumbnail keep the same text size."""
    with screen_style():
        fig = _new(figsize)
        ax = fig.subplots()
        err = pointing_error_deg(sim)
        band_deg = 0.01 * float(err[0])
        ax.plot(sim.t, err, color=PALETTE["machine"], label="simulation")
        _error_axes(ax, [err], t_limit, band_deg)
        xmax = max(float(sim.t[-1]), t_sym * 1.05)
        ax.set_xlim(0, xmax)
        # the band label sits inside the shaded band (under the line), clear of the curve
        ax.text(xmax * 0.015, band_deg * 0.85, f"{band_deg:.2g}° band", ha="left", va="top",
                color=_MUTED, zorder=1.5)
        ax.text(t_limit + xmax * 0.01, ax.get_ylim()[1] / 1.5, f"{t_limit:g} s limit", ha="left", va="top",
                color=PALETTE["prescribed"])
        y_tick = band_deg / 30  # the SymPy tick runs down to near the axis floor, where the curve is not
        ax.plot([t_sym, t_sym], [y_tick, band_deg * 2], color=PALETTE["machine"], ls="--", lw=2.5)
        t_sim = float(sim.summary()["settling_time_s"])
        y_sim = float(np.interp(t_sim, sim.t, err))
        box = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9)
        ax.annotate(f"SymPy: {t_sym:.0f} s", (t_sym, y_tick), xytext=(6 if t_sym < 0.75 * xmax else -6, -3),
                    textcoords="offset points", ha="left" if t_sym < 0.75 * xmax else "right", va="top",
                    color=PALETTE["machine"], bbox=box)
        sim_off, sim_ha, sim_va = ((-14, -22), "right", "top") if t_sym >= t_sim else ((14, 34), "right", "bottom")
        ax.plot([t_sim], [y_sim], "o", ms=13, color=PALETTE["machine"], mec="white", mew=2, zorder=5)
        ax.annotate(f"simulation:{' ' if figsize[0] >= 8 else chr(10)}{t_sim:.0f} s", (t_sim, y_sim), xytext=sim_off,
                    textcoords="offset points", ha=sim_ha, va=sim_va, color=PALETTE["machine"],
                    fontweight="bold", bbox=box)
        ax.set_title(title, loc="left")
        if caption:
            fig.supxlabel(caption, fontsize=MIN_FONT_PT)
        return _finish(fig)


def overlay_figure(sim_a, sim_b, labels, t_limit: float, band: float,
                   figsize: tuple[float, float] = (11, 5.4)) -> Figure:
    """Two designs on one pointing-error axis: the first faded, the second solid."""
    with screen_style():
        fig = _new(figsize)
        ax = fig.subplots()
        ea, eb = pointing_error_deg(sim_a), pointing_error_deg(sim_b)
        ax.plot(sim_a.t, ea, color=PALETTE["machine"], alpha=0.3, label=labels[0])
        ax.plot(sim_b.t, eb, color=PALETTE["machine"], label=labels[1])
        _error_axes(ax, [ea, eb], t_limit, band)
        xmax = float(max(sim_a.t[-1], sim_b.t[-1]))
        ax.set_xlim(0, xmax)
        ax.text(xmax * 0.015, band * 1.15, f"{band:g}° band", ha="left", va="bottom", color=_MUTED)
        ax.text(t_limit + xmax * 0.01, ax.get_ylim()[1] / 1.5, f"{t_limit:g} s limit", ha="left", va="top",
                color=PALETTE["prescribed"])
        ax.legend(loc="lower left", frameon=False)
        ax.set_title("Pointing error after the slew", loc="left")
        return _finish(fig)


def neighbour_strip(rows, t_limit: float, figsize: tuple[float, float] | None = None) -> Figure:
    """One dumbbell per design joining the SymPy estimate (open diamond) and the simulated
    settling time (filled dot). `rows` is [(label, t_sym, t_sim, highlight)]. Left of the
    limit line is within the requirement, right of it is not. `figsize` (inches) lets a thumbnail
    keep the same text size."""
    with screen_style():
        fig = _new(figsize or (11, 0.62 * len(rows) + 2.4))
        ax = fig.subplots()
        n = len(rows)
        for i, (label, t_sym, t_sim, highlight) in enumerate(rows):
            y = n - 1 - i
            ax.plot([t_sym, t_sim], [y, y], color=_MUTED, lw=3 if highlight else 2, alpha=0.7, zorder=1)
            ax.plot([t_sym], [y], "D", ms=11, mfc="white", mec=PALETTE["machine"], mew=2.5, zorder=3)
            ax.plot([t_sim], [y], "o", ms=13 if highlight else 11, color=PALETTE["machine"], zorder=3)
        ax.set_yticks(range(n), [r[0] for r in reversed(rows)])
        for tick, row in zip(ax.get_yticklabels(), reversed(rows)):
            if row[3]:
                tick.set_fontweight("bold")
        xmax = max(max(r[1], r[2]) for r in rows) * 1.08
        xmax = max(xmax, t_limit * 1.25)
        ax.axvspan(t_limit, xmax, color=PALETTE["prescribed"], alpha=0.07, lw=0, zorder=0)  # over the limit: reads without the text
        ax.axvline(t_limit, color=PALETTE["prescribed"], ls="--", lw=2)
        ax.set_xlim(0, xmax)
        ax.set_ylim(-0.6, n - 0.2)
        ax.text(t_limit - xmax * 0.03, n - 0.5, f"within {t_limit:g} s", ha="right", va="center", color=_MUTED)
        ax.text(t_limit + xmax * 0.03, n - 0.5, f"over {t_limit:g} s", ha="left", va="center", color=_MUTED)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("settling time [s]")
        ax.plot([], [], "D", ms=11, mfc="white", mec=PALETTE["machine"], mew=2.5, label="SymPy estimate")
        ax.plot([], [], "o", ms=11, color=PALETTE["machine"], label="simulation")
        fig.legend(*ax.get_legend_handles_labels(), loc="outside lower center", ncol=2, frameon=False)
        return _finish(fig)


def torque_figure(sim, Kp: float, Kd: float, limit: float, t_max: float = 120.0) -> Figure:
    """Top: commanded torque against delivered torque, the part over the limit shaded and the
    saturated interval marked "clipped". Bottom: pointing error. Time axis shared.

    The torque plotted is the magnitude about the axis with the largest command, a single-axis
    slew. The limit line is drawn first and the delivered trace thicker on top, so the flat top
    at the limit is unmistakable."""
    with screen_style():
        fig = _new((11, 7.4))
        ax_t, ax_e = fig.subplots(2, 1, sharex=True, height_ratios=[3, 2])
        cmd = commanded_torque(sim, Kp, Kd)
        k = int(np.argmax(np.max(np.abs(cmd), axis=0)))
        axis = "XYZ"[k]
        c, d = np.abs(cmd[:, k]), np.abs(sim.tau_ctrl[:, k])
        top = max(c.max(), limit) * 1.18
        ax_t.axhline(limit, color=PALETTE["prescribed"], ls="--", lw=2, zorder=1)
        ax_t.plot(sim.t, c, color=PALETTE["machine"], ls="--", lw=2, alpha=0.75, zorder=2,
                  label="commanded by the control law")
        ax_t.fill_between(sim.t, limit, c, where=c > limit, color=PALETTE["machine"], alpha=0.25, lw=0, zorder=2)
        ax_t.plot(sim.t, d, color=PALETTE["machine"], lw=5, solid_capstyle="butt", zorder=4,
                  label="delivered (clipped)")
        ax_t.text(t_max, limit * 0.97, f"actuator limit {limit:g} N·m", ha="right", va="top",
                  color=PALETTE["prescribed"])
        box = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9)
        sat = np.where(c > limit)[0]
        x_lab = 0.12 * t_max
        if len(sat):
            t0, t1 = float(sim.t[sat[0]]), float(sim.t[sat[-1]])
            ax_t.annotate(f"clipped, {t0:.0f} to {t1:.0f} s", ((t0 + t1) / 2, limit),
                          xytext=(max(x_lab, t1 + 0.02 * t_max), limit * 1.12), textcoords="data",
                          ha="left", va="bottom", color=PALETTE["machine"], fontweight="bold", bbox=box,
                          arrowprops=dict(arrowstyle="->", color=PALETTE["machine"], lw=2))
        ax_t.annotate(f"commanded peak {c.max():.3f} N·m", (float(sim.t[int(np.argmax(c))]), float(c.max())),
                      xytext=(x_lab, top * 0.93), textcoords="data", ha="left", va="center",
                      color=PALETTE["machine"], bbox=box,
                      arrowprops=dict(arrowstyle="->", color=PALETTE["machine"], lw=1.5))
        ax_t.set_ylabel(f"|torque|, {axis} axis [N·m]")
        ax_t.set_ylim(0, top)
        ax_t.legend(loc="upper right", bbox_to_anchor=(1, 0.8), frameon=False)
        err = pointing_error_deg(sim)
        ax_e.plot(sim.t, err, color=PALETTE["machine"])
        ax_e.set_yscale("log")
        ax_e.set_ylim(err.max() * 1e-4, err.max() * 2)
        ax_e.set_ylabel("pointing error [deg]")
        ax_e.set_xlabel("time after slew [s]")
        ax_e.set_xlim(0, t_max)
        return _finish(fig)


# ---------- HTML snippets (strings; wrap with mo.Html in the notebook) ----------

_PILL = {  # kind -> (background, text colour, border)
    "pass": (PALETTE["pass"], "#fff", PALETTE["pass"]),
    "fail": (PALETTE["fail"], "#fff", PALETTE["fail"]),
    "inconclusive": (PALETTE["inconclusive"], "#fff", PALETTE["inconclusive"]),
    "tbc": ("transparent", PALETTE["inconclusive"], PALETTE["inconclusive"]),
}


def pill(text: str, kind: str) -> str:
    """A verdict or status badge. `kind` is pass, fail, inconclusive or tbc (grey, dashed outline,
    for 'no person has judged yet'). Amber is reserved for a person's words, so a pending pill that
    names nobody is grey."""
    if kind not in _PILL:
        raise ValueError(f"pill kind must be one of {sorted(_PILL)}, got {kind!r}")
    bg, fg, border = _PILL[kind]
    dash = "dashed" if kind == "tbc" else "solid"
    return (f'<span class="pill pill-{kind}" style="display:inline-block;padding:.15em .75em;'
            f'border-radius:999px;background:{bg};color:{fg};border:3px {dash} {border};'
            f'font-weight:700;font-size:1.5rem;line-height:1.3">{html.escape(text)}</span>')


def human_card(name: str, status: str, text: str, evidence_line: str = "") -> str:
    """The amber card: a named person's words. The only warm element on screen."""
    ev = (f'<div style="margin-top:.5rem;font-size:1.05rem;opacity:.8">{html.escape(evidence_line)}</div>'
          if evidence_line else "")
    return (f'<div class="human-card" style="border-left:8px solid {PALETTE["human"]};'
            f'background:rgba(217,119,6,.10);padding:.9rem 1.2rem;border-radius:6px">'
            f'<div style="font-weight:700;font-size:1.2rem;color:{PALETTE["human"]}">'
            f'{html.escape(name)} · {html.escape(status)}</div>'
            f'<div style="font-size:1.3rem;margin-top:.3rem">{html.escape(text)}</div>{ev}</div>')


def machine_card(text: str) -> str:
    """A blue-edged card for what a tool computed."""
    return (f'<div class="machine-card" style="border-left:8px solid {PALETTE["machine"]};'
            f'background:rgba(33,102,172,.07);padding:.8rem 1.2rem;border-radius:6px;'
            f'font-size:1.3rem">{html.escape(text)}</div>')
