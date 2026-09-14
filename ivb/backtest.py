"""Trade simulation with the pessimistic intrabar rule -- IVB-SPEC.md sec a.5.

A 1-minute bar reports only O, H, L, C. The ORDER in which H and L were visited is
not recoverable. Every such ambiguity is resolved AGAINST the trade, every time.

Cases handled here:
  1. stop and target in one bar        -> stop fills
  2. entry and stop in one bar         -> stop fills, full loss
  4. entry and target in one bar       -> entry fills, target does NOT
  MFE on a stop-out bar                -> 0 (adverse extreme assumed first)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .config import Config
from .sessions import Session, find_breakout, round_tick, stop_level


@dataclass
class Trade:
    session_date: pd.Timestamp
    direction: int
    entry_idx: int
    entry_price: float
    stop_price: float
    target_price: float
    exit_idx: int
    exit_price: float
    exit_reason: str          # "stop" | "target" | "time"
    risk_points: float
    gross_points: float
    net_points: float
    net_dollars: float
    r_multiple: float
    mfe_points: float         # MFE-before-stop, pessimistic
    mae_points: float
    mfe_raw_points: float     # MFE to trade_end with NO stop (research only)
    ambiguous: bool
    ambiguous_case: str
    ib_range: float
    brk_delay_min: int
    is_half_day: bool
    roll_day_flag: bool
    covid_flag: bool


def simulate(
    s: Session,
    direction: int,
    entry_idx: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
    cfg: Config,
    *,
    brk_delay_min: int = -1,
) -> Trade:
    """Walk bars from entry_idx to trade_end and resolve the exit."""
    arr_hi, arr_lo = s.hi, s.lo
    long = direction == 1

    stop_price = round_tick(stop_price)
    target_price = round_tick(target_price)

    mfe = 0.0
    mae = 0.0
    exit_idx = s.trade_end_idx
    exit_price = float(s.cl[s.trade_end_idx])
    reason = "time"
    ambiguous = False
    case = ""

    for i in range(entry_idx, s.trade_end_idx + 1):
        hi = arr_hi[i]
        lo = arr_lo[i]

        hit_stop = (lo <= stop_price) if long else (hi >= stop_price)
        hit_tgt = (hi >= target_price) if long else (lo <= target_price)

        fav = (hi - entry_price) if long else (entry_price - lo)
        adv = (entry_price - lo) if long else (hi - entry_price)
        mae = max(mae, adv)

        if hit_stop and hit_tgt:
            # Case 1 (or case 2 if this is the entry bar). Pessimistic: stop.
            ambiguous = True
            case = "entry_and_stop" if i == entry_idx else "stop_and_target"
            if cfg.intrabar == "pessimistic":
                exit_idx, exit_price, reason = i, stop_price, "stop"
                # MFE on a stop-out bar is 0 -- adverse extreme assumed first.
                break
            exit_idx, exit_price, reason = i, target_price, "target"
            mfe = max(mfe, target_price - entry_price if long else entry_price - target_price)
            break

        if hit_stop:
            if i == entry_idx:
                ambiguous = True
                case = "entry_and_stop"
            exit_idx, exit_price, reason = i, stop_price, "stop"
            break

        if hit_tgt:
            # Case 4: on the entry bar the favourable half is assumed to have
            # happened BEFORE the fill, so the target does not count.
            if i == entry_idx and cfg.intrabar == "pessimistic":
                ambiguous = True
                case = "entry_and_target"
                mfe = max(mfe, fav)
                continue
            mfe = max(mfe, fav)
            exit_idx, exit_price, reason = i, target_price, "target"
            break

        mfe = max(mfe, fav)

    # ---- MFE_raw: no stop applied, to trade_end (research instrument only) ----
    end = s.trade_end_idx + 1
    mfe_raw = (float(arr_hi[entry_idx:end].max() - entry_price) if long
               else float(entry_price - arr_lo[entry_idx:end].min()))
    mfe_raw = max(0.0, mfe_raw)

    # ---- costs -------------------------------------------------------------
    slip = cfg.slippage_points
    entry_fill = entry_price + slip if long else entry_price - slip
    if reason == "target":
        exit_fill = exit_price                      # limit order, no slippage
    else:
        exit_fill = exit_price - slip if long else exit_price + slip  # market/stop

    gross = (exit_price - entry_price) if long else (entry_price - exit_price)
    net_pts = (exit_fill - entry_fill) if long else (entry_fill - exit_fill)
    commission_pts = (2 * cfg.commission_per_side) / cfg.point_value
    net_pts -= commission_pts
    risk = abs(entry_price - stop_price)

    return Trade(
        session_date=s.session_date,
        direction=direction,
        entry_idx=entry_idx,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        exit_idx=exit_idx,
        exit_price=exit_price,
        exit_reason=reason,
        risk_points=risk,
        gross_points=gross,
        net_points=net_pts,
        net_dollars=net_pts * cfg.point_value,
        r_multiple=(net_pts / risk) if risk > 0 else np.nan,
        mfe_points=max(0.0, mfe),
        mae_points=max(0.0, mae),
        mfe_raw_points=mfe_raw,
        ambiguous=ambiguous,
        ambiguous_case=case,
        ib_range=s.ib_range,
        brk_delay_min=brk_delay_min,
        is_half_day=s.is_half_day,
        roll_day_flag=s.roll_day_flag,
        covid_flag=_covid(s.session_date),
    )


def _covid(d: pd.Timestamp) -> bool:
    return pd.Timestamp("2020-02-15") <= d <= pd.Timestamp("2020-04-30")


def run_strategy(sessions: list[Session], feats: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """P0 on every session. Returns one row per session in S_all.

    Sessions with no breakout appear with net_dollars = 0 and traded = False, so
    the S_all denominator is correct by construction (sec g.2).
    """
    fmap = feats.set_index("session_date")
    rows = []

    for s in sessions:
        if cfg.exclude_half_days and s.is_half_day:
            continue

        atr = float(fmap["atr14"].get(s.session_date, np.nan))
        base = {
            "session_date": s.session_date,
            "traded": False,
            "net_dollars": 0.0,
            "net_points": 0.0,
            "r_multiple": np.nan,
            "direction": 0,
            "ib_range": s.ib_range,
            "atr14": atr,
            "ib_range_atr": s.ib_range / atr if atr and np.isfinite(atr) and atr > 0 else np.nan,
            "is_half_day": s.is_half_day,
            "roll_day_flag": s.roll_day_flag,
            "covid_flag": _covid(s.session_date),
            "skip_reason": "",
        }

        # ---- no-trade filter, known at IB close, no leakage (sec f) --------
        if np.isfinite(base["ib_range_atr"]) and base["ib_range_atr"] < cfg.min_ib_range_atr:
            base["skip_reason"] = "min_ib_range_atr"
            rows.append(base)
            continue
        if cfg.min_ib_range_ticks and s.ib_range < cfg.min_ib_range_ticks * 0.25:
            base["skip_reason"] = "min_ib_range_ticks"
            rows.append(base)
            continue

        bo = find_breakout(s, cfg)
        if bo is None:
            base["skip_reason"] = "no_breakout"
            rows.append(base)
            continue
        if bo["ambiguous_breakout"]:
            base["skip_reason"] = "ambiguous_breakout"
            rows.append(base)
            continue

        d, ei, ep = bo["direction"], bo["entry_idx"], bo["entry_price"]
        sl = stop_level(s, d, ep, cfg)
        risk = abs(ep - sl)
        if risk <= 0:
            base["skip_reason"] = "zero_risk"
            rows.append(base)
            continue
        tgt = ep + cfg.r_mult * risk * d

        t = simulate(s, d, ei, ep, sl, tgt, cfg, brk_delay_min=bo["brk_delay_min"])
        row = {**base, **asdict(t), "traded": True}
        row["session_date"] = s.session_date
        rows.append(row)

    return pd.DataFrame(rows)
