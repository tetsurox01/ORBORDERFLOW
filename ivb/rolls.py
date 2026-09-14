"""Contract roll calendar -- IVB-SPEC.md sec 0.1.

Computed ONCE from per-contract RTH volume, written to data/roll_calendar.csv,
version controlled, and never recomputed inside a backtest.

Two series result (sec 0.1.2):
  A) intraday_raw    front-month, UNADJUSTED  -> IB, levels, entries, PnL
  B) daily_adjusted  ratio-adjusted continuous -> ATR14, gap_atr, rolling medians

Series B exists because gap_atr, ATR14 and the rolling medians CROSS session
boundaries. On roll day the raw "prior close" is a different contract, which turns
a calendar spread into a fake market gap.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import DATA

ROLL_FILE = DATA / "roll_calendar.csv"
CONFIRM_SESSIONS = 2  # volume crossover must hold this many consecutive sessions

_MONTH_CODE = {"H": 3, "M": 6, "U": 9, "Z": 12}


def _expiry_key(symbol: str) -> tuple[int, int]:
    """NQH5 / NQZ24 -> sortable (year, month). Unknown symbols sort last."""
    m = re.fullmatch(r"NQ([HMUZ])(\d{1,2})", symbol.strip().upper())
    if not m:
        return (9999, 99)
    code, yy = m.group(1), int(m.group(2))
    year = 2000 + yy if yy < 80 else 1900 + yy
    return (year, _MONTH_CODE[code])


def build_roll_calendar(bars: pd.DataFrame, *, rth_only: bool = True) -> pd.DataFrame:
    """Volume-crossover roll, confirmed over CONFIRM_SESSIONS, effective NEXT session.

    Returns one row per session: session_date, front_symbol, roll_day_flag.
    """
    b = bars.copy()
    if rth_only:
        hm = b["ts_et"].dt.strftime("%H:%M")
        b = b[(hm >= "09:30") & (hm <= "15:59")]

    vol = (b.groupby(["session_date", "symbol"])["volume"].sum()
             .reset_index(name="rth_volume"))
    vol["expiry"] = vol["symbol"].map(_expiry_key)

    rows = []
    current: str | None = None
    streak_candidate: str | None = None
    streak = 0

    for session, grp in vol.groupby("session_date", sort=True):
        grp = grp.sort_values("rth_volume", ascending=False)
        top = grp.iloc[0]["symbol"]

        if current is None:
            current = top
            streak_candidate, streak = None, 0
            rows.append((session, current, False))
            continue

        # Only ever roll FORWARD, never back to an expired contract.
        rolled = False
        if top != current and _expiry_key(top) > _expiry_key(current):
            if top == streak_candidate:
                streak += 1
            else:
                streak_candidate, streak = top, 1
            if streak >= CONFIRM_SESSIONS:
                current = top            # effective from THIS session onward,
                streak_candidate, streak = None, 0   # i.e. the session AFTER the
                rolled = True            # second confirming session
        else:
            streak_candidate, streak = None, 0

        rows.append((session, current, rolled))

    cal = pd.DataFrame(rows, columns=["session_date", "front_symbol", "roll_effective"])

    # Flag the roll session and the one before it (sec 0.1.4).
    cal["roll_day_flag"] = cal["roll_effective"] | cal["roll_effective"].shift(-1, fill_value=False)

    ROLL_FILE.parent.mkdir(parents=True, exist_ok=True)
    cal.to_csv(ROLL_FILE, index=False)
    return cal


def load_roll_calendar() -> pd.DataFrame:
    if not ROLL_FILE.exists():
        raise FileNotFoundError(f"{ROLL_FILE} missing. Run scripts/02_build_rolls.py")
    cal = pd.read_csv(ROLL_FILE, parse_dates=["session_date"])
    return cal


def front_month_bars(bars: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Series A: raw front-month bars, one contract per session, never split."""
    m = cal[["session_date", "front_symbol", "roll_day_flag"]]
    out = bars.merge(m, on="session_date", how="inner")
    out = out[out["symbol"] == out["front_symbol"]].copy()
    return out.drop(columns=["front_symbol"]).sort_values("ts_et").reset_index(drop=True)


def daily_adjusted(bars: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Series B: RATIO-adjusted continuous daily series for cross-session features.

    On each roll, every prior price is scaled by (new_close / old_close) on the
    session before the roll, so the artificial spread gap is removed while
    proportional returns are preserved.
    """
    hm = bars["ts_et"].dt.strftime("%H:%M")
    rth = bars[(hm >= "09:30") & (hm <= "15:59")]

    daily = (rth.groupby(["session_date", "symbol"])
                .agg(open=("open", "first"), high=("high", "max"),
                     low=("low", "min"), close=("close", "last"),
                     volume=("volume", "sum"))
                .reset_index())

    cal = cal.sort_values("session_date").reset_index(drop=True)
    front = daily.merge(cal[["session_date", "front_symbol", "roll_effective"]],
                        on="session_date", how="inner")
    series = front[front["symbol"] == front["front_symbol"]].copy()
    series = series.sort_values("session_date").reset_index(drop=True)

    # Backward ratio adjustment: walk from the newest session to the oldest.
    factor = 1.0
    factors = np.ones(len(series))
    for i in range(len(series) - 1, 0, -1):
        factors[i] = factor
        if bool(series.loc[i, "roll_effective"]):
            prev_date = series.loc[i - 1, "session_date"]
            new_sym = series.loc[i, "symbol"]
            old_sym = series.loc[i - 1, "symbol"]
            prev_new = daily[(daily["session_date"] == prev_date) & (daily["symbol"] == new_sym)]
            prev_old = daily[(daily["session_date"] == prev_date) & (daily["symbol"] == old_sym)]
            if len(prev_new) and len(prev_old):
                ratio = float(prev_new["close"].iloc[0]) / float(prev_old["close"].iloc[0])
                if np.isfinite(ratio) and ratio > 0:
                    factor *= ratio
    factors[0] = factor

    for c in ("open", "high", "low", "close"):
        series[f"adj_{c}"] = series[c] * factors

    audit(series)
    return series


def audit(series: pd.DataFrame, *, atr_period: int = 14, max_mult: float = 8.0) -> None:
    """Mandatory audit (sec 0.1.4): no single-day return may exceed 8 * ATR14.

    A spike at a roll date means the adjustment is broken.
    """
    s = series.sort_values("session_date").reset_index(drop=True)
    tr = pd.concat([
        s["adj_high"] - s["adj_low"],
        (s["adj_high"] - s["adj_close"].shift()).abs(),
        (s["adj_low"] - s["adj_close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    move = (s["adj_close"] - s["adj_close"].shift()).abs()

    bad = s[(move > max_mult * atr) & atr.notna()]
    if len(bad):
        dates = ", ".join(str(d.date()) for d in bad["session_date"].head(5))
        near_roll = bad["roll_effective"].any() if "roll_effective" in bad else False
        raise ValueError(
            f"Ratio adjustment audit FAILED: {len(bad)} sessions move > {max_mult}x ATR14 "
            f"({dates}...). roll_effective present in failures: {near_roll}. "
            "IVB-SPEC.md sec 0.1.4 -- fix the adjustment before proceeding."
        )
