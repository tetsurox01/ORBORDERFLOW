"""Fixed-range volume profile over the initial balance -- IVB-SPEC.md sec (b).

Implements sec b.2 (binning + the four allocation methods of sec b.9), sec b.3
(POC and the 70% value area by standard expansion) and sec b.6 (the reload zone).

STATUS: written to make sec b.9 visible on a chart. It is a faithful transcription
of the spec, but it has NOT yet been through a synthetic unit-test suite the way
backtest.py has. Before any Layer 1 PnL is reported from it, it needs its own tests
(hand-built profiles with a known POC / VAH / VAL).

Every method here is an ALLOCATION ASSUMPTION over a quantity that 1-minute OHLCV
does not resolve: we know a bar's total volume and its [low, high], never where
inside that range the volume traded. That is exactly why sec b.9 is a gate.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import TICK_SIZE

# sec b.2 / b.3 / b.6 defaults
DEFAULT_VA_PCT = 0.70
MIN_ZONE_WIDTH = 2 * TICK_SIZE

# --------------------------------------------------------------------------
# sec b.2  BIN WIDTH IS RELATIVE -- RULE A, AMENDED 2026-09-15
# --------------------------------------------------------------------------
# A bin width fixed in POINTS is not the same object at both ends of the sample,
# so the width must be relative. That part of sec b.2 stands and is unchanged.
#
# WHAT CHANGED, AND WHY. The original pre-registered primary was
#
#     bin_width = median 1-minute bar range over THIS session's IB window
#
# It is scale-invariant, exactly as registered -- measured r(bins_across_IB,
# price) = -0.019 over 2,365 sessions, 2015-2026, across a 6.3x move in NQ. It is
# also uselessly COARSE, and was coarse in 2015 too. The reason is arithmetic,
# not drift: for a near-random walk the range of N bars is ~sqrt(N) bar heights,
# so setting bin = median bar height yields ~sqrt(30) = 5.5 bins for a 30-minute
# IB at ANY price in ANY regime. Measured p50 of ib_range / med_ib_bar_range =
# 5.85 against sqrt(30) = 5.48. 96.0% of sessions had under 10 bins. A POC, a VAH
# and a VAL resolved on a 5-bin histogram are not locations, they are noise.
# No multiplier rescues this: the whole {0.5, 1.0, 2.0} axis spans 2.7 to 11 bins.
#
# The original rule's own REGISTERED WEAKNESS ("the median bar spans ~1 bin BY
# CONSTRUCTION", which pushes the sec b.9 gate mechanically toward 'not
# material') is the same fact stated from the other side. Removing the coarseness
# and removing the rigged gate are one action, not two.
#
# AMENDED PRIMARY (RULE A):
#
#     bin_width = (IB_high - IB_low) / N,  N = 20,
#                 rounded to the nearest tick (half-up), floored at 1 tick
#
# Still per session. Still computed from IB bars alone, so still known at IB
# close and still carries NO lookahead. Still scale-invariant -- and now also
# invariant to volatility, which the old rule was not: bins-across-IB is 20 by
# construction instead of 5.9 by accident.
#
# THE COST, STATED IN ADVANCE -- READ BEFORE BELIEVING A sec b.9 VERDICT.
# The median 1-minute IB bar now spans ~3.4 bins instead of ~1. sec b.9 records
# that the four allocation methods AGREE when a bar spans about one bin. That
# agreement was previously manufactured by the bin rule. Under Rule A it is not.
# sec b.9 therefore becomes a real gate for the first time, AND IT MAY NOW FAIL.
# A sec b.9 failure under Rule A is evidence about Layer 1, not evidence against
# Rule A, and must not be used to argue the old rule back.
#
# PROVENANCE -- THIS IS NOT A BLIND PRE-REGISTRATION ANY MORE.
# The original rule was fixed before any real bar was loaded. THIS ONE WAS NOT:
# N = 20 was chosen on 2026-09-15 after the bin-grid census had been computed on
# real bars (scripts/07_bin_grid_census.py). It was chosen on GEOMETRY ONLY --
# no PnL, no win rate, no expectancy, no sec b.9 verdict was computed under any
# candidate rule before the choice, and 07_bin_grid_census.py deliberately does
# not import run_strategy. That limits the selection risk; it does not remove it.
# Every Layer 1 output produced under the old rule is VOID. See IVB-SPEC.md
# sec b.2 AMENDMENT 1.
BIN_WIDTH_RULE = "ib_range_over_n"
BIN_WIDTH_N = 20                     # PRIMARY. bins across the IB, by construction.
BIN_WIDTH_MULT = 1.0                 # PRIMARY. {0.5, 1.0, 2.0} is the sensitivity.
BIN_WIDTH_FLOOR_TICKS = 1
BIN_WIDTH_MULT_GRID = (0.5, 1.0, 2.0)
# The multiplier now reads as an EFFECTIVE BIN COUNT: mult = 0.5 -> ~40 bins,
# mult = 2.0 -> ~10 bins. Wider bin, fewer bins. Reported, never selected.

# Superseded rules. NOT primaries. Kept only so the old worlds can be run as
# labelled sensitivities (sec g.0.1) and compared against.
SUPERSEDED_BIN_WIDTH_RULE = "median_ib_bar_range"   # the original sec b.2 primary
FIXED_BIN_SIZE_SENSITIVITY = 1.0                    # points; the pre-relative default


def median_ib_bar_range_width(ib_bars: pd.DataFrame, *, mult: float = 1.0,
                              floor_ticks: int = BIN_WIDTH_FLOOR_TICKS) -> float:
    """SUPERSEDED sec b.2 primary, kept as a labelled sensitivity only.

    Retained so "what the old rule would have said" is still computable and
    comparable. Never call this as the primary.
    """
    rng = (ib_bars["high"].to_numpy(float) - ib_bars["low"].to_numpy(float))
    med = float(np.median(rng)) if len(rng) else 0.0
    n_ticks = int(np.floor(med * mult / TICK_SIZE + 0.5))
    return max(int(floor_ticks), n_ticks) * TICK_SIZE


def bin_width(ib_bars: pd.DataFrame, *, mult: float = BIN_WIDTH_MULT,
              floor_ticks: int = BIN_WIDTH_FLOOR_TICKS,
              n_bins: int = BIN_WIDTH_N) -> float:
    """sec b.2 RULE A bin width, in points, for ONE session's IB window.

    bin_width = (IB_high - IB_low) / n_bins, scaled by `mult`, rounded half-up to
    the nearest tick, floored at 1 tick.

    Rounding is half-up and explicit -- numpy rounds halves to even, which would
    make the width depend on the parity of the tick count.
    """
    if not len(ib_bars):
        return max(int(floor_ticks), 1) * TICK_SIZE
    ib_range = float(ib_bars["high"].max()) - float(ib_bars["low"].min())
    raw = ib_range / float(n_bins)
    n_ticks = int(np.floor(raw * mult / TICK_SIZE + 0.5))
    return max(int(floor_ticks), n_ticks) * TICK_SIZE


def resolve_bin_size(ib_bars: pd.DataFrame, bin_size: float | None,
                     *, mult: float = BIN_WIDTH_MULT) -> float:
    """`None` means 'apply the pre-registered rule'. A float is an explicit
    override and is only ever a labelled sensitivity (sec g.0.1).
    """
    if bin_size is None:
        return bin_width(ib_bars, mult=mult)
    return float(bin_size)

METHODS = ("volume_uniform", "volume_triangular", "volume_close_only", "tpo_minute")
METHOD_LABELS = {
    "volume_uniform": "M1 volume_uniform (primary)",
    "volume_triangular": "M2 volume_triangular",
    "volume_close_only": "M3 volume_close_only",
    "tpo_minute": "M4 tpo_minute (control)",
}


@dataclass(frozen=True)
class Profile:
    method: str
    bin_size: float
    edges: np.ndarray      # len n+1
    centers: np.ndarray    # len n
    weights: np.ndarray    # len n -- volume, or bar count for tpo_minute
    poc: float
    vah: float
    val: float
    va_pct: float

    @property
    def total(self) -> float:
        return float(self.weights.sum())


def _bins(ib_low: float, ib_high: float, bin_size: float) -> tuple[np.ndarray, np.ndarray]:
    """Grid ANCHORED AT ib_low -- defect C2, fixed 2026-09-15.

    It used to be  lo = floor(ib_low / bin_size) * bin_size, i.e. a grid counted
    from ABSOLUTE PRICE ZERO. value_area() returns VAH / VAL as bin EDGES, so the
    outermost bins hung outside the IB window by up to one bin_size per side and
    a value-area edge could be reported OUTSIDE the initial balance that defines
    it. Measured over 2,365 sessions: VAH > IB_high on 26.0%, VAL < IB_low on
    22.6%, either on 46.6%. Worst case was bounded at 0.9844 bin_size, exactly as
    the mechanism predicts. The magnitude tracked the bin width, so the same
    defect was +1.75 pt in 2015 (invisible on a chart) and +27.25 pt in 2026.

    Anchoring at ib_low makes edges[0] == ib_low EXACTLY, so the low side can no
    longer hang out at all. The high side still needs a whole number of equal
    bins to cover the range, so edges[-1] may sit up to one bin_size above
    ib_high; value_area() clamps the reported VAH/VAL/POC into [ib_low, ib_high]
    to close that. The grid itself stays uniform, which _span() relies on.
    """
    lo = float(ib_low)
    span = float(ib_high) - lo
    # tolerance so an exact multiple does not buy a spurious extra empty bin
    n = int(np.ceil(span / bin_size - 1e-9))
    n = max(n, 1)
    edges = lo + np.arange(n + 1) * bin_size
    return edges, edges[:-1] + bin_size / 2.0


def _span(low: float, high: float, edges: np.ndarray, bin_size: float) -> tuple[int, int]:
    """Inclusive bin index range overlapped by [low, high]."""
    n = len(edges) - 1
    i0 = int(np.clip(np.floor((low - edges[0]) / bin_size), 0, n - 1))
    i1 = int(np.clip(np.floor((high - edges[0]) / bin_size), 0, n - 1))
    # a high sitting exactly on an edge belongs to the bin below it
    if i1 > i0 and np.isclose(high, edges[i1]):
        i1 -= 1
    return i0, max(i0, i1)


def allocate(ib_bars: pd.DataFrame, method: str, *, bin_size: float | None = None,
             bin_mult: float = BIN_WIDTH_MULT
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Distribute each IB bar into price bins under one allocation method.

    Returns (edges, centers, weights).
    """
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")

    bin_size = resolve_bin_size(ib_bars, bin_size, mult=bin_mult)
    ib_low = float(ib_bars["low"].min())
    ib_high = float(ib_bars["high"].max())
    edges, centers = _bins(ib_low, ib_high, bin_size)
    w = np.zeros(len(centers))

    lows = ib_bars["low"].to_numpy(float)
    highs = ib_bars["high"].to_numpy(float)
    closes = ib_bars["close"].to_numpy(float)
    vols = ib_bars["volume"].to_numpy(float)

    for l, h, c, v in zip(lows, highs, closes, vols):
        i0, i1 = _span(l, h, edges, bin_size)
        k = i1 - i0 + 1

        if method == "volume_uniform":                      # M1
            w[i0:i1 + 1] += v / k

        elif method == "volume_triangular":                 # M2
            p = (h + l + c) / 3.0
            x = centers[i0:i1 + 1]
            up = np.where(x <= p,
                          (x - l) / (p - l) if p > l else 1.0,
                          (h - x) / (h - p) if h > p else 1.0)
            up = np.clip(up, 0.0, None)
            s = up.sum()
            w[i0:i1 + 1] += (v * up / s) if s > 0 else (v / k)

        elif method == "volume_close_only":                 # M3
            j, _ = _span(c, c, edges, bin_size)
            w[j] += v

        else:                                               # M4 tpo_minute
            w[i0:i1 + 1] += 1.0

    return edges, centers, w


