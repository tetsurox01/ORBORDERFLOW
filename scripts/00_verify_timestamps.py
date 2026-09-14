"""STEP 0 -- verify the bar timestamp convention. RUN THIS FIRST.

IVB-SPEC.md sec 0.2.2. A one-minute error here silently leaks the future into the
initial balance and invalidates every result in this project.

Usage:
    python scripts/00_verify_timestamps.py data/raw/nq_ohlcv1m_2015-01-01_2026-09-01.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.data import load            # noqa: E402
from ivb.timestamps import verify    # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    print(f"[00] loading {path}")
    bars = load(path)
    print(f"[00] {len(bars):,} bars, {bars['session_date'].nunique():,} sessions, "
          f"{bars['symbol'].nunique()} contracts")

    v = verify(bars)

    print("\n" + "=" * 70)
    print("TIMESTAMP CONVENTION VERIFICATION")
    print("=" * 70)
    print(f"convention            : {v.convention}")
    print(f"confident             : {v.confident}")
    print(f"sessions tested       : {v.sessions_tested}")
    print(f"open spike at 09:29   : {v.spike_at_0929}")
    print(f"open spike at 09:30   : {v.spike_at_0930}   <- expected for open-stamped")
    print(f"open spike at 09:31   : {v.spike_at_0931}   <- would mean CLOSE-stamped")
    print(f"halt check weeknights : {v.halt_sessions_tested:,}")
    print(f"last pre-halt = 16:59 : {v.last_bar_before_halt_1659:,}   <- expected for open-stamped")
    print(f"last pre-halt = 17:00 : {v.last_bar_before_halt_1700:,}   <- would mean CLOSE-stamped")
    print(f"median RTH bar count  : {v.median_rth_bar_count}  (expect 390)")
    print(f"sessions with 390 bars: {v.sessions_with_390_bars}")
    for n in v.notes:
        print(f"\n  ! {n}")

    if v.confident and v.convention == "open_stamped":
        print("\nVERDICT: PASS -- spec sec 0 stamping confirmed. Safe to proceed.")
        return 0
    print("\nVERDICT: DO NOT PROCEED. Fix the loader, then re-run this script.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
