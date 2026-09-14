"""Generate synthetic NQ-shaped bars so the whole pipeline can be smoke-tested
WITHOUT spending money on Databento.

TWO generators, for two different jobs.

  structure="random_walk"      (default, data/raw/synthetic.parquet)
      Price is a driftless random walk and bar volume is drawn from
      rng.integers(200, 2000) -- i.i.d. and INDEPENDENT of price. No breakout
      edge by construction, so Step 1 SHOULD fail its kill criteria here. That
      is the null hypothesis made literal; a pipeline that reports an edge on
      this data has a bug.

      This file is ALSO the NEGATIVE CONTROL for the sec b.9 gate. Volume carries
      no price information, so no POC exists for a profile to find, the four
      allocation methods disagree freely, and b.9 MUST return MATERIAL.

  structure="anchored_volume"  (data/raw/synthetic_structured.parquet)
      POSITIVE CONTROL for the sec b.9 gate, and nothing else.

      Inside the IB window only, price mean-reverts (AR(1)) around a slowly
      drifting anchor and bar volume is a Gaussian kernel of the bar's distance
      from that anchor. So a real POC exists: price spends most of its TIME near
      the anchor and most of its VOLUME there too, which is what lets all four
      sec b.9 methods -- three volume-weighted, one pure bar-count -- agree.
      Bar ranges inside the IB are narrow. Under the OLD fixed 1.0-point bin that
      was half the reason the methods agreed. Under the sec b.2 RELATIVE bin width
      it no longer is -- the bin scales with the bar, so absolute bar height stops
      separating the two controls and they separate on volume STRUCTURE alone,
      which is what they were always meant to test. Both verdicts survived the
      switch; see sec b.2 for the before/after table.

      After the IB closes the process reverts to a driftless random walk, scaled
      down to match the quieter IB so that IB_range / ATR14 stays realistic and
      the min_ib_range_atr filter (sec f) does not quietly eat the sample.

WHY BOTH ARE NEEDED
      A gate that has only ever been run on data where it MUST trip has never
      executed its pass branch. Until it returns NOT MATERIAL on data where a POC
      genuinely exists, "MATERIAL" is not evidence about Layer 1 -- it is the only
      answer the gate has ever been able to give. Same argument as any
      synthetic-positive control: the test has to be shown capable of saying no.

QUARANTINE -- sec b.11
      The anchored file may be used for EXACTLY ONE thing: proving that the sec b.9
      gate's PASS branch executes. It may never source a reported statistic -- not a
      fill rate, not an exit mix, not a close_invalidation frequency, not a funnel
      count, not PnL. This is enforced in ivb/provenance.py, not left to memory:
      scripts/03 refuses to run on it, scripts/04 redacts every statistic and does
      not draw charts 3-5, and ivb/report.py re-checks at the artifact writer.

WHAT THE POSITIVE CONTROL DOES *NOT* SHOW
      The anchored generator's parameters were tuned until b.9 returned NOT
      MATERIAL. That is what a positive control is for, and it is not a finding
      about NQ. It shows the gate is capable of passing; it says nothing about
      whether real NQ volume is structured enough to pass it. The b.9 THRESHOLDS
      were not touched -- tuning those would be fitting the gate to a verdict.
      sec b.9 is still decided on real bars only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ET = "America/New_York"
_MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}

STRUCTURES = ("random_walk", "anchored_volume")

# ---- anchored_volume parameters --------------------------------------------
# Tuned until sec b.9 returns NOT MATERIAL. The GATE THRESHOLDS were not touched.
# THESE NUMBERS WERE SELECTED TO PRODUCE A VERDICT -- see the sec b.11 quarantine
# note above before quoting anything measured on this file.
#
# The mechanism that makes the four methods agree is stated plainly because it is
# the useful part: an IB bar must span about ONE profile bin. When a bar covers one
# bin, "where inside the bar did the volume trade" has no room to matter, and
# M1/M2/M3 collapse onto each other; the volume kernel then aligns M4 (pure bar
# count) with them by putting volume where price also spends its time.
#
# These parameters were tuned against the OLD fixed 1.0-point bin, which is why IB
# bar range sits near 0.9 points. sec b.2 now derives the bin width FROM the bar
# range, so that particular tuning no longer does anything -- the bin follows the
# bar whatever height it has. They are left as they are on purpose: re-tuning them
# against the new rule would be a second round of selection for no gain, and the
# verdict did not change.
IB_MINUTES = 30           # must match Config.ib_minutes
ANCHOR_SIGMA = 0.15       # per-minute drift of the fair-value anchor, points
AR_PHI = 0.94             # mean-reversion of price toward the anchor
AR_STEP = 0.90            # per-minute innovation sd, points -- sets the bar range
IB_WIG = 0.08             # half-range added beyond the bar body, points
VOL_KERNEL_W = 6.0        # points; volume e-folds at this distance from anchor
VOL_PEAK = 2400.0         # bar volume at the anchor
VOL_FLOOR = 60.0          # bar volume far from the anchor
OPEN_SPIKE = 1.5          # opening-bar volume multiple (timestamp verifier sec 0.2.2)

# The IB is quieter than the null generator's, so the REST of the day is scaled to
# match. Otherwise IB_range / ATR14 collapses and min_ib_range_atr (sec f) would
# silently filter out most of the sample -- the positive control would then be
# measured on whatever survived, which is not the sample it claims to be.
# Held at the null generator's OWN ratio of post-IB sigma to IB range
# (1.6 / 13.8 = 0.116), applied to this file's IB range of ~6 points. That keeps the
# breakout rate, the fill rate and the exit mix comparable between the two files, so
# the only thing that differs is the volume structure the gate reads.
POST_SIGMA = 0.70         # per-minute sd after the IB closes, points
POST_WIG = 0.48           # bar half-range after the IB closes, points
OVERNIGHT_SD = 0.0015     # overnight gap, fraction of price


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


def _tick(a):
    return np.round(a / 0.25) * 0.25


def _random_walk_session(rng, session_open, n, *, sigma=1.6, wig_sd=1.1):
    """Driftless walk, volume independent of price."""
    steps = rng.normal(0, sigma, n)
    closes = session_open + np.cumsum(steps)
    opens = np.r_[session_open, closes[:-1]]
    wig = np.abs(rng.normal(0, wig_sd, n))
    vol = rng.integers(200, 2000, n).astype(float)
    return opens, closes, wig, vol


def _anchored_ib(rng, session_open, n_ib):
    """AR(1) around a slowly drifting anchor; volume is a kernel of |price - anchor|.

    Returns (opens, closes, wig, vol) for the IB window only.
    """
    anchor = session_open + np.cumsum(rng.normal(0, ANCHOR_SIGMA, n_ib))
    e = np.empty(n_ib)
    e[0] = rng.normal(0, 2.0 * AR_STEP)
    for i in range(1, n_ib):
        e[i] = AR_PHI * e[i - 1] + rng.normal(0, AR_STEP)
    closes = anchor + e
    opens = np.r_[session_open, closes[:-1]]
    wig = np.abs(rng.normal(0, IB_WIG, n_ib))

    # Volume peaks where price is closest to the anchor. The kernel is evaluated
    # at the bar MIDPOINT, so it is a property of the bar as observed, not of a
    # hidden state -- there is nothing here a backtest could read that a trader
    # could not.
    mid = (np.maximum(opens, closes) + np.minimum(opens, closes)) / 2.0
    k = np.exp(-0.5 * ((mid - anchor) / VOL_KERNEL_W) ** 2)
    vol = VOL_FLOOR + (VOL_PEAK - VOL_FLOOR) * k
    vol *= rng.lognormal(0.0, 0.18, n_ib)       # dispersion, not structure
    return opens, closes, wig, vol


def make(start="2015-01-02", end="2017-12-29", seed=7, out=None,
         structure="random_walk"):
    if structure not in STRUCTURES:
        raise ValueError(f"unknown structure {structure!r}; expected {STRUCTURES}")
    if out is None:
        out = ("data/raw/synthetic.parquet" if structure == "random_walk"
               else "data/raw/synthetic_structured.parquet")

    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, end)
    rows = []
    px = 4200.0

    for d in days:
        fs, ns = front_symbol(d)
        # overnight drift
        px *= (1 + rng.normal(0, 0.006 if structure == "random_walk" else OVERNIGHT_SD))
        session_open = px

        idx = pd.date_range(f"{d.date()} 09:30", f"{d.date()} 15:59", freq="1min", tz=ET)
        n = len(idx)

        if structure == "random_walk":
            opens, closes, wig, vol = _random_walk_session(rng, session_open, n)
        else:
            # structured IB, then the SAME driftless walk afterwards so the
            # breakout rate and the daily range stay comparable across files
            o_ib, c_ib, w_ib, v_ib = _anchored_ib(rng, session_open, IB_MINUTES)
            o_rw, c_rw, w_rw, v_rw = _random_walk_session(
                rng, float(c_ib[-1]), n - IB_MINUTES,
                sigma=POST_SIGMA, wig_sd=POST_WIG)
            opens = np.r_[o_ib, o_rw]
            closes = np.r_[c_ib, c_rw]
            wig = np.r_[w_ib, w_rw]
            vol = np.r_[v_ib, v_rw]

        highs = np.maximum(opens, closes) + wig
        lows = np.minimum(opens, closes) - wig
        opens, highs, lows, closes = _tick(opens), _tick(highs), _tick(lows), _tick(closes)
        highs = np.maximum.reduce([highs, opens, closes])
        lows = np.minimum.reduce([lows, opens, closes])

        # open volume spike so the timestamp verifier has something to find
        vol = np.asarray(vol, float)
        vol[0] *= (12.0 if structure == "random_walk" else OPEN_SPIKE)

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
    print(f"wrote {len(df):,} rows, {df['symbol'].nunique()} contracts, "
          f"structure={structure} -> {p}")
    return p


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "random_walk"
    if which == "both":
        make(structure="random_walk")
        make(structure="anchored_volume")
    else:
        make(structure=which)
