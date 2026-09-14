"""Contract roll calendar -- IVB-SPEC.md sec 0.1.

Computed ONCE from per-contract RTH volume, written to data/roll_calendar.csv,
version controlled, and never recomputed inside a backtest.

Two series result (sec 0.1.2):
  A) intraday_raw    front-month, UNADJUSTED  -> IB, levels, entries, PnL
  B) daily_adjusted  ratio-adjusted continuous -> ATR14, gap_atr, rolling medians

Series B exists because gap_atr, ATR14 and the rolling medians CROSS session
boundaries. On roll day the raw "prior close" is a different contract, which turns
a calendar spread into a fake market gap.

TWO DEFECTS FIXED 2026-09-15, both of which produced ONE roll in sixteen years
and a plausible-looking price series that was not NQ at all:

  D1  SPREADS RANKED AS CONTRACTS. 119 of the 159 symbols in the vendor file are
      calendar spreads (NQH2-NQM2). They are not outright contracts and must never
      win the front-month vote. They did, on 226 of 4,122 sessions.

  D2  THE PARSER FAILED UPWARD. _expiry_key returned (9999, 99) for anything it
      could not parse, so an unparseable symbol sorted ABOVE every real contract,
      the "only roll forward" rule promoted it, and nothing could ever displace it.
      A parser's failure mode must never be "wins". It now RAISES.

  D3  DECADE WRAP. The vendor year code is a single digit, so NQH5 is March 2015
      AND March 2025. Expiry is resolved from the SESSION DATE, never from the
      string alone, and instrument_id is carried as the real contract key.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import DATA

ROLL_FILE = DATA / "roll_calendar.csv"
CONFIRM_SESSIONS = 2  # volume crossover must hold this many consecutive sessions

_MONTH_CODE = {"H": 3, "M": 6, "U": 9, "Z": 12}
_OUTRIGHT_RE = re.compile(r"^NQ([HMUZ])(\d{1,2})$")

# How far before its own expiry a contract may legitimately trade. MEASURED over
# all 70 contracts in this dataset, not guessed:
#
#   median lead   385 days   (the liquid front/second month)
#   NQZ6          1,150 days  56,880 lots   deferred but real
#   NQZ7            931 days       2 lots   deep deferred
#   NQZ9          1,771 days       1 lot    Dec 2029, traded once on 2025-02-14
#
# The deep-deferred tail is genuine CME listing behaviour, not bad data, so the
# ceiling must clear 1,771. It must also stay under ~3,650 days, the distance
# between two candidate expiries sharing a year digit: as long as the window is
# narrower than that gap, at most ONE candidate can fall inside it and the decade
# stays unambiguous. 2,000 clears the observed maximum and is well inside the gap.
MAX_LEAD_DAYS = 2000
EXPIRY_GRACE_DAYS = 3  # tolerate a stray bar stamped just after expiry

# Four quarterly rolls per year is knowable a priori, not measured. Asserting it
# is what turns D1/D2 from a silent wrong answer into a loud failure.
ROLLS_PER_YEAR = 4.0
ROLL_COUNT_TOL = 0.25  # +/- 25% band


class SymbolParseError(ValueError):
    """Raised when a symbol cannot be resolved. Never swallowed, never ranked."""


def is_spread(symbol: str) -> bool:
    """True for calendar spreads (NQH2-NQM2), which are not tradeable outrights.

    Checked EXPLICITLY before ranking. The old code relied on spreads sorting
    last via a sentinel expiry key, which is exactly backwards: the sentinel
    sorted them FIRST and locked the calendar for sixteen years.
    """
    return "-" in symbol


def third_friday(year: int, month: int) -> pd.Timestamp:
    """CME equity-index quarterly expiry: the third Friday of the contract month."""
    first = pd.Timestamp(year=year, month=month, day=1)
    offset = (4 - first.dayofweek) % 7  # 4 = Friday
    return first + pd.Timedelta(days=offset + 14)


def expiry_key(symbol: str, session_date) -> tuple[int, int]:
    """Resolve NQH5 -> (2015, 3) or (2025, 3) USING THE SESSION DATE.

    The vendor year code is one digit, so the string alone is ambiguous over any
    window longer than a decade. The session date picks the decade: of the three
    candidate years sharing that digit, take the nearest expiry that has not yet
    passed.

    Raises SymbolParseError on spreads and on anything unparseable. There is no
    sentinel return value -- see D2 in the module docstring.
    """
    sym = str(symbol).strip().upper()

    if is_spread(sym):
        raise SymbolParseError(
            f"{sym!r} is a calendar spread, not an outright contract. "
            "Filter spreads out before ranking (ivb.rolls.is_spread)."
        )

    m = _OUTRIGHT_RE.match(sym)
    if not m:
        raise SymbolParseError(
            f"Cannot parse contract symbol {sym!r}. Expected NQ<HMUZ><year digits>. "
            "Refusing to guess -- an unparseable symbol must never enter the "
            "front-month ranking."
        )

    code, digits = m.group(1), m.group(2)
    month = _MONTH_CODE[code]
    session = pd.Timestamp(session_date).normalize()

    if len(digits) == 2:  # unambiguous 2-digit year, no decade to resolve
        year = 2000 + int(digits)
        return (year, month)

    digit = int(digits)
    base = (session.year // 10) * 10
    candidates = []
    for decade in (base - 10, base, base + 10):
        year = decade + digit
        exp = third_friday(year, month)
        lead = (exp - session).days
        if lead >= -EXPIRY_GRACE_DAYS and lead <= MAX_LEAD_DAYS:
            candidates.append((lead, year))

    if not candidates:
        raise SymbolParseError(
            f"{sym!r} on session {session.date()} resolves to no plausible expiry "
            f"within {MAX_LEAD_DAYS} days. A contract trading far outside its own "
            "listing window means the data or the symbology is wrong."
        )

    candidates.sort()
    return (candidates[0][1], month)


def build_roll_calendar(bars: pd.DataFrame, *, rth_only: bool = True) -> pd.DataFrame:
    """Volume-crossover roll, confirmed over CONFIRM_SESSIONS, effective NEXT session.

    Returns one row per session: session_date, front_symbol, front_instrument_id,
    roll_effective, roll_day_flag.
    """
    b = bars.copy()
    if rth_only:
        hm = b["ts_et"].dt.strftime("%H:%M")
        b = b[(hm >= "09:30") & (hm <= "15:59")]

    # D1: drop spreads BEFORE ranking, explicitly, not via sort order.
    n_before = b["symbol"].nunique()
    b = b[~b["symbol"].astype(str).map(is_spread)].copy()
    n_after = b["symbol"].nunique()
    if n_after == 0:
        raise ValueError("No outright contracts left after dropping spreads.")
    print(f"[rolls] symbols: {n_before} total -> {n_after} outrights "
          f"({n_before - n_after} spreads dropped before ranking)")

    keys = ["session_date", "symbol"]
    if "instrument_id" in b.columns:
        keys = ["session_date", "instrument_id", "symbol"]

    vol = b.groupby(keys)["volume"].sum().reset_index(name="rth_volume")

    # D2/D3: parse every symbol, on its own session date. Raises on anything odd.
    vol["expiry"] = [expiry_key(s, d)
                     for s, d in zip(vol["symbol"], vol["session_date"])]

    _assert_one_id_per_symbol_per_session(vol)

    rows = []
    current_exp: tuple[int, int] | None = None
    current_sym: str | None = None
    current_id = None
    streak_exp: tuple[int, int] | None = None
    streak = 0

    for session, grp in vol.groupby("session_date", sort=True):
        grp = grp.sort_values("rth_volume", ascending=False)
        top = grp.iloc[0]
        top_exp, top_sym = top["expiry"], top["symbol"]
        top_id = top["instrument_id"] if "instrument_id" in grp.columns else None

        if current_exp is None:
            current_exp, current_sym, current_id = top_exp, top_sym, top_id
            streak_exp, streak = None, 0
            rows.append((session, current_sym, current_id, False))
            continue

        # Only ever roll FORWARD, never back to an expired contract. Compared on
        # the date-resolved expiry, so the decade wrap cannot invert the order.
        rolled = False
        if top_exp != current_exp and top_exp > current_exp:
            if top_exp == streak_exp:
                streak += 1
            else:
                streak_exp, streak = top_exp, 1
            if streak >= CONFIRM_SESSIONS:
                current_exp, current_sym, current_id = top_exp, top_sym, top_id
                streak_exp, streak = None, 0
                rolled = True
        else:
            streak_exp, streak = None, 0

        # Keep the id in step with the symbol even between rolls: the front
        # contract's id is whatever carries that expiry on THIS session.
        if not rolled and current_exp is not None:
            same = grp[grp["expiry"] == current_exp]
            if len(same):
                current_sym = same.iloc[0]["symbol"]
                if "instrument_id" in grp.columns:
                    current_id = same.iloc[0]["instrument_id"]

        rows.append((session, current_sym, current_id, rolled))

    cal = pd.DataFrame(
        rows,
        columns=["session_date", "front_symbol", "front_instrument_id", "roll_effective"],
    )

    # Flag the roll session and the one before it (sec 0.1.4).
    cal["roll_day_flag"] = cal["roll_effective"] | cal["roll_effective"].shift(-1, fill_value=False)

    assert_no_spread_front(cal)
    assert_roll_count(cal)

    ROLL_FILE.parent.mkdir(parents=True, exist_ok=True)
    cal.to_csv(ROLL_FILE, index=False)
    return cal


def _assert_one_id_per_symbol_per_session(vol: pd.DataFrame) -> None:
    """Within one session a symbol string must name exactly one contract.

    Across the full window it names two (the decade wrap). Within a session it
    must not, or front_month_bars would silently merge two contracts' bars.
    """
    if "instrument_id" not in vol.columns:
        return
    n = vol.groupby(["session_date", "symbol"])["instrument_id"].nunique()
    bad = n[n > 1]
    if len(bad):
        raise ValueError(
            f"{len(bad)} (session, symbol) pairs map to more than one instrument_id, "
            f"first: {bad.index[0]}. The symbol string is ambiguous WITHIN a session, "
            "which breaks front-month selection."
        )


def assert_no_spread_front(cal: pd.DataFrame) -> None:
    """The front month may never be a calendar spread. This is defect D1's alarm."""
    bad = cal[cal["front_symbol"].astype(str).map(is_spread)]
    if len(bad):
        raise ValueError(
            f"Front month is a calendar spread on {len(bad)} sessions "
            f"(first {bad['session_date'].iloc[0].date()}, {bad['front_symbol'].iloc[0]}). "
            "Spreads must be filtered before ranking -- IVB-SPEC.md sec 0.1.1."
        )


