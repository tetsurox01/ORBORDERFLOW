# ***** VOID -- DO NOT READ THE LEVELS ON THESE CHARTS *****

**Voided 2026-09-15. Not deleted, not redrawn.**

Every chart in this folder was drawn under the ORIGINAL §b.2 bin-width rule and
under the zero-anchored profile grid. Both were replaced on 2026-09-15
(IVB-SPEC.md §b.2 AMENDMENT 1 and AMENDMENT 2). Concretely, on these 21 charts:

1. **The volume profile has about 5 bins across the whole initial balance**, not
   20. Median measured over 2,365 real sessions was 5.28 to 5.97 bins in every
   year. A POC, a VAH and a VAL resolved on a 5-bin histogram are not locations.
2. **The value-area edges can sit OUTSIDE the initial balance they were built
   from.** 46.6% of measured sessions had VAH above IB_high or VAL below IB_low.
   On `2026-01-09` VAH sat **+27.25 pt above IB_high**.

So every POC, VAH, VAL, reload zone, entry, stop and TP1 line drawn here is
wrong, and every R and net figure in the table below is therefore wrong too --
`risk_R` is the value-area width plus a constant (§b.10), so a wrong value area
is a wrong denominator for every R in the table.

**These files are kept as the record of the defect, nothing else.** They are not
evidence about NQ, about Layer 1, or about the strategy. Nothing here may be
quoted, summed, averaged or compared against a post-amendment chart.

The PNGs are unchanged on disk and still carry their original filenames.

---

# 2026-01 -- LAYER 1 session census

**ILLUSTRATIVE, NOT A RESULT -- UNSEALED HOLDOUT DATA.**

Source: `nq_ohlcv1m_2010-07-01_2026-08-31.parquet` -- REAL NQ 1-minute bars.

Range: FORWARD_HOLDOUT 2026-01-01 .. 2026-08-31, unsealed 2026-09-15 (IVB-SPEC.md sec 0.2.3b UNSEAL #1).
These sessions are IN-SAMPLE from that date. Any statistic taken from this range must say so.

Geometry: `illustrate_layer1_trade()` -- a plain reading of the spec FOR DRAWING ONLY. Step 3 does not exist.
The sec b.9 profile-method sensitivity gate has NEVER been run on real bars, so every VAH / VAL / POC behind these rows is of unknown stability.

**This table sums nothing.** No totals, no win rate, no expectancy, no counts by outcome. One row per session, per-session values only.

Filtered sessions are drawn but carry no exit reason, R or net: P0 never takes those trades.

| date | outcome | direction | exit reason | R achieved | net |
|---|---|---|---|---|---|
| 2026-01-02 | no_fill | SHORT | - | - | - |
| 2026-01-05 | no_fill | LONG | - | - | - |
| 2026-01-06 | time_stop | LONG | time_stop | -0.71R | -89.85 pt |
| 2026-01-07 | time_stop | LONG | time_stop | +0.20R | +19.40 pt |
| 2026-01-08 | time_stop | SHORT | time_stop | -0.02R | -3.10 pt |
| 2026-01-09 | hard_stop | SHORT | hard_stop | -1.01R | -147.10 pt |
| 2026-01-12 | time_stop | LONG | time_stop | +0.17R | +18.90 pt |
| 2026-01-13 | time_stop | SHORT | time_stop | +0.19R | +15.15 pt |
| 2026-01-14 | time_stop | SHORT | time_stop | +0.03R | +3.90 pt |
| 2026-01-15 | time_stop | SHORT | time_stop | -0.36R | -31.35 pt |
| 2026-01-16 | no_fill | SHORT | - | - | - |
| 2026-01-19 | filtered:half_day | LONG | n/a (filtered) | n/a (filtered) | n/a (filtered) |
| 2026-01-20 | time_stop | LONG | time_stop | +0.64R | +71.90 pt |
| 2026-01-21 | no_fill | LONG | - | - | - |
| 2026-01-22 | time_stop | SHORT | time_stop | -0.91R | -126.35 pt |
| 2026-01-23 | no_fill | LONG | - | - | - |
| 2026-01-26 | no_fill | LONG | - | - | - |
| 2026-01-27 | time_stop | LONG | time_stop | +0.67R | +64.15 pt |
| 2026-01-28 | time_stop | SHORT | time_stop | +0.63R | +39.65 pt |
| 2026-01-29 | no_fill | SHORT | - | - | - |
| 2026-01-30 | hard_stop | SHORT | hard_stop | -1.01R | -102.35 pt |

Charts: `C:/Users/user/Desktop/ORB + Order flow/output/charts/2026-01`
