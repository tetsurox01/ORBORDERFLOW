"""BIN-GRID CENSUS -- how many profile bins span the initial balance, by year.

===========================================================================
REPORT ONLY. THIS SCRIPT CHANGES NOTHING AND FIXES NOTHING.
It does not edit ivb/profile.py, does not run run_strategy(), does not run
b9_sensitivity(), and computes no PnL, expectancy, win rate or R of any kind.
It measures the GEOMETRY of the sec b.2 bin rule and nothing else.
===========================================================================

THE DEFECT BEING MEASURED (two separate causes, reported separately)

C1  BIN WIDTH SCALES WITH PRICE LEVEL.
    sec b.2 sets  bin_width = median 1-minute bar range inside the IB. NQ bar
    heights are roughly proportional to price level, so the width grows with the
    index. The IB range grows with it too -- but not necessarily at the same
    rate, and the ratio ib_range / bin_width is what decides how many bins the
    profile has to work with. The rule was registered as scale-INVARIANT. This
    script tests whether it actually is.

C2  THE BIN GRID IS ANCHORED AT ABSOLUTE PRICE ZERO.
    ivb/profile.py::_bins() computes  lo = floor(ib_low / bin_size) * bin_size
    and  hi = ceil(ib_high / bin_size) * bin_size. The grid is a multiple of
    bin_size counted from 0.00, not from the IB. The outermost bins hang OUTSIDE
    the IB window by up to one bin_size at each end. value_area() then returns
    VAH as edges[hi_i + 1] and VAL as edges[lo_i] -- bin EDGES -- so VAH can sit
    ABOVE ib_high and VAL BELOW ib_low. A value area outside the window it was
    built from is not a value area.
    C2's magnitude is bounded by one bin_size per side, so C1 makes C2 worse.
    They are separate bugs and either could be fixed without the other.

WHAT IS MEASURED PER SESSION (nothing is aggregated beyond percentiles of geometry)
    ib_range            points
    med_ib_bar_range    points, the input to the rule
    bin_width           points, the sec b.2 rule output (tick-rounded, floored)
    bins_across_ib      ib_range / bin_width          <-- the headline number
    n_grid_bins         len(edges) - 1, the integer bin count actually built
    over_high           vah - ib_high   (>0 means VAH is OUTSIDE the IB)
    over_low            ib_low - val    (>0 means VAL is OUTSIDE the IB)
    over_high_bins      over_high / bin_width   (C2 is bounded by 1.0)
    ib_mid              price level, so C1 can be read against it

SAMPLE -- AND THE HOLE IN IT, WHICH IS NOT OPTIONAL
    DEVELOPMENT              2015-01-01 .. 2024-05-01   read freely
    SEALED GAP               2024-05-02 .. 2025-12-31   NOT READ. NOT MEASURED.
    UNSEALED FORWARD WINDOW  2026-01-01 .. 2026-08-31   read; IN-SAMPLE since
                                                        2026-09-15, sec 0.2.3b

    The gap is 412 sessions of FORWARD_HOLDOUT that remain sealed. They are the
    entire out-of-sample capacity the study has left. A bin-count percentile is
    still a statistic computed on those bars, so reading them would spend part of
    that capacity to answer a question about a grid. This script refuses to do it
    and prints the hole instead of hiding it. Years 2024 (partial) and 2025
    (absent) are incomplete BY DESIGN, not by accident.

    Every 2026 row printed here is labelled IN-SAMPLE (unsealed 2026-09-15).

Usage:
    python scripts/07_bin_grid_census.py \
        data/raw/nq_ohlcv1m_2010-07-01_2026-08-31.parquet \
        --roll-calendar data/roll_calendar_6635298.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ivb.config import OUT, P0                                        # noqa: E402
from ivb.data import load                                             # noqa: E402
from ivb.partitions import load_partitions                            # noqa: E402
from ivb.profile import bin_width, build_profile                      # noqa: E402
from ivb.quality import degraded_dates                                # noqa: E402
from ivb.rolls import ROLL_FILE, front_month_bars                     # noqa: E402
from ivb.sessions import build_sessions                               # noqa: E402

UNSEAL_START = pd.Timestamp("2026-01-01")
UNSEAL_END = pd.Timestamp("2026-08-31")
UNSEAL_DATE = "2026-09-15"
UNSEAL_REF = "IVB-SPEC.md sec 0.2.3b UNSEAL #1"

OUT_DIR = OUT / "diagnostics"


def session_rows(sessions, cfg, degraded: set):
    """One row per session. Half-days and vendor-degraded days are EXCLUDED --
    run_strategy never builds a profile on them either, so including them would
    describe a grid the strategy does not use. They are counted, not silent.
    """
    rows = []
    skipped = {"half_day": 0, "vendor_degraded": 0}
    ib_end_min = 9 * 60 + 30 + cfg.ib_minutes
    ib_end_hm = "{:02d}:{:02d}".format(ib_end_min // 60, ib_end_min % 60)

    for s in sessions:
        if s.is_half_day:
            skipped["half_day"] += 1
            continue
        if s.session_date.normalize() in degraded:
            skipped["vendor_degraded"] += 1
            continue

        ib = s.bars[s.bars["hm"] < ib_end_hm]
        bw = bin_width(ib, mult=cfg.bin_width_mult,
                       floor_ticks=cfg.bin_width_floor_ticks)
        prof = build_profile(ib, method="volume_uniform",
                            bin_mult=cfg.bin_width_mult, va_pct=cfg.va_pct)
        med = float(np.median(ib["high"].to_numpy(float) - ib["low"].to_numpy(float)))

        rows.append({
            "session_date": s.session_date,
            "year": int(s.session_date.year),
            "ib_high": s.ib_high,
            "ib_low": s.ib_low,
            "ib_mid": (s.ib_high + s.ib_low) / 2.0,
            "ib_range": s.ib_range,
            "med_ib_bar_range": med,
            "bin_width": bw,
            "bins_across_ib": s.ib_range / bw if bw > 0 else np.nan,
            "n_grid_bins": len(prof.edges) - 1,
            "poc": prof.poc,
            "vah": prof.vah,
            "val": prof.val,
            "over_high": prof.vah - s.ib_high,
            "over_low": s.ib_low - prof.val,
            "over_high_bins": (prof.vah - s.ib_high) / bw if bw > 0 else np.nan,
            "over_low_bins": (s.ib_low - prof.val) / bw if bw > 0 else np.nan,
        })
    return pd.DataFrame(rows), skipped


def pct_table(df: pd.DataFrame) -> pd.DataFrame:
    def q(g, col, p):
        return float(np.percentile(g[col].dropna().to_numpy(float), p))

    out = []
    for yr, g in df.groupby("year", sort=True):
        out.append({
            "year": yr,
            "n": len(g),
            "bins_p10": q(g, "bins_across_ib", 10),
            "bins_p50": q(g, "bins_across_ib", 50),
            "bins_p90": q(g, "bins_across_ib", 90),
            "ib_mid_p50": q(g, "ib_mid", 50),
            "ib_range_p50": q(g, "ib_range", 50),
            "bin_w_p50": q(g, "bin_width", 50),
            "over_hi_p50": q(g, "over_high", 50),
            "over_hi_p90": q(g, "over_high", 90),
            "out_of_ib_pct": 100.0 * float(
                ((g["over_high"] > 0) | (g["over_low"] > 0)).mean()),
        })
    return pd.DataFrame(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="1-minute OHLCV parquet")
    ap.add_argument("--roll-calendar", default=None,
                    help="READ a roll calendar from here. Nothing is written or rebuilt.")
    args = ap.parse_args()

    cfg = P0
    p = load_partitions()

    print("\n" + "=" * 74)
    print("BIN-GRID CENSUS -- REPORT ONLY. No fix applied. No PnL computed.")
    print("=" * 74)
    print("sec b.2 rule under test: bin_width = median IB 1-min bar range")
    print("                         x mult {}  floor {} tick(s)".format(
        cfg.bin_width_mult, cfg.bin_width_floor_ticks))
    print("\nSAMPLE")
    print("  DEVELOPMENT      {} .. {}   read".format(
        p.dev_start.date(), p.dev_end.date()))
    print("  SEALED GAP       {} .. {}   NOT READ, NOT MEASURED".format(
        (p.dev_end + pd.Timedelta(days=1)).date(),
        (UNSEAL_START - pd.Timedelta(days=1)).date()))
    print("  UNSEALED WINDOW  {} .. {}   read -- IN-SAMPLE (unsealed {})".format(
        UNSEAL_START.date(), UNSEAL_END.date(), UNSEAL_DATE))
    print("  The gap is 412 sealed FORWARD_HOLDOUT sessions ({}).".format(UNSEAL_REF))
    print("  2024 is PARTIAL and 2025 is ABSENT for that reason, by design.")

    roll_path = Path(args.roll_calendar) if args.roll_calendar else ROLL_FILE
    if not roll_path.exists():
        print("\n[07] roll calendar missing: {}".format(roll_path))
        return 2

    bars = load(args.path)
    cal = pd.read_csv(roll_path, parse_dates=["session_date"])
    print("\n[07] roll calendar: {}  ({:,} rows)".format(roll_path, len(cal)))
    if roll_path != ROLL_FILE:
        print("     *** NOT the default data/roll_calendar.csv.")

    front = front_month_bars(bars, cal)
    d = pd.to_datetime(front["session_date"])

    dev = front[(d >= p.dev_start) & (d <= p.dev_end)].copy()
    uns = front[(d >= UNSEAL_START) & (d <= UNSEAL_END)].copy()
    kept = pd.concat([dev, uns], ignore_index=True)
    if len(kept) == 0:
        print("[07] no bars in the readable windows. Check the roll calendar.")
        return 2

    degraded = degraded_dates()
    sessions = build_sessions(kept, cfg)
    print("[07] sessions with a definable IB: {:,}".format(len(sessions)))

    df, skipped = session_rows(sessions, cfg, degraded)
    print("[07] excluded: half_day {}, vendor_degraded {}".format(
        skipped["half_day"], skipped["vendor_degraded"]))
    print("[07] sessions measured: {:,}".format(len(df)))

    tab = pct_table(df)

    print("\n" + "-" * 104)
    print("BINS ACROSS THE INITIAL BALANCE  (ib_range / bin_width), per session, by year")
    print("-" * 104)
    hdr = "{:<6} {:>5} | {:>6} {:>6} {:>6} | {:>8} {:>8} {:>7} | {:>7} {:>7} {:>7}"
    print(hdr.format("year", "n", "p10", "p50", "p90",
                     "ibMid50", "ibRng50", "binW50", "ovHi50", "ovHi90", "outIB%"))
    for _, r in tab.iterrows():
        mark = ""
        if int(r["year"]) == 2026:
            mark = "  <-- IN-SAMPLE (unsealed {})".format(UNSEAL_DATE)
        if int(r["year"]) == 2024:
            mark = "  <-- PARTIAL (to {}; rest sealed)".format(p.dev_end.date())
        print(hdr.format(int(r["year"]), int(r["n"]),
                         "{:.2f}".format(r["bins_p10"]),
                         "{:.2f}".format(r["bins_p50"]),
                         "{:.2f}".format(r["bins_p90"]),
                         "{:,.0f}".format(r["ib_mid_p50"]),
                         "{:.2f}".format(r["ib_range_p50"]),
                         "{:.2f}".format(r["bin_w_p50"]),
                         "{:+.2f}".format(r["over_hi_p50"]),
                         "{:+.2f}".format(r["over_hi_p90"]),
                         "{:.1f}".format(r["out_of_ib_pct"])) + mark)
    print("-" * 104)
    print("ovHi = vah - ib_high in POINTS. Positive means the value area high sits")
    print("OUTSIDE the window it was built from (cause C2, the zero-anchored grid).")
    print("outIB% = share of sessions where VAH > ib_high OR VAL < ib_low.")
    print("2025 has no row: those sessions are sealed and were never read.")

    print("\nC2 BOUND CHECK -- over_high / bin_width must never exceed 1.0")
    print("  max over_high_bins = {:.4f}   max over_low_bins = {:.4f}".format(
        float(df["over_high_bins"].max()), float(df["over_low_bins"].max())))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_p = OUT_DIR / "bin_grid_census_sessions.csv"
    tab_p = OUT_DIR / "bin_grid_census_by_year.csv"
    for pth in (csv_p, tab_p):
        if pth.exists():
            print("\n[07] REFUSED: {} already exists. Not overwriting.".format(pth))
            return 3
    df.to_csv(csv_p, index=False)
    tab.to_csv(tab_p, index=False)
    print("\n[07] wrote {}".format(csv_p))
    print("[07] wrote {}".format(tab_p))
    print("[07] NOTHING WAS FIXED. ivb/profile.py is unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
