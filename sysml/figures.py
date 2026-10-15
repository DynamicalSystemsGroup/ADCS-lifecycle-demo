"""Figures and HTML snippets for the SysML talk notebook.

Plain functions: computed data in, a matplotlib Figure (or an HTML string) out. Nothing here runs a
simulation or makes a judgement. Every number drawn or written in a label is interpolated from the
arguments, never typed in.

Colour meaning (talk/FOUNDATIONS section 7): amber = a human said it, and nothing else uses amber;
blue = the machine computed it; neutral = prescribed by the design; green / red / grey = verdict
pills only (so no figure uses them).
"""

from __future__ import annotations

import calendar
import html
import math
import textwrap
from contextlib import contextmanager

import matplotlib as mpl
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

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
        ax.legend(loc="upper right", frameon=False)
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
        ax.set_ylim(-0.6, n + 0.6)
        ax.xaxis.set_major_locator(MultipleLocator(50))  # few ticks: they stay legible in a thumbnail
        ax.text(t_limit - xmax * 0.03, n + 0.05, f"within\n{t_limit:g} s", ha="right", va="center", color=_MUTED)
        ax.text(t_limit + xmax * 0.03, n + 0.05, f"over\n{t_limit:g} s", ha="left", va="center", color=_MUTED)
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


def _year(date: str) -> float:
    """"YYYY" or "YYYY-MM" as a decimal year (a bare year sits at mid-year, a month at mid-month)."""
    y, _, m = date.partition("-")
    return int(y) + ((int(m) - 0.5) / 12 if m else 0.5)


def _month_label(month: str) -> str:
    y, m = month.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


