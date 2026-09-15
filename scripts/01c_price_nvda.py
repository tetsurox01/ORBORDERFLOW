"""NVDA 1-MINUTE BAR PRICING -- ESTIMATE ONLY. NOTHING IS DOWNLOADED.

THIS SCRIPT CANNOT BUY DATA.
    It calls metadata.list_datasets, metadata.get_dataset_range,
    metadata.get_cost and metadata.get_billable_size. All four are FREE metadata
    endpoints. It never constructs a timeseries request, and there is no
    IVB_CONFIRM_SPEND branch in this file -- not a disabled one, not a
    commented-out one. Buying NVDA bars would need a NEW script, which is a
    separate and visible decision. Same discipline as scripts/01b_price_ticks.py.

REQUESTED WINDOW vs WHAT EXISTS
    The request was ohlcv-1m, NVDA, 2015-01-01 .. 2026-08-31. Databento has no
    US equity dataset that reaches 2015. The script prints the coverage start of
    every equity dataset it can price, CLAMPS the request to what exists, and
    labels the clamp. It does not silently return a cheaper number for a shorter
    window.

VENUE COVERAGE IS A RESEARCH PROBLEM, NOT A BILLING DETAIL
    XNAS.ITCH is the Nasdaq order book ALONE. NVDA is Nasdaq-listed but a large
    share of its volume prints away from Nasdaq, so a single-venue ohlcv-1m bar
    carries a FRACTION of consolidated volume and its high/low can differ from
    the consolidated high/low. For a strategy whose entire Layer 1 is a VOLUME
    profile and whose Layer 0 is a high/low breakout, that is a first-order
    problem. The consolidated datasets (DBEQ.BASIC, EQUS.MINI) are priced
    alongside it so the trade-off is visible.

SPLIT ADJUSTMENT
    See the block printed at the end. Short version: Databento historical equity
    data is the exchange feed as it was published, so prices are AS-TRADED and
    UNADJUSTED for splits. NVDA split 10-for-1 effective 2024-06-10, so an
    unadjusted series steps down ~90% on that date. Handling is the caller's job.

Usage:
    python scripts/01c_price_nvda.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.data import _load_env  # noqa: E402

SYMBOL = "NVDA"
SCHEMA = "ohlcv-1m"

# The window as asked for. Never quietly moved -- clamped and labelled instead.
REQ_START = "2015-01-01"
REQ_END = "2026-08-31"

# Equity datasets that can serve ohlcv-1m. Nasdaq-listed NVDA trades on all of
# them; what differs is whether the bar is one venue or consolidated.
CANDIDATES = [
    ("XNAS.ITCH", "Nasdaq TotalView-ITCH -- SINGLE VENUE (listing exchange)"),
    ("DBEQ.BASIC", "Databento Equities Basic -- CONSOLIDATED (multi-venue)"),
    ("EQUS.MINI", "Databento US Equities Mini -- CONSOLIDATED (multi-venue)"),
    ("XBOS.ITCH", "Nasdaq BX -- SINGLE VENUE, small share. Priced for contrast."),
    ("XPSX.ITCH", "Nasdaq PSX -- SINGLE VENUE, small share. Priced for contrast."),
]

# Observed on THIS account for the NQ ohlcv-1m futures pull. Recorded for
# contrast only. Equity rates are not futures rates and neither predicts the
# other; see IVB-SPEC.md sec 0.2.1.
NQ_OHLCV_OBSERVED_USD_PER_GB = 66.0


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

    print("\n" + "=" * 78)
    print("NVDA ohlcv-1m PRICING -- ESTIMATE ONLY. NOTHING IS DOWNLOADED.")
    print("=" * 78)
    print("symbol={}  schema={}  requested {} .. {}".format(
        SYMBOL, SCHEMA, REQ_START, REQ_END))
    print()

    print("-" * 78)
    print("STEP 1 -- COVERAGE. What actually exists for {}?".format(SCHEMA))
    print("-" * 78)
    avail = {}
    for ds, note in CANDIDATES:
        try:
            rng = client.metadata.get_dataset_range(dataset=ds)
        except Exception as e:
            print("{:<12} unavailable: {}".format(ds, str(e)[:60]))
            continue
        sch = rng.get("schema", {}).get(SCHEMA)
        if not sch:
            print("{:<12} does NOT serve {}".format(ds, SCHEMA))
            continue
        s = str(sch["start"])[:10]
        e = str(sch["end"])[:10]
        avail[ds] = (s, e)
        gap = "" if s <= REQ_START else "   <-- STARTS {} AFTER THE REQUEST".format(s)
        print("{:<12} {} .. {}{}".format(ds, s, e, gap))
        print("             {}".format(note))
    print()

    if not avail:
        print("No candidate dataset serves {}. Nothing to price.".format(SCHEMA))
        return 2

    earliest = min(s for s, _ in avail.values())
    if earliest > REQ_START:
        print("*** THE REQUESTED WINDOW CANNOT BE FILLED. ***")
        print("    Requested start {}.  Earliest equity {} anywhere: {}.".format(
            REQ_START, SCHEMA, earliest))
        print("    {} .. {} does not exist at Databento in any equity dataset.".format(
            REQ_START, earliest))
        print("    Every cost below is for a SHORTER window than was asked for.")
        print()

    print("-" * 78)
    print("STEP 2 -- COST, each dataset over its OWN maximum available window")
    print("-" * 78)
    rows = []
    for ds, note in CANDIDATES:
        if ds not in avail:
            continue
        ds_start, ds_end = avail[ds]
        start = max(REQ_START, ds_start)
        end = min(REQ_END, ds_end)
        if start >= end:
            print("{:<12} no overlap with the requested window.".format(ds))
            continue
        kw = dict(dataset=ds, symbols=[SYMBOL], stype_in="raw_symbol",
                  schema=SCHEMA, start=start, end=end)
        try:
            cost = float(client.metadata.get_cost(**kw))
            size = float(client.metadata.get_billable_size(**kw))
        except Exception as e:
            print("{:<12} pricing failed: {}".format(ds, str(e)[:100]))
            continue
        gb = size / 1e9
        rate = cost / gb if gb else float("nan")
        clamped = (start != REQ_START) or (end != REQ_END)
        rows.append((ds, start, end, cost, gb, rate, clamped))
        print("{:<12} {} .. {}{}".format(
            ds, start, end, "   [CLAMPED from the request]" if clamped else ""))
        print("             cost           ${:,.2f}".format(cost))
        print("             billable       {:.6f} GB   ({:,} bytes)".format(gb, int(size)))
        print("             implied rate   ${:,.2f} / GB".format(rate))
        print()

    print("-" * 78)
    print("STEP 3 -- THE REQUESTED WINDOW, PRICED AS ASKED (expected to fail)")
    print("-" * 78)
    best = "XNAS.ITCH" if "XNAS.ITCH" in avail else sorted(avail)[0]
    kw = dict(dataset=best, symbols=[SYMBOL], stype_in="raw_symbol",
              schema=SCHEMA, start=REQ_START, end=REQ_END)
    try:
        cost = float(client.metadata.get_cost(**kw))
        print("{} {} .. {}  cost ${:,.2f}".format(best, REQ_START, REQ_END, cost))
        print("If this printed a number, the vendor served the pre-{} window after"
              " all -- verify the coverage claim above before believing it.".format(
                  avail[best][0]))
    except Exception as e:
        print("{} refused {} .. {}, as expected:".format(best, REQ_START, REQ_END))
        print("    {}: {}".format(type(e).__name__, str(e)[:240]))

    print()
    print("=" * 78)
    print("SPLIT ADJUSTMENT -- RAW, NOT ADJUSTED")
    print("=" * 78)
    print("Databento historical equity market data is the exchange feed as it was")
    print("published, so prices are AS-TRADED and UNADJUSTED. There is no")
    print("'adjusted' flag on a timeseries request and no adjusted ohlcv schema.")
    print()
    print("EVIDENCE, and its limit. Databento sells ADJUSTMENT FACTORS as a")
    print("SEPARATE reference-data product -- 'Adjustment factors are applied to")
    print("historical data to account for the effects of various corporate actions")
    print("on a security's price and maintain price continuity over long holding")
    print("periods' -- served over the reference API, contact-sales, pricing from")
    print("$225/month (databento.com/blog/adjustment-factors, 2024-10-16). A")
    print("vendor does not sell back-adjustment factors for data it already")
    print("adjusted. That is strong inference, NOT a quoted vendor sentence")
    print("saying 'ohlcv is unadjusted'. The definitive one-line check is to read")
    print("ohlcv-1d across 2024-06-07 .. 2024-06-10 and look for the 10x step.")
    print("This script does not run it, because that is a download.")
    print()
    print("COST SHAPE THAT FOLLOWS: the bars are cheap and the FIX is not. The")
    print("adjustment feed starts at $225/month against single-dollar bar costs,")
    print("so a split-correct NVDA series costs far more than the NVDA bars do.")
    print()
    print("NVDA 10-for-1 split, effective 2024-06-10. An unadjusted 1-minute")
    print("series therefore steps from roughly $1,200 to roughly $120 between")
    print("2024-06-07 close and 2024-06-10 open. Consequences for THIS project:")
    print("  - ATR14 sees a ~-90% true range on the split date and stays wrong")
    print("    for 14 sessions afterwards, because ATR is a trailing mean.")
    print("  - min_ib_range_atr compares a post-split IB range against a")
    print("    pre-split ATR for those sessions. The filter silently inverts.")
    print("  - Layer 0 breakout levels and Layer 1 bin widths are in dollars,")
    print("    so both are 10x too wide on either side of the boundary.")
    print("  - The ratio-adjusted daily series this project already builds for")
    print("    futures rolls (ivb/rolls.py::daily_adjusted) is the SAME shape of")
    print("    fix. A split is a ratio adjustment with ratio 1/10. Reusing that")
    print("    code needs a corporate-action calendar, which Databento's ohlcv")
    print("    schema does not ship -- it has to come from somewhere else.")
    print()
    print("VENUE WARNING, repeated because it is easy to skip:")
    print("XNAS.ITCH ohlcv-1m volume is NASDAQ ONLY, not consolidated. A volume")
    print("profile built on one venue's share of NVDA is not the volume profile")
    print("of NVDA. Consolidated coverage starts 2023-03-28 at the earliest.")
    print()
    print("[01c] NOTHING WAS DOWNLOADED. NOTHING WAS PURCHASED.")
    print("[01c] NQ ohlcv-1m billed ~${:,.0f}/GB on this account; the equity rates"
          .format(NQ_OHLCV_OBSERVED_USD_PER_GB))
    print("      above are MEASURED, not extrapolated from it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