def assert_roll_count(cal: pd.DataFrame, *, per_year: float = ROLLS_PER_YEAR,
                      tol: float = ROLL_COUNT_TOL) -> None:
    """NQ rolls four times a year. Over N years expect ~4N rolls, +/- a band.

    This is an A PRIORI count, not a measured one, which is what makes it a real
    test. The defect it exists to catch produced 1 roll over 16.2 years while
    still emitting a complete, plausible-looking calendar.
    """
    dates = pd.to_datetime(cal["session_date"])
    years = (dates.max() - dates.min()).days / 365.25
    n_rolls = int(cal["roll_effective"].sum())
    expected = per_year * years
    lo, hi = expected * (1 - tol), expected * (1 + tol)

    print(f"[rolls] {n_rolls} rolls over {years:.2f} years "
          f"(expected ~{expected:.0f}, band {lo:.0f}-{hi:.0f})")

    if not (lo <= n_rolls <= hi):
        raise ValueError(
            f"Roll count {n_rolls} outside the a-priori band {lo:.0f}-{hi:.0f} "
            f"for {years:.2f} years at {per_year}/year. "
            "A quarterly contract rolls four times a year; a count far from that "
            "means the front-month vote is broken, not that the market changed. "
            "IVB-SPEC.md sec 0.1.1."
        )