def history_timeline(data: dict, figsize: tuple[float, float] = (13.4, 5.7), recent: float = 0.4) -> Figure:
    """The project's history as one picture, drawn from `talk/history.json`; every label is data.

    The time axis is piecewise linear: everything before the last phase takes `1 - recent` of the
    width and the last phase takes `recent`, with an axis break (//) at the seam. The recent era is
    zoomed on purpose: that is where the acceleration is. Top: phase bands, the organizations
    documented in each era, milestone dots with short labels (each event carries a placement hint
    `place`: side, level, align). Inside the last band: a sparkline of the last twelve months in
    blue, drawn over the period it measures (the series is computed elsewhere). `figsize` is in
    inches: at 87 dpi the 15 pt text is 18 px, and the PNG's natural width is its display width."""
    phases, events, orgs = data["phases"], data["events"], data["orgs"]
    seam = _year(phases[-1]["start"])
    x0, x1 = _year(phases[0]["start"]) - 0.7, _year(phases[-1]["end"]) + 0.4
    w_in, h_in = figsize
    top_in = h_in - 0.05
    width = w_in * 0.98  # axes width in inches: one x unit is one inch
    gap = 0.3  # the axis break
    left_w = (width - gap) * (1 - recent)
    char_in = MIN_FONT_PT * 0.52 / 72  # width of a character, inches (conservative)

    def X(year: float) -> float:
        if year < seam:
            return (year - x0) / (seam - x0) * left_w
        return left_w + gap + (year - seam) / (x1 - seam) * (width - left_w - gap)

    def wrapped(label: str) -> str:
        if len(label) <= 28 or " · " not in label:
            return label
        return "\n".join(label.split(" · "))

    with screen_style():
        fig = Figure(figsize=figsize)
        ax = fig.add_axes((0.01, 0.05 / h_in, 0.98, top_in / h_in), frameon=False)
        ax.set_xlim(0, width)
        ax.set_ylim(0, top_in)  # one y unit is one inch too
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        step = 0.38  # inches between label levels
        n_below = max([e["place"]["level"] for e in events if e["place"]["side"] == "below"] or [0])
        line_y = 0.35 + 0.2 + step * n_below + 0.2
        names_y = top_in - 0.05
        tints = ["#f3f4f6", "#e5e7eb"]
        last = len(phases) - 1
        for i, ph in enumerate(phases):
            a = X(_year(ph["start"])) if i == last else X(_year(ph["start"]))
            b = width if i == last else (left_w if i == last - 1 else X(_year(ph["end"])))
            ax.fill_betweenx([0, top_in], a, b, color=tints[i % 2], lw=0, zorder=0)
            chars = int((b - a - 0.2) / char_in)
            ax.text(a + 0.1, names_y, textwrap.fill(ph["name"], width=max(chars - 4, 8)), ha="left", va="top",
                    fontweight="bold", color=PALETTE["prescribed"], linespacing=1.1, zorder=3)
            names = [o["name"] for o in orgs if o["era"] == ph["name"]]
            if names:
                ax.text(a + 0.1, names_y - 0.75,
                        textwrap.fill(" ".join(n.replace(" ", "\u00a0") + "\u00a0·" for n in names)[:-2],
                                      width=max(chars, 12)),
                        ha="left", va="top", color=_MUTED, linespacing=1.3, zorder=3)
        end_year = int(_year(phases[-1]["end"]))
        for yr in range(math.ceil(x0), end_year + 1):  # year ticks on both sides of the break
            ax.plot([X(yr)] * 2, [0.3, line_y], color="white", lw=1.5, zorder=1)
            ax.text(X(yr), 0.0, str(yr), ha="center", va="bottom", color=_MUTED, zorder=3)
        ax.plot([X(_year(phases[0]["start"])), left_w], [line_y] * 2, color=PALETTE["prescribed"], lw=2.5, zorder=2,
                solid_capstyle="butt")
        ax.plot([left_w + gap, X(_year(phases[-1]["end"]))], [line_y] * 2, color=PALETTE["prescribed"], lw=2.5,
                zorder=2, solid_capstyle="butt")
        for dx in (-0.06, 0.06):  # the axis break: two slashes
            xb = left_w + gap / 2 + dx
            ax.plot([xb - 0.05, xb + 0.05], [line_y - 0.16, line_y + 0.16], color=PALETTE["prescribed"], lw=2.2,
                    zorder=4, solid_capstyle="butt")
        for ev in events:
            x, pl = X(_year(ev["date"])), ev["place"]
            y = line_y + (1 if pl["side"] == "above" else -1) * (0.2 + step * pl["level"])
            ax.plot([x, x], [line_y, y], color=_MUTED, lw=1.2, zorder=2)
            ax.plot([x], [line_y], "o", ms=11, color=PALETTE["prescribed"], zorder=4)
            ax.text(x + (0.08 if pl["align"] == "left" else -0.08), y, wrapped(ev["label"]), ha=pl["align"],
                    va="center", multialignment=pl["align"], color=PALETTE["prescribed"], linespacing=1.45, zorder=4)
        # the sparkline: a white card inside the last band, upper part, under the band title
        v = data["velocity"]
        series = v["series"]
        vals = [pt["value"] for pt in series]
        card_l, card_r = left_w + gap + 0.2, width - 0.15
        card_t, card_b = names_y - 0.75, line_y + 0.45

        def fx(xv):
            return 0.01 + xv / w_in

        def fy(yv):
            return (0.05 + yv) / h_in

        card = fig.add_axes((fx(card_l), fy(card_b), (card_r - card_l) / w_in, (card_t - card_b) / h_in))
        card.set_xticks([])
        card.set_yticks([])
        card.grid(False)
        for sp in card.spines.values():
            sp.set_edgecolor(_GRID)
        axs = fig.add_axes((fx(card_l + 0.3), fy(card_b + 0.55), (card_r - card_l - 0.6) / w_in,
                            (card_t - card_b - 1.0) / h_in), frameon=False)
        axs.plot(range(len(vals)), vals, color=PALETTE["machine"], lw=3, zorder=3)
        for i, pt in enumerate(series):
            if pt.get("partial"):  # an open marker: the month is not over
                axs.plot([i], [pt["value"]], "o", ms=11, mfc="white", mec=PALETTE["machine"], mew=2.5, zorder=4)
        k = int(np.argmax(vals))
        axs.plot([k], [vals[k]], "o", ms=9, color=PALETTE["machine"], zorder=4)
        axs.annotate(f"{vals[k]}", (k, vals[k]), xytext=(10, 4), textcoords="offset points", ha="left",
                     va="center", color=PALETTE["machine"], fontweight="bold")
        axs.set_xlim(-0.3, len(vals) - 0.7)
        axs.set_ylim(0, max(vals) * 1.2)
        axs.set_yticks([])
        axs.grid(False)
        axs.spines["left"].set_visible(False)
        partial = " (partial)" if series[-1].get("partial") else ""
        axs.set_xticks([0, len(vals) - 1], [_month_label(series[0]["month"]), _month_label(series[-1]["month"]) + partial])
        axs.get_xticklabels()[0].set_ha("left")
        axs.get_xticklabels()[-1].set_ha("right")
        fig.text(fx(card_l + 0.15), fy(card_t - 0.1), v["title"], ha="left", va="top", color=PALETTE["machine"],
                 fontweight="bold")
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


# ---------- inline SVG for the deck (strings; styled by talk/slides/deck.css under .slide) ----------

def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v) >= 1 else f"{v:g}"


