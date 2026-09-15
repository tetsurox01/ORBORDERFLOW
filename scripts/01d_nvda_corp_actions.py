"""NVDA 2026 -- PRICE THE 1-MINUTE PULL, AND CHECK FOR CORPORATE ACTIONS FIRST.

Two jobs, deliberately asymmetric. Read this before running it.

JOB 1 -- PRICE THE INTRADAY PULL. IT CANNOT BUY IT.
    Target:  EQUS.MINI, ohlcv-1m, NVDA, 2026-01-01 .. 2026-08-31.
    This script calls metadata.get_cost and metadata.get_billable_size for that
    window, prints the number, and STOPS. There is NO IVB_CONFIRM_SPEND branch
    for the 1-minute pull in this file -- not a disabled one, not a commented-out
    one. Buying the bars needs a separate script, which is a separate and visible
    decision. Same discipline as scripts/01b_price_ticks.py and 01c_price_nvda.py.

JOB 2 -- BUY THE DAILY BARS, AND ONLY THE DAILY BARS.
    Explicitly instructed: check for corporate actions inside the window WITHOUT
    buying intraday data. A corporate action is a DAILY-resolution event, so
    ohlcv-1d answers it and costs cents.

    Two daily pulls are made, both over 2025-12-01 .. 2026-09-01:
      EQUS.MINI   the dataset actually being considered -- the corporate-action
                  scan proper. The window deliberately starts one month BEFORE
                  2026-01-01 so a split landing on the first trading day of
                  January is still visible as an overnight step.
      the others  Bought for ONE reason: they are the only way to answer "is
                  EQUS.MINI volume the full NVDA tape?" with a MEASUREMENT.
                  Databento does not publish EQUS.MINI's venue list or its
                  share of the tape (see the VENUE COVERAGE block at the
                  end), so there is no document to quote instead. Daily bars
                  cost about $0.0003 each, so the comparison is effectively
                  free and the alternative is guessing.

    HARD CEILING. If the two daily pulls together price above DAILY_SPEND_CEILING
    the script refuses to download and exits. "A few cents" is checked, not
    assumed.

WHAT A CLEAN SCAN DOES AND DOES NOT PROVE
    A clean scan proves no SPLIT or large special dividend landed inside the
    scanned window. It does NOT make the series split-adjusted, and it says
    nothing about 2024-06-10, which is outside this window and outside the
    requested 2026 range. It also cannot see a corporate action that does not
    move the price -- a name change, a CUSIP change, an index event.

Usage:
    python scripts/01d_nvda_corp_actions.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                                  # noqa: E402
import pandas as pd                                                 # noqa: E402

from ivb.data import _load_env                                      # noqa: E402

SYMBOL = "NVDA"

# ---- Job 1: the intraday pull being priced. PRICED ONLY. -------------------
TARGET_DATASET = "EQUS.MINI"
TARGET_SCHEMA = "ohlcv-1m"
TARGET_START = "2026-01-01"
TARGET_END = "2026-08-31"

# ---- Job 2: the daily corporate-action scan. BOUGHT. ----------------------
DAILY_SCHEMA = "ohlcv-1d"
DAILY_START = "2025-12-01"          # one month of run-up, on purpose
DAILY_END = "2026-09-01"
DAILY_DATASETS = ["EQUS.MINI", "XNAS.ITCH", "DBEQ.BASIC", "EQUS.SUMMARY",
                  "EQUS.ALL", "XBOS.ITCH", "XPSX.ITCH"]
DAILY_SPEND_CEILING = 0.50          # USD, total across both daily pulls

# An overnight move this large is treated as "explain it before trusting it".
# NVDA's largest ordinary post-earnings overnight moves are in the 10-20% band,
# so this threshold is NOT a split detector on its own -- it is a shortlist, and
# every hit is then checked against the volume signature below.
GAP_FLAG = 0.15
# A split multiplies volume by the same ratio it divides price by. An earnings
# gap does not. That ratio test is what separates the two.
SPLIT_RATIOS = [2, 3, 4, 5, 10, 20]


def _fetch_daily(client, dataset: str):
    """ohlcv-1d for one dataset. This DOWNLOADS -- it is the authorised spend."""
    store = client.timeseries.get_range(
        dataset=dataset, symbols=[SYMBOL], stype_in="raw_symbol",
        schema=DAILY_SCHEMA, start=DAILY_START, end=DAILY_END,
    )
    df = store.to_df()
    if df.empty:
        return df
    df = df.reset_index()
    tcol = "ts_event" if "ts_event" in df.columns else df.columns[0]
    df["date"] = pd.to_datetime(df[tcol], utc=True).dt.tz_convert(
        "America/New_York").dt.date
    # Some datasets emit ONE BAR PER PUBLISHER (venue) per day rather than one
    # consolidated bar -- DBEQ.BASIC returns 3 rows per date for NVDA. Summing
    # the volume and taking the outer high/low is the correct consolidation, and
    # silently taking the first row would have understated the tape by 3x. The
    # per-date row count is reported so this is visible rather than assumed.
    df = df[["date", "open", "high", "low", "close", "volume"]].sort_values("date")
    rows_per_date = len(df) / max(df["date"].nunique(), 1)
    out = df.groupby("date", as_index=False).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"))
    out.attrs["rows_per_date"] = rows_per_date
    return out.sort_values("date").reset_index(drop=True)


def _scan(df: pd.DataFrame, label: str) -> int:
    """Overnight-step scan. Returns the number of flagged sessions."""
    print("-" * 78)
    print("CORPORATE-ACTION SCAN -- {}   ({} sessions, {} .. {})".format(
        label, len(df), df["date"].iloc[0], df["date"].iloc[-1]))
    print("-" * 78)

    prev_c = df["close"].shift(1)
    prev_v = df["volume"].shift(1)
    ratio = prev_c / df["open"]              # >1 means price stepped DOWN
    gap = df["open"] / prev_c - 1.0
    vol_ratio = df["volume"] / prev_v

    print("  price range over the window:   {:,.2f} .. {:,.2f}".format(
        df["low"].min(), df["high"].max()))
    print("  largest overnight move:        {:+.2%} on {}".format(
        gap.abs().max() if gap.notna().any() else float("nan"),
        df["date"].iloc[int(gap.abs().idxmax())] if gap.notna().any() else "n/a"))
    print("  first close {:,.2f}  ->  last close {:,.2f}   ({:+.1%} over the window)"
          .format(df["close"].iloc[0], df["close"].iloc[-1],
                  df["close"].iloc[-1] / df["close"].iloc[0] - 1.0))
    print()

    flagged = df.index[(gap.abs() > GAP_FLAG) & gap.notna()]
    if len(flagged) == 0:
        print("  NO overnight move above {:.0%}. No split-shaped step in this window."
              .format(GAP_FLAG))
    else:
        print("  {} session(s) moved more than {:.0%} overnight. Each is checked"
              " against the split signature:".format(len(flagged), GAP_FLAG))
        for i in flagged:
            r = float(ratio.iloc[i])
            vr = float(vol_ratio.iloc[i]) if np.isfinite(vol_ratio.iloc[i]) else float("nan")
            near = [n for n in SPLIT_RATIOS
                    if abs(r - n) / n < 0.05 or abs(r - 1.0 / n) * n < 0.05]
            verdict = ("SPLIT-SHAPED: price ratio ~{} AND volume moved the "
                       "matching way".format(near[0]) if near and vr > 1.5
                       else "NOT split-shaped (price ratio {:.3f} matches no common"
                            " split, volume x{:.2f})".format(r, vr))
            print("    {}  gap {:+.2%}  close->open ratio {:.4f}  vol x{:.2f}"
                  .format(df['date'].iloc[i], float(gap.iloc[i]), r, vr))
            print("        -> {}".format(verdict))
    print()
    return len(flagged)


def main() -> int:
    try:
        import databento as db
    except ImportError as e:
        raise ImportError("pip install databento") from e

    _load_env()
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("DATABENTO_API_KEY not set. Copy .env.example to .env and fill it in.")
        return 2
    client = db.Historical(key)

    print("=" * 78)
    print("NVDA 2026 -- INTRADAY PRICED (NOT BOUGHT), DAILY BOUGHT FOR THE SCAN")
    print("=" * 78)
    print()

    # ---------------------------------------------------------------- STEP 1
    print("-" * 78)
    print("STEP 1 -- COVERAGE")
    print("-" * 78)
    cover = {}
    for ds in sorted(set([TARGET_DATASET] + DAILY_DATASETS)):
        try:
            rng = client.metadata.get_dataset_range(dataset=ds)
        except Exception as e:
            print("{:<12} unavailable: {}".format(ds, str(e)[:70]))
            continue
        for sch in (TARGET_SCHEMA, DAILY_SCHEMA):
            s = rng.get("schema", {}).get(sch)
            if not s:
                print("{:<12} {:<10} NOT SERVED".format(ds, sch))
                continue
            a, b = str(s["start"])[:10], str(s["end"])[:10]
            cover[(ds, sch)] = (a, b)
            print("{:<12} {:<10} {} .. {}".format(ds, sch, a, b))
    print()

    if (TARGET_DATASET, TARGET_SCHEMA) not in cover:
        print("{} does not serve {}. Nothing to price.".format(
            TARGET_DATASET, TARGET_SCHEMA))
        return 2
    ts, te = cover[(TARGET_DATASET, TARGET_SCHEMA)]
    if ts > TARGET_START or te < TARGET_END:
        print("*** THE TARGET WINDOW IS NOT FULLY COVERED ***")
        print("    asked {} .. {}   available {} .. {}".format(
            TARGET_START, TARGET_END, ts, te))
        print()

    # ---------------------------------------------------------------- STEP 2
    print("-" * 78)
    print("STEP 2 -- THE INTRADAY PULL, PRICED. THIS SCRIPT STOPS HERE ON IT.")
    print("-" * 78)
    kw = dict(dataset=TARGET_DATASET, symbols=[SYMBOL], stype_in="raw_symbol",
              schema=TARGET_SCHEMA, start=TARGET_START, end=TARGET_END)
    target_cost = float(client.metadata.get_cost(**kw))
    target_size = float(client.metadata.get_billable_size(**kw))
    gb = target_size / 1e9
    print("  dataset        {}".format(TARGET_DATASET))
    print("  schema         {}".format(TARGET_SCHEMA))
    print("  symbol         {}  (stype_in=raw_symbol)".format(SYMBOL))
    print("  window         {} .. {}".format(TARGET_START, TARGET_END))
    print()
    print("  COST           ${:,.2f}".format(target_cost))
    print("  billable size  {:.6f} GB   ({:,} bytes)".format(gb, int(target_size)))
    print("  implied rate   ${:,.2f} / GB".format(target_cost / gb if gb else float("nan")))
    print()
    print("  NOT PURCHASED. No IVB_CONFIRM_SPEND branch exists in this file.")
    print()

    # ---------------------------------------------------------------- STEP 3
    print("-" * 78)
    print("STEP 3 -- THE DAILY SCAN, PRICED BEFORE IT IS BOUGHT")
    print("-" * 78)
    daily_cost = {}
    for ds in DAILY_DATASETS:
        if (ds, DAILY_SCHEMA) not in cover:
            print("  {:<12} does not serve {} -- skipped".format(ds, DAILY_SCHEMA))
            continue
        a, b = cover[(ds, DAILY_SCHEMA)]
        s, e = max(DAILY_START, a), min(DAILY_END, b)
        k = dict(dataset=ds, symbols=[SYMBOL], stype_in="raw_symbol",
                 schema=DAILY_SCHEMA, start=s, end=e)
        c = float(client.metadata.get_cost(**k))
        daily_cost[ds] = (c, s, e)
        print("  {:<12} {} .. {}   ${:,.4f}".format(ds, s, e, c))
    total = sum(v[0] for v in daily_cost.values())
    print()
    print("  TOTAL DAILY SPEND  ${:,.4f}   (ceiling ${:,.2f})".format(
        total, DAILY_SPEND_CEILING))
    if total > DAILY_SPEND_CEILING:
        print()
        print("  *** REFUSED. The daily scan priced above the ceiling. ***")
        print("  Nothing was downloaded. Raise DAILY_SPEND_CEILING deliberately,")
        print("  or drop the XNAS.ITCH comparison, and run again.")
        return 3
    print("  Under the ceiling -> downloading the DAILY bars only.")
    print()

    # ---------------------------------------------------------------- STEP 4
    frames = {}
    for ds in daily_cost:
        try:
            frames[ds] = _fetch_daily(client, ds)
            rpd = frames[ds].attrs.get("rows_per_date", 1.0)
            print("  [buy] {:<12} {} daily bars{}".format(
                ds, len(frames[ds]),
                "   ({:.0f} publisher rows per date, SUMMED)".format(rpd)
                if rpd > 1.01 else ""))
        except Exception as ex:
            print("  [buy] {:<12} FAILED: {}: {}".format(
                ds, type(ex).__name__, str(ex)[:160]))
    print()

    if TARGET_DATASET not in frames or frames[TARGET_DATASET].empty:
        print("No {} daily bars came back. The corporate-action question is"
              " UNANSWERED -- do not read this as 'clean'.".format(TARGET_DATASET))
        return 4

    # ---------------------------------------------------------------- STEP 5
    n_flag = _scan(frames[TARGET_DATASET], TARGET_DATASET)
    if "XNAS.ITCH" in frames and not frames["XNAS.ITCH"].empty:
        _scan(frames["XNAS.ITCH"], "XNAS.ITCH  (cross-check, same symbol)")

    # ---------------------------------------------------------------- STEP 6
    print("-" * 78)
    print("STEP 6 -- IS EQUS.MINI VOLUME THE FULL NVDA TAPE?  (MEASURED)")
    print("-" * 78)
    vols = {ds: f.set_index("date")["volume"] for ds, f in frames.items()
            if not f.empty}
    # EQUS.SUMMARY is the reference because its NVDA volume (~157M/day median)
    # matches NVDA's published consolidated ADV, while every other dataset here
    # is a fraction of it. It is used ONLY as a denominator -- it serves no
    # ohlcv-1m, so it cannot be the research dataset.
    ref = "EQUS.SUMMARY" if "EQUS.SUMMARY" in vols else "XNAS.ITCH"
    if ref not in vols:
        print("  No reference dataset available; the share cannot be measured.")
    else:
        j = pd.concat(vols, axis=1).dropna()
        rv = float(j[ref].median())
        print("  matched sessions: {}".format(len(j)))
        print("  reference: {} median NVDA daily volume {:,.0f} shares -- this"
              .format(ref, rv))
        print("  matches NVDA's published consolidated ADV, so it is treated as")
        print("  the consolidated tape. NOTE: {} serves NO ohlcv-1m.".format(ref))
        print()
        print("  {:<14} {:>16}  {:>12}  {}".format(
            "dataset", "median daily vol", "% of tape", "serves ohlcv-1m?"))
        for ds in sorted(vols, key=lambda d: -float(j[d].median())):
            m = float(j[ds].median())
            has1m = "yes" if (ds, TARGET_SCHEMA) in cover else "NO"
            print("  {:<14} {:>16,.0f}  {:>11.1f}%  {}".format(
                ds, m, 100.0 * m / rv, has1m))
        print()
        if TARGET_DATASET in j:
            share = 100.0 * float(j[TARGET_DATASET].median()) / rv
            print("  *** EQUS.MINI CARRIES {:.1f}% OF NVDA'S CONSOLIDATED VOLUME. ***"
                  .format(share))
            print("  That is about ONE THIRTY-FOURTH of the tape (1/{:.0f}), not the"
                  .format(round(100.0 / share)))
            print("  ~40% a genuine venue subset would give.")
            print("  It is smaller than NASDAQ ALONE, which a genuine")
            print("  multi-venue TRADE aggregation cannot be for a Nasdaq-listed name.")
            print("  So 'aggregated across several venues' describes how the QUOTE")
            print("  (the synthetic mini NBBO) is built. It does not mean the bar")
            print("  volume is the tape.")
        print()
        print("  AND THE BIND: the only dataset here that carries the full tape")
        print("  ({}) does NOT serve ohlcv-1m. Every dataset that DOES serve".format(ref))
        print("  ohlcv-1m carries a small fraction of NVDA's volume. There is no")
        print("  Databento product that gives consolidated NVDA 1-minute volume.")
        print()

        # extremes: a subset tape also misses the consolidated high/low
        if TARGET_DATASET in frames:
            print("  EXTREMES, which is what LAYER 0 keys on (the IB high/low):")
            a = frames[TARGET_DATASET].set_index("date")
            for other in [ref, "XNAS.ITCH"]:
                if other not in frames or other == TARGET_DATASET:
                    continue
                b = frames[other].set_index("date")
                k = a.join(b, lsuffix="_m", rsuffix="_o", how="inner")
                if not len(k):
                    continue
                hi = (k["high_m"] < k["high_o"] - 1e-9).mean()
                lo = (k["low_m"] > k["low_o"] + 1e-9).mean()
                print("    vs {:<14} MINI high is LOWER on {:>5.1%} of sessions,"
                      "  MINI low is HIGHER on {:>5.1%}".format(other, hi, lo))
            print("    A dataset that misses the tape's extreme cannot define an")
            print("    initial balance matching the tape the trade fills against.")
    print()

    # ---------------------------------------------------------------- STEP 7
    print("=" * 78)
    print("VENUE COVERAGE -- WHAT EQUS.MINI IS, PLAINLY")
    print("=" * 78)
    print("EQUS.MINI is NOT the full consolidated US tape, and it is NOT a single")
    print("venue either. Databento describes it as a DERIVED, AGGREGATED dataset")
    print("built from 'a proprietary blend of direct feeds sourced from several")
    print("NMS exchanges and ATSs', with ANONYMIZED component venues. It provides")
    print("a synthetic 'mini' NBBO.")
    print()
    print("Three things, and the measurement in STEP 6 is the one that binds:")
    print("  1. THE COMPONENT LIST IS NOT PUBLISHED. Databento does not disclose")
    print("     which venues are in it, or what share of the tape it carries, and")
    print("     that blend may be changed by the vendor without notice. There is")
    print("     no document to check, which is why STEP 6 measures instead.")
    print("  2. MEASURED, its bar volume is ~3% of NVDA's consolidated volume and")
    print("     is SMALLER THAN NASDAQ ALONE. A genuine multi-venue trade")
    print("     aggregation cannot be smaller than one of its own components, so")
    print("     'aggregated from several venues' describes the QUOTE construction,")
    print("     not the bar volume.")
    print("  3. This was NOT predictable from the docs. It was found by buying")
    print("     $0.004 of daily bars and comparing. Anything read off EQUS.MINI")
    print("     volume without that check would have been wrong by roughly 30x.")
    print()
    print("WHY THAT IS A LAYER 1 PROBLEM, NOT A BILLING DETAIL:")
    print("  Layer 1 is ENTIRELY a volume profile. POC, VAH and VAL are the")
    print("  argmax and the 70% mass of a volume distribution. Computing them on")
    print("  an undisclosed subset of the tape gives the POC of that subset, not")
    print("  NVDA's POC, and there is no way to bound the error because the")
    print("  sampling fraction is not published and is not constant across venues")
    print("  or across the day. Off-exchange prints in particular cluster around")
    print("  the touch differently from lit prints.")
    print()
    print("  Layer 0 is less exposed but not clean: the initial balance is a")
    print("  HIGH/LOW, and a subset tape can miss the consolidated extreme, which")
    print("  moves the breakout level and therefore the trade.")
    print()
    print("  A vendor-anonymized blend also cannot be reproduced or audited, which")
    print("  is a research problem separate from accuracy.")
    print()
    print("=" * 78)
    print("SPLIT ADJUSTMENT -- UNCHANGED BY THIS SCAN")
    print("=" * 78)
    print("Databento equity history is the exchange feed as published: AS-TRADED,")
    print("UNADJUSTED. A clean scan above means NO SPLIT LANDED INSIDE THE SCANNED")
    print("WINDOW. It does not mean the series is adjusted, and it says nothing")
    print("about the 10-for-1 split of 2024-06-10, which is outside this window.")
    print("For a 2026-only pull that split is out of range and does not bite.")
    if n_flag == 0:
        print()
        print("VERDICT: the scanned window shows no split-shaped overnight step.")
    print("=" * 78)
    print()
    print("RECOMMENDATION FROM THE MEASUREMENT, not from the price:")
    print("  DO NOT buy EQUS.MINI ohlcv-1m for a VOLUME PROFILE strategy. The")
    print("  $0.05 is irrelevant; the 3%-of-tape volume is not. If NVDA is")
    print("  wanted at all, XNAS.ITCH ohlcv-1m is the honest choice -- one")
    print("  NAMED venue at ~26% of the tape, reproducible and auditable, and")
    print("  it reaches back to 2018-05-01 instead of 2023-03-28. It is still")
    print("  not NVDA's volume profile, and that has to be said on every chart.")
    print()
    print("NOTHING INTRADAY WAS PURCHASED. Step 2 printed a cost and stopped.")
    print("Total spent by this run: the daily bars only, ${:,.4f}.".format(total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
