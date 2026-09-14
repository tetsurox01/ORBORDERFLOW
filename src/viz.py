"""Chart layer for IVB -- drawing only, no research logic.

Every function here takes data that has ALREADY been computed elsewhere and
returns a matplotlib Figure. Nothing in this file decides what a level is, what a
trade did, or whether something passed. That separation is deliberate: a picture
must never be able to disagree with the backtest.

matplotlib only, and the candles are drawn by hand, so there is no charting
dependency to debug.

Profile objects are duck-typed: anything with .centers, .weights and .bin_size
works, so this file does not import the research package.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt           # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

TICK = 0.25

C = {
    "up": "#17864f",
    "down": "#c03a2b",
    "wick_up": "#0f5c37",
    "wick_dn": "#8c281d",
    "ib_box": "#4a5568",
    "ib_line": "#2d3748",
    "zone": "#2d6cdf",
    "vah": "#7d3c98",
    "val": "#7d3c98",
    "poc": "#e08214",
    "brk": "#2d6cdf",
    "entry": "#111111",
    "stop": "#c03a2b",
    "tp1": "#17864f",
    "va_bar": "#9fb6d9",
    "bar": "#c9d3e0",
    "ref": "#888888",
    "grid": "#e3e8ee",
}

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#b8c1cc",
    "axes.grid": True,
    "grid.color": C["grid"],
    "grid.linewidth": 0.6,
    "font.size": 9,
    "axes.titlesize": 11,
    "legend.frameon": False,
})


# ----------------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------------
def draw_candles(ax, bars: pd.DataFrame, *, width: float = 0.68) -> None:
    """Manual candlesticks on an integer x axis (no weekend / session gaps)."""
    o = bars["open"].to_numpy(float)
    h = bars["high"].to_numpy(float)
    lo = bars["low"].to_numpy(float)
    c = bars["close"].to_numpy(float)
    x = np.arange(len(bars))
    up = c >= o

    span = max(h.max() - lo.min(), TICK)
    floor_h = span * 0.0012                      # keep dojis visible

    for mask, body, wick in ((up, C["up"], C["wick_up"]),
                             (~up, C["down"], C["wick_dn"])):
        if not mask.any():
            continue
        ax.vlines(x[mask], lo[mask], h[mask], color=wick, linewidth=0.7, zorder=2)
        ax.bar(x[mask], np.maximum(np.abs(c - o)[mask], floor_h),
               bottom=np.minimum(o, c)[mask], width=width,
               color=body, edgecolor=body, linewidth=0.4, zorder=3)


def time_axis(ax, bars: pd.DataFrame, *, every: int = 15) -> None:
    ts = pd.to_datetime(bars["ts_et"])
    x = np.arange(len(bars))
    keep = x[::every]
    ax.set_xticks(keep)
    ax.set_xticklabels([t.strftime("%H:%M") for t in ts.iloc[keep]], fontsize=8)
    ax.set_xlim(-1.5, len(bars) + 11)


def draw_levels(ax, items, *, xtext) -> None:
    """Horizontal lines plus right-margin labels, nudged apart so they stay readable.

    items: [(y, label, color, linestyle, linewidth), ...]
    The label always prints its TRUE price; only the text row moves.
    """
    for y, _lab, col, ls, lw in items:
        ax.axhline(y, color=col, linestyle=ls, linewidth=lw, zorder=4)

    lo, hi = ax.get_ylim()
    # one text row in DATA units, so labels never overlap at any price scale
    inv = ax.transData.inverted()
    gap = abs(inv.transform((0, 14))[1] - inv.transform((0, 0))[1])
    ordered = sorted(items, key=lambda t: t[0])

    rows, last = [], -np.inf
    for y, *_ in ordered:
        yy = max(y, last + gap)
        rows.append(yy)
        last = yy
    over = rows[-1] - (hi - gap * 0.5)
    if over > 0:
        rows = [r - over for r in rows]

    for (y, lab, col, ls, lw), yy in zip(ordered, rows):
        if abs(yy - y) > gap * 0.2:      # leader line back to the real level
            ax.plot([xtext - 0.4, xtext + 0.2], [y, yy], color=col, linewidth=0.6,
                    alpha=0.7, zorder=5)
        ax.text(xtext + 0.3, yy, " {} {:,.2f}".format(lab, y), color=col,
                fontsize=8, va="center", ha="left", zorder=6)


def draw_profile(ax, profile, *, vah=None, val=None, poc=None,
                 face=C["bar"], va_face=C["va_bar"], leftward: bool = True) -> None:
    """Horizontal histogram sharing the price axis."""
    cen = np.asarray(profile.centers, float)
    w = np.asarray(profile.weights, float)
    bs = float(profile.bin_size)

    colors = np.array([face] * len(cen), dtype=object)
    if vah is not None and val is not None:
        colors[(cen >= val) & (cen <= vah)] = va_face
    if poc is not None:
        j = int(np.argmin(np.abs(cen - poc)))
        colors[j] = C["poc"]

    ax.barh(cen, w, height=bs * 0.9, color=list(colors), edgecolor="none", zorder=2)
    if leftward:
        ax.invert_xaxis()
    ax.set_xticks([])


# ----------------------------------------------------------------------------
# CHART 1 -- one annotated session
# ----------------------------------------------------------------------------
def chart_session(bars: pd.DataFrame, levels: dict, trade: dict | None = None,
                  profile=None, *, title: str = "", subtitle: str = "") -> plt.Figure:
    """One session: IB box, fixed-range profile, levels, and the trade.

    bars    session dataframe with ts_et / open / high / low / close / volume,
            already sliced to the window that should be drawn.
    levels  ib_high, ib_low, vah, poc, val, ib_end_idx;
            optional zone_bottom, zone_top.
    trade   optional; keys are documented in scripts/04_charts.py.
    """
    if profile is not None:
        fig, (axp, ax) = plt.subplots(
            1, 2, figsize=(15.5, 9.0), sharey=True,
            gridspec_kw={"width_ratios": [1, 5.0], "wspace": 0.015})
        ax.tick_params(labelleft=False, left=False)
    else:
        fig, ax = plt.subplots(figsize=(14, 9.0))
        axp = None

    draw_candles(ax, bars)
    time_axis(ax, bars)
    n = len(bars)
    xt = n + 0.6

    # ---- initial balance box ----------------------------------------------
    ib_end = int(levels["ib_end_idx"])
    ax.add_patch(Rectangle(
        (-0.8, levels["ib_low"]), ib_end + 0.3, levels["ib_high"] - levels["ib_low"],
        facecolor=C["ib_box"], alpha=0.10, edgecolor=C["ib_box"],
        linewidth=1.0, linestyle="--", zorder=1))
    ax.text(ib_end / 2, levels["ib_high"], "  initial balance window ",
            fontsize=8, color=C["ib_line"], va="bottom", ha="center", zorder=6)

    # ---- reload zone -------------------------------------------------------
    zb = levels.get("zone_bottom")
    zt = levels.get("zone_top")
    if zb is not None and zt is not None:
        ax.axhspan(zb, zt, color=C["zone"], alpha=0.15, zorder=1)
        ax.text(ib_end + 1, (zb + zt) / 2, " reload zone", fontsize=8,
                color=C["zone"], va="center", ha="left", zorder=6)

    # ---- levels ------------------------------------------------------------
    level_items = [
        (levels["ib_high"], "IB_high", C["ib_line"], "-", 1.4),
        (levels["ib_low"], "IB_low", C["ib_line"], "-", 1.4),
        (levels["vah"], "VAH", C["vah"], "--", 1.2),
        (levels["poc"], "POC", C["poc"], "-", 1.6),
        (levels["val"], "VAL", C["val"], "--", 1.2),
    ]
    note_lines: list[str] = []

    # ---- trade -------------------------------------------------------------
    if trade:
        d = trade["direction"]
        bi = trade.get("breakout_idx")
        if bi is not None:
            y = bars["high"].iloc[bi] if d == 1 else bars["low"].iloc[bi]
            ax.plot([bi], [y], marker="^" if d == 1 else "v", markersize=13,
                    color=C["brk"], zorder=7)
            ax.annotate("breakout", (bi, y), textcoords="offset points",
                        xytext=(0, 16 if d == 1 else -22), ha="center",
                        fontsize=8, color=C["brk"], zorder=7)

        ei = trade.get("entry_idx")
        if ei is not None:
            level_items += [
                (trade["stop_price"], "HARD STOP", C["stop"], ":", 1.6),
                (trade["tp1_price"], "TP1", C["tp1"], ":", 1.6),
            ]
            # the invalidation level IS the far VA boundary, already drawn above
            ax.plot([ei], [trade["entry_price"]], marker="o", markersize=9,
                    markerfacecolor="white", markeredgecolor=C["entry"],
                    markeredgewidth=1.8, zorder=8)
            ax.annotate("limit entry", (ei, trade["entry_price"]),
                        textcoords="offset points", xytext=(8, 12),
                        fontsize=8, color=C["entry"], zorder=8)

            xi = trade.get("exit_idx")
            if xi is not None:
                ok = trade["exit_reason"] == "target"
                ax.plot([xi], [trade["exit_price"]], marker="*" if ok else "X",
                        markersize=16 if ok else 11,
                        color=C["tp1"] if ok else C["stop"], zorder=8)
                ax.annotate("exit: " + trade["exit_reason"],
                            (xi, trade["exit_price"]), textcoords="offset points",
                            xytext=(8, -16), fontsize=8,
                            color=C["tp1"] if ok else C["stop"], zorder=8)
                ax.plot([ei, xi], [trade["entry_price"], trade["exit_price"]],
                        color="#555555", linewidth=1.0, alpha=0.6, zorder=6)

            note_lines += [
                "direction      {}".format("LONG" if d == 1 else "SHORT"),
                "entry          {:,.2f}   (limit at {})".format(
                    trade["entry_price"], "VAH" if d == 1 else "VAL"),
                "invalidation   {:,.2f}   (first 5-min CLOSE beyond {})".format(
                    trade.get("inval_price", float("nan")),
                    "VAL" if d == 1 else "VAH"),
                "hard stop      {:,.2f}   (sec c.1, whichever fires first)".format(
                    trade["stop_price"]),
                "risk_R         {:,.2f} pt  ({:,.0f} ticks)   measured to the "
                "HARD stop (sec c.2)".format(
                    trade["risk_points"], trade["risk_points"] / TICK),
                "TP1            {:,.2f}   ({:.2f}R)".format(
                    trade["tp1_price"], trade["tp1_r"]),
                "achieved       {:+.2f}R  ({:+,.2f} pt net)".format(
                    trade["r_multiple"], trade["net_points"]),
            ]
            if trade.get("touch_only_fill"):
                note_lines.append(
                    "WARNING        touch-only fill: the bar grazed the limit and "
                    "never traded through it.")
                note_lines.append(
                    "               Assumes front-of-queue. sec b.7 says re-run "
                    "with require_penetration_ticks = 1.")
        else:
            note_lines += [
                "direction      {}".format("LONG" if d == 1 else "SHORT"),
                "entry          NONE -- reload zone never touched",
                "reason         {}".format(trade.get("no_fill_reason", "no_fill")),
                "Layer 1 sits out. Layer 0 holds this move.",
            ]

    # ---- profile margin ----------------------------------------------------
    if profile is not None:
        draw_profile(axp, profile, vah=levels["vah"], val=levels["val"],
                     poc=levels["poc"])
        axp.set_title("IB volume profile", fontsize=9, color="#555555")
        axp.set_ylabel("price (NQ index points)")
        axp.grid(False)
        for side in ("top", "left", "bottom"):
            axp.spines[side].set_visible(False)
    else:
        ax.set_ylabel("price (NQ index points)")

    ax.set_xlabel("time, ET (1-minute bars)")

    fig.subplots_adjust(left=0.055, right=0.905, top=0.895,
                        bottom=0.05 + 0.021 * len(note_lines))

    # levels LAST: the label nudging needs the final axes box and y limits
    draw_levels(ax, level_items, xtext=xt)

    if note_lines:
        fig.text(0.055, 0.012, "\n".join(note_lines), fontsize=9,
                 family="monospace", va="bottom", ha="left",
                 bbox=dict(boxstyle="round,pad=0.55", facecolor="#f7f9fb",
                           edgecolor="#b8c1cc"))

    fig.suptitle(title, fontsize=13, y=0.982)
    if subtitle:
        fig.text(0.5, 0.948, subtitle, fontsize=9, color="#555555", ha="center")
    return fig


# ----------------------------------------------------------------------------
# CHART 2 -- sec b.9 allocation sensitivity
# ----------------------------------------------------------------------------
def chart_profile_methods(profiles: dict, *, reference: str | None = None,
                          labels: dict | None = None, spreads: dict | None = None,
                          title: str = "", subtitle: str = "") -> plt.Figure:
    """One session, one panel per allocation method, VAH / POC / VAL on each."""
    keys = list(profiles)
    fig, axes = plt.subplots(1, len(keys), figsize=(15.5, 7.6), sharey=True)
    axes = np.atleast_1d(axes)

    ref = profiles.get(reference) if reference else None

    for ax, k in zip(axes, keys):
        p = profiles[k]
        draw_profile(ax, p, vah=p.vah, val=p.val, poc=p.poc, leftward=False)
        ax.grid(False)

        if ref is not None and k != reference:
            for y in (ref.vah, ref.val):
                ax.axhline(y, color=C["ref"], linestyle=(0, (2, 3)), linewidth=1.0,
                           zorder=3)

        for y, lab, col, ls in ((p.vah, "VAH", C["vah"], "--"),
                                (p.poc, "POC", C["poc"], "-"),
                                (p.val, "VAL", C["val"], "--")):
            ax.axhline(y, color=col, linestyle=ls, linewidth=1.5, zorder=4)
            # white plate: the POC label would otherwise sit on the orange POC bar
            ax.text(0.985, y, "{} {:,.2f}".format(lab, y),
                    transform=ax.get_yaxis_transform(), ha="right", va="bottom",
                    fontsize=8, color=col, zorder=6,
                    bbox=dict(boxstyle="square,pad=0.18", facecolor="white",
                              edgecolor="none", alpha=0.88))

        name = (labels or {}).get(k, k)
        if ref is not None and k != reference:
            name += "\nvs ref:  VAH {:+.0f} tk   VAL {:+.0f} tk".format(
                (p.vah - ref.vah) / TICK, (p.val - ref.val) / TICK)
        elif ref is not None:
            name += "\n(reference; grey dashes on the other panels)"
        ax.set_title(name, fontsize=9)
        ax.set_xticks([])
        ax.tick_params(left=(ax is axes[0]))

    axes[0].set_ylabel("price (NQ index points)")
    if spreads:
        txt = "   ".join("{} = {:.0f} ticks".format(k, v) for k, v in spreads.items())
        fig.text(0.5, 0.035, "session spread (max - min across M1-M4):  " + txt,
                 ha="center", fontsize=9, family="monospace", color="#333333")

    fig.suptitle(title, fontsize=13, y=0.975)
    if subtitle:
        fig.text(0.5, 0.925, subtitle, fontsize=9, color="#555555", ha="center")
    fig.tight_layout(rect=(0, 0.07, 1, 0.905))
    return fig


# ----------------------------------------------------------------------------
# CHART 3 -- sample funnel
# ----------------------------------------------------------------------------
def chart_funnel(stages: list, *, title: str = "", subtitle: str = "",
                 notes: list | None = None) -> plt.Figure:
    """Horizontal funnel from [(label, count), ...], widest first."""
    labels = [s[0] for s in stages]
    counts = [int(s[1]) for s in stages]
    top = counts[0] if counts and counts[0] else 1
    y = np.arange(len(counts))[::-1]

    fig, ax = plt.subplots(figsize=(12.5, 1.35 * len(counts) + 3.0))
    shades = ["#2d6cdf", "#5b8fe6", "#8bb2ee", "#b6cef5", "#d7e4fa"]
    ax.barh(y, counts, height=0.58,
            color=[shades[i % len(shades)] for i in range(len(counts))],
            edgecolor="none")

    for i, (yy, c) in enumerate(zip(y, counts)):
        of_prev = ("   {:5.1f}% of previous".format(100.0 * c / counts[i - 1])
                   if i and counts[i - 1] else "")
        ax.text(c + top * 0.012, yy,
                "{:,}   ({:5.1f}% of S_all){}".format(c, 100.0 * c / top, of_prev),
                va="center", ha="left", fontsize=9.5, family="monospace")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlim(0, top * 1.45)
    ax.set_xlabel("sessions")
    ax.grid(axis="y", visible=False)

    if notes:
        fig.text(0.012, 0.02, "\n".join(notes), fontsize=8.5, color="#555555",
                 family="monospace", va="bottom")

    fig.suptitle(title, fontsize=13, y=0.98)
    if subtitle:
        fig.text(0.5, 0.925, subtitle, fontsize=9, color="#555555", ha="center")
    fig.tight_layout(rect=(0, 0.10 if notes else 0.02, 1, 0.90))
    return fig


# ----------------------------------------------------------------------------
# CHART 4 -- MFE distribution and TP1
# ----------------------------------------------------------------------------
def chart_mfe(mfe, *, tp1: float, ci=None, pct: float = 32.5, bins: int = 60,
              title: str = "", subtitle: str = "", notes: list | None = None
              ) -> plt.Figure:
    """Histogram of MFE-before-stop with TP1 at the pct-th percentile.

    TP1 sits in the LOWER tail on purpose: a target reached ~67.5% of the time is
    the 32.5th percentile of the excursion distribution, not the 67.5th.
    """
    m = np.asarray(mfe, float)
    m = m[np.isfinite(m)]

    fig, ax = plt.subplots(figsize=(13, 7.4))
    ax.hist(m, bins=bins, color="#b6cef5", edgecolor="#7fa4dd", linewidth=0.5)

    if ci is not None and np.isfinite(ci[0]) and np.isfinite(ci[1]):
        ax.axvspan(ci[0], ci[1], color=C["tp1"], alpha=0.16, zorder=2,
                   label="95% block-bootstrap CI  [{:,.2f}, {:,.2f}]".format(*ci))

    ax.axvline(tp1, color=C["tp1"], linewidth=2.2, zorder=4,
               label="TP1 = {:.1f}th pct = {:,.2f} pt".format(pct, tp1))
    med = float(np.median(m)) if len(m) else np.nan
    ax.axvline(med, color=C["poc"], linewidth=1.4, linestyle="--", zorder=4,
               label="median = {:,.2f} pt".format(med))

    hit = 100.0 * (m >= tp1).mean() if len(m) else np.nan
    ax.text(0.985, 0.965,
            "n = {:,}\nMFE >= TP1 in {:.1f}% of trades".format(len(m), hit),
            transform=ax.transAxes, ha="right", va="top", fontsize=9.5,
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#b8c1cc"))

    ax.set_xlabel("MFE before stop (index points, pessimistic intrabar)")
    ax.set_ylabel("trades")
    ax.legend(loc="upper right", bbox_to_anchor=(0.985, 0.86), fontsize=9)

    if notes:
        fig.text(0.012, 0.02, "\n".join(notes), fontsize=8.5, color="#555555",
                 family="monospace", va="bottom")

    fig.suptitle(title, fontsize=13, y=0.98)
    if subtitle:
        fig.text(0.5, 0.928, subtitle, fontsize=9, color="#555555", ha="center")
    fig.tight_layout(rect=(0, 0.10 if notes else 0.02, 1, 0.91))
    return fig


# ----------------------------------------------------------------------------
# CHART 5 -- Layer 3 cell counts
# ----------------------------------------------------------------------------
def chart_cell_counts(counts_by_design: dict, *, min_obs: int, title: str = "",
                      subtitle: str = "", notes: list | None = None) -> plt.Figure:
    """One panel per bucket design. Cells under min_obs are drawn in red."""
    designs = list(counts_by_design)
    widths = [max(1, len(counts_by_design[d])) for d in designs]
    fig, axes = plt.subplots(1, len(designs), figsize=(15.5, 7.4),
                             gridspec_kw={"width_ratios": widths})
    axes = np.atleast_1d(axes)

    for ax, d in zip(axes, designs):
        cells = counts_by_design[d]
        names = list(cells)
        vals = np.array([cells[k] for k in names], float)
        short = vals < min_obs
        ax.bar(np.arange(len(vals)), vals, width=0.72,
               color=np.where(short, C["down"], "#5b8fe6"), edgecolor="none")
        ax.axhline(min_obs, color=C["ib_line"], linestyle="--", linewidth=1.4,
                   zorder=5)
        ax.text(len(vals) - 0.4, min_obs,
                " min_obs_per_bucket = {}".format(min_obs),
                fontsize=8.5, va="bottom", ha="right", color=C["ib_line"])
        ax.set_xticks(np.arange(len(vals)))
        ax.set_xticklabels(names, rotation=90, fontsize=7.5)
        ax.set_title("{}\n{} of {} cells below threshold".format(
            d, int(short.sum()), len(vals)), fontsize=9.5)
        ax.grid(axis="x", visible=False)

    axes[0].set_ylabel("observations per cell")
    if notes:
        fig.text(0.012, 0.02, "\n".join(notes), fontsize=8.5, color="#555555",
                 family="monospace", va="bottom")

    fig.suptitle(title, fontsize=13, y=0.98)
    if subtitle:
        fig.text(0.5, 0.928, subtitle, fontsize=9, color="#555555", ha="center")
    fig.tight_layout(rect=(0, 0.10 if notes else 0.02, 1, 0.91))
    return fig


# ----------------------------------------------------------------------------
def save(fig: plt.Figure, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=140, facecolor="white")
    plt.close(fig)
    return p