def error_plot_svg(curves, t0: float = 0.0, t1: float = 360.0, y0: float = 0.01, y1: float = 10.0,
                   limit: float = 120.0, band: float = 0.1, cursor: float | None = None,
                   width: int = 700, height: int = 340, x_step: float = 60.0) -> str:
    """Pointing error (degrees, log axis) against time, with the requirement's band and the time limit.

    `curves` is a list of dicts {t, error_deg, color, dash(optional), label(optional)}; the first curve
    carries the optional time `cursor` (a vertical line and a dot). The 0.1 degree band and the limit
    line are the requirement; nothing here marks an estimate from another model (different metric)."""
    import math
    L, R, T, B = 66, 24, 14, 62
    pw, ph = width - L - R, height - T - B
    ly0, ly1 = math.log10(y0), math.log10(y1)

    def X(t):
        return L + (t - t0) / (t1 - t0) * pw

    def Y(e):
        return T + (1 - (math.log10(max(e, y0 / 10)) - ly0) / (ly1 - ly0)) * ph

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Pointing error against time on a log axis, '
           f'with the {band:g} degree band and the {limit:g} second limit">',
           f'<defs><clipPath id="clip{int(t0)}{int(t1)}"><rect x="{L}" y="{T}" width="{pw}" height="{ph}"/></clipPath></defs>']
    d = 10 ** math.ceil(ly0)
    while d <= y1 * 1.0001:  # decade gridlines
        out.append(f'<path d="M{L},{Y(d):.1f} H{L + pw}" stroke="#e5e7eb" stroke-width="1"/>'
                   f'<text x="{L - 8}" y="{Y(d) + 6:.1f}" text-anchor="end" style="font-size:18px;fill:#4b5563">{d:g}</text>')
        d *= 10
    t = math.ceil(t0 / x_step) * x_step
    while t <= t1 + 1e-9:
        out.append(f'<path d="M{X(t):.1f},{T + ph} v6" stroke="#4b5563"/>'
                   f'<text x="{X(t):.1f}" y="{T + ph + 28}" text-anchor="middle" style="font-size:18px;fill:#4b5563">{t:g}</text>')
        t += x_step
    out.append(f'<path d="M{L},{T} V{T + ph} H{L + pw}" fill="none" stroke="#4b5563" stroke-width="1.5"/>'
               f'<text x="{L + pw / 2}" y="{height - 6}" text-anchor="middle" style="font-size:18px;fill:#4b5563">time (s)</text>')
    out.append(f'<text transform="translate(18,{T + ph / 2:.0f}) rotate(-90)" text-anchor="middle" '
               f'style="font-size:18px;fill:#4b5563">pointing error (deg.)</text>')
    if y0 < band < y1:
        out.append(f'<path d="M{L},{Y(band):.1f} H{L + pw}" stroke="#111111" stroke-width="2" stroke-dasharray="9 7"/>'
                   f'<text x="{L + pw - 6}" y="{Y(band) - 8:.1f}" text-anchor="end" style="font-size:18px">{band:g}° band</text>')
    if t0 < limit < t1:
        out.append(f'<path d="M{X(limit):.1f},{T} V{T + ph}" stroke="#111111" stroke-width="2" stroke-dasharray="9 7"/>'
                   f'<text x="{X(limit) + 8:.1f}" y="{T + 20}" style="font-size:18px">{limit:g} s limit</text>')
    for c in curves:
        pts = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(c["t"], c["error_deg"]) if t0 - 5 <= a <= t1 + 5)
        dash = f' stroke-dasharray="{c["dash"]}"' if c.get("dash") else ""
        out.append(f'<polyline points="{pts}" fill="none" stroke="{c["color"]}" stroke-width="3.5" '
                   f'stroke-linejoin="round" clip-path="url(#clip{int(t0)}{int(t1)})"{dash}/>')
    if cursor is not None and curves:
        c0 = curves[0]
        e = float(np.interp(cursor, c0["t"], c0["error_deg"]))
        out.append(f'<path d="M{X(cursor):.1f},{T} V{T + ph}" stroke="{c0["color"]}" stroke-width="1.5"/>'
                   f'<circle cx="{X(cursor):.1f}" cy="{Y(e):.1f}" r="7" fill="{c0["color"]}" stroke="#ffffff" stroke-width="2"/>')
    out.append("</svg>")
    return "".join(out)


