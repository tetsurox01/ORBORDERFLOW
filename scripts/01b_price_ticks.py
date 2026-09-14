"""STEP 4 PRE-PRICING -- what would the TICK pull cost? ESTIMATE ONLY.

IVB-SPEC.md sec 0.2.2 (Layer 2 data requirement). Layer 2 needs aggressor side,
which ohlcv-1m does not carry. That means GLBX.MDP3 / schema "trades".

THIS SCRIPT CANNOT DOWNLOAD ANYTHING.
    It calls metadata.get_cost and metadata.get_billable_size, which are FREE
    metadata endpoints, and it never constructs a timeseries request. There is no
    IVB_CONFIRM_SPEND branch in this file, deliberately -- not a disabled one, not
    a commented-out one. To actually buy tick data a NEW script has to be written,
    which is a separate, visible decision.

WHY THIS RUNS NOW, AHEAD OF THE GATE IT SERVES.
    Step 4 is gated: Layer 2 is not built until Layers 0/1/3 pass on bars. Nothing
    here changes that. What is time-limited is the ACCOUNT CREDIT, which expires
    six months after signup. If the tick sample fits inside credits that would
    otherwise be lost, the acquisition decision and the research decision come
    apart, and only the acquisition one is urgent. Buying data is not the same as
    believing the layer works, and a cheap dataset is not evidence for Layer 2.

Usage:
    # key from .env at the repo root (copy .env.example), or from the environment
    python scripts/01b_price_ticks.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.data import DATASET, PARENT, _load_env  # noqa: E402

# Same .env handling as the download path: repo-root .env, override=False so a
# real environment variable still wins, and the same refusal to run if .env is
# tracked by git. Nothing here can spend, but a leaked key is a leaked key.

TICK_SCHEMA = "trades"

# Pre-registered pricing windows. A six-month sample and one month of it, so the
# scaling is visible rather than assumed -- tick volume is not uniform across
# months (roll weeks and high-volatility months carry far more messages).
WINDOWS = [
    ("6 months", "2025-01-01", "2025-06-30"),
    ("1 month ", "2025-01-01", "2025-01-31"),
]

# Observed on THIS account for the ohlcv-1m pull. Recorded for contrast only --
# see the warning printed at the end and IVB-SPEC.md sec 0.2.1.
OHLCV_OBSERVED_USD_PER_GB = 66.0


def main() -> int:
    try:
        import databento as db
    except ImportError as e:
        raise ImportError("pip install databento") from e

    _load_env()
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("DATABENTO_API_KEY not set.")
        print("Either copy .env.example to .env and fill it in, or:")
        print("PowerShell:  $env:DATABENTO_API_KEY = 'db-...'")
        return 2

    client = db.Historical(key)

    print("[01b] STEP 4 TICK PRICING -- ESTIMATE ONLY, NOTHING IS DOWNLOADED")
    print("[01b] dataset={}  symbols=[{}]  stype_in=parent  schema={}".format(
        DATASET, PARENT, TICK_SCHEMA))
    print()

    rows = []
    for label, start, end in WINDOWS:
        kw = dict(dataset=DATASET, symbols=[PARENT], stype_in="parent",
                  schema=TICK_SCHEMA, start=start, end=end)
        cost = float(client.metadata.get_cost(**kw))
        size = float(client.metadata.get_billable_size(**kw))
        gb = size / 1e9
        rate = cost / gb if gb else float("nan")
        rows.append((label, start, end, cost, gb, rate))
        print("[01b] {}  {} -> {}".format(label, start, end))
        print("        cost          ${:,.2f}".format(cost))
        print("        billable      {:,.3f} GB   ({:,} bytes)".format(gb, int(size)))
        print("        implied rate  ${:,.2f} / GB".format(rate))
        print()

    six, one = rows[0], rows[1]
    if one[3] > 0:
        print("[01b] SCALING: 6 months costs {:.2f}x one month "
              "(a flat 6.00x would mean uniform message volume; it is not).".format(
                  six[3] / one[3]))
    print("[01b] rough per-month rate from the 6-month window: ${:,.2f}/month"
          .format(six[3] / 6.0))
    print()

    print("[01b] DO NOT EXTRAPOLATE BETWEEN SCHEMAS, IN EITHER DIRECTION.")
    print("        ohlcv-1m billed at ~${:,.0f}/GB on this account, NOT the $0.50/GB"
          .format(OHLCV_OBSERVED_USD_PER_GB))
    print("        headline rate. Aggregated schemas are priced far higher per byte,")
    print("        because the price tracks the UNDERLYING MESSAGES, not the bytes")
    print("        delivered. So a bar cost predicts nothing about a tick cost, and a")
    print("        tick cost predicts nothing about a bar cost. The only admissible")
    print("        number for either is the one get_cost returns for that exact")
    print("        dataset, schema, symbology and window. (sec 0.2.1)")
    print()
    print("[01b] NOTHING WAS DOWNLOADED. This script has no purchase path.")
    print("[01b] Buying tick data requires a new script and a separate decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
