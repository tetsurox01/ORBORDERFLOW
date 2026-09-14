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
DEFAULT_BIN_SIZE = 1.0        # points (4 ticks)
DEFAULT_VA_PCT = 0.70
MIN_ZONE_WIDTH = 2 * TICK_SIZE

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
    lo = np.floor(ib_low / bin_size) * bin_size
    hi = np.ceil(ib_high / bin_size) * bin_size
    if hi <= lo:
        hi = lo + bin_size
    n = int(round((hi - lo) / bin_size))
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


def allocate(ib_bars: pd.DataFrame, method: str, *, bin_size: float = DEFAULT_BIN_SIZE
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Distribute each IB bar into price bins under one allocation method.

    Returns (edges, centers, weights).
    """
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")

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
               *, va_pct: float = DEFAULT_VA_PCT) -> tuple[float, float, float]:
    """POC, VAH, VAL by the standard 2-bin expansion of sec b.3."""
    total = float(weights.sum())
    if total <= 0:
        mid = float(centers[len(centers) // 2])
        return mid, float(edges[-1]), float(edges[0])

    # POC: max weight; tie -> bin closest to IB mid; still tied -> lower bin
    mx = weights.max()
    tied = np.flatnonzero(np.isclose(weights, mx))
    ib_mid = (edges[0] + edges[-1]) / 2.0
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

    return float(centers[poc_i]), float(edges[hi_i + 1]), float(edges[lo_i])


def build_profile(ib_bars: pd.DataFrame, *, method: str = "volume_uniform",
                  bin_size: float = DEFAULT_BIN_SIZE,
                  va_pct: float = DEFAULT_VA_PCT) -> Profile:
    edges, centers, w = allocate(ib_bars, method, bin_size=bin_size)
    poc, vah, val = value_area(centers, w, edges, va_pct=va_pct)
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