def grid_svg(points, kps, kds, limit: float = 120.0, box_label: str = "z3 box", width: int = 520,
             height: int = 340, mark: tuple | None = None) -> str:
    """The Kp x Kd gain box as a grid: each cell is a verdict pill carrying that design's simulated
    settling time (worst slew axis). `points` is [{kp, kd, worst}]. The outline is the box z3 searched."""
    w = {(p["kp"], p["kd"]): p["worst"] for p in points}
    L, T, cw, ch = 96, 40, (width - 96 - 14) / len(kds), (height - 40 - 54) / len(kps)
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Simulated settling time at each design in the gain box">']
    out.append(f'<rect x="{L - 8}" y="{T - 8}" width="{cw * len(kds) + 16:.0f}" height="{ch * len(kps) + 16:.0f}" rx="12" '
               f'fill="none" stroke="#2166ac" stroke-width="3" stroke-dasharray="3 0"/>')
    out.append(f'<text x="{L - 8}" y="{T - 16}" style="font-size:18px;fill:#2166ac;font-weight:700">{box_label}</text>')
    for j, kd in enumerate(kds):
        out.append(f'<text x="{L + cw * (j + .5):.0f}" y="{height - 32}" text-anchor="middle" style="font-size:20px">{kd:g}</text>')
    out.append(f'<text x="{L + cw * len(kds) / 2:.0f}" y="{height - 6}" text-anchor="middle" style="font-size:18px;fill:#4b5563">Kd</text>')
    for i, kp in enumerate(kps):
        yy = T + ch * (i + .5)
        out.append(f'<text x="{L - 22}" y="{yy + 7:.0f}" text-anchor="end" style="font-size:20px">{kp:g}</text>')
        for j, kd in enumerate(kds):
            v = w[(kp, kd)]
            ok = v <= limit
            col = PALETTE["pass"] if ok else PALETTE["fail"]
            cx = L + cw * (j + .5)
            ring = (f'<rect x="{cx - 46:.0f}" y="{yy - 24:.0f}" width="92" height="48" rx="24" fill="none" '
                    f'stroke="#111111" stroke-width="3"/>' if mark == (kp, kd) else "")
            out.append(f'{ring}<rect x="{cx - 40:.0f}" y="{yy - 18:.0f}" width="80" height="36" rx="18" fill="{col}"/>'
                       f'<text x="{cx:.0f}" y="{yy + 7:.0f}" text-anchor="middle" style="font-size:20px;font-weight:700;'
                       f'fill:#ffffff">{v:.1f}</text>')
    out.append(f'<text transform="translate(16,{T + ch * len(kps) / 2:.0f}) rotate(-90)" text-anchor="middle" '
               f'style="font-size:18px;fill:#4b5563">Kp</text>')
    out.append("</svg>")
    return "".join(out)


def axis_bars_svg(values: dict, limit: float = 120.0, t_max: float = 140.0, width: int = 700,
                  height: int = 200, blank: bool = False) -> str:
    """Simulated settling time for a slew about each body axis (x, y, z) against the limit; the worst
    axis (the one that governs) is drawn solid, the others lighter. Blue throughout: verdict colours
    belong to verdict pills."""
    L, R = 40, 90
    pw = width - L - R
    worst = max(values, key=values.get)
    rows = list(values.items())
    # blank=True draws the empty frame: the axis names and the limit, no bars and no numbers
    rh = (height - 40) / len(rows)
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Settling time about each slew axis against the {limit:g} second limit">']
    for i, (ax, v) in enumerate(rows):
        y = 8 + rh * i
        if blank:
            out.append(f'<text x="{L - 12}" y="{y + rh * .55 + 6:.0f}" text-anchor="end" style="font-size:22px;font-weight:700">{ax}</text>'
                       f'<path d="M{L},{y + rh * .55:.0f} H{L + pw}" stroke="#e5e7eb" stroke-width="2" stroke-dasharray="3 6"/>')
            continue
        w = v / t_max * pw
        fill = PALETTE["machine"] if ax == worst else "#93b4d8"
        out.append(f'<text x="{L - 12}" y="{y + rh * .55 + 6:.0f}" text-anchor="end" style="font-size:22px;font-weight:700">{ax}</text>'
                   f'<rect x="{L}" y="{y + 4:.0f}" width="{w:.0f}" height="{rh - 14:.0f}" rx="6" fill="{fill}"/>'
                   f'<text x="{L + w + 10:.0f}" y="{y + rh * .55 + 6:.0f}" style="font-size:22px;font-weight:{700 if ax == worst else 400}">{v:.1f} s</text>')
    xl = L + limit / t_max * pw
    out.append(f'<path d="M{xl:.0f},2 V{height - 34}" stroke="#111111" stroke-width="2" stroke-dasharray="9 7"/>'
               f'<text x="{xl:.0f}" y="{height - 8}" text-anchor="middle" style="font-size:18px">{limit:g} s limit</text>')
    out.append("</svg>")
    return "".join(out)
