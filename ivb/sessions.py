"""Session assembly: initial balance, breakout detection, features.

Every feature here is computable at breakout time or from PRIOR sessions only.
No same-day forward information. See IVB-SPEC.md sec (e).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import TICK_SIZE, Config

FULL_RTH_BARS = 390
HALF_DAY_MAX_BARS = 250   # below this a session is treated as a half day


@dataclass
class Session:
    session_date: pd.Timestamp
    bars: pd.DataFrame          # RTH bars 09:30..15:59, index reset
    ib_high: float
    ib_low: float
    ib_range: float
    ib_close_idx: int           # first index eligible for a breakout
    trade_end_idx: int          # last index that may hold a position
    is_half_day: bool
    roll_day_flag: bool
    # Cached numpy views. The simulator is called ~500k times by the C2 shuffle,
    # so pandas .loc in the inner loop is the difference between minutes and hours.
    op: np.ndarray = None
    hi: np.ndarray = None
    lo: np.ndarray = None
    cl: np.ndarray = None
    _bo_cache: dict | None = None

    def __post_init__(self):
        if self.op is None:
            self.op = self.bars["open"].to_numpy(dtype=np.float64)
            self.hi = self.bars["high"].to_numpy(dtype=np.float64)
            self.lo = self.bars["low"].to_numpy(dtype=np.float64)
            self.cl = self.bars["close"].to_numpy(dtype=np.float64)


def daily_features(adj: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Cross-session features from the RATIO-ADJUSTED series (sec 0.1.3).

    All are shifted so that session s only ever sees data strictly before s.
    """
    s = adj.sort_values("session_date").reset_index(drop=True).copy()
    tr = pd.concat([
        s["adj_high"] - s["adj_low"],
        (s["adj_high"] - s["adj_close"].shift()).abs(),
        (s["adj_low"] - s["adj_close"].shift()).abs(),
    ], axis=1).max(axis=1)

    # shift(1): ATR as known BEFORE the session opens.
    s["atr14"] = tr.rolling(cfg.atr_period).mean().shift(1)
    s["prior_close_adj"] = s["adj_close"].shift(1)
    rng = (s["adj_high"] - s["adj_low"]).replace(0, np.nan)
    s["prior_day_type"] = ((s["adj_close"] - s["adj_open"]).abs() / rng).shift(1)
    return s[["session_date", "atr14", "prior_close_adj", "prior_day_type"]]


def build_sessions(front: pd.DataFrame, cfg: Config) -> list[Session]:
    """Slice front-month bars into RTH sessions and compute the initial balance."""
    hm = front["ts_et"].dt.strftime("%H:%M")
    rth = front[(hm >= "09:30") & (hm <= "15:59")].copy()
    rth["hm"] = hm[rth.index]

    ib_end_min = 9 * 60 + 30 + cfg.ib_minutes
    ib_end_hm = f"{ib_end_min // 60:02d}:{ib_end_min % 60:02d}"
    end_hm = cfg.trade_end.strftime("%H:%M")

    out: list[Session] = []
    for date, g in rth.groupby("session_date", sort=True):
        g = g.sort_values("ts_et").reset_index(drop=True)
        is_half = len(g) < HALF_DAY_MAX_BARS

        ib = g[g["hm"] < ib_end_hm]
        if len(ib) < max(5, cfg.ib_minutes // 3):
            continue  # not enough bars to define an IB at all

        eligible = g.index[g["hm"] >= ib_end_hm]
        if len(eligible) == 0:
            continue
        ib_close_idx = int(eligible[0])

        before_end = g.index[g["hm"] < end_hm]
        trade_end_idx = int(before_end[-1])
        if trade_end_idx <= ib_close_idx:
            continue

        out.append(Session(
            session_date=pd.Timestamp(date),
            bars=g,
            ib_high=float(ib["high"].max()),
            ib_low=float(ib["low"].min()),
            ib_range=float(ib["high"].max() - ib["low"].min()),
            ib_close_idx=ib_close_idx,
            trade_end_idx=trade_end_idx,
            is_half_day=is_half,
            roll_day_flag=bool(g["roll_day_flag"].iloc[0]) if "roll_day_flag" in g else False,
        ))
    return out


def find_breakout(s: Session, cfg: Config, _cache: dict | None = None) -> dict | None:
    """First IB break of the session. One shot (sec a.3). Vectorised.

    Returns None if no break occurs before the trade-end bar.
    Result is memoised per (session, trigger, buffer, entry_fill) because the C2
    shuffle asks for it 1000 times and the answer never changes.
    """
    key = (cfg.breakout_trigger, cfg.breakout_buffer_ticks, cfg.entry_fill)
    if s._bo_cache is not None and key in s._bo_cache:
        return s._bo_cache[key]

    buf = cfg.buffer_points
    up_lvl = s.ib_high + buf
    dn_lvl = s.ib_low - buf

    a, b = s.ib_close_idx, s.trade_end_idx + 1
    if cfg.breakout_trigger == "close_through":
        up_arr = s.cl[a:b] > up_lvl
        dn_arr = s.cl[a:b] < dn_lvl
    else:  # trade_through
        up_arr = s.hi[a:b] >= up_lvl
        dn_arr = s.lo[a:b] <= dn_lvl

    any_arr = up_arr | dn_arr
    hits = np.flatnonzero(any_arr)
    result: dict | None = None

    if len(hits):
        j = int(hits[0])
        idx = a + j
        up, dn = bool(up_arr[j]), bool(dn_arr[j])

        if up and dn:
            # Both sides satisfied in one bar. Pessimistic: the sequence is
            # unknowable, so the session is unusable rather than guessed at.
            result = {"ambiguous_breakout": True, "signal_idx": idx,
                      "direction": 0, "entry_idx": None, "entry_price": np.nan,
                      "brk_delay_min": j}
        else:
            direction = 1 if up else -1
            if cfg.entry_fill == "next_bar_open":
                entry_idx = idx + 1
                if entry_idx > s.trade_end_idx:
                    result = None  # broke on the last bar; no time to enter
                else:
                    result = {"ambiguous_breakout": False, "signal_idx": idx,
                              "direction": direction, "entry_idx": entry_idx,
                              "entry_price": float(s.op[entry_idx]),
                              "brk_delay_min": j}
            else:  # trigger_price -- optimistic, sensitivity only
                result = {"ambiguous_breakout": False, "signal_idx": idx,
                          "direction": direction, "entry_idx": idx,
                          "entry_price": up_lvl if direction == 1 else dn_lvl,
                          "brk_delay_min": j}

    if s._bo_cache is None:
        s._bo_cache = {}
    s._bo_cache[key] = result
    return result


def stop_level(s: Session, direction: int, entry_price: float, cfg: Config) -> float:
    """Stop as a LEVEL. Distance is derived from it (sec c.2)."""
    if cfg.baseline_stop == "opposite_ib_extreme":
        return (s.ib_low - cfg.buffer_points) if direction == 1 else (s.ib_high + cfg.buffer_points)
    k = cfg.baseline_stop_k * s.ib_range
    return entry_price - k if direction == 1 else entry_price + k


def round_tick(x: float) -> float:
    return round(x / TICK_SIZE) * TICK_SIZE
