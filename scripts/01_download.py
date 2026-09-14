"""STEP 1 -- download NQ 1-minute bars from Databento.

IVB-SPEC.md sec 0.2.1: GLBX.MDP3 / ohlcv-1m / NQ.FUT parent -> INDIVIDUAL contracts.
Costs money. Prints an estimate and refuses to spend without confirmation.

Usage:
    $env:DATABENTO_API_KEY = 'db-...'
    python scripts/01_download.py 2015-01-01 2026-09-01
    # review the printed cost, then:
    $env:IVB_CONFIRM_SPEND = 'yes'
    python scripts/01_download.py 2015-01-01 2026-09-01
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