def value_area(centers: np.ndarray, weights: np.ndarray, edges: np.ndarray,
               *, va_pct: float = DEFAULT_VA_PCT,
               ib_low: float | None = None,
               ib_high: float | None = None) -> tuple[float, float, float]:
    """POC, VAH, VAL by the standard 2-bin expansion of sec b.3.

    `ib_low` / `ib_high` are the TRUE initial balance extremes. VAH, VAL and POC
    are CLAMPED into [ib_low, ib_high] -- defect C2, see _bins(). A value-area
    edge outside the window that defines it is not a location, it is a grid
    artefact. They default to the grid extremes, which is a no-op for a caller
    that passes a hand-built grid.
    """
    lo_b = float(edges[0]) if ib_low is None else float(ib_low)
    hi_b = float(edges[-1]) if ib_high is None else float(ib_high)

    def clamp(x: float) -> float:
        return float(min(max(x, lo_b), hi_b))

    total = float(weights.sum())
    if total <= 0:
        mid = float(centers[len(centers) // 2])
        return clamp(mid), clamp(float(edges[-1])), clamp(float(edges[0]))

    # POC: max weight; tie -> bin closest to IB mid; still tied -> lower bin
    mx = weights.max()
    tied = np.flatnonzero(np.isclose(weights, mx))
    ib_mid = (lo_b + hi_b) / 2.0
    poc_i = int(tied[np.lexsort((tied, np.abs(centers[tied] - ib_mid)))[0]])

    lo_i = hi_i = poc_i
    cum = float(weights[poc_i])
    target = va_pct * total
    n = len(weights)

    while cum < target and (lo_i > 0 or hi_i < n - 1):
        up = float(weights[hi_i + 1:hi_i + 3].sum()) if hi_i < n - 1 else -1.0
        dn = float(weights[max(0, lo_i - 2):lo_i].sum()) if lo_i > 0 else -1.0
        if up < 0 and dn < 0:
            break
        if up >= dn:                       # tie -> upper pair (sec b.3)
            new_hi = min(n - 1, hi_i + 2)
            cum += float(weights[hi_i + 1:new_hi + 1].sum())
            hi_i = new_hi
        else:
            new_lo = max(0, lo_i - 2)
            cum += float(weights[new_lo:lo_i].sum())
            lo_i = new_lo

    return clamp(float(centers[poc_i])), clamp(float(edges[hi_i + 1])), clamp(float(edges[lo_i]))


def build_profile(ib_bars: pd.DataFrame, *, method: str = "volume_uniform",
                  bin_size: float | None = None,
                  bin_mult: float = BIN_WIDTH_MULT,
                  va_pct: float = DEFAULT_VA_PCT) -> Profile:
    """`bin_size=None` applies the sec b.2 pre-registered relative rule."""
    bin_size = resolve_bin_size(ib_bars, bin_size, mult=bin_mult)
    edges, centers, w = allocate(ib_bars, method, bin_size=bin_size)
    poc, vah, val = value_area(centers, w, edges, va_pct=va_pct,
                               ib_low=float(ib_bars["low"].min()),
                               ib_high=float(ib_bars["high"].max()))
    return Profile(method=method, bin_size=bin_size, edges=edges, centers=centers,
                   weights=w, poc=poc, vah=vah, val=val, va_pct=va_pct)


def reload_zone(direction: int, poc: float, vah: float, val: float
                ) -> tuple[float, float, bool]:
    """sec b.6. Returns (zone_bottom, zone_top, degenerate)."""
    if direction == 1:
        bot, top = poc, vah
    else:
        bot, top = val, poc
    degenerate = (top - bot) < MIN_ZONE_WIDTH
    if degenerate:
        mid = (top + bot) / 2.0
        bot, top = mid - MIN_ZONE_WIDTH / 2.0, mid + MIN_ZONE_WIDTH / 2.0
    return bot, top, degenerate


def method_spread(profiles: dict[str, Profile]) -> dict[str, float]:
    """sec b.9 per-session spreads (max - min across methods), in TICKS."""
    def sp(vals):
        return (max(vals) - min(vals)) / TICK_SIZE

    pocs = [p.poc for p in profiles.values()]
    vahs = [p.vah for p in profiles.values()]
    vals = [p.val for p in profiles.values()]
    risks = [p.vah - p.val for p in profiles.values()]
    return {"d_POC": sp(pocs), "d_VAH": sp(vahs), "d_VAL": sp(vals),
            "d_risk": sp(risks)}
