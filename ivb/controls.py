"""Controls C1-C4 -- RESEARCH-PLAN.md, Step 1.

All evaluated on S_all with non-breakout days entering the numerator as zero.
C1 trades every session; the strategy does not. Comparing on S_breakout would
delete C1's performance on exactly the days the strategy sits out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import _covid, simulate
from .config import Config
from .sessions import Session, find_breakout, stop_level


def _blank(s: Session, reason: str) -> dict:
    return {
        "session_date": s.session_date, "traded": False, "net_dollars": 0.0,
        "net_points": 0.0, "direction": 0, "skip_reason": reason,
        "covid_flag": _covid(s.session_date),
    }


def c1_drift(sessions: list[Session], cfg: Config, *, stop_matched: bool = True) -> pd.DataFrame:
    """C1 -- buy at IB close every session, flat at trade_end.

    stop_matched=True mirrors P0's geometry (stop at IB low, target at R_mult)
    so the comparison is not confounded by the exit rules.
    """
    rows = []
    for s in sessions:
        if cfg.exclude_half_days and s.is_half_day:
            continue
        ei = s.ib_close_idx
        if ei >= s.trade_end_idx:
            rows.append(_blank(s, "no_time"))
            continue
        ep = float(s.bars.loc[ei, "open"])

        if stop_matched:
            sl = stop_level(s, 1, ep, cfg)
            risk = abs(ep - sl)
            if risk <= 0:
                rows.append(_blank(s, "zero_risk"))
                continue
            t = simulate(s, 1, ei, ep, sl, ep + cfg.r_mult * risk, cfg)
        else:
            # no stop, no target: exit at trade_end close
            far = 1e9
            t = simulate(s, 1, ei, ep, ep - far, ep + far, cfg)

        rows.append({"session_date": s.session_date, "traded": True,
                     "net_dollars": t.net_dollars, "net_points": t.net_points,
                     "direction": 1, "skip_reason": "",
                     "covid_flag": t.covid_flag})
    return pd.DataFrame(rows)


def c2_coinflip(sessions: list[Session], cfg: Config, n: int | None = None) -> pd.DataFrame:
    """C2 -- random direction at the real breakout bar, geometry held fixed.

    Re-randomises DIRECTION only. Entry time, stop distance and target distance
    stay identical to the real strategy.

    Returns one row per shuffle: shuffle, total_dollars, expectancy_per_session.
    """
    n = n or cfg.n_shuffles
    rng = np.random.default_rng(cfg.seed)

    # Pre-compute each session's real signal geometry once.
    setups = []
    n_sessions = 0
    for s in sessions:
        if cfg.exclude_half_days and s.is_half_day:
            continue
        n_sessions += 1
        bo = find_breakout(s, cfg)
        if bo is None or bo["ambiguous_breakout"]:
            continue
        d, ei, ep = bo["direction"], bo["entry_idx"], bo["entry_price"]
        risk = abs(ep - stop_level(s, d, ep, cfg))
        if risk <= 0:
            continue
        setups.append((s, ei, ep, risk))

    out = []
    for k in range(n):
        total = 0.0
        for s, ei, ep, risk in setups:
            d = 1 if rng.random() < 0.5 else -1
            sl = ep - risk * d
            tgt = ep + cfg.r_mult * risk * d
            total += simulate(s, d, ei, ep, sl, tgt, cfg).net_dollars
        out.append({"shuffle": k, "total_dollars": total,
                    "expectancy_per_session": total / max(1, n_sessions)})
    return pd.DataFrame(out)


def c3_inversion(sessions: list[Session], cfg: Config) -> pd.DataFrame:
    """C3 -- GEOMETRY-PRESERVING inversion.

    Opposite side, SAME stop distance, SAME target distance. Only the sign of the
    direction changes. The swap reading (target level becomes the stop) is
    rejected: it would mix direction with geometry.
    """
    rows = []
    for s in sessions:
        if cfg.exclude_half_days and s.is_half_day:
            continue
        bo = find_breakout(s, cfg)
        if bo is None or bo["ambiguous_breakout"]:
            rows.append(_blank(s, "no_breakout"))
            continue
        d_real, ei, ep = bo["direction"], bo["entry_idx"], bo["entry_price"]
        risk = abs(ep - stop_level(s, d_real, ep, cfg))
        if risk <= 0:
            rows.append(_blank(s, "zero_risk"))
            continue

        d = -d_real
        sl = ep - risk * d                       # same DISTANCE, opposite side
        tgt = ep + cfg.r_mult * risk * d         # same DISTANCE, opposite side
        t = simulate(s, d, ei, ep, sl, tgt, cfg)
        rows.append({"session_date": s.session_date, "traded": True,
                     "net_dollars": t.net_dollars, "net_points": t.net_points,
                     "direction": d, "skip_reason": "", "covid_flag": t.covid_flag})
    return pd.DataFrame(rows)


def c4_random_time(sessions: list[Session], cfg: Config) -> pd.DataFrame:
    """C4 -- real direction, random entry minute after IB close."""
    rng = np.random.default_rng(cfg.seed + 1)
    rows = []
    for s in sessions:
        if cfg.exclude_half_days and s.is_half_day:
            continue
        bo = find_breakout(s, cfg)
        if bo is None or bo["ambiguous_breakout"]:
            rows.append(_blank(s, "no_breakout"))
            continue
        d = bo["direction"]
        lo, hi = s.ib_close_idx, s.trade_end_idx - 1
        if hi <= lo:
            rows.append(_blank(s, "no_time"))
            continue
        ei = int(rng.integers(lo, hi))
        ep = float(s.bars.loc[ei, "open"])
        sl = stop_level(s, d, ep, cfg)
        risk = abs(ep - sl)
        if risk <= 0:
            rows.append(_blank(s, "zero_risk"))
            continue
        t = simulate(s, d, ei, ep, sl, ep + cfg.r_mult * risk * d, cfg)
        rows.append({"session_date": s.session_date, "traded": True,
                     "net_dollars": t.net_dollars, "net_points": t.net_points,
                     "direction": d, "skip_reason": "", "covid_flag": t.covid_flag})
    return pd.DataFrame(rows)