def load_roll_calendar() -> pd.DataFrame:
    if not ROLL_FILE.exists():
        raise FileNotFoundError(f"{ROLL_FILE} missing. Run scripts/02_build_rolls.py")
    cal = pd.read_csv(ROLL_FILE, parse_dates=["session_date"])
    return cal


def front_month_bars(bars: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Series A: raw front-month bars, one contract per session, never split.

    Matched on instrument_id where available -- the symbol string is not a key.
    """
    use_id = "front_instrument_id" in cal.columns and "instrument_id" in bars.columns
    cols = ["session_date", "front_symbol", "roll_day_flag"]
    if use_id:
        cols.insert(2, "front_instrument_id")

    m = cal[cols]
    out = bars.merge(m, on="session_date", how="inner")
    if use_id:
        out = out[out["instrument_id"] == out["front_instrument_id"]].copy()
        out = out.drop(columns=["front_symbol", "front_instrument_id"])
    else:
        out = out[out["symbol"] == out["front_symbol"]].copy()
        out = out.drop(columns=["front_symbol"])
    return out.sort_values("ts_et").reset_index(drop=True)


def daily_adjusted(bars: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """Series B: RATIO-adjusted continuous daily series for cross-session features.

    On each roll, every prior price is scaled by (new_close / old_close) on the
    session before the roll, so the artificial spread gap is removed while
    proportional returns are preserved.
    """
    hm = bars["ts_et"].dt.strftime("%H:%M")
    rth = bars[(hm >= "09:30") & (hm <= "15:59")]

    use_id = "front_instrument_id" in cal.columns and "instrument_id" in bars.columns
    key = "instrument_id" if use_id else "symbol"

    daily = (rth.groupby(["session_date", key])
                .agg(open=("open", "first"), high=("high", "max"),
                     low=("low", "min"), close=("close", "last"),
                     volume=("volume", "sum"))
                .reset_index())

    cal = cal.sort_values("session_date").reset_index(drop=True)
    cal_cols = ["session_date", "front_symbol", "roll_effective"]
    if use_id:
        cal_cols.insert(2, "front_instrument_id")
    front = daily.merge(cal[cal_cols], on="session_date", how="inner")
    front_key = "front_instrument_id" if use_id else "front_symbol"
    series = front[front[key] == front[front_key]].copy()
    series = series.sort_values("session_date").reset_index(drop=True)

    # Backward ratio adjustment: walk from the newest session to the oldest.
    factor = 1.0
    factors = np.ones(len(series))
    for i in range(len(series) - 1, 0, -1):
        factors[i] = factor
        if bool(series.loc[i, "roll_effective"]):
            prev_date = series.loc[i - 1, "session_date"]
            new_k = series.loc[i, key]
            old_k = series.loc[i - 1, key]
            prev_new = daily[(daily["session_date"] == prev_date) & (daily[key] == new_k)]
            prev_old = daily[(daily["session_date"] == prev_date) & (daily[key] == old_k)]
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
