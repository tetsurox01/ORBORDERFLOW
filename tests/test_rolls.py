"""Roll calendar regression tests -- IVB-SPEC.md sec 0.1.

Written after three defects let build_roll_calendar emit ONE roll over sixteen
years and a complete, plausible-looking price series that was a calendar spread.

Every case below is pinned to something that ACTUALLY OCCURRED in
data/raw/nq_ohlcv1m_2010-07-01_2026-08-31.parquet, not to an invented example.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.rolls import (SymbolParseError, assert_no_spread_front,  # noqa: E402
                       assert_roll_count, build_roll_calendar, expiry_key,
                       is_spread, third_friday)

PASS, FAIL = [], []


def check(name: str, ok: bool, extra: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print("{} {}{}".format("PASS" if ok else "FAIL", name,
                           "   " + extra if extra else ""))


def raises(fn, exc=Exception) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------
# D3 -- THE DECADE WRAP, pinned to the real NQH5 collision.
#
#   instrument_id 50207     NQH5   2014-01-02 .. 2015-03-20   -> March 2015
#   instrument_id 42288528  NQH5   2024-01-02 .. 2025-03-21   -> March 2025
#
# One symbol string, two contracts, ten years apart. The old _expiry_key mapped
# the string to (2005, 3) and was wrong for both.
# --------------------------------------------------------------------------
def test_decade_wrap() -> None:
    a = expiry_key("NQH5", pd.Timestamp("2014-01-02"))   # id 50207, first bar
    b = expiry_key("NQH5", pd.Timestamp("2015-03-20"))   # id 50207, expiry day
    c = expiry_key("NQH5", pd.Timestamp("2024-01-02"))   # id 42288528, first bar
    d = expiry_key("NQH5", pd.Timestamp("2025-03-21"))   # id 42288528, last bar

    check("NQH5 in 2014 resolves to March 2015", a == (2015, 3), str(a))
    check("NQH5 on 2015-03-20 still resolves to March 2015", b == (2015, 3), str(b))
    check("NQH5 in 2024 resolves to March 2025", c == (2025, 3), str(c))
    check("NQH5 on 2025-03-21 still resolves to March 2025", d == (2025, 3), str(d))
    check("the same string gives DIFFERENT contracts a decade apart", a != c,
          f"{a} vs {c}")
    check("2025 sorts after 2015 (roll-forward order survives the wrap)", c > a)

    # The other two collisions in this dataset.
    u0_2010 = expiry_key("NQU0", pd.Timestamp("2010-06-30"))
    u0_2020 = expiry_key("NQU0", pd.Timestamp("2019-07-16"))
    check("NQU0 in 2010 -> Sep 2010", u0_2010 == (2010, 9), str(u0_2010))
    check("NQU0 in 2019 -> Sep 2020", u0_2020 == (2020, 9), str(u0_2020))

    z0_2010 = expiry_key("NQZ0", pd.Timestamp("2010-06-30"))
    z0_2019 = expiry_key("NQZ0", pd.Timestamp("2019-12-02"))
    check("NQZ0 in 2010 -> Dec 2010", z0_2010 == (2010, 12), str(z0_2010))
    check("NQZ0 in 2019 -> Dec 2020", z0_2019 == (2020, 12), str(z0_2019))


# --------------------------------------------------------------------------
# D2 -- THE PARSER MUST FAIL DOWNWARD. It used to return (9999, 99), which sorts
# above every real contract, so an unparseable symbol WON the front-month vote
# and could never be displaced. Failure mode must be "raise", never "wins".
# --------------------------------------------------------------------------
def test_parser_fails_loudly() -> None:
    d = pd.Timestamp("2015-06-01")
    check("spread symbol RAISES", raises(lambda: expiry_key("NQH2-NQM2", d), SymbolParseError))
    check("garbage symbol RAISES", raises(lambda: expiry_key("XYZZY", d), SymbolParseError))
    check("empty symbol RAISES", raises(lambda: expiry_key("", d), SymbolParseError))
    check("wrong month code RAISES", raises(lambda: expiry_key("NQF5", d), SymbolParseError))
    check("wrong product root RAISES", raises(lambda: expiry_key("ESH5", d), SymbolParseError))
    # The dead zone: leads between MAX_LEAD_DAYS (2000) and the ~3,650-day decade
    # gap. On 2017-07-20 the March-2015 contract is 854 days dead and the
    # March-2025 one is 2,800 days from listing, so an "NQH5" bar there is
    # impossible and must raise rather than silently pick a decade.
    check("contract in the dead zone between two decades RAISES",
          raises(lambda: expiry_key("NQH5", pd.Timestamp("2017-07-20")), SymbolParseError))

    # The regression itself: no sentinel may outrank a real contract.
    real = expiry_key("NQZ5", pd.Timestamp("2015-06-01"))
    check("no sentinel value is produced at all", real < (9999, 99), str(real))


# --------------------------------------------------------------------------
# D1 -- SPREADS ARE NOT CONTRACTS, and are filtered BEFORE ranking.
# 119 of 159 symbols in the vendor file are spreads; one won the vote on
# 2010-08-12 and held the front month for 4,094 of 4,122 sessions.
# --------------------------------------------------------------------------
def test_spread_detection() -> None:
    check("NQH2-NQM2 is a spread", is_spread("NQH2-NQM2"))
    check("NQU0-NQZ0 is a spread (the one that broke it)", is_spread("NQU0-NQZ0"))
    check("NQZ9-NQH0 is a spread", is_spread("NQZ9-NQH0"))
    check("NQH5 is NOT a spread", not is_spread("NQH5"))
    check("NQZ24 is NOT a spread", not is_spread("NQZ24"))

    bad = pd.DataFrame({
        "session_date": pd.to_datetime(["2010-08-12", "2010-08-13"]),
        "front_symbol": ["NQU0-NQZ0", "NQU0"],
    })
    check("assert_no_spread_front catches a spread front month",
          raises(lambda: assert_no_spread_front(bad), ValueError))

    good = pd.DataFrame({
        "session_date": pd.to_datetime(["2010-08-12", "2010-08-13"]),
        "front_symbol": ["NQU0", "NQU0"],
    })
    check("assert_no_spread_front passes a clean calendar",
          not raises(lambda: assert_no_spread_front(good), ValueError))


# --------------------------------------------------------------------------
# THE A PRIORI COUNT. Four rolls a year is arithmetic, not an observation.
# This is the alarm that would have caught D1 and D2 on the first run.
# --------------------------------------------------------------------------
def test_roll_count_band() -> None:
    dates = pd.date_range("2010-07-01", "2026-08-31", freq="B")

    def cal_with(n_rolls: int) -> pd.DataFrame:
        flags = [False] * len(dates)
        step = max(1, len(dates) // max(n_rolls, 1))
        for i in range(n_rolls):
            flags[min(i * step, len(dates) - 1)] = True
        return pd.DataFrame({"session_date": dates, "roll_effective": flags})

    check("1 roll over 16 years FAILS (the actual defect)",
          raises(lambda: assert_roll_count(cal_with(1)), ValueError))
    check("0 rolls FAILS", raises(lambda: assert_roll_count(cal_with(0)), ValueError))
    check("65 rolls PASSES", not raises(lambda: assert_roll_count(cal_with(65)), ValueError))
    check("64 rolls PASSES", not raises(lambda: assert_roll_count(cal_with(64)), ValueError))
    check("300 rolls FAILS (runaway flip-flop)",
          raises(lambda: assert_roll_count(cal_with(300)), ValueError))
    check("40 rolls FAILS (a quarter of them silently missing)",
          raises(lambda: assert_roll_count(cal_with(40)), ValueError))


def test_third_friday() -> None:
    # Verified against the real last-bar dates in the dataset.
    check("Mar 2015 expiry = 2015-03-20",
          third_friday(2015, 3) == pd.Timestamp("2015-03-20"))
    check("Sep 2010 expiry = 2010-09-17",
          third_friday(2010, 9) == pd.Timestamp("2010-09-17"))
    check("Dec 2020 expiry = 2020-12-18",
          third_friday(2020, 12) == pd.Timestamp("2020-12-18"))
    check("Jun 2020 expiry = 2020-06-19",
          third_friday(2020, 6) == pd.Timestamp("2020-06-19"))


# --------------------------------------------------------------------------
# End to end on a tiny synthetic frame that reproduces the failure shape:
# a spread out-volumes the outrights right at the roll.
# --------------------------------------------------------------------------
def test_build_calendar_ignores_spreads() -> None:
    """Four years of quarterly contracts, with a spread that always out-volumes.

    This is the failure shape that actually occurred: the spread carried more
    RTH volume than either outright, so it won the vote and, because the parser
    failed upward, held the front month forever.
    """
    sessions = pd.date_range("2015-01-02", "2018-12-31", freq="B")
    codes = [("H", 3), ("M", 6), ("U", 9), ("Z", 12)]

    def chain(d: pd.Timestamp):
        """(front, back) outright for this session: roll ~8 days before expiry."""
        seq = []
        for yr in range(d.year, d.year + 2):
            for c, mth in codes:
                seq.append((third_friday(yr, mth), f"NQ{c}{yr % 10}"))
        seq.sort()
        live = [s for s in seq if (s[0] - d).days > 8]
        return live[0][1], live[1][1]

    rows = []
    for d in sessions:
        front, back = chain(d)
        spread = f"{front}-{back}"
        for sym, vol in ((front, 1000), (back, 300), (spread, 99_999)):
            for minute in range(3):
                ts = pd.Timestamp(d) + pd.Timedelta(hours=10, minutes=minute)
                rows.append({
                    "ts_et": ts.tz_localize("America/New_York"),
                    "instrument_id": abs(hash(sym)) % 1_000_000,
                    "symbol": sym, "open": 100.0, "high": 101.0, "low": 99.0,
                    "close": 100.5, "volume": vol, "session_date": pd.Timestamp(d),
                })
    df = pd.DataFrame(rows)

    cal = build_roll_calendar(df)
    fronts = sorted(set(cal["front_symbol"]))
    n_rolls = int(cal["roll_effective"].sum())

    check("spread never becomes the front month even at 100x the volume",
          not any(is_spread(s) for s in fronts), str(fronts))
    check("roll count lands in the a-priori band (~16 over 4 years)",
          12 <= n_rolls <= 20, f"rolls={n_rolls}")
    check("every front symbol is a real outright",
          all(s.startswith("NQ") and len(s) == 4 for s in fronts), str(fronts))


def main() -> int:
    for fn in (test_decade_wrap, test_parser_fails_loudly, test_spread_detection,
               test_roll_count_band, test_third_friday,
               test_build_calendar_ignores_spreads):
        fn()
    total = len(PASS) + len(FAIL)
    print(f"\n{len(PASS)}/{total} roll tests passed.")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
