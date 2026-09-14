"""Generate synthetic NQ-shaped bars so the whole pipeline can be smoke-tested
WITHOUT spending money on Databento.

This is plumbing validation only. The price process is a random walk with no
breakout edge by construction, so Step 1 SHOULD fail its kill criteria on this
data. That is the expected and correct result -- it is the null hypothesis made
literal, and a pipeline that reports an edge here has a bug.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ET = "America/New_York"
_MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}


def front_symbol(d: pd.Timestamp) -> tuple[str, str]:
    """Return (front, next) contract symbols for a date, quarterly cycle."""
    q = ((d.month - 1) // 3 + 1) * 3
    year = d.year
    if d.month == q and d.day > 8:      # rolled already
        q += 3
    if q > 12:
        q, year = q - 12, year + 1
    nq = q + 3
    nyear = year
    if nq > 12:
        nq, nyear = nq - 12, year + 1
    return (f"NQ{_MONTH_CODE[q]}{year % 100}", f"NQ{_MONTH_CODE[nq]}{nyear % 100}")


def make(start="2015-01-02", end="2017-12-29", seed=7, out="data/raw/synthetic.parquet"):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, end)
    rows = []
    px = 4200.0

    for d in days:
        fs, ns = front_symbol(d)
        # overnight drift
        px *= (1 + rng.normal(0, 0.006))
        session_open = px

        idx = pd.date_range(f"{d.date()} 09:30", f"{d.date()} 15:59", freq="1min", tz=ET)
        n = len(idx)
        # random walk, no breakout edge by construction
        steps = rng.normal(0, 1.6, n)
        closes = session_open + np.cumsum(steps)
        opens = np.r_[session_open, closes[:-1]]
        wig = np.abs(rng.normal(0, 1.1, n))
        highs = np.maximum(opens, closes) + wig
        lows = np.minimum(opens, closes) - wig
        # tick-align
        q = lambda a: np.round(a / 0.25) * 0.25  # noqa: E731
        opens, highs, lows, closes = q(opens), q(highs), q(lows), q(closes)
        highs = np.maximum.reduce([highs, opens, closes])
        lows = np.minimum.reduce([lows, opens, closes])

        # open volume spike so the timestamp verifier has something to find
        vol = rng.integers(200, 2000, n).astype(float)
        vol[0] *= 12

        for t, o, h, l, c, v in zip(idx, opens, highs, lows, closes, vol):
            rows.append((t, fs, o, h, l, c, v))
            # thin back-month volume so the roll crossover is detectable
            rows.append((t, ns, o, h, l, c, v * (0.05 if d.day <= 8 else 2.0)))

        px = closes[-1]

    df = pd.DataFrame(rows, columns=["ts_et", "symbol", "open", "high", "low", "close", "volume"])
    df["ts_event"] = df["ts_et"].dt.tz_convert("UTC")
    df = df.drop(columns=["ts_et"])
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    print(f"wrote {len(df):,} rows, {df['symbol'].nunique()} contracts -> {p}")
    return p


if __name__ == "__main__":
    make()
