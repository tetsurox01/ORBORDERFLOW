"""STEP 2 -- build the roll calendar and the sample partitions.

IVB-SPEC.md sec 0.1 (rolls) and sec 0.2.3 (partitions).
Both are computed ONCE and written to data/. Never recomputed inside a backtest.

Usage:
    python scripts/02_build_rolls.py data/raw/nq_ohlcv1m_2015-01-01_2026-09-01.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivb.data import load                                        # noqa: E402
from ivb.partitions import build_partitions                      # noqa: E402
from ivb.rolls import build_roll_calendar, daily_adjusted        # noqa: E402
from ivb.timestamps import assert_verified                       # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    assert_verified()
    print("[02] timestamp convention verified")

    bars = load(sys.argv[1])
    print(f"[02] {len(bars):,} bars loaded")

    cal = build_roll_calendar(bars)
    n_rolls = int(cal["roll_effective"].sum())
    print(f"[02] roll calendar: {len(cal):,} sessions, {n_rolls} rolls -> data/roll_calendar.csv")
    print(cal[cal["roll_effective"]].head(10).to_string(index=False))

    adj = daily_adjusted(bars, cal)
    adj.to_parquet("data/daily_adjusted.parquet")
    print(f"[02] ratio-adjusted daily series: {len(adj):,} sessions (audit PASSED)")

    p = build_partitions(cal["session_date"])
    print("\n[02] partitions -> data/partitions.json")
    for k, v in p.to_json().items():
        print(f"     {k}: {v}")
    print("\n[02] NEXT: python scripts/03_run_step1.py " + sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
