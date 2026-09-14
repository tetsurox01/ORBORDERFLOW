"""STEP 1 -- download NQ 1-minute bars from Databento.

IVB-SPEC.md sec 0.2.1: GLBX.MDP3 / ohlcv-1m / NQ.FUT parent -> INDIVIDUAL contracts.
Costs money. Prints an estimate and refuses to spend without confirmation.

Usage:
    $env:DATABENTO_API_KEY = 'db-...'
    python scripts/01_download.py 2010-07-01 2026-08-31
    # review the printed cost, then:
    $env:IVB_CONFIRM_SPEND = 'yes'
    python scripts/01_download.py 2010-07-01 2026-08-31

The pre-registered range (sec 0.2.3 / g.1.5):
    start 2010-07-01  pulls the SEALED BACKWARD_HOLDOUT in the same job, so there is
                      no second spend decision later.

                      JULY, not January, and this is NOT a preference:
                        2010-06-06  GLBX.MDP3 dataset coverage BEGINS. Databento has
                                    nothing before it. 2010-01-01 was never available
                                    to ask for -- a vendor boundary, not a choice.
                        2010-07-01  the first clean month boundary at or after that,
                                    so the sec (i) monthly block bootstrap gets whole
                                    blocks at BOTH ends of the sample.
                      The ~24 sessions of June 2010 that do exist are deliberately
                      skipped: a partial block is worth less than a clean one, and
                      the backward holdout is a regime check, not a size exercise.
                      So "2010-2014" in prose means 2010-07-01 .. 2014-12-31.

    end   2026-08-31  a clean month boundary, for the same bootstrap reason.

Neither date can move DEVELOPMENT or FORWARD_HOLDOUT: ivb/partitions.py hardcodes
DEV_START = 2015-01-01 and computes the 80% split over sessions >= 2015 only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.data import download  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    start, end = sys.argv[1], sys.argv[2]
    out = download(start, end)
    print(f"[01] done -> {out}")
    print("[01] NEXT: python scripts/00_verify_timestamps.py " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
